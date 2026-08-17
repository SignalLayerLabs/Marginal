import pytest

from marginal.controls import ActionOutcomeStatus
from marginal.integrations.hookkit.events import SessionBoundary, ToolCallEnd, ToolCallStart


def test_session_boundary_requires_a_known_kind() -> None:
    with pytest.raises(ValueError):
        SessionBoundary(
            engine="test-engine",
            session_id="session-1",
            workspace="/workspace",
            kind="restart",
        )


def test_session_boundary_rejects_empty_identity() -> None:
    with pytest.raises(ValueError):
        SessionBoundary(engine="", session_id="session-1", workspace="/workspace", kind="start")


def test_tool_call_start_copies_and_defaults_turn_identity() -> None:
    arguments = {"file_path": "/workspace/example.txt"}
    start = ToolCallStart(
        session_id="session-1",
        call_id="call-1",
        tool_name="Read",
        tool_input=arguments,
    )
    arguments["file_path"] = "/workspace/mutated.txt"
    assert start.tool_input == {"file_path": "/workspace/example.txt"}
    assert start.turn_id == ""


def test_tool_call_start_rejects_non_mapping_arguments() -> None:
    with pytest.raises(TypeError):
        ToolCallStart(
            session_id="session-1",
            call_id="call-1",
            tool_name="Read",
            tool_input=["not", "a", "mapping"],  # type: ignore[arg-type]
        )


def test_tool_call_end_parses_outcome_and_duration() -> None:
    end = ToolCallEnd(
        session_id="session-1",
        call_id="call-1",
        tool_name="Read",
        outcome="success",  # type: ignore[arg-type]
        duration_ms=12,
    )
    assert end.outcome is ActionOutcomeStatus.SUCCESS
    assert end.duration_ms == 12.0


def test_tool_call_end_rejects_negative_duration() -> None:
    with pytest.raises(ValueError):
        ToolCallEnd(
            session_id="session-1",
            call_id="call-1",
            tool_name="Read",
            outcome=ActionOutcomeStatus.SUCCESS,
            duration_ms=-1.0,
        )


def test_tool_call_end_rejects_unknown_outcome_text() -> None:
    with pytest.raises(ValueError):
        ToolCallEnd(
            session_id="session-1",
            call_id="call-1",
            tool_name="Read",
            outcome="probably-fine",  # type: ignore[arg-type]
        )
