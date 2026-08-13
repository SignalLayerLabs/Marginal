from __future__ import annotations

import pytest

from marginal.integrations.codex.events import (
    PostToolUseEvent,
    PreToolUseEvent,
    SessionEvent,
    build_post_tool_output,
    build_pre_tool_output,
    parse_hook_event,
)


def _common(event: str) -> dict[str, object]:
    return {
        "session_id": "session-1",
        "transcript_path": None,
        "cwd": "/workspace",
        "hook_event_name": event,
        "model": "gpt-5.6-sol",
        "permission_mode": "default",
    }


def test_pre_tool_event_requires_complete_tool_identity() -> None:
    payload = _common("PreToolUse")
    payload.update(
        {
            "turn_id": "turn-1",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q"},
        }
    )

    with pytest.raises(ValueError, match="tool_use_id"):
        parse_hook_event(payload)


def test_pre_and_post_events_preserve_typed_lifecycle_fields() -> None:
    pre_payload = _common("PreToolUse")
    pre_payload.update(
        {
            "turn_id": "turn-1",
            "tool_name": "Bash",
            "tool_use_id": "call-1",
            "tool_input": {"command": "pytest -q"},
        }
    )
    post_payload = {**pre_payload, "hook_event_name": "PostToolUse", "tool_response": "ok"}

    pre = parse_hook_event(pre_payload)
    post = parse_hook_event(post_payload)

    assert isinstance(pre, PreToolUseEvent)
    assert isinstance(post, PostToolUseEvent)
    assert pre.tool_use_id == post.tool_use_id == "call-1"
    assert post.tool_response == "ok"


@pytest.mark.parametrize(
    ("name", "extra"),
    [("SessionStart", {"source": "startup"}), ("SessionEnd", {"reason": "other"})],
)
def test_session_events_are_typed(name: str, extra: dict[str, str]) -> None:
    event = parse_hook_event({**_common(name), **extra})

    assert isinstance(event, SessionEvent)
    assert event.hook_event_name == name


def test_unknown_hook_event_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported Codex hook event"):
        parse_hook_event(_common("UserPromptSubmit"))


def test_denial_uses_official_codex_shape() -> None:
    assert build_pre_tool_output(
        allowed=False,
        reason="No progress",
        reason_code="NO_PROGRESS",
    ) == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "No progress [NO_PROGRESS]",
        }
    }


def test_allow_and_non_blocking_post_emit_no_output() -> None:
    assert build_pre_tool_output(allowed=True, reason="allowed", reason_code="ALLOW") is None
    assert build_post_tool_output(blocked=False, reason="", reason_code="") is None


def test_blocking_post_replaces_result_with_redacted_feedback() -> None:
    assert build_post_tool_output(
        blocked=True,
        reason="Review this result",
        reason_code="REVIEW_REQUIRED",
    ) == {
        "decision": "block",
        "reason": "Review this result [REVIEW_REQUIRED]",
    }

