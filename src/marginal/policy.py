"""Deterministic marginal-value allocation policy."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .budget import BudgetLedger
from .canonical import canonical_hash
from .controls import DiminishingReturnDetector, DiminishingReturnSignal
from .estimator import EstimatorIdentity, ValueEstimate, ValueEstimator
from .models import Action, Decision


@dataclass(frozen=True, slots=True)
class PolicyIdentity:
    name: str
    version: str
    config_hash: str

    def __post_init__(self) -> None:
        for field_name in ("name", "version", "config_hash"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


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
            ("token_shadow_price_per_million_usd", self.token_shadow_price_per_million_usd),
            ("latency_shadow_price_per_second_usd", self.latency_shadow_price_per_second_usd),
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
        if any(float(value) < 0 for _, value in values[:-1]):
            raise ValueError("policy values must be non-negative")
        if not 0.0 <= self.minimum_expected_gain <= 1.0:
            raise ValueError("minimum_expected_gain must be between 0 and 1")
        if not 0.0 <= self.target_success_probability <= 1.0:
            raise ValueError("target_success_probability must be between 0 and 1")


class MarginalPolicy:
    """Authorize actions only when expected marginal value justifies total cost.

    State-aware diminishing-return control is opt-in. This preserves v0.2 behavior while
    allowing engine adapters to enable repetition control first in Shadow/Recommend mode and
    promote it to enforcement only after measured validation.
    """

    def __init__(
        self,
        config: PolicyConfig | None = None,
        estimator: ValueEstimator | None = None,
        *,
        name: str = "marginal-reference",
        version: str = "2.0.0",
        diminishing_detector: DiminishingReturnDetector | None = None,
    ) -> None:
        self.config = config or PolicyConfig()
        self.estimator = estimator or ValueEstimator()
        self.diminishing_detector = diminishing_detector
        if not isinstance(name, str):
            raise TypeError("name must be a string")
        if not name.strip():
            raise ValueError("name must not be empty")
        if not isinstance(version, str):
            raise TypeError("version must be a string")
        if not version.strip():
            raise ValueError("version must not be empty")
        self.identity = PolicyIdentity(
            name=name,
            version=version,
            config_hash=canonical_hash(asdict(self.config)),
        )
        self._executed_fingerprints: set[str] = set()

    def mark_executed(self, fingerprint: str) -> None:
        """Backward-compatible exact duplicate accounting."""

        if fingerprint:
            self._executed_fingerprints.add(fingerprint)

    def observe_execution(self, action: Action) -> None:
        """Record one successfully executed action for exact and semantic repetition control."""

        if action.fingerprint:
            self.mark_executed(action.fingerprint)
        if self.diminishing_detector is not None:
            self.diminishing_detector.observe(action)

    def diminishing_signal(self, action: Action) -> DiminishingReturnSignal | None:
        if self.diminishing_detector is None:
            return None
        return self.diminishing_detector.evaluate(action)

    def evaluate(self, action: Action, ledger: BudgetLedger) -> Decision:
        if action.current_success_probability >= self.config.target_success_probability:
            return self._decision(
                False,
                "rejected: target success probability already reached",
                "TARGET_REACHED",
            )
        if action.fingerprint and action.fingerprint in self._executed_fingerprints:
            return self._decision(False, "rejected: duplicate action", "DUPLICATE_ACTION")

        affordability = ledger.can_afford(action)
        if not affordability.allowed:
            return self._decision(
                False,
                f"rejected: {affordability.reason}",
                "BUDGET_REJECTED",
            )

        diminishing = self.diminishing_signal(action)
        if diminishing is not None and diminishing.should_stop:
            return self._decision(
                False,
                f"rejected: {diminishing.reason}",
                diminishing.reason_code,
            )

        estimate = self._estimate(action)
        gain_multiplier = diminishing.gain_multiplier if diminishing is not None else 1.0
        remaining_probability = max(
            0.0,
            self.config.target_success_probability - action.current_success_probability,
        )
        expected_gain = min(estimate.expected_gain * gain_multiplier, remaining_probability)
        if expected_gain < self.config.minimum_expected_gain:
            return self._decision(
                False,
                "rejected: expected gain below minimum",
                "EXPECTED_GAIN_REJECTED",
                expected_gain=expected_gain,
                estimate=estimate,
            )

        cost_value = self._cost_value(action)
        expected_value = expected_gain * self.config.outcome_value_usd
        score = expected_value - cost_value
        roi = float("inf") if cost_value == 0 else expected_value / cost_value
        if score < 0 or roi < self.config.minimum_roi:
            return self._decision(
                False,
                f"rejected: marginal ROI {roi:.3f} below {self.config.minimum_roi:.3f}",
                "MARGINAL_ROI_REJECTED",
                score=score,
                expected_gain=expected_gain,
                estimated_cost_value=cost_value,
                estimate=estimate,
            )
        return self._decision(
            True,
            f"approved: marginal ROI {roi:.3f}",
            "APPROVED",
            score=score,
            expected_gain=expected_gain,
            estimated_cost_value=cost_value,
            estimate=estimate,
        )

    @property
    def estimator_identity(self) -> EstimatorIdentity:
        identity = getattr(self.estimator, "identity", None)
        if isinstance(identity, EstimatorIdentity):
            return identity
        estimator_type = type(self.estimator)
        return EstimatorIdentity(
            name=f"{estimator_type.__module__}.{estimator_type.__qualname__}",
            version="unversioned",
            config_hash="unversioned",
        )

    def _estimate(self, action: Action) -> ValueEstimate:
        detailed = getattr(self.estimator, "estimate_detail", None)
        if callable(detailed):
            result = detailed(action)
            if not isinstance(result, ValueEstimate):
                raise TypeError("estimate_detail must return ValueEstimate")
            return result
        value = self.estimator.estimate(action)
        return ValueEstimate(
            expected_gain=value,
            uncertainty=0.0,
            confidence=0.0,
            sample_size=0,
            provenance="legacy-estimator",
            estimator=self.estimator_identity,
        )

    def _decision(
        self,
        allowed: bool,
        reason: str,
        reason_code: str,
        *,
        score: float = 0.0,
        expected_gain: float = 0.0,
        estimated_cost_value: float = 0.0,
        estimate: ValueEstimate | None = None,
    ) -> Decision:
        return Decision(
            allowed=allowed,
            reason=reason,
            score=score,
            expected_gain=expected_gain,
            estimated_cost_value=estimated_cost_value,
            recommended=allowed,
            recommendation_reason=reason,
            reason_code=reason_code,
            recommendation_reason_code=reason_code,
            uncertainty=estimate.uncertainty if estimate else 0.0,
            confidence=estimate.confidence if estimate else 0.0,
            estimator_name=estimate.estimator.name if estimate else self.estimator_identity.name,
            estimator_version=(
                estimate.estimator.version if estimate else self.estimator_identity.version
            ),
        )

    def _cost_value(self, action: Action) -> float:
        cost = action.cost
        token_cost = cost.tokens / 1_000_000 * self.config.token_shadow_price_per_million_usd
        latency_cost = cost.latency_ms / 1_000 * self.config.latency_shadow_price_per_second_usd
        risk_cost = cost.risk * self.config.risk_shadow_price_usd
        return cost.usd + token_cost + latency_cost + risk_cost
