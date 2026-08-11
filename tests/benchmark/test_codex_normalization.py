from __future__ import annotations

import pytest
from benchmark.codex_adapter.normalization import normalize_pre_tool_use


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "tool_use_id": "call-1",
        "tool_name": "Bash",
        "tool_input": {"command": "pytest -q"},
        "cwd": "/tmp/worktree",
    }
    payload.update(overrides)
    return payload


def test_normalization_builds_zero_cost_verification_action() -> None:
    proposal = normalize_pre_tool_use(
        _payload(), state_hash="state-a", previous_evidence_hash="evidence-a"
    )

    assert proposal.tool_use_id == "call-1"
    assert proposal.action.kind == "verification"
    assert proposal.action.is_verification is True
    assert proposal.action.cost.tokens == 0
    assert proposal.action.cost.usd == 0
    assert proposal.action.fingerprint == "codex:call-1"
    assert proposal.action.metadata["state_hash"] == "state-a"
    assert proposal.action.metadata["evidence_hash"] == "evidence-a"
    assert proposal.action.metadata["phase"] == "codex-tool-use"


def test_semantic_key_is_canonical_but_invocation_fingerprint_is_unique() -> None:
    first = normalize_pre_tool_use(
        _payload(tool_input={"command": "git status", "timeout_ms": 1}),
        state_hash="same",
    )
    second = normalize_pre_tool_use(
        _payload(
            tool_use_id="call-2",
            tool_input={"timeout_ms": 1, "command": "git status"},
        ),
        state_hash="same",
    )

    assert (
        first.action.metadata["marginal_semantic_key"]
        == second.action.metadata["marginal_semantic_key"]
    )
    assert first.action.fingerprint != second.action.fingerprint


@pytest.mark.parametrize(
    ("tool_name", "tool_input", "expected_kind"),
    [
        ("apply_patch", {"patch": "*** Begin Patch"}, "edit"),
        ("mcp__github__search", {"query": "needle"}, "mcp"),
        ("Bash", {"command": "rg needle src"}, "shell"),
        ("Read", {"path": "README.md"}, "tool"),
    ],
)
def test_tool_kind_classification(
    tool_name: str, tool_input: dict[str, object], expected_kind: str
) -> None:
    proposal = normalize_pre_tool_use(
        _payload(tool_name=tool_name, tool_input=tool_input), state_hash="state"
    )

    assert proposal.action.kind == expected_kind
    assert proposal.action.is_verification is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tool_use_id", ""),
        ("tool_name", ""),
        ("tool_input", []),
        ("cwd", 3),
    ],
)
def test_invalid_hook_payload_is_rejected(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError), match=field):
        normalize_pre_tool_use(_payload(**{field: value}), state_hash="state")


def test_non_finite_tool_input_is_rejected() -> None:
    with pytest.raises(ValueError, match="JSON"):
        normalize_pre_tool_use(
            _payload(tool_input={"temperature": float("nan")}), state_hash="state"
        )
