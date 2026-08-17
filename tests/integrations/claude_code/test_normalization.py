import pytest

from marginal.controls import ActionOutcomeStatus
from marginal.integrations.claude_code.events import parse_hook_event
from marginal.integrations.claude_code.normalization import (
    ENGINE,
    session_boundary,
    tool_call_end,
    tool_call_start,
)

from .conftest import PayloadFactory


def test_session_boundaries_map_to_start_and_end(payloads: PayloadFactory) -> None:
    start = session_boundary(parse_hook_event(payloads.session_start()))  # type: ignore[arg-type]
    end = session_boundary(parse_hook_event(payloads.session_end()))  # type: ignore[arg-type]
    assert (start.kind, end.kind) == ("start", "end")
    assert start.engine == ENGINE == "claude-code"


def test_a_proposal_keeps_its_call_and_turn_identity(payloads: PayloadFactory) -> None:
    start = tool_call_start(parse_hook_event(payloads.pre_tool_use()))  # type: ignore[arg-type]
    assert start.call_id == "toolu_synthetic0001"
    assert start.turn_id == "synthetic-prompt-0001"
    assert start.tool_name == "Read"


def test_post_tool_use_is_a_documented_success(payloads: PayloadFactory) -> None:
    end = tool_call_end(parse_hook_event(payloads.post_tool_use()))  # type: ignore[arg-type]
    assert end.outcome is ActionOutcomeStatus.SUCCESS
    assert end.duration_ms == 11.0
    assert end.evidence is not None


def test_post_tool_use_failure_is_a_documented_failure(payloads: PayloadFactory) -> None:
    end = tool_call_end(parse_hook_event(payloads.post_tool_use_failure()))  # type: ignore[arg-type]
    assert end.outcome is ActionOutcomeStatus.FAILURE


def test_an_interrupted_call_is_not_charged_as_a_tool_failure(
    payloads: PayloadFactory,
) -> None:
    payload = payloads.post_tool_use_failure(is_interrupt=True)
    end = tool_call_end(parse_hook_event(payload))  # type: ignore[arg-type]
    assert end.outcome is ActionOutcomeStatus.UNKNOWN


def test_different_failures_produce_different_evidence(payloads: PayloadFactory) -> None:
    first = tool_call_end(parse_hook_event(payloads.post_tool_use_failure(error="Exit code 3")))  # type: ignore[arg-type]
    second = tool_call_end(parse_hook_event(payloads.post_tool_use_failure(error="Exit code 4")))  # type: ignore[arg-type]
    assert first.evidence != second.evidence


def test_normalization_rejects_foreign_event_types(payloads: PayloadFactory) -> None:
    with pytest.raises(TypeError):
        tool_call_start(parse_hook_event(payloads.post_tool_use()))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        tool_call_end(parse_hook_event(payloads.pre_tool_use()))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        session_boundary(parse_hook_event(payloads.pre_tool_use()))  # type: ignore[arg-type]
