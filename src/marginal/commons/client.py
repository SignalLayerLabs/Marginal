"""Bounded zero-dependency HTTP transport for MARGINAL Commons."""

from __future__ import annotations

import http.client
import json
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import SplitResult, urlsplit

from .outbox import _TOKEN_PATTERN, OutboxEntry, _validate_envelope

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
    """Issue only fixed-path GET and POST requests with strict resource limits."""

    def __init__(
        self,
        *,
        pack_origin: str,
        ingress_origin: str,
        connect_timeout: float = 2.0,
        read_timeout: float = 3.0,
        max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        self._pack_origin = _parse_origin(pack_origin)
        self._ingress_origin = _parse_origin(ingress_origin)
        self._connect_timeout = _positive_timeout(connect_timeout, label="connect")
        self._read_timeout = _positive_timeout(read_timeout, label="read")
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or not 1 <= max_response_bytes <= _DEFAULT_MAX_RESPONSE_BYTES
        ):
            raise ValueError("Commons response byte limit is invalid")
        self._max_response_bytes = max_response_bytes

    def _connection(self, origin: _Origin) -> http.client.HTTPConnection:
        connection_type: type[http.client.HTTPConnection]
        connection_type = (
            http.client.HTTPSConnection if origin.scheme == "https" else http.client.HTTPConnection
        )
        return connection_type(origin.host, port=origin.port, timeout=self._connect_timeout)

    def _request(
        self,
        origin: _Origin,
        *,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes]:
        connection = self._connection(origin)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            if connection.sock is not None:
                connection.sock.settimeout(self._read_timeout)
            response = connection.getresponse()
            declared = response.getheader("Content-Length")
            if declared is not None:
                try:
                    declared_size = int(declared)
                except ValueError:
                    raise CommonsProtocolError("invalid Commons response") from None
                if declared_size < 0:
                    raise CommonsProtocolError("invalid Commons response")
            raw = response.read(self._max_response_bytes + 1)
            if len(raw) > self._max_response_bytes:
                raise CommonsProtocolError("invalid Commons response")
            return response.status, raw
        except CommonsProtocolError:
            raise
        except (TimeoutError, OSError, http.client.HTTPException):
            raise CommonsTransportError("Commons transport failed") from None
        finally:
            connection.close()

    def download(self) -> bytes:
        """Download the pack from its fixed public path."""

        status, raw = self._request(
            self._pack_origin,
            method="GET",
            path=_PACK_PATH,
            headers={"Accept": "application/json"},
        )
        if status != 200:
            raise CommonsHTTPError(status=status)
        return raw

    def submit(self, entry: OutboxEntry) -> CommonsAck:
        """Submit one validated envelope with retry identity only in its header."""

        if not isinstance(entry, OutboxEntry):
            raise TypeError("Commons submission requires an outbox entry")
        if _TOKEN_PATTERN.fullmatch(entry.retry_token) is None:
            raise ValueError("Commons retry token is invalid")
        envelope = _validate_envelope(entry.envelope)
        body = (
            json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        ).encode("utf-8")
        if len(body) > _MAX_REQUEST_BYTES:
            raise ValueError("Commons evidence envelope is too large")
        status, raw = self._request(
            self._ingress_origin,
            method="POST",
            path=_EVIDENCE_PATH,
            body=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Idempotency-Key": entry.retry_token,
            },
        )
        if not 200 <= status < 300:
            raise CommonsHTTPError(status=status)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise CommonsProtocolError("invalid Commons response") from None
        if (
            not isinstance(payload, dict)
            or set(payload) != {"accepted", "duplicate"}
            or payload.get("accepted") is not True
            or type(payload.get("duplicate")) is not bool
        ):
            raise CommonsProtocolError("invalid Commons response")
        return CommonsAck(accepted=True, duplicate=payload["duplicate"])
