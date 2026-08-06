from __future__ import annotations

import pytest

from marginal import Action, BudgetLimits, Cost, MarginalPolicy, PolicyConfig, Treasury
from marginal.modes import ExecutionMode


def rejecting_policy() -> MarginalPolicy:
    return MarginalPolicy(
        PolicyConfig(
            outcome_value_usd=1.0,
            token_shadow_price_per_million_usd=100_000.0,
            minimum_roi=10.0,
        )
    )


def test_shadow_mode_executes_policy_denial_and_preserves_recommendation() -> None:
    treasury = Treasury(BudgetLimits(max_tokens=100), policy=rejecting_policy(), mode="shadow")
    action = Action(name="expensive", kind="llm", cost=Cost(tokens=10), expected_gain=0.01)
    decision = treasury.authorize(action)
    assert decision.allowed is True
    assert decision.recommended is False
    assert decision.mode == "shadow"
    assert decision.recommendation_reason_code == "MARGINAL_ROI_REJECTED"
    treasury.commit(action)
    assert treasury.usage.tokens == 10


def test_shadow_mode_observes_hard_budget_violation_without_raising() -> None:
    policy = MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0))
    treasury = Treasury(BudgetLimits(max_tokens=5), policy=policy, mode=ExecutionMode.SHADOW)
    action = Action(name="over", kind="tool", cost=Cost(tokens=10), expected_gain=0.5)
    decision = treasury.authorize(action)
    assert decision.allowed
    assert decision.recommended is False
    treasury.commit(action)
    assert treasury.usage.tokens == 10
    assert treasury.summary()["observed_overruns"] == 1


def test_shadow_pending_reservations_inform_later_recommendations() -> None:
    policy = MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0))
    treasury = Treasury(BudgetLimits(max_tokens=100), policy=policy, mode="shadow")
    first = Action(name="first", kind="tool", cost=Cost(tokens=70), expected_gain=0.5)
    second = Action(name="second", kind="tool", cost=Cost(tokens=40), expected_gain=0.5)
    assert treasury.authorize(first).recommended is True
    second_decision = treasury.authorize(second)
    assert second_decision.allowed is True
    assert second_decision.recommended is False
    assert treasury.ledger.reserved_usage.tokens == 110


def test_enforce_mode_preserves_denial_behavior() -> None:
    treasury = Treasury(BudgetLimits(max_tokens=100), policy=rejecting_policy(), mode="enforce")
    action = Action(name="expensive", kind="llm", cost=Cost(tokens=10), expected_gain=0.01)
    decision = treasury.authorize(action)
    assert decision.allowed is False
    assert decision.recommended is False
    assert not treasury.is_authorized(action)


def test_recommend_mode_is_nonblocking_and_identifiable() -> None:
    treasury = Treasury(BudgetLimits(max_tokens=100), policy=rejecting_policy(), mode="recommend")
    decision = treasury.authorize(
        Action(name="review", kind="review", cost=Cost(tokens=10), expected_gain=0.01)
    )
    assert decision.allowed
    assert not decision.recommended
    assert decision.mode == "recommend"


def test_observe_value_updates_estimator_without_inferring_from_outcome() -> None:
    treasury = Treasury(BudgetLimits(), mode="shadow")
    action = Action(name="search", kind="research")
    treasury.observe_value(action, 0.4)
    assert treasury.policy.estimator.estimate(action) == pytest.approx(0.4)


def test_shadow_mode_allows_concurrent_duplicate_actions_without_losing_accounting() -> None:
    treasury = Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
        mode="shadow",
    )
    action = Action(name="same call", kind="llm", cost=Cost(tokens=10), expected_gain=0.5)

    first = treasury.authorize(action)
    second = treasury.authorize(action)

    assert first.allowed and first.recommended
    assert second.allowed and not second.recommended
    assert treasury.ledger.reserved_usage.tokens == 20

    treasury.commit(action)
    treasury.commit(action)

    assert treasury.usage.tokens == 20
    assert treasury.ledger.reserved_usage.tokens == 0
