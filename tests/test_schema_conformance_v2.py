from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from marginal import (
    AgentAction,
    AgentCapabilities,
    AgentDecision,
    AgentEvent,
    BudgetLimits,
    Cost,
    DecisionLedgerContext,
    JsonlDecisionLedger,
    MarginalPolicy,
    Outcome,
    PolicyConfig,
    TokenUsage,
    Treasury,
    aggregate_ledger_records,
)
from marginal.ledger import read_decision_ledger

ROOT = Path(__file__).parents[1]


def _schema(name: str) -> dict[str, object]:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _validate(name: str, payload: object) -> None:
    validator = Draft202012Validator(_schema(name), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    assert not errors, [error.message for error in errors]


def test_protocol_payloads_conform_to_published_schemas() -> None:
    action = AgentAction(
        action_id="action",
        name="run test",
        kind="verification",
        estimated_cost=Cost(tokens=100),
        token_usage=TokenUsage(input_tokens=60, cached_input_tokens=20, output_tokens=20),
        expected_gain=0.2,
        is_verification=True,
    )
    event = AgentEvent(
        engine="codex",
        session_id="session",
        task_id="task",
        event_type="action.before",
        action=action,
    )
    decision = AgentDecision(
        action_id="action",
        allowed=True,
        recommended=True,
        reason="approved",
        reason_code="APPROVED",
        recommendation_reason="approved",
        recommendation_reason_code="APPROVED",
        mode="shadow",
        expected_gain=0.2,
        confidence=1.0,
    )
    capabilities = AgentCapabilities(block_actions=True, record_outcomes=True)

    _validate("agent-event-v1.json", event.to_dict())
    _validate("agent-decision-v1.json", decision.to_dict())
    _validate("agent-capabilities-v1.json", capabilities.to_dict())
    assert action.token_usage is not None
    _validate("token-usage-v2.json", asdict(action.token_usage))


def test_outcome_and_ledger_records_conform_to_published_schemas(tmp_path: Path) -> None:
    outcome = Outcome(task_id="task", reward=1.0, resolved=True, verifier="pytest")
    _validate("outcome-v1.json", outcome.to_dict())

    path = tmp_path / "ledger.jsonl"
    ledger = JsonlDecisionLedger(
        path,
        context=DecisionLedgerContext(run_id="run", task_id="task", engine="codex"),
    )
    treasury = Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
        trace_sink=ledger,
        mode="shadow",
    )
    treasury.record_outcome(outcome)
    for record in read_decision_ledger(path):
        _validate("decision-ledger-v2.json", record)


def test_aggregate_export_records_conform_to_published_schema() -> None:
    records = [
        {
            "event": "authorization",
            "action": {
                "kind": "verification",
                "cost": {"tokens": 100, "usd": 0.0, "latency_ms": 0, "risk": 0.0},
            },
            "decision": {
                "allowed": True,
                "recommended": False,
                "reason_code": "SHADOW_OVERRIDE",
                "expected_gain": 0.2,
            },
        }
    ]
    rows = aggregate_ledger_records(records, minimum_group_size=1)
    assert len(rows) == 1
    _validate("aggregate-export-v1.json", rows[0])


def test_safe_telemetry_ledger_record_conforms_to_published_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "safe.jsonl"
    ledger = JsonlDecisionLedger(
        path,
        context=DecisionLedgerContext(
            run_id="customer-acme",
            task_id="customer-acme",
            model="internal-model",
        ),
        privacy_profile="safe_telemetry",
        privacy_key=b"k" * 32,
    )
    ledger.emit({"event": "custom", "metadata": {"repository": "secret"}})
    record = read_decision_ledger(path)[0]
    _validate("decision-ledger-v2.json", record)
    _validate("safe-telemetry-v1.json", record)
    assert record["privacy_profile"] == "safe_telemetry"


def test_complete_safe_telemetry_lifecycle_conforms_to_strict_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "safe-lifecycle.jsonl"
    ledger = JsonlDecisionLedger(
        path,
        context=DecisionLedgerContext(
            run_id="customer-acme",
            task_id="customer-acme",
            trajectory_id="secret-trajectory",
            engine="codex",
            model="internal-model",
        ),
        privacy_profile="safe_telemetry",
        privacy_key=b"k" * 32,
    )
    treasury = Treasury(
        BudgetLimits(max_tokens=1_000),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
        trace_sink=ledger,
        mode="shadow",
    )
    action = AgentAction(
        action_id="customer-action",
        name="review secret contract",
        kind="verification",
        estimated_cost=Cost(tokens=100),
        expected_gain=0.2,
        is_verification=True,
        metadata={"repository": "secret-merger"},
    ).to_core_action(engine="codex")

    assert treasury.authorize(action).allowed
    treasury.commit(action)
    treasury.record_outcome(
        Outcome(
            task_id="customer-acme",
            trajectory_id="secret-trajectory",
            reward=1.0,
            resolved=True,
            verifier="internal-verifier",
            evidence={"repository": "secret-merger"},
        )
    )

    records = read_decision_ledger(path)
    assert {record["event"] for record in records} == {
        "authorization",
        "commit",
        "outcome",
    }
    for record in records:
        _validate("safe-telemetry-v1.json", record)
