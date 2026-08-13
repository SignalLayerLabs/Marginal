from __future__ import annotations

import pytest

from marginal.controls import ActionOutcomeStatus
from marginal.integrations.codex.events import PostToolUseEvent
from marginal.integrations.codex.outcomes import classify_tool_outcome


def _post(response: object) -> PostToolUseEvent:
    return PostToolUseEvent(
        session_id="session-1",
        cwd="/workspace",
        hook_event_name="PostToolUse",
        model="gpt-5.6-sol",
        permission_mode="default",
        turn_id="turn-1",
        tool_name="Bash",
        tool_use_id="call-1",
        tool_input={"command": "pytest -q"},
        tool_response=response,
    )


@pytest.mark.parametrize(
    "response",
    [
        "Process exited with code 0",
        "success",
        {"message": "exit_code=0"},
        {"exit_code": True},
        {"status": "completed"},
    ],
)
def test_prose_and_non_allowlisted_values_remain_unknown(response: object) -> None:
    assert classify_tool_outcome(_post(response)) is ActionOutcomeStatus.UNKNOWN


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"exit_code": 0}, ActionOutcomeStatus.SUCCESS),
        ({"exit_code": 7}, ActionOutcomeStatus.FAILURE),
        ({"success": True}, ActionOutcomeStatus.SUCCESS),
        ({"success": False}, ActionOutcomeStatus.FAILURE),
        ({"is_error": False}, ActionOutcomeStatus.SUCCESS),
        ({"is_error": True}, ActionOutcomeStatus.FAILURE),
        ({"status": "success"}, ActionOutcomeStatus.SUCCESS),
        ({"outcome": "failure"}, ActionOutcomeStatus.FAILURE),
    ],
)
def test_explicit_structured_outcome_is_classified(
    response: object, expected: ActionOutcomeStatus
) -> None:
    assert classify_tool_outcome(_post(response)) is expected


def test_conflicting_structured_signals_fail_open() -> None:
    response = {"exit_code": 0, "is_error": True}

    assert classify_tool_outcome(_post(response)) is ActionOutcomeStatus.UNKNOWN
