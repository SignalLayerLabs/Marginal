from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from marginal.integrations.codex.events import SessionEvent
from marginal.integrations.codex.service import (
    demote_repository,
    read_mode,
    run_hook,
    start_session_service,
    stop_session_service,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repository(path: Path) -> Path:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(path, "add", "tracked.txt")
    _git(path, "commit", "-qm", "initial")
    return path


def _start(workspace: Path) -> SessionEvent:
    return SessionEvent(
        session_id="session-1",
        cwd=str(workspace),
        hook_event_name="SessionStart",
        model="gpt-5.6-sol",
        permission_mode="default",
        source="startup",
    )


def test_start_is_idempotent_and_end_removes_credentials(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _repository(workspace)
    data = tmp_path / "data"
    first = start_session_service(_start(workspace), data_root=data)
    try:
        assert start_session_service(_start(workspace), data_root=data) == first
    finally:
        stop_session_service("session-1", data_root=data)

    assert not first.connection_file.exists()


def test_missing_service_fails_open_and_demotes(tmp_path: Path) -> None:
    data = tmp_path / "data"
    demote_repository(data, repository_hash="repository", reason="test", mode="enforce")
    pre_payload = {
        "session_id": "missing",
        "cwd": str(tmp_path),
        "hook_event_name": "PreToolUse",
        "model": "gpt-5.6-sol",
        "permission_mode": "default",
        "turn_id": "turn-1",
        "tool_name": "Bash",
        "tool_use_id": "call-1",
        "tool_input": {"command": "git status"},
    }

    result = run_hook(pre_payload, data_root=data)

    assert result.exit_code == 0
    assert result.output is None
    assert read_mode(data, repository_hash="repository")["mode"] == "shadow"
    assert result.warning_code == "SERVICE_UNAVAILABLE"


def test_session_start_and_end_are_complete_hook_lifecycle(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _repository(workspace)
    data = tmp_path / "data"
    start_payload = json.loads(json.dumps(asdict(_start(workspace))))
    end_payload = {
        **start_payload,
        "hook_event_name": "SessionEnd",
        "source": None,
        "reason": "other",
    }

    start_result = run_hook(start_payload, data_root=data)
    end_result = run_hook(end_payload, data_root=data)

    assert start_result.exit_code == 0
    assert end_result.exit_code == 0
    assert not (data / "sessions" / "session-1.json").exists()
