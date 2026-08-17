from pathlib import Path

import pytest

from marginal import BudgetLimits, Treasury
from marginal.controls import ActionOutcomeStatus
from marginal.integrations.hookkit.bootstrap import OBSERVE_CAPABILITIES
from marginal.integrations.hookkit.events import ToolCallEnd, ToolCallStart
from marginal.integrations.hookkit.session import HookIntegrationError, HookSessionRuntime
from marginal.runtime import UniversalRuntime

SESSION = "session-1"


def _runtime() -> UniversalRuntime:
    return UniversalRuntime(
        Treasury(BudgetLimits(), mode="shadow"),
        engine="test-engine",
        session_id=SESSION,
        task_id="task-1",
        capabilities=OBSERVE_CAPABILITIES,
    )


def _session(workspace: Path) -> HookSessionRuntime:
    return HookSessionRuntime(_runtime(), workspace=workspace)


def _start(call_id: str, tool: str = "Read", **arguments: object) -> ToolCallStart:
    return ToolCallStart(
        session_id=SESSION,
        call_id=call_id,
        tool_name=tool,
        tool_input=arguments or {"file_path": "/workspace/example.txt"},
    )


def _end(
    call_id: str,
    *,
    tool: str = "Read",
    outcome: ActionOutcomeStatus = ActionOutcomeStatus.SUCCESS,
    evidence: object = None,
    duration_ms: float | None = None,
) -> ToolCallEnd:
    return ToolCallEnd(
        session_id=SESSION,
        call_id=call_id,
        tool_name=tool,
        outcome=outcome,
        evidence=evidence if evidence is not None else {"content": "hello"},
        duration_ms=duration_ms,
    )


def test_a_completed_call_is_settled_exactly_once(tmp_path: Path) -> None:
    session = _session(tmp_path)
    decision = session.tool_call_start(_start("call-1"))
    assert decision.allowed is True
    assert session.pending_action_ids() == ("call-1",)
    assert session.tool_call_end(_end("call-1", duration_ms=7.0)) is ActionOutcomeStatus.SUCCESS
    assert session.pending_action_ids() == ()
    assert session.summary()["successful_observations"] == 1
    assert session.summary()["enforced_denials"] == 0


def test_an_observed_session_never_denies(tmp_path: Path) -> None:
    session = _session(tmp_path)
    for index in range(4):
        decision = session.tool_call_start(_start(f"call-{index}"))
        assert decision.allowed is True
        session.tool_call_end(_end(f"call-{index}"))
    assert session.summary()["enforced_denials"] == 0


def test_repeated_identical_work_is_recommended_against(git_workspace: Path) -> None:
    session = _session(git_workspace)
    recommendations: list[bool] = []
    signals: list[str] = []
    for index in range(4):
        decision = session.tool_call_start(_start(f"call-{index}"))
        recommendations.append(decision.recommended)
        signal = session.last_no_progress_signal
        signals.append(signal.reason_code if signal else "")
        session.tool_call_end(_end(f"call-{index}"))
    assert recommendations[0] is True
    assert recommendations[-1] is False
    assert signals[-1] == "NO_PROGRESS_ENFORCEMENT_ELIGIBLE"
    assert session.summary()["recommended_stops"] >= 1


def test_new_evidence_clears_the_repetition_signal(git_workspace: Path) -> None:
    session = _session(git_workspace)
    session.tool_call_start(_start("call-1"))
    session.tool_call_end(_end("call-1", evidence={"content": "first"}))
    session.tool_call_start(_start("call-2"))
    session.tool_call_end(_end("call-2", evidence={"content": "second"}))
    session.tool_call_start(_start("call-3"))
    signal = session.last_no_progress_signal
    assert signal is not None
    assert signal.should_recommend_stop is False


def test_a_duplicate_pending_identity_is_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.tool_call_start(_start("call-1"))
    with pytest.raises(HookIntegrationError):
        session.tool_call_start(_start("call-1"))


def test_a_completion_for_a_different_tool_is_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.tool_call_start(_start("call-1", tool="Read"))
    with pytest.raises(HookIntegrationError):
        session.tool_call_end(_end("call-1", tool="Bash"))


def test_a_completion_without_a_proposal_is_reported_not_settled(tmp_path: Path) -> None:
    session = _session(tmp_path)
    assert session.tool_call_end(_end("call-unknown")) is ActionOutcomeStatus.UNKNOWN
    assert session.summary()["unmatched_completions"] == 1
    assert session.summary()["completed_observations"] == 0


def test_a_foreign_session_identity_is_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    foreign = ToolCallStart(
        session_id="other-session",
        call_id="call-1",
        tool_name="Read",
        tool_input={"file_path": "/workspace/example.txt"},
    )
    with pytest.raises(HookIntegrationError):
        session.tool_call_start(foreign)


def test_close_settles_unobserved_proposals(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.tool_call_start(_start("call-1"))
    session.close()
    assert session.pending_action_ids() == ()
    assert session.summary()["unknown_observations"] == 1
    with pytest.raises(HookIntegrationError):
        session.tool_call_start(_start("call-2"))


def test_close_is_idempotent(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.close()
    session.close()
    assert session.summary()["pending_actions"] == 0


def test_action_evidence_never_exposes_raw_identity(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.tool_call_start(_start("call-1", file_path="/workspace/secret.txt"))
    evidence = session.action_evidence("call-1")
    assert evidence is not None
    assert "secret" not in str(evidence)
    assert "call-1" not in str(evidence)
    assert len(evidence["action_hash"]) == 64
    assert session.action_evidence("missing") is None


def test_an_explicit_failure_is_settled_as_a_failure(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.tool_call_start(_start("call-1"))
    outcome = session.tool_call_end(
        _end("call-1", outcome=ActionOutcomeStatus.FAILURE, duration_ms=3.0)
    )
    assert outcome is ActionOutcomeStatus.FAILURE
    assert session.summary()["failed_observations"] == 1


def test_an_unknown_outcome_is_not_counted_as_success(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.tool_call_start(_start("call-1"))
    outcome = session.tool_call_end(_end("call-1", outcome=ActionOutcomeStatus.UNKNOWN))
    assert outcome is ActionOutcomeStatus.UNKNOWN
    assert session.summary()["unknown_observations"] == 1
    assert session.summary()["successful_observations"] == 0


def test_the_runtime_must_be_a_universal_runtime(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        HookSessionRuntime(object(), workspace=tmp_path)  # type: ignore[arg-type]
