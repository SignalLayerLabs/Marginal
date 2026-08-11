"""JSON-over-Unix-socket daemon that persists MARGINAL state for one task."""

from __future__ import annotations

import argparse
import json
import signal
import socketserver
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .engine import CodexGovernanceEngine, IntegrationError

_MAX_REQUEST_BYTES = 16 * 1024 * 1024


class GovernanceUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """Threaded local server with one shared task-scoped governance engine."""

    daemon_threads = True

    def __init__(
        self,
        server_address: str,
        handler_class: type[socketserver.StreamRequestHandler],
        *,
        engine: CodexGovernanceEngine,
    ) -> None:
        self.engine = engine
        super().__init__(server_address, handler_class)


class GovernanceRequestHandler(socketserver.StreamRequestHandler):
    """Handle exactly one bounded request per local socket connection."""

    server: GovernanceUnixServer

    def handle(self) -> None:
        raw = self.rfile.readline(_MAX_REQUEST_BYTES + 1)
        if len(raw) > _MAX_REQUEST_BYTES:
            self._write_error("INVALID_REQUEST", "request exceeds size limit")
            return
        try:
            request = json.loads(raw)
            if not isinstance(request, Mapping):
                raise TypeError("request must be a JSON object")
            operation = request.get("operation")
            payload = request.get("payload", {})
            if not isinstance(operation, str) or not operation:
                raise ValueError("operation must be a non-empty string")
            if not isinstance(payload, Mapping):
                raise TypeError("payload must be a JSON object")
            result = self._dispatch(operation, payload)
        except IntegrationError as exc:
            self._write_error("INTEGRATION_ERROR", str(exc))
            return
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self._write_error("INVALID_REQUEST", str(exc))
            return
        except Exception as exc:  # pragma: no cover - last-resort protocol containment
            self._write_error("INTERNAL_ERROR", f"{type(exc).__name__}: {exc}")
            return
        self._write({"ok": True, "result": result})

    def _dispatch(self, operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if operation == "health":
            return {"status": "ready"}
        if operation == "pre_tool_use":
            return self.server.engine.pre_tool_use(payload)
        if operation == "post_tool_use":
            return self.server.engine.post_tool_use(payload)
        if operation == "summary":
            return self.server.engine.summary()
        raise ValueError(f"unknown operation: {operation}")

    def _write_error(self, code: str, message: str) -> None:
        self._write({"ok": False, "error_code": code, "message": message})

    def _write(self, payload: Mapping[str, Any]) -> None:
        self.wfile.write(json.dumps(payload, sort_keys=True).encode("utf-8") + b"\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.socket.parent.mkdir(parents=True, exist_ok=True)
    args.events.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.socket.unlink(missing_ok=True)

    engine = CodexGovernanceEngine(events_path=args.events)
    server = GovernanceUnixServer(str(args.socket), GovernanceRequestHandler, engine=engine)
    stopping = threading.Event()

    def stop_server(_signum: int, _frame: object) -> None:
        if not stopping.is_set():
            stopping.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        args.summary.write_text(
            json.dumps(engine.summary(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        args.socket.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
