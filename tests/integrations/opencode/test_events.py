import pytest

from marginal.integrations.opencode.events import (
    SessionRequest,
    ToolEndRequest,
    ToolStartRequest,
    parse_request,
)

from .conftest import RequestFactory


def test_a_session_request_is_parsed(requests: RequestFactory) -> None:
    request = parse_request("session_start", requests.session())
    assert isinstance(request, SessionRequest)
    assert request.session_id == "ses_synthetic0001"


def test_a_tool_start_request_is_parsed(requests: RequestFactory) -> None:
    request = parse_request("tool_start", requests.tool_start())
    assert isinstance(request, ToolStartRequest)
    assert request.tool_name == "read"
    assert request.arguments == {"filePath": "./example.txt"}


def test_a_tool_end_request_is_parsed(requests: RequestFactory) -> None:
    payload = requests.tool_end(signals={"exit": 0}, duration_ms=9.5)
    request = parse_request("tool_end", payload)
    assert isinstance(request, ToolEndRequest)
    assert request.evidence_digest == "a" * 64
    assert request.signals == {"exit": 0}
    assert request.duration_ms == 9.5


def test_a_tool_end_request_tolerates_missing_evidence(requests: RequestFactory) -> None:
    payload = requests.tool_end()
    del payload["evidence_digest"]
    request = parse_request("tool_end", payload)
    assert isinstance(request, ToolEndRequest)
    assert request.evidence_digest == ""


@pytest.mark.parametrize("field", ["session_id", "call_id", "tool_name"])
def test_required_identity_is_enforced(requests: RequestFactory, field: str) -> None:
    payload = requests.tool_start()
    payload[field] = ""
    with pytest.raises(ValueError):
        parse_request("tool_start", payload)


def test_arguments_must_be_a_mapping(requests: RequestFactory) -> None:
    payload = requests.tool_start()
    payload["arguments"] = ["not", "a", "mapping"]
    with pytest.raises(ValueError):
        parse_request("tool_start", payload)


def test_signals_must_be_a_mapping(requests: RequestFactory) -> None:
    payload = requests.tool_end()
    payload["signals"] = "exit=0"
    with pytest.raises(ValueError):
        parse_request("tool_end", payload)


def test_a_malformed_duration_is_rejected(requests: RequestFactory) -> None:
    payload = requests.tool_end(duration_ms=1.0)
    payload["duration_ms"] = "fast"
    with pytest.raises(ValueError):
        parse_request("tool_end", payload)


def test_a_negative_duration_is_rejected(requests: RequestFactory) -> None:
    payload = requests.tool_end()
    payload["duration_ms"] = -1.0
    with pytest.raises(ValueError):
        parse_request("tool_end", payload)


def test_an_unsupported_operation_is_rejected(requests: RequestFactory) -> None:
    with pytest.raises(ValueError):
        parse_request("deny", requests.tool_start())


def test_a_non_mapping_payload_is_rejected() -> None:
    with pytest.raises(TypeError):
        parse_request("tool_start", ["not", "a", "mapping"])  # type: ignore[arg-type]
