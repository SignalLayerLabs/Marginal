from __future__ import annotations

import io
import json
import tempfile
import threading
from pathlib import Path

from benchmark.codex_adapter.daemon import GovernanceRequestHandler, GovernanceUnixServer
from benchmark.codex_adapter.engine import CodexGovernanceEngine
from benchmark.codex_adapter.hook_client import hook_output, run_hook


def _payload(call_id: str = "call-1") -> dict[str, object]:
    return {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "tool_use_id": call_id,
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
        "cwd": "/task",
    }


def test_allowed_pre_and_successful_post_emit_no_control_output() -> None:
    assert hook_output("pre", {"allowed": True, "reason": "approved"}) is None
    assert hook_output("post", {"settled": True}) is None


def test_denied_pre_emits_official_codex_block_shape() -> None:
    output = hook_output(
        "pre",
        {"allowed": False, "reason": "repetition exhausted", "reason_code": "STOP"},
    )

    assert output == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "repetition exhausted [STOP]",
        }
    }


def test_hook_round_trip_through_daemon(tmp_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="marginal-hook-", dir="/tmp") as short_dir:
        socket_path = Path(short_dir) / "m.sock"
        engine = CodexGovernanceEngine(
            events_path=tmp_path / "events.jsonl", state_hasher=lambda _: "same"
        )
        server = GovernanceUnixServer(str(socket_path), GovernanceRequestHandler, engine=engine)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            stdout = io.StringIO()
            stderr = io.StringIO()
            exit_code = run_hook(
                "pre",
                stdin=io.StringIO(json.dumps(_payload())),
                stdout=stdout,
                stderr=stderr,
                socket_path=socket_path,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    assert exit_code == 0
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""


def test_unavailable_daemon_fails_explicitly(tmp_path: Path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    failure_log = tmp_path / "hook-failures.log"
    exit_code = run_hook(
        "pre",
        stdin=io.StringIO(json.dumps(_payload())),
        stdout=stdout,
        stderr=stderr,
        socket_path=tmp_path / "missing.sock",
        failure_log=failure_log,
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "MARGINAL integration failure" in stderr.getvalue()
    assert "MARGINAL integration failure" in failure_log.read_text(encoding="utf-8")
