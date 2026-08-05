from __future__ import annotations

import pytest

from marginal.budget import BudgetLedger, BudgetLimits
from marginal.estimator import ValueEstimator
from marginal.models import Action, Cost
from marginal.policy import MarginalPolicy, PolicyConfig


def make_policy() -> MarginalPolicy:
    return MarginalPolicy(
        PolicyConfig(
            outcome_value_usd=1.0,
            token_shadow_price_per_million_usd=10.0,
            latency_shadow_price_per_second_usd=0.0,
            risk_shadow_price_usd=1.0,
            minimum_roi=1.0,
            minimum_expected_gain=0.01,
            target_success_probability=0.95,
        )
    )


def test_accepts_action_with_positive_marginal_return() -> None:
    policy = make_policy()
    ledger = BudgetLedger(BudgetLimits(max_tokens=10_000, max_usd=2.0))
    action = Action(
        name="run targeted test",
        kind="verification",
        cost=Cost(tokens=1_000, usd=0.02),
        expected_gain=0.20,
        is_verification=True,
    )

    decision = policy.evaluate(action, ledger)

    assert decision.allowed
    assert decision.score > 0
    assert decision.reason.startswith("approved:")


def test_rejects_action_with_insufficient_marginal_return() -> None:
    policy = make_policy()
    ledger = BudgetLedger(BudgetLimits(max_tokens=10_000, max_usd=2.0))
    action = Action(
        name="ask another reviewer",
        kind="review",
        cost=Cost(tokens=5_000, usd=0.10),
        expected_gain=0.02,
    )

    decision = policy.evaluate(action, ledger)

    assert not decision.allowed
    assert decision.reason.startswith("rejected: marginal ROI")
    assert decision.estimated_cost_value > decision.expected_gain


def test_risk_is_priced_into_the_decision() -> None:
    policy = make_policy()
    ledger = BudgetLedger(BudgetLimits(max_tokens=10_000, max_usd=2.0))
    safe = Action(name="safe", kind="tool", cost=Cost(usd=0.01, risk=0.0), expected_gain=0.10)
    risky = Action(name="risky", kind="tool", cost=Cost(usd=0.01, risk=0.20), expected_gain=0.10)

    safe_decision = policy.evaluate(safe, ledger)
    risky_decision = policy.evaluate(risky, ledger)

    assert safe_decision.allowed
    assert not risky_decision.allowed
    assert risky_decision.estimated_cost_value > safe_decision.estimated_cost_value


def test_rejects_duplicate_fingerprint() -> None:
    policy = make_policy()
    policy.mark_executed("same-call")
    ledger = BudgetLedger(BudgetLimits(max_tokens=10_000, max_usd=2.0))
    action = Action(
        name="repeat",
        kind="llm",
        cost=Cost(tokens=100),
        expected_gain=0.5,
        fingerprint="same-call",
    )

    decision = policy.evaluate(action, ledger)

    assert not decision.allowed
    assert decision.reason == "rejected: duplicate action"


def test_stops_when_target_success_probability_is_reached() -> None:
    policy = make_policy()
    ledger = BudgetLedger(BudgetLimits(max_tokens=10_000, max_usd=2.0))
    action = Action(
        name="continue",
        kind="reasoning",
        cost=Cost(tokens=100),
        expected_gain=0.5,
        current_success_probability=0.96,
    )

    decision = policy.evaluate(action, ledger)

    assert not decision.allowed
    assert decision.reason == "rejected: target success probability already reached"


def test_estimator_uses_observed_mean_when_action_has_no_explicit_gain() -> None:
    estimator = ValueEstimator(default_gain=0.03)
    estimator.observe("research", 0.10)
    estimator.observe("research", 0.20)
    action = Action(name="search docs", kind="research", cost=Cost())

    assert estimator.estimate(action) == pytest.approx(0.15)


def test_expected_gain_is_capped_by_remaining_success_probability() -> None:
    policy = MarginalPolicy(
        PolicyConfig(
            outcome_value_usd=1.0,
            minimum_roi=1.0,
            target_success_probability=0.95,
        )
    )
    ledger = BudgetLedger(BudgetLimits(max_usd=1.0))
    action = Action(
        name="small remaining upside",
        kind="reasoning",
        cost=Cost(usd=0.06),
        expected_gain=0.50,
        current_success_probability=0.90,
    )

    decision = policy.evaluate(action, ledger)

    assert not decision.allowed
    assert decision.expected_gain == pytest.approx(0.05)


def test_policy_rejects_non_finite_configuration() -> None:
    with pytest.raises(ValueError, match="finite"):
        PolicyConfig(outcome_value_usd=float("inf"))


def test_policy_rejects_boolean_and_non_numeric_configuration() -> None:
    with pytest.raises(TypeError, match="outcome_value_usd must be a number"):
        PolicyConfig(outcome_value_usd=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="minimum_roi must be a number"):
        PolicyConfig(minimum_roi="1")  # type: ignore[arg-type]


def test_value_estimator_rejects_boolean_and_non_finite_observations() -> None:
    with pytest.raises(TypeError, match="default_gain must be a number"):
        ValueEstimator(default_gain=True)  # type: ignore[arg-type]

    estimator = ValueEstimator()
    with pytest.raises(ValueError, match="realized_gain must be finite"):
        estimator.observe("research", float("nan"))
