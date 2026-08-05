"""Deterministic marginal-value allocation policy."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .budget import BudgetLedger
from .estimator import ValueEstimator
from .models import Action, Decision


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    """Economic assumptions used to score proposed actions."""

    outcome_value_usd: float = 1.0
    token_shadow_price_per_million_usd: float = 0.0
    latency_shadow_price_per_second_usd: float = 0.0
    risk_shadow_price_usd: float = 1.0
    minimum_roi: float = 1.0
    minimum_expected_gain: float = 0.0
    target_success_probability: float = 1.0

    def __post_init__(self) -> None:
        values = (
            ("outcome_value_usd", self.outcome_value_usd),
            (
                "token_shadow_price_per_million_usd",
                self.token_shadow_price_per_million_usd,
            ),
            (
                "latency_shadow_price_per_second_usd",
                self.latency_shadow_price_per_second_usd,
            ),
            ("risk_shadow_price_usd", self.risk_shadow_price_usd),
            ("minimum_roi", self.minimum_roi),
            ("minimum_expected_gain", self.minimum_expected_gain),
            ("target_success_probability", self.target_success_probability),
        )
        for name, value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(float(value)):
                raise ValueError("policy values must be finite")
            object.__setattr__(self, name, float(value))

        non_negative = values[:-1]
        if any(float(value) < 0 for _, value in non_negative):
            raise ValueError("policy values must be non-negative")
        if not 0.0 <= self.minimum_expected_gain <= 1.0:
            raise ValueError("minimum_expected_gain must be between 0 and 1")
        if not 0.0 <= self.target_success_probability <= 1.0:
            raise ValueError("target_success_probability must be between 0 and 1")


class MarginalPolicy:
    """Authorize actions only when expected marginal value justifies total cost."""

    def __init__(
        self,
        config: PolicyConfig | None = None,
        estimator: ValueEstimator | None = None,
    ) -> None:
        self.config = config or PolicyConfig()
        self.estimator = estimator or ValueEstimator()
        self._executed_fingerprints: set[str] = set()

    def mark_executed(self, fingerprint: str) -> None:
        if fingerprint:
            self._executed_fingerprints.add(fingerprint)

    def evaluate(self, action: Action, ledger: BudgetLedger) -> Decision:
        if action.current_success_probability >= self.config.target_success_probability:
            return Decision(False, "rejected: target success probability already reached")

        if action.fingerprint and action.fingerprint in self._executed_fingerprints:
            return Decision(False, "rejected: duplicate action")

        affordability = ledger.can_afford(action)
        if not affordability.allowed:
            return Decision(False, f"rejected: {affordability.reason}")

        estimated_gain = self.estimator.estimate(action)
        remaining_probability = max(
            0.0,
            self.config.target_success_probability - action.current_success_probability,
        )
        expected_gain = min(estimated_gain, remaining_probability)
        if expected_gain < self.config.minimum_expected_gain:
            return Decision(
                False,
                "rejected: expected gain below minimum",
                expected_gain=expected_gain,
            )

        cost_value = self._cost_value(action)
        expected_value = expected_gain * self.config.outcome_value_usd
        score = expected_value - cost_value
        roi = float("inf") if cost_value == 0 else expected_value / cost_value

        if score < 0 or roi < self.config.minimum_roi:
            return Decision(
                False,
                f"rejected: marginal ROI {roi:.3f} below {self.config.minimum_roi:.3f}",
                score=score,
                expected_gain=expected_gain,
                estimated_cost_value=cost_value,
            )

        return Decision(
            True,
            f"approved: marginal ROI {roi:.3f}",
            score=score,
            expected_gain=expected_gain,
            estimated_cost_value=cost_value,
        )

    def _cost_value(self, action: Action) -> float:
        cost = action.cost
        token_cost = cost.tokens / 1_000_000 * self.config.token_shadow_price_per_million_usd
        latency_cost = cost.latency_ms / 1_000 * self.config.latency_shadow_price_per_second_usd
        risk_cost = cost.risk * self.config.risk_shadow_price_usd
        return cost.usd + token_cost + latency_cost + risk_cost
