from __future__ import annotations

from pathlib import Path

from marginal import Action, BudgetLimits, Cost, MarginalPolicy, PolicyConfig, Treasury
from marginal.ledger import DecisionLedgerContext, JsonlDecisionLedger
from marginal.replay import render_replay_report, replay_ledger


def test_replay_compares_recorded_and_new_policy_without_causal_claim(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = JsonlDecisionLedger(path, context=DecisionLedgerContext(run_id="run"))
    permissive = MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0))
    treasury = Treasury(BudgetLimits(max_tokens=100), policy=permissive, trace_sink=ledger)
    action = Action(name="review", kind="review", cost=Cost(tokens=40), expected_gain=0.01)
    treasury.authorize(action)
    treasury.commit(action)

    strict = MarginalPolicy(
        PolicyConfig(
            outcome_value_usd=1.0,
            token_shadow_price_per_million_usd=1000.0,
            minimum_roi=2.0,
        )
    )
    result = replay_ledger(path, strict, BudgetLimits(max_tokens=100))
    assert result.actions == 1
    assert result.recorded_allowed == 1
    assert result.replayed_allowed == 0
    assert result.estimated_avoided_tokens == 40
    report = render_replay_report(result)
    assert "not causal proof" in report.lower()


def test_replay_rejects_non_boolean_recorded_recommendation(tmp_path: Path) -> None:
    import json

    import pytest

    path = tmp_path / "ledger.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "event_id": "event",
                "sequence": 1,
                "timestamp": "2026-08-06T00:00:00+00:00",
                "run_id": "run",
                "event": "authorization",
                "action": {
                    "name": "review",
                    "kind": "review",
                    "cost": {"tokens": 10, "usd": 0.0, "latency_ms": 0, "risk": 0.0},
                    "expected_gain": 0.1,
                    "current_success_probability": 0.0,
                    "is_verification": False,
                    "fingerprint": "fp",
                    "metadata": {},
                },
                "decision": {"allowed": True, "recommended": "false"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="recommended"):
        replay_ledger(path, MarginalPolicy())


def test_replay_reports_malformed_authorization_as_value_error(tmp_path: Path) -> None:
    import json

    import pytest

    path = tmp_path / "ledger.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "event_id": "event",
                "sequence": 1,
                "timestamp": "2026-08-06T00:00:00+00:00",
                "run_id": "run",
                "event": "authorization",
                "action": {"kind": "review", "cost": {}},
                "decision": {"allowed": True, "recommended": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="malformed authorization"):
        replay_ledger(path, MarginalPolicy())
