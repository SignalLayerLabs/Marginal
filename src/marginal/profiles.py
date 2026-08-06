"""Conservative reference policy profiles for common user intents."""

from __future__ import annotations

from enum import Enum

from .estimator import ValueEstimator
from .policy import MarginalPolicy, PolicyConfig


class PolicyProfile(str, Enum):
    QUALITY_FIRST = "quality-first"
    BALANCED = "balanced"
    TOKEN_SAVER = "token-saver"
    STRICT_BUDGET = "strict-budget"

    @classmethod
    def parse(cls, value: PolicyProfile | str) -> PolicyProfile:
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().lower().replace("_", "-")
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"unknown policy profile: {value}") from exc


def policy_config_for_profile(profile: PolicyProfile | str) -> PolicyConfig:
    """Return transparent reference defaults, not empirically calibrated guarantees."""

    selected = PolicyProfile.parse(profile)
    configs = {
        PolicyProfile.QUALITY_FIRST: PolicyConfig(
            outcome_value_usd=10.0,
            token_shadow_price_per_million_usd=2.0,
            minimum_roi=0.5,
            minimum_expected_gain=0.005,
            target_success_probability=0.99,
        ),
        PolicyProfile.BALANCED: PolicyConfig(
            outcome_value_usd=5.0,
            token_shadow_price_per_million_usd=10.0,
            minimum_roi=1.0,
            minimum_expected_gain=0.01,
            target_success_probability=0.95,
        ),
        PolicyProfile.TOKEN_SAVER: PolicyConfig(
            outcome_value_usd=3.0,
            token_shadow_price_per_million_usd=25.0,
            minimum_roi=1.2,
            minimum_expected_gain=0.02,
            target_success_probability=0.92,
        ),
        PolicyProfile.STRICT_BUDGET: PolicyConfig(
            outcome_value_usd=2.0,
            token_shadow_price_per_million_usd=60.0,
            minimum_roi=1.5,
            minimum_expected_gain=0.03,
            target_success_probability=0.90,
        ),
    }
    return configs[selected]


def build_policy(
    profile: PolicyProfile | str,
    *,
    estimator: ValueEstimator | None = None,
) -> MarginalPolicy:
    selected = PolicyProfile.parse(profile)
    return MarginalPolicy(
        policy_config_for_profile(selected),
        estimator=estimator,
        name=f"profile:{selected.value}",
        version="2.0.0",
    )
