from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from marginal import BudgetLimits, Treasury
from marginal.integrations.codex.events import PostToolUseEvent, PreToolUseEvent
from marginal.integrations.codex.runtime import CodexIntegrationError, CodexSessionRuntime
from marginal.protocol import AgentCapabilities
from marginal.runtime import UniversalRuntime


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


def _runtime(workspace: Path) -> CodexSessionRuntime:
    universal = UniversalRuntime(
        Treasury(BudgetLimits(max_tokens=100), mode="shadow"),
        engine="codex",
        session_id="session-1",
        task_id="workspace",
        capabilities=AgentCapabilities(block_actions=True),
    )
    return CodexSessionRuntime(universal, workspace=workspace)


def _pre(action_id: str, *, command: str = "pytest -q") -> PreToolUseEvent:
    return PreToolUseEvent(
        session_id="session-1",
        cwd="/workspace",
        hook_event_name="PreToolUse",
        model="gpt-5.6-sol",
        permission_mode="default",
        turn_id="turn-1",
        tool_name="Bash",
        tool_use_id=action_id,
        tool_input={"command": command},
    )


def _post(action_id: str, response: object) -> PostToolUseEvent:
    before = _pre(action_id)
    return PostToolUseEvent(
        session_id=before.session_id,
        cwd=before.cwd,
        hook_event_name="PostToolUse",
        model=before.model,
        permission_mode=before.permission_mode,
        turn_id=before.turn_id,
        tool_name=before.tool_name,
        tool_use_id=before.tool_use_id,
        tool_input=before.tool_input,
        tool_response=response,
    )


def test_unknown_post_does_not_advance_success_history(tmp_path: Path) -> None:
    runtime = _runtime(_repository(tmp_path))
    runtime.pre_tool_use(_pre("call-1"))

    runtime.post_tool_use(_post("call-1", "red test output"))

    assert runtime.summary()["successful_observations"] == 0
    assert runtime.summary()["unknown_observations"] == 1
    assert runtime.pending_action_ids() == ()


def test_failure_settles_without_success_observation(tmp_path: Path) -> None:
    runtime = _runtime(_repository(tmp_path))
    runtime.pre_tool_use(_pre("call-1"))

    runtime.post_tool_use(_post("call-1", {"exit_code": 1}))

    assert runtime.summary()["failed_observations"] == 1
    assert runtime.summary()["successful_observations"] == 0


def test_explicit_success_advances_success_history(tmp_path: Path) -> None:
    runtime = _runtime(_repository(tmp_path))
    runtime.pre_tool_use(_pre("call-1"))

    runtime.post_tool_use(_post("call-1", {"exit_code": 0}))

    assert runtime.summary()["successful_observations"] == 1


def test_identity_mismatch_keeps_original_pending(tmp_path: Path) -> None:
    runtime = _runtime(_repository(tmp_path))
    runtime.pre_tool_use(_pre("call-1"))

    with pytest.raises(CodexIntegrationError, match="identity"):
        runtime.post_tool_use(_post("call-2", {"exit_code": 0}))

    assert runtime.pending_action_ids() == ("call-1",)


def test_replayed_pre_identity_is_rejected(tmp_path: Path) -> None:
    runtime = _runtime(_repository(tmp_path))
    runtime.pre_tool_use(_pre("call-1"))

    with pytest.raises(CodexIntegrationError, match="pending"):
        runtime.pre_tool_use(_pre("call-1"))


def test_close_aborts_pending_actions_as_unknown(tmp_path: Path) -> None:
    runtime = _runtime(_repository(tmp_path))
    runtime.pre_tool_use(_pre("call-1"))
    runtime.pre_tool_use(_pre("call-2", command="git status"))

    runtime.close()

    assert runtime.pending_action_ids() == ()
    assert runtime.summary()["unknown_observations"] == 2

