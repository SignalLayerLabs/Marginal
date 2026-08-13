from __future__ import annotations

import json

import pytest

from marginal.integrations.codex.events import PreToolUseEvent
from marginal.integrations.codex.normalization import normalize_pre_tool_use


def _event(command: str, *, tool_name: str = "Bash") -> PreToolUseEvent:
    return PreToolUseEvent(
        session_id="session-1",
        cwd="/workspace",
        hook_event_name="PreToolUse",
        model="gpt-5.6-sol",
        permission_mode="default",
        turn_id="turn-1",
        tool_name=tool_name,
        tool_use_id="call-1",
        tool_input={"command": command, "description": "private description"},
    )


def test_normalization_never_persists_raw_tool_input() -> None:
    action = normalize_pre_tool_use(_event("echo secret-marker"), state_hash="state")

    serialized = json.dumps(action.to_dict(), sort_keys=True)
    assert "secret-marker" not in serialized
    assert "private description" not in serialized
    assert action.name == "Codex Bash action"
    assert action.metadata["semantic_key"]


def test_canonical_input_order_has_one_semantic_identity() -> None:
    first = _event("pytest -q")
    second = PreToolUseEvent(
        session_id=first.session_id,
        cwd=first.cwd,
        hook_event_name=first.hook_event_name,
        model=first.model,
        permission_mode=first.permission_mode,
        turn_id=first.turn_id,
        tool_name=first.tool_name,
        tool_use_id="call-2",
        tool_input={"description": "private description", "command": "pytest -q"},
    )

    normalized_first = normalize_pre_tool_use(first, state_hash="state")
    normalized_second = normalize_pre_tool_use(second, state_hash="state")

    assert normalized_first.metadata["semantic_key"] == normalized_second.metadata["semantic_key"]


def test_verification_commands_are_classified_without_storing_command() -> None:
    action = normalize_pre_tool_use(_event("python -m pytest -q"), state_hash="state")

    assert action.kind == "verification"
    assert action.is_verification is True
    assert "pytest" not in json.dumps(action.to_dict())


def test_previous_evidence_is_available_to_policy_as_a_hash() -> None:
    action = normalize_pre_tool_use(
        _event("git status"),
        state_hash="state",
        previous_evidence_hash="evidence-hash",
    )

    assert action.metadata["evidence_hash"] == "evidence-hash"


def test_non_json_tool_input_is_rejected() -> None:
    event = _event("git status")
    object.__setattr__(event, "tool_input", {"bad": {1, 2}})

    with pytest.raises(ValueError, match="canonical JSON"):
        normalize_pre_tool_use(event, state_hash="state")

