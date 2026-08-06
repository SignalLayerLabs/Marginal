"""Create a strict local ledger and a shareable aggregate export."""

from pathlib import Path

from marginal import (
    Action,
    BudgetLimits,
    Cost,
    DecisionLedgerContext,
    JsonlDecisionLedger,
    Outcome,
    Treasury,
    export_decision_ledger,
)

output = Path("privacy-example")
output.mkdir(exist_ok=True)

ledger_path = output / "safe-ledger.jsonl"
ledger = JsonlDecisionLedger(
    ledger_path,
    context=DecisionLedgerContext(
        run_id="customer-acme-contract-2026",
        task_id="customer-acme-contract-2026",
        engine="codex",
        model="internal-legal-model",
    ),
    privacy_profile="safe_telemetry",
    privacy_key_path=output / "privacy.key",
)

treasury = Treasury(
    BudgetLimits(max_tokens=10_000),
    trace_sink=ledger,
    mode="shadow",
)
for index in range(5):
    action = Action(
        name=f"review termination clause {index}",
        kind="verification",
        cost=Cost(tokens=1_200, usd=0.01, latency_ms=200),
        expected_gain=0.2,
        is_verification=True,
        metadata={
            "repository": "secret-merger-project",
            "document_index": index,
        },
    )
    treasury.authorize(action)
    treasury.commit(action)
treasury.record_outcome(
    Outcome(
        task_id="customer-acme-contract-2026",
        reward=1.0,
        resolved=True,
        verifier="internal legal verifier",
        evidence={"repository": "secret-merger-project"},
    )
)

export_decision_ledger(
    ledger_path,
    output / "aggregate.jsonl",
    privacy_profile="aggregate_export",
    minimum_group_size=5,
)
print(f"Safe operational ledger: {ledger_path}")
print(f"Aggregate shareable export: {output / 'aggregate.jsonl'}")
