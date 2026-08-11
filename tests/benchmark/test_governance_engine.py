from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from benchmark.codex_adapter.engine import CodexGovernanceEngine, IntegrationError


def _pre(
    call_id: str,
    *,
    tool_name: str = "apply_patch",
    tool_input: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "tool_use_id": call_id,
        "tool_name": tool_name,
        "tool_input": tool_input or {"patch": "*** Begin Patch\\n*** End Patch"},
        "cwd": "/task",
    }


def _post(
    call_id: str,
    response: object = None,
    *,
    tool_name: str = "apply_patch",
    tool_input: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "tool_use_id": call_id,
        "tool_name": tool_name,
        "tool_input": tool_input or {"patch": "*** Begin Patch\\n*** End Patch"},
        "tool_response": {"output": ""} if response is None else response,
        "cwd": "/task",
    }


def test_third_same_state_same_evidence_execution_is_denied(tmp_path: Path) -> None:
    engine = CodexGovernanceEngine(
        events_path=tmp_path / "events.jsonl", state_hasher=lambda _: "state-a"
    )

    first = engine.pre_tool_use(_pre("call-1"))
    assert first["allowed"] is True
    engine.post_tool_use(_post("call-1"))

    second = engine.pre_tool_use(_pre("call-2"))
    assert second["allowed"] is True
    engine.post_tool_use(_post("call-2"))

    third = engine.pre_tool_use(_pre("call-3"))
    assert third["allowed"] is False
    assert third["reason_code"] == "DIMINISHING_RETURN_REJECTED"

    summary = engine.summary()
    assert summary["approved"] == 2
    assert summary["committed"] == 2
    assert summary["denied"] == 1
    assert summary["interventions"]["applied_denies"] == 1
    assert summary["governance"]["external_tokens"] == 0
    assert summary["governance"]["external_usd"] == 0.0


def test_changed_state_clears_repetition_penalty(tmp_path: Path) -> None:
    states: Iterator[str] = iter(["a", "a", "a", "a", "changed"])
    engine = CodexGovernanceEngine(
        events_path=tmp_path / "events.jsonl", state_hasher=lambda _: next(states)
    )

    engine.pre_tool_use(_pre("call-1"))
    engine.post_tool_use(_post("call-1"))
    engine.pre_tool_use(_pre("call-2"))
    engine.post_tool_use(_post("call-2"))

    assert engine.pre_tool_use(_pre("call-3"))["allowed"] is True


def test_new_tool_evidence_clears_repetition_penalty(tmp_path: Path) -> None:
    engine = CodexGovernanceEngine(
        events_path=tmp_path / "events.jsonl", state_hasher=lambda _: "same"
    )

    engine.pre_tool_use(_pre("call-1"))
    engine.post_tool_use(_post("call-1", {"output": "first"}))
    engine.pre_tool_use(_pre("call-2"))
    engine.post_tool_use(_post("call-2", {"output": "second"}))

    assert engine.pre_tool_use(_pre("call-3"))["allowed"] is True


def test_completed_shell_action_advances_history_without_inferred_exit_status(
    tmp_path: Path,
) -> None:
    engine = CodexGovernanceEngine(
        events_path=tmp_path / "events.jsonl", state_hasher=lambda _: "same"
    )
    shell_input = {"command": "pytest -q"}

    for index in (1, 2):
        pre = _pre(f"call-{index}", tool_name="Bash", tool_input=shell_input)
        assert engine.pre_tool_use(pre)["allowed"] is True
        post = _post(f"call-{index}", tool_name="Bash", tool_input=shell_input)
        result = engine.post_tool_use(post)
        assert result == {"settled": True, "completed": True}

    third = engine.pre_tool_use(_pre("call-3", tool_name="Bash", tool_input=shell_input))
    assert third["allowed"] is False
    assert third["reason_code"] == "DIMINISHING_RETURN_REJECTED"

    summary = engine.summary()
    assert summary["committed"] == 2
    assert summary["failed_settled"] == 0
    assert summary["denied"] == 1


def test_denied_action_is_not_left_pending(tmp_path: Path) -> None:
    engine = CodexGovernanceEngine(
        events_path=tmp_path / "events.jsonl", state_hasher=lambda _: "same"
    )
    for index in (1, 2):
        engine.pre_tool_use(_pre(f"call-{index}"))
        engine.post_tool_use(_post(f"call-{index}"))

    engine.pre_tool_use(_pre("call-3"))
    with pytest.raises(IntegrationError, match="not pending"):
        engine.post_tool_use(_post("call-3"))


def test_duplicate_pending_id_and_unknown_post_are_integration_errors(tmp_path: Path) -> None:
    engine = CodexGovernanceEngine(
        events_path=tmp_path / "events.jsonl", state_hasher=lambda _: "same"
    )
    engine.pre_tool_use(_pre("call-1"))

    with pytest.raises(IntegrationError, match="already pending"):
        engine.pre_tool_use(_pre("call-1"))
    with pytest.raises(IntegrationError, match="not pending"):
        engine.post_tool_use(_post("unknown"))


def test_post_must_match_complete_pre_identity(tmp_path: Path) -> None:
    engine = CodexGovernanceEngine(
        events_path=tmp_path / "events.jsonl", state_hasher=lambda _: "same"
    )
    engine.pre_tool_use(_pre("call-1"))
    mismatched = _post("call-1")
    mismatched["session_id"] = "another-session"

    with pytest.raises(IntegrationError, match="identity does not match"):
        engine.post_tool_use(mismatched)

    assert engine.summary()["pending"] == 1


def test_events_are_append_only_jsonl(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    engine = CodexGovernanceEngine(events_path=events_path, state_hasher=lambda _: "same")
    engine.pre_tool_use(_pre("call-1"))
    engine.post_tool_use(_post("call-1"))

    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 4
    assert all(line.startswith("{") and line.endswith("}") for line in lines)
