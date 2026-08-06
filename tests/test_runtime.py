from __future__ import annotations

from pathlib import Path

from marginal import BudgetLimits, Cost, MarginalPolicy, PolicyConfig, Treasury
from marginal.ledger import DecisionLedgerContext, JsonlDecisionLedger, read_decision_ledger
from marginal.outcomes import Outcome
from marginal.protocol import AgentAction, AgentCapabilities
from marginal.runtime import UniversalRuntime


def test_runtime_executes_complete_shadow_lifecycle(tmp_path: Path) -> None:
    ledger = JsonlDecisionLedger(
        tmp_path / "ledger.jsonl",
        context=DecisionLedgerContext(run_id="run", engine="opencode"),
    )
    treasury = Treasury(
        BudgetLimits(max_tokens=5),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=1.0, minimum_roi=10.0)),
        trace_sink=ledger,
        mode="shadow",
    )
    runtime = UniversalRuntime(
        treasury,
        engine="opencode",
        session_id="session",
        task_id="task",
        capabilities=AgentCapabilities(block_actions=True, record_outcomes=True),
    )
    action = AgentAction(
        action_id="a1",
        name="read repository",
        kind="file_read",
        estimated_cost=Cost(tokens=10),
        expected_gain=0.01,
        state_hash="state-1",
    )
    decision = runtime.before_action(action)
    assert decision.allowed
    assert not decision.recommended
    runtime.after_action("a1", actual_cost=Cost(tokens=8))
    runtime.record_outcome(Outcome(task_id="task", reward=1.0, resolved=True))
    assert treasury.usage.tokens == 8
    assert [record["event"] for record in read_decision_ledger(ledger.path)] == [
        "authorization",
        "commit",
        "outcome",
    ]


def test_runtime_failure_with_measured_cost_settles_action() -> None:
    treasury = Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
    )
    runtime = UniversalRuntime(
        treasury,
        engine="codex",
        session_id="s",
        task_id="t",
        capabilities=AgentCapabilities(block_actions=True),
    )
    runtime.before_action(
        AgentAction(
            action_id="a",
            name="model turn",
            kind="llm",
            estimated_cost=Cost(tokens=50),
            expected_gain=0.5,
        )
    )
    runtime.fail_action("a", reason="timeout", actual_cost=Cost(tokens=20))
    assert treasury.usage.tokens == 20


def test_enforce_runtime_requires_blocking_capability() -> None:
    import pytest

    treasury = Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
        mode="enforce",
    )

    with pytest.raises(ValueError, match="block_actions"):
        UniversalRuntime(
            treasury,
            engine="codex",
            session_id="s",
            task_id="t",
            capabilities=AgentCapabilities(),
        )


def test_runtime_rejects_outcome_for_another_task() -> None:
    import pytest

    treasury = Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
        mode="shadow",
    )
    runtime = UniversalRuntime(treasury, engine="codex", session_id="s", task_id="task-a")

    with pytest.raises(ValueError, match="task_id"):
        runtime.record_outcome(Outcome(task_id="task-b", reward=1.0, resolved=True))


def test_runtime_adds_session_and_task_identity_to_core_action() -> None:
    treasury = Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
        mode="shadow",
    )
    runtime = UniversalRuntime(treasury, engine="codex", session_id="session", task_id="task")

    runtime.before_action(
        AgentAction(action_id="a", name="read", kind="file_read", expected_gain=0.2)
    )

    pending = runtime._pending["a"]
    assert pending.metadata["session_id"] == "session"
    assert pending.metadata["task_id"] == "task"


def test_runtime_invalid_actual_cost_keeps_action_pending() -> None:
    import pytest

    treasury = Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
        mode="shadow",
    )
    runtime = UniversalRuntime(treasury, engine="codex", session_id="s", task_id="t")
    runtime.before_action(
        AgentAction(action_id="a", name="read", kind="file_read", expected_gain=0.2)
    )

    with pytest.raises(TypeError, match="actual_cost"):
        runtime.after_action("a", actual_cost={})  # type: ignore[arg-type]

    assert runtime.pending_action_ids() == ("a",)


def test_runtime_invalid_failure_cost_keeps_action_pending() -> None:
    import pytest

    treasury = Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
        mode="shadow",
    )
    runtime = UniversalRuntime(treasury, engine="codex", session_id="s", task_id="t")
    runtime.before_action(
        AgentAction(action_id="a", name="read", kind="file_read", expected_gain=0.2)
    )

    with pytest.raises(TypeError, match="actual_cost"):
        runtime.fail_action("a", reason="timeout", actual_cost={})  # type: ignore[arg-type]

    assert runtime.pending_action_ids() == ("a",)


def test_runtime_rejects_invalid_capabilities_type() -> None:
    import pytest

    treasury = Treasury(BudgetLimits(max_tokens=100), mode="shadow")

    with pytest.raises(TypeError, match="capabilities"):
        UniversalRuntime(
            treasury,
            engine="codex",
            session_id="s",
            task_id="t",
            capabilities={},  # type: ignore[arg-type]
        )


def test_runtime_rejects_invalid_action_type_without_mutating_state() -> None:
    import pytest

    runtime = UniversalRuntime(
        Treasury(BudgetLimits(max_tokens=100), mode="shadow"),
        engine="codex",
        session_id="s",
        task_id="t",
    )

    with pytest.raises(TypeError, match="action"):
        runtime.before_action({})  # type: ignore[arg-type]

    assert runtime.pending_action_ids() == ()
