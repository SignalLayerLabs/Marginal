import json

import pytest

from marginal.integrations.hookkit.events import ToolCallStart
from marginal.integrations.hookkit.normalization import (
    classify_action,
    normalize_tool_call,
    semantic_key,
)
from marginal.protocol import DeduplicationScope


def _start(tool: str = "Read", **arguments: object) -> ToolCallStart:
    return ToolCallStart(
        session_id="session-1",
        call_id="call-1",
        tool_name=tool,
        tool_input=arguments or {"file_path": "/workspace/example.txt"},
        turn_id="turn-1",
    )


def test_semantic_key_is_stable_and_argument_sensitive() -> None:
    first = semantic_key(_start())
    assert first == semantic_key(_start())
    assert first != semantic_key(_start(file_path="/workspace/other.txt"))
    assert first != semantic_key(_start(tool="Write"))


def test_semantic_key_ignores_tool_name_case_only() -> None:
    assert semantic_key(_start(tool="read")) == semantic_key(_start(tool="READ"))


@pytest.mark.parametrize(
    ("tool", "arguments", "expected_kind", "expected_verification"),
    [
        ("Bash", {"command": "pytest -q"}, "verification", True),
        ("bash", {"command": "echo hi"}, "shell", False),
        ("Edit", {"file_path": "/workspace/a.py"}, "edit", False),
        ("Read", {"file_path": "/workspace/a.py"}, "read", False),
        ("WebFetch", {"url": "https://example.invalid"}, "fetch", False),
        ("mcp__server__tool", {"argument": 1}, "mcp", False),
        ("Task", {"prompt_kind": "subagent"}, "tool", False),
    ],
)
def test_classify_action_labels_generic_kinds(
    tool: str,
    arguments: dict[str, object],
    expected_kind: str,
    expected_verification: bool,
) -> None:
    kind, is_verification = classify_action(_start(tool=tool, **arguments))
    assert kind == expected_kind
    assert is_verification is expected_verification


def test_normalized_action_retains_no_raw_arguments() -> None:
    action = normalize_tool_call(
        _start(file_path="/workspace/secret-plan.txt"),
        engine="test-engine",
        state_hash="state-hash",
    )
    serialized = json.dumps(
        {
            "name": action.name,
            "kind": action.kind,
            "phase": action.phase,
            "state_hash": action.state_hash,
            "metadata": dict(action.metadata),
        }
    )
    assert "secret-plan" not in serialized
    assert action.deduplication_scope is DeduplicationScope.ONCE_PER_STATE
    assert action.phase == "test-engine-tool-use"
    assert action.metadata["turn_id"] == "turn-1"
    assert action.metadata["evidence_hash"] == ""


def test_normalization_accepts_unobservable_state() -> None:
    action = normalize_tool_call(_start(), engine="test-engine", state_hash="")
    assert action.state_hash == ""


def test_normalization_records_previous_evidence() -> None:
    action = normalize_tool_call(
        _start(),
        engine="test-engine",
        state_hash="state-hash",
        previous_evidence_hash="evidence-hash",
    )
    assert action.metadata["evidence_hash"] == "evidence-hash"


def test_normalization_rejects_an_empty_engine() -> None:
    with pytest.raises(ValueError):
        normalize_tool_call(_start(), engine="  ", state_hash="state-hash")


def test_normalization_rejects_unserializable_arguments() -> None:
    start = ToolCallStart(
        session_id="session-1",
        call_id="call-1",
        tool_name="Read",
        tool_input={"handle": object()},
    )
    with pytest.raises(ValueError):
        normalize_tool_call(start, engine="test-engine", state_hash="state-hash")
