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
            minimum_roi=1.0,
            minimum_expected_gain=0.01,
            target_success_probability=0.95,
        )
    )


def test_accepts_action_with_positive_marginal_return() -> None:
    decision = make_policy().evaluate(
        Action(
            name="run targeted test",
            kind="verification",
            cost=Cost(tokens=1_000, usd=0.02),
            expected_gain=0.20,
            is_verification=True,
        ),
        BudgetLedger(BudgetLimits(max_tokens=10_000, max_usd=2.0)),
    )
    assert decision.allowed
    assert decision.score > 0
    assert decision.reason.startswith("approved:")


def test_rejects_action_with_insufficient_marginal_return() -> None:
    decision = make_policy().evaluate(
        Action(
            name="ask another reviewer",
            kind="review",
            cost=Cost(tokens=5_000, usd=0.10),
            expected_gain=0.02,
        ),
        BudgetLedger(BudgetLimits(max_tokens=10_000, max_usd=2.0)),
    )
    assert not decision.allowed
    assert decision.reason.startswith("rejected: marginal ROI")


def test_estimator_uses_observed_mean_when_action_has_no_explicit_gain() -> None:
    estimator = ValueEstimator(default_gain=0.03)
    estimator.observe("research", 0.10)
    estimator.observe("research", 0.20)
    assert estimator.estimate(Action(name="search docs", kind="research")) == pytest.approx(0.15)


def test_expected_gain_is_capped_by_remaining_success_probability() -> None:
    policy = MarginalPolicy(PolicyConfig(outcome_value_usd=1.0, target_success_probability=0.95))
    decision = policy.evaluate(
        Action(
            name="small remaining upside",
            kind="reasoning",
            cost=Cost(usd=0.06),
            expected_gain=0.50,
            current_success_probability=0.90,
        ),
        BudgetLedger(BudgetLimits(max_usd=1.0)),
    )
    assert not decision.allowed
    assert decision.expected_gain == pytest.approx(0.05)
