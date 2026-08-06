"""Observe recommendations without changing application behavior."""

from marginal import (
    Action,
    BudgetLimits,
    Cost,
    DecisionLedgerContext,
    JsonlDecisionLedger,
    Outcome,
    Treasury,
    budgeted_call,
    build_policy,
)

ledger = JsonlDecisionLedger(
    "shadow-ledger.jsonl",
    context=DecisionLedgerContext(run_id="example-run", task_id="example-task"),
)
treasury = Treasury(
    BudgetLimits(max_tokens=1_000, verification_reserve_tokens=100),
    policy=build_policy("quality-first"),
    trace_sink=ledger,
    mode="shadow",
)

result = budgeted_call(
    treasury,
    lambda: "executed even if the policy recommends deny",
    action=Action(
        name="optional reviewer",
        kind="review",
        cost=Cost(tokens=2_000),
        expected_gain=0.01,
    ),
)
print(result)

treasury.record_outcome(
    Outcome(task_id="example-task", reward=1.0, resolved=True, verifier="example")
)
print(treasury.summary())
