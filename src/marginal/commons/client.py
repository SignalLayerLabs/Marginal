"""Bounded zero-dependency HTTP transport for MARGINAL Commons."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import SplitResult, urlsplit

from .outbox import OutboxEntry, _entry_boundary_valid, _reject_duplicate_keys

_PACK_PATH = "/dist/commons-pack-v1.json"
_EVIDENCE_PATH = "/v1/evidence"
_DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_REQUEST_BYTES = 512 * 1024


class CommonsTransportError(Exception):
    """A redacted DNS, TLS, socket, or timeout failure."""


class CommonsProtocolError(Exception):
    """A bounded response failed the closed Commons response contract."""


class CommonsHTTPError(Exception):
    """A non-success HTTP status, without response content or endpoint details."""

    def __init__(self, *, status: int) -> None:
        self.status = status
        category = "client" if 400 <= status < 500 else "server"
        super().__init__(f"Commons request failed ({category} response)")


@dataclass(frozen=True, slots=True)
class CommonsAck:
    """The only accepted evidence response shape."""

    accepted: bool
    duplicate: bool

    def __post_init__(self) -> None:
        if self.accepted is not True or type(self.duplicate) is not bool:
            raise ValueError("invalid Commons ACK")


class CommonsClientProtocol(Protocol):
    """Narrow transport boundary consumed by fail-open orchestration."""

    def download(self) -> bytes: ...

    def submit(self, entry: OutboxEntry) -> CommonsAck: ...


@dataclass(frozen=True, slots=True)
class _Origin:
    scheme: str
    host: str
    port: int | None


def _parse_origin(value: str) -> _Origin:
    if not isinstance(value, str):
        raise ValueError("Commons origin must be an absolute HTTP origin")
    parsed: SplitResult = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Commons origin is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Commons origin must not contain credentials, paths, or query parameters")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Commons origin must use TLS unless it is loopback")
    return _Origin(parsed.scheme, parsed.hostname, port)


def _positive_timeout(value: float, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 30:
        raise ValueError(f"Commons {label} timeout must be between 0 and 30 seconds")
    return float(value)


class CommonsClient:
    """Issue fixed-path bounded requests.

    The monotonic request deadline covers socket connect, request send, headers, and body once
    ``getaddrinfo`` returns. Python's synchronous stdlib resolver cannot preempt a blocked DNS
    lookup without a helper thread, so DNS delay is checked and failed open immediately after
    resolution rather than claimed as a hard cancellable deadline.
    """

    def __init__(
        self,
        *,
        pack_origin: str,
        ingress_origin: str,
        connect_timeout: float = 2.0,
        read_timeout: float = 3.0,
        request_timeout: float = 5.0,
        max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        self._pack_origin = _parse_origin(pack_origin)
        self._ingress_origin = _parse_origin(ingress_origin)
        self._connect_timeout = _positive_timeout(connect_timeout, label="connect")
        self._read_timeout = _positive_timeout(read_timeout, label="read")
        self._request_timeout = _positive_timeout(request_timeout, label="request")
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or not 1 <= max_response_bytes <= _DEFAULT_MAX_RESPONSE_BYTES
        ):
            raise ValueError("Commons response byte limit is invalid")
        self._max_response_bytes = max_response_bytes

    def _connection(self, origin: _Origin, *, timeout: float) -> http.client.HTTPConnection:
        connection_type: type[http.client.HTTPConnection]
        connection_type = (
            http.client.HTTPSConnection if origin.scheme == "https" else http.client.HTTPConnection
        )
        return connection_type(origin.host, port=origin.port, timeout=timeout)

    @staticmethod
    def _abort_socket(socket_holder: list[socket.socket | None]) -> None:
        sock = socket_holder[0]
        if sock is None:
            return
        with suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)
        with suppress(OSError):
            sock.close()

    @staticmethod
    def _remaining(deadline: float, *, cap: float | None = None) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CommonsTransportError("Commons transport failed")
        return min(remaining, cap) if cap is not None else remaining

    def _set_read_timeout(self, connection: http.client.HTTPConnection, *, deadline: float) -> None:
        if connection.sock is not None:
            connection.sock.settimeout(self._remaining(deadline, cap=self._read_timeout))

    def _read_bounded_response(
        self,
        response: http.client.HTTPResponse,
        connection: http.client.HTTPConnection,
        *,
        deadline: float,
        validate_length: bool,
    ) -> bytes:
        declared_size: int | None = None
        if validate_length:
            declared = response.getheader("Content-Length")
            if declared is not None:
                try:
                    declared_size = int(declared)
                except ValueError:
                    raise CommonsProtocolError("invalid Commons response") from None
                if declared_size < 0 or declared_size > self._max_response_bytes:
                    raise CommonsProtocolError("invalid Commons response")
        chunks: list[bytes] = []
        remaining_bytes = self._max_response_bytes + 1
        while remaining_bytes > 0:
            self._set_read_timeout(connection, deadline=deadline)
            chunk = response.read1(min(64 * 1024, remaining_bytes))
            if not chunk:
                break
            chunks.append(chunk)
            remaining_bytes -= len(chunk)
        raw = b"".join(chunks)
        self._remaining(deadline)
        if validate_length and len(raw) > self._max_response_bytes:
            raise CommonsProtocolError("invalid Commons response")
        if validate_length and declared_size is not None and len(raw) != declared_size:
            raise CommonsProtocolError("invalid Commons response")
        return raw

    def _request(
        self,
        origin: _Origin,
        *,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        success_status: object,
    ) -> bytes:
        deadline = time.monotonic() + self._request_timeout
        connection = self._connection(
            origin,
            timeout=self._remaining(deadline, cap=self._connect_timeout),
        )
        socket_holder: list[socket.socket | None] = [None]
        deadline_guard = threading.Timer(
            self._request_timeout,
            self._abort_socket,
            args=(socket_holder,),
        )
        deadline_guard.daemon = True
        deadline_guard.start()
        try:
            connection.connect()
            socket_holder[0] = connection.sock
            if connection.sock is not None:
                connection.sock.settimeout(self._remaining(deadline))
            connection.request(method, path, body=body, headers=headers or {})
            self._set_read_timeout(connection, deadline=deadline)
            response = connection.getresponse()
            status_is_success = (
                response.status == success_status
                if isinstance(success_status, int)
                else 200 <= response.status < 300
            )
            if not status_is_success:
                with suppress(CommonsTransportError, OSError, http.client.HTTPException):
                    self._read_bounded_response(
                        response,
                        connection,
                        deadline=deadline,
                        validate_length=False,
                    )
                raise CommonsHTTPError(status=response.status)
            return self._read_bounded_response(
                response,
                connection,
                deadline=deadline,
                validate_length=True,
            )
        except (CommonsProtocolError, CommonsHTTPError):
            raise
        except (TimeoutError, OSError, http.client.HTTPException):
            raise CommonsTransportError("Commons transport failed") from None
        finally:
            deadline_guard.cancel()
            connection.close()

    def download(self) -> bytes:
        """Download the pack from its fixed public path."""

        return self._request(
            self._pack_origin,
            method="GET",
            path=_PACK_PATH,
            headers={"Accept": "application/json"},
            success_status=200,
        )

    def submit(self, entry: OutboxEntry) -> CommonsAck:
        """Submit one validated envelope with retry identity only in its header."""

        if not _entry_boundary_valid(entry):
            raise ValueError("Commons submission requires a valid outbox entry")
        body = entry.body_bytes
        if len(body) > _MAX_REQUEST_BYTES:
            raise ValueError("Commons evidence envelope is too large")
        raw = self._request(
            self._ingress_origin,
            method="POST",
            path=_EVIDENCE_PATH,
            body=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Idempotency-Key": entry.retry_token,
            },
            success_status=range(200, 300),
        )
        try:
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
            RecursionError,
            MemoryError,
            OverflowError,
        ):
            raise CommonsProtocolError("invalid Commons response") from None
        if (
            not isinstance(payload, dict)
            or set(payload) != {"accepted", "duplicate"}
            or payload.get("accepted") is not True
            or type(payload.get("duplicate")) is not bool
        ):
            raise CommonsProtocolError("invalid Commons response")
        return CommonsAck(accepted=True, duplicate=payload["duplicate"])
