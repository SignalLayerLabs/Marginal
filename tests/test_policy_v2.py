from __future__ import annotations

from marginal import Action, BudgetLimits, Cost
from marginal.budget import BudgetLedger
from marginal.policy import MarginalPolicy, PolicyConfig
from marginal.profiles import PolicyProfile, build_policy, policy_config_for_profile


def test_policy_has_stable_versioned_identity() -> None:
    first = MarginalPolicy(PolicyConfig(minimum_roi=1.2), name="reference", version="2.0.0")
    second = MarginalPolicy(PolicyConfig(minimum_roi=1.2), name="reference", version="2.0.0")
    assert first.identity == second.identity
    assert first.identity.config_hash


def test_policy_decision_contains_structured_reason_and_estimator_metadata() -> None:
    policy = MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0))
    decision = policy.evaluate(
        Action(name="verify", kind="verification", cost=Cost(tokens=10), expected_gain=0.2),
        BudgetLedger(BudgetLimits(max_tokens=100)),
    )
    assert decision.allowed
    assert decision.reason_code == "APPROVED"
    assert decision.confidence == 1.0
    assert decision.estimator_version


def test_budget_rejection_has_stable_reason_code() -> None:
    policy = MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0))
    decision = policy.evaluate(
        Action(name="large", kind="tool", cost=Cost(tokens=101), expected_gain=0.2),
        BudgetLedger(BudgetLimits(max_tokens=100)),
    )
    assert not decision.allowed
    assert decision.reason_code == "BUDGET_REJECTED"


def test_reference_profiles_are_distinct_and_buildable() -> None:
    configs = [policy_config_for_profile(profile) for profile in PolicyProfile]
    assert len({config.token_shadow_price_per_million_usd for config in configs}) == len(configs)
    policy = build_policy("balanced")
    assert policy.identity.name == "profile:balanced"


def test_policy_rejects_non_string_identity_fields() -> None:
    import pytest

    with pytest.raises(TypeError, match="name"):
        MarginalPolicy(name=123)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="version"):
        MarginalPolicy(version=123)  # type: ignore[arg-type]
