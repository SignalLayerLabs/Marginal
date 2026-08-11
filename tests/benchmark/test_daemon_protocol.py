from __future__ import annotations

import json
import socket
import tempfile
import threading
from pathlib import Path

from benchmark.codex_adapter.daemon import GovernanceRequestHandler, GovernanceUnixServer
from benchmark.codex_adapter.engine import CodexGovernanceEngine


def _request(socket_path: Path, payload: object) -> dict[str, object]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        response = client.makefile("rb").readline()
    decoded = json.loads(response)
    assert isinstance(decoded, dict)
    return decoded


def test_unix_protocol_routes_requests_and_reports_errors(tmp_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="marginal-test-", dir="/tmp") as short_dir:
        socket_path = Path(short_dir) / "m.sock"
        engine = CodexGovernanceEngine(
            events_path=tmp_path / "events.jsonl", state_hasher=lambda _: "state"
        )
        server = GovernanceUnixServer(str(socket_path), GovernanceRequestHandler, engine=engine)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            health = _request(socket_path, {"operation": "health", "payload": {}})
            assert health == {"ok": True, "result": {"status": "ready"}}

            invalid = _request(socket_path, {"operation": "unknown", "payload": {}})
            assert invalid["ok"] is False
            assert invalid["error_code"] == "INVALID_REQUEST"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        assert not thread.is_alive()
