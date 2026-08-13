"""Authenticated, bounded loopback transport for one Codex session."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import socketserver
import threading
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MAX_MESSAGE_BYTES = 256 * 1024


def connection_filename(session_id: str) -> str:
    """Return a stable receipt name without exposing the raw Codex session identity."""

    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id must be a non-empty string")
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return f"{digest}.json"


@dataclass(frozen=True, slots=True)
class ConnectionInfo:
    session_id: str
    host: str
    port: int
    token: str
    pid: int
    connection_file: Path

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["connection_file"] = str(self.connection_file)
        return payload

    @classmethod
    def from_file(cls, path: str | Path) -> ConnectionInfo:
        source = Path(path).resolve()
        payload = json.loads(source.read_text(encoding="utf-8"))
        return cls(
            session_id=str(payload["session_id"]),
            host=str(payload["host"]),
            port=int(payload["port"]),
            token=str(payload["token"]),
            pid=int(payload["pid"]),
            connection_file=source,
        )


SessionHandler = Callable[[str, Mapping[str, Any]], Mapping[str, Any] | None]


def _response_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


class _BoundedRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        owner: _LoopbackServer = self.server  # type: ignore[assignment]
        self.connection.settimeout(5.0)
        raw = self.rfile.readline(MAX_MESSAGE_BYTES + 2)
        if len(raw) > MAX_MESSAGE_BYTES + 1:
            self.wfile.write(_response_bytes(_error("MESSAGE_TOO_LARGE")))
            return
        try:
            request = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.wfile.write(_response_bytes(_error("INVALID_MESSAGE")))
            return
        if not isinstance(request, dict):
            self.wfile.write(_response_bytes(_error("INVALID_MESSAGE")))
            return
        supplied_token = request.get("token")
        if not isinstance(supplied_token, str) or not hmac.compare_digest(
            supplied_token, owner.token
        ):
            self.wfile.write(_response_bytes(_error("AUTH_FAILED")))
            return
        operation = request.get("operation")
        payload = request.get("payload")
        if not isinstance(operation, str) or not isinstance(payload, dict):
            self.wfile.write(_response_bytes(_error("INVALID_MESSAGE")))
            return
        try:
            result = owner.callback(operation, payload)
            response: Mapping[str, Any] = {"ok": True, "result": result}
        except Exception:
            response = _error("SERVICE_ERROR")
        self.wfile.write(_response_bytes(response))


class _LoopbackServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, token: str, callback: SessionHandler) -> None:
        self.token = token
        self.callback = callback
        super().__init__(("127.0.0.1", 0), _BoundedRequestHandler)


def _error(code: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code}


class SessionServer:
    """Own one authenticated server and its user-private connection receipt."""

    def __init__(
        self,
        *,
        data_root: str | Path,
        session_id: str,
        token: str,
        handler: SessionHandler,
    ) -> None:
        if len(token.encode("utf-8")) < 16:
            raise ValueError("session token must contain at least 128 bits")
        self.data_root = Path(data_root).resolve()
        self.data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.sessions_root = self.data_root / "sessions"
        self.sessions_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            self.data_root.chmod(0o700)
            self.sessions_root.chmod(0o700)
        self._server = _LoopbackServer(token, handler)
        self._thread: threading.Thread | None = None
        connection_path = self.sessions_root / connection_filename(session_id)
        self.connection = ConnectionInfo(
            session_id=session_id,
            host="127.0.0.1",
            port=int(self._server.server_address[1]),
            token=token,
            pid=os.getpid(),
            connection_file=connection_path,
        )

    def start(self) -> ConnectionInfo:
        if self._thread is not None:
            return self.connection
        descriptor = os.open(
            self.connection.connection_file,
            os.O_CREAT | os.O_TRUNC | os.O_WRONLY,
            0o600,
        )
        try:
            os.write(descriptor, _response_bytes(self.connection.to_dict()))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if os.name == "posix":
            self.connection.connection_file.chmod(0o600)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name=f"marginal-{self.connection.session_id}",
            daemon=True,
        )
        self._thread.start()
        return self.connection

    def stop(self) -> None:
        if self._thread is not None:
            self._server.shutdown()
            self._thread.join(timeout=5)
            self._thread = None
        self._server.server_close()
        self.connection.connection_file.unlink(missing_ok=True)


def request_session(
    connection: ConnectionInfo,
    *,
    operation: str,
    payload: Mapping[str, Any],
    token: str | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Send one bounded request; transport errors are returned as stable error codes."""

    request = _response_bytes(
        {
            "token": connection.token if token is None else token,
            "operation": operation,
            "payload": dict(payload),
        }
    )
    if len(request) > MAX_MESSAGE_BYTES + 1:
        return _error("MESSAGE_TOO_LARGE")
    try:
        with socket.create_connection((connection.host, connection.port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(request)
            reader = sock.makefile("rb")
            raw = reader.readline(MAX_MESSAGE_BYTES + 2)
    except (OSError, TimeoutError):
        return _error("SERVICE_UNAVAILABLE")
    if len(raw) > MAX_MESSAGE_BYTES + 1:
        return _error("MESSAGE_TOO_LARGE")
    try:
        response = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error("INVALID_RESPONSE")
    if not isinstance(response, dict):
        return _error("INVALID_RESPONSE")
    return response
