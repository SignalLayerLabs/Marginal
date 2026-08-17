import pytest

from marginal.integrations.claude_code.events import (
    PostToolUseEvent,
    PostToolUseFailureEvent,
    PreToolUseEvent,
    SessionEvent,
    parse_hook_event,
)

from .conftest import PayloadFactory


def test_session_start_is_parsed_without_transcript_material(
    payloads: PayloadFactory,
) -> None:
    event = parse_hook_event(payloads.session_start())
    assert isinstance(event, SessionEvent)
    assert event.hook_event_name == "SessionStart"
    assert event.source == "startup"
    assert not hasattr(event, "transcript_path")


def test_session_end_carries_its_reason(payloads: PayloadFactory) -> None:
    event = parse_hook_event(payloads.session_end())
    assert isinstance(event, SessionEvent)
    assert event.reason == "clear"


def test_pre_tool_use_is_parsed(payloads: PayloadFactory) -> None:
    event = parse_hook_event(payloads.pre_tool_use())
    assert isinstance(event, PreToolUseEvent)
    assert event.tool_name == "Read"
    assert event.tool_use_id == "toolu_synthetic0001"
    assert event.prompt_id == "synthetic-prompt-0001"
    assert event.permission_mode == "default"


def test_pre_tool_use_tolerates_a_missing_permission_mode(
    payloads: PayloadFactory,
) -> None:
    payload = payloads.pre_tool_use()
    del payload["permission_mode"]
    event = parse_hook_event(payload)
    assert isinstance(event, PreToolUseEvent)
    assert event.permission_mode == ""


def test_post_tool_use_is_parsed_with_measured_latency(payloads: PayloadFactory) -> None:
    event = parse_hook_event(payloads.post_tool_use())
    assert isinstance(event, PostToolUseEvent)
    assert event.duration_ms == 11.0
    assert event.tool_response["type"] == "text"


def test_post_tool_use_accepts_the_documented_output_key(payloads: PayloadFactory) -> None:
    payload = payloads.post_tool_use()
    payload["tool_output"] = payload.pop("tool_response")
    event = parse_hook_event(payload)
    assert isinstance(event, PostToolUseEvent)
    assert event.tool_response["type"] == "text"


def test_post_tool_use_requires_a_result(payloads: PayloadFactory) -> None:
    payload = payloads.post_tool_use()
    del payload["tool_response"]
    with pytest.raises(ValueError):
        parse_hook_event(payload)


def test_post_tool_use_without_latency_reports_none(payloads: PayloadFactory) -> None:
    event = parse_hook_event(payloads.post_tool_use(duration_ms=None))
    assert isinstance(event, PostToolUseEvent)
    assert event.duration_ms is None


def test_post_tool_use_failure_is_parsed(payloads: PayloadFactory) -> None:
    event = parse_hook_event(payloads.post_tool_use_failure())
    assert isinstance(event, PostToolUseFailureEvent)
    assert event.error == "Exit code 3"
    assert event.is_interrupt is False
    assert event.duration_ms == 4.0


def test_an_interrupt_is_recorded_as_such(payloads: PayloadFactory) -> None:
    event = parse_hook_event(payloads.post_tool_use_failure(is_interrupt=True))
    assert isinstance(event, PostToolUseFailureEvent)
    assert event.is_interrupt is True


@pytest.mark.parametrize("field", ["session_id", "cwd", "hook_event_name"])
def test_required_identity_is_enforced(payloads: PayloadFactory, field: str) -> None:
    payload = payloads.pre_tool_use()
    payload[field] = ""
    with pytest.raises(ValueError):
        parse_hook_event(payload)


@pytest.mark.parametrize("field", ["tool_name", "tool_use_id"])
def test_required_tool_identity_is_enforced(payloads: PayloadFactory, field: str) -> None:
    payload = payloads.pre_tool_use()
    del payload[field]
    with pytest.raises(ValueError):
        parse_hook_event(payload)


def test_tool_input_must_be_a_mapping(payloads: PayloadFactory) -> None:
    payload = payloads.pre_tool_use()
    payload["tool_input"] = ["not", "a", "mapping"]
    with pytest.raises(ValueError):
        parse_hook_event(payload)


def test_an_unsupported_event_is_rejected(payloads: PayloadFactory) -> None:
    payload = payloads.pre_tool_use()
    payload["hook_event_name"] = "UserPromptSubmit"
    with pytest.raises(ValueError):
        parse_hook_event(payload)


def test_a_non_mapping_payload_is_rejected() -> None:
    with pytest.raises(TypeError):
        parse_hook_event(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_a_malformed_duration_is_rejected(payloads: PayloadFactory) -> None:
    payload = payloads.post_tool_use()
    payload["duration_ms"] = "fast"
    with pytest.raises(ValueError):
        parse_hook_event(payload)


def test_a_malformed_interrupt_flag_is_rejected(payloads: PayloadFactory) -> None:
    payload = payloads.post_tool_use_failure()
    payload["is_interrupt"] = "yes"
    with pytest.raises(ValueError):
        parse_hook_event(payload)
