"""Contextual, explainable evidence evaluation for progressive authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from types import MappingProxyType

from .authority import AuthorityLevel, AuthorityTransitionReceipt, transition_receipt_hash
from .governance_ledger import LedgerVerificationReport

TRUST_SNAPSHOT_SCHEMA_VERSION = "1.0"
MIN_EVALUABLE_SAMPLES = 20
MIN_COVERAGE = 0.95
MAX_HARM_RATE = 0.05
MAX_MEAN_REGRET = 0.10
MAX_GOVERNANCE_TAX_RATIO = 0.10
DEMOTION_MIN_EVALUABLE_SAMPLES = 10
DEMOTION_MIN_COVERAGE = 0.90
DEMOTION_MAX_HARM_RATE = 0.10
DEMOTION_MAX_MEAN_REGRET = 0.20
DEMOTION_MAX_GOVERNANCE_TAX_RATIO = 0.20
INACTIVITY_WINDOW = timedelta(days=30)
CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)
RECOVERY_CLEAN_EVALUATIONS = 1

_CRITICAL_SHIFT_REASONS = frozenset(
    {"capability", "capability_drift", "integrity", "model", "policy"}
)
_SOFT_SHIFT_REASONS = frozenset({"large_repository", "repository", "task_class"})
_HEX = frozenset("0123456789abcdef")


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _non_negative_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _ratio(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number or None")
    result = float(value)
    if result < 0.0 or result != result or result in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _valid_root(value: str | None) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    _required_text(value, "last_observed_at")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("last_observed_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("last_observed_at must include an offset")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class TrustContext:
    """The identity boundaries within which evidence is valid."""

    repository: str
    agent: str
    model: str
    task_class: str
    policy_version: str

    def __post_init__(self) -> None:
        for name in ("repository", "agent", "model", "task_class", "policy_version"):
            _required_text(getattr(self, name), name)

    def payload(self) -> dict[str, str]:
        return {
            "repository": self.repository,
            "agent": self.agent,
            "model": self.model,
            "task_class": self.task_class,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True, slots=True)
class TrustEvidence:
    """Aggregated evidence with unavailable measurements explicitly represented by ``None``."""

    observed: int
    evaluable: int
    covered: int
    coverable: int
    beneficial: int
    neutral: int
    harmful: int
    indeterminate: int
    governance_tax_ratio: float | None
    mean_regret: float | None
    integrity_valid: bool
    last_observed_at: str | None
    evidence_ledger_root: str | None = None
    ledger_verification: LedgerVerificationReport | None = None

    def __post_init__(self) -> None:
        for name in (
            "observed",
            "evaluable",
            "covered",
            "coverable",
            "beneficial",
            "neutral",
            "harmful",
            "indeterminate",
        ):
            _non_negative_int(getattr(self, name), name)
        if self.evaluable > self.observed:
            raise ValueError("evaluable must not exceed observed")
        if self.covered > self.coverable:
            raise ValueError("covered must not exceed coverable")
        outcomes = self.beneficial + self.neutral + self.harmful + self.indeterminate
        if outcomes > self.evaluable:
            raise ValueError("outcomes must not exceed evaluable")
        object.__setattr__(
            self, "governance_tax_ratio", _ratio(self.governance_tax_ratio, "governance_tax_ratio")
        )
        object.__setattr__(self, "mean_regret", _ratio(self.mean_regret, "mean_regret"))
        if not isinstance(self.integrity_valid, bool):
            raise TypeError("integrity_valid must be a bool")
        _parse_timestamp(self.last_observed_at)
        if self.evidence_ledger_root is not None and not _valid_root(self.evidence_ledger_root):
            raise ValueError("evidence_ledger_root must be a lowercase SHA-256 digest or None")
        if self.ledger_verification is not None and not isinstance(
            self.ledger_verification, LedgerVerificationReport
        ):
            raise TypeError("ledger_verification must be LedgerVerificationReport or None")


@dataclass(frozen=True, slots=True)
class TrustSnapshot:
    """A schema-shaped, component-level explanation of one authority decision."""

    schema_version: str
    context: TrustContext
    components: Mapping[str, float | int | None]
    confidence_band: str
    eligible_authority: AuthorityLevel
    current_authority: AuthorityLevel
    authority: AuthorityLevel
    blockers: tuple[str, ...]
    transition_receipt: AuthorityTransitionReceipt | None

    def __post_init__(self) -> None:
        if self.schema_version != TRUST_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("unsupported trust snapshot schema version")
        if not isinstance(self.context, TrustContext):
            raise TypeError("context must be TrustContext")
        if not isinstance(self.components, Mapping):
            raise TypeError("components must be a mapping")
        normalized: dict[str, float | int | None] = {}
        for key, value in self.components.items():
            _required_text(key, "component key")
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise TypeError("component values must be numeric or None")
            normalized[key] = value
        object.__setattr__(self, "components", MappingProxyType(normalized))
        if self.confidence_band not in {"low", "medium", "high"}:
            raise ValueError("confidence_band must be low, medium, or high")
        for name in ("eligible_authority", "current_authority", "authority"):
            if not isinstance(getattr(self, name), AuthorityLevel):
                raise TypeError(f"{name} must be AuthorityLevel")
        if not isinstance(self.blockers, tuple) or not all(
            isinstance(item, str) and item for item in self.blockers
        ):
            raise TypeError("blockers must be a tuple of non-empty strings")
        if self.transition_receipt is not None and not isinstance(
            self.transition_receipt, AuthorityTransitionReceipt
        ):
            raise TypeError("transition_receipt must be AuthorityTransitionReceipt or None")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "context": self.context.payload(),
            "components": dict(self.components),
            "confidence_band": self.confidence_band,
            "eligible_authority": int(self.eligible_authority),
            "current_authority": int(self.current_authority),
            "authority": int(self.authority),
            "blockers": list(self.blockers),
            "transition_receipt": (
                None
                if self.transition_receipt is None
                else self.transition_receipt.payload()
                | {"receipt_hash": self.transition_receipt.receipt_hash}
            ),
        }


class TrustEngine:
    """Evaluate evidence with conservative promotion and asymmetric demotion rules."""

    def __init__(self, *, now: datetime | None = None) -> None:
        if now is not None and (now.tzinfo is None or now.utcoffset() is None):
            raise ValueError("now must include an offset")
        self._now = now.astimezone(timezone.utc) if now is not None else None
        self._recovery_remaining: dict[TrustContext, int] = {}

    def evaluate(
        self,
        context: TrustContext,
        evidence: TrustEvidence,
        current: AuthorityLevel,
        *,
        capabilities: int,
        shift_reasons: tuple[str, ...] = (),
    ) -> TrustSnapshot:
        """Produce the next authority with visible evidence components and blockers."""

        if not isinstance(context, TrustContext) or not isinstance(evidence, TrustEvidence):
            raise TypeError("context and evidence must use their trust models")
        if not isinstance(current, AuthorityLevel):
            raise TypeError("current must be AuthorityLevel")
        if isinstance(capabilities, bool) or not isinstance(capabilities, int):
            raise TypeError("capabilities must be an integer authority ceiling")
        if capabilities < int(AuthorityLevel.OBSERVE) or capabilities > int(
            AuthorityLevel.COMPUTE_GOVERN
        ):
            raise ValueError("capabilities must be between OBSERVE and COMPUTE_GOVERN")
        if not isinstance(shift_reasons, tuple) or not all(
            isinstance(reason, str) and reason for reason in shift_reasons
        ):
            raise TypeError("shift_reasons must be a tuple of non-empty strings")

        ceiling = AuthorityLevel(capabilities)
        now = self._now or datetime.now(timezone.utc)
        components, blockers = self._components(evidence, now)
        root_verified = self._root_is_verified(evidence)
        if not root_verified:
            blockers.append("unverified_evidence_ledger_root")
        reasons = frozenset(shift_reasons)
        critical = (
            not evidence.integrity_valid
            or current > ceiling
            or bool(reasons & _CRITICAL_SHIFT_REASONS)
        )
        soft_shift = bool(reasons & _SOFT_SHIFT_REASONS)
        if not evidence.integrity_valid:
            blockers.append("integrity_failure")
        if current > ceiling:
            blockers.append("capability_drift")
        if reasons & _CRITICAL_SHIFT_REASONS:
            blockers.append("identity_shift")
        if soft_shift:
            blockers.append("distribution_shift")

        promotion_ok = not blockers
        eligible = ceiling if promotion_ok else AuthorityLevel.OBSERVE
        demotion_required = self._requires_soft_demotion(evidence, now, soft_shift)
        if critical:
            authority = AuthorityLevel.OBSERVE
        elif demotion_required:
            authority = AuthorityLevel(max(int(AuthorityLevel.OBSERVE), int(current) - 1))
        elif promotion_ok:
            recovery_remaining = self._recovery_remaining.get(context, 0)
            if recovery_remaining:
                authority = current
                blockers.append("recovery_hysteresis")
                if recovery_remaining == 1:
                    del self._recovery_remaining[context]
                else:
                    self._recovery_remaining[context] = recovery_remaining - 1
            else:
                authority = AuthorityLevel(min(int(ceiling), int(current) + 1))
                if (
                    authority == ceiling
                    and current == ceiling
                    and ceiling < AuthorityLevel.COMPUTE_GOVERN
                ):
                    blockers.append("capability_ceiling")
        else:
            authority = current

        if critical:
            self._recovery_remaining.pop(context, None)
        elif authority < current:
            self._recovery_remaining[context] = RECOVERY_CLEAN_EVALUATIONS
        blockers = list(dict.fromkeys(blockers))
        receipt = self._receipt(
            context,
            current,
            authority,
            evidence.evidence_ledger_root,
            evidence.ledger_verification,
            blockers,
        )
        confidence_band = (
            "high"
            if promotion_ok and not soft_shift
            else "medium"
            if current >= authority
            else "low"
        )
        return TrustSnapshot(
            schema_version=TRUST_SNAPSHOT_SCHEMA_VERSION,
            context=context,
            components=components,
            confidence_band=confidence_band,
            eligible_authority=eligible,
            current_authority=current,
            authority=authority,
            blockers=tuple(blockers),
            transition_receipt=receipt,
        )

    @staticmethod
    def _components(
        evidence: TrustEvidence, now: datetime
    ) -> tuple[dict[str, float | int | None], list[str]]:
        coverage = evidence.covered / evidence.coverable if evidence.coverable else None
        harm_rate = evidence.harmful / evidence.evaluable if evidence.evaluable else None
        outcomes = (
            evidence.beneficial + evidence.neutral + evidence.harmful + evidence.indeterminate
        )
        observed_at = _parse_timestamp(evidence.last_observed_at)
        age_hours = None if observed_at is None else (now - observed_at).total_seconds() / 3600
        components: dict[str, float | int | None] = {
            "observed": evidence.observed,
            "evaluable": evidence.evaluable,
            "covered": evidence.covered,
            "coverable": evidence.coverable,
            "beneficial": evidence.beneficial,
            "neutral": evidence.neutral,
            "harmful": evidence.harmful,
            "indeterminate": evidence.indeterminate,
            "unclassified_outcomes": evidence.evaluable - outcomes,
            "coverage": coverage,
            "harm_rate": harm_rate,
            "mean_regret": evidence.mean_regret,
            "governance_tax_ratio": evidence.governance_tax_ratio,
            "evidence_age_hours": age_hours,
        }
        blockers: list[str] = []
        if evidence.evaluable < MIN_EVALUABLE_SAMPLES:
            blockers.append("minimum_evaluable_samples")
        if outcomes != evidence.evaluable:
            blockers.append("unclassified_outcomes")
        if coverage is None or coverage < MIN_COVERAGE:
            blockers.append("insufficient_coverage")
        if harm_rate is None or harm_rate > MAX_HARM_RATE:
            blockers.append("harm_rate_too_high")
        if evidence.mean_regret is None or evidence.mean_regret > MAX_MEAN_REGRET:
            blockers.append("mean_regret_too_high")
        if (
            evidence.governance_tax_ratio is None
            or evidence.governance_tax_ratio > MAX_GOVERNANCE_TAX_RATIO
        ):
            blockers.append("governance_tax_too_high")
        if observed_at is None or now - observed_at > INACTIVITY_WINDOW:
            blockers.append("inactivity")
        if observed_at is not None and observed_at - now > CLOCK_SKEW_TOLERANCE:
            blockers.append("future_observation")
        return components, blockers

    @staticmethod
    def _requires_soft_demotion(evidence: TrustEvidence, now: datetime, soft_shift: bool) -> bool:
        coverage = evidence.covered / evidence.coverable if evidence.coverable else None
        harm_rate = evidence.harmful / evidence.evaluable if evidence.evaluable else None
        outcomes = (
            evidence.beneficial + evidence.neutral + evidence.harmful + evidence.indeterminate
        )
        observed_at = _parse_timestamp(evidence.last_observed_at)
        return bool(
            soft_shift
            or evidence.evaluable < DEMOTION_MIN_EVALUABLE_SAMPLES
            or coverage is None
            or coverage < DEMOTION_MIN_COVERAGE
            or harm_rate is None
            or harm_rate > DEMOTION_MAX_HARM_RATE
            or evidence.mean_regret is None
            or evidence.mean_regret > DEMOTION_MAX_MEAN_REGRET
            or evidence.governance_tax_ratio is None
            or evidence.governance_tax_ratio > DEMOTION_MAX_GOVERNANCE_TAX_RATIO
            or outcomes != evidence.evaluable
            or observed_at is None
            or now - observed_at > INACTIVITY_WINDOW
            or observed_at - now > CLOCK_SKEW_TOLERANCE
        )

    @staticmethod
    def _root_is_verified(evidence: TrustEvidence) -> bool:
        report = evidence.ledger_verification
        return bool(
            _valid_root(evidence.evidence_ledger_root)
            and isinstance(report, LedgerVerificationReport)
            and report.valid
            and report.root_hash == evidence.evidence_ledger_root
        )

    @staticmethod
    def _receipt(
        context: TrustContext,
        previous: AuthorityLevel,
        current: AuthorityLevel,
        root: str | None,
        verification: LedgerVerificationReport | None,
        blockers: list[str],
    ) -> AuthorityTransitionReceipt | None:
        if (
            previous == current
            or not _valid_root(root)
            or not isinstance(verification, LedgerVerificationReport)
            or not verification.valid
            or verification.root_hash != root
        ):
            return None
        assert root is not None
        unsigned = AuthorityTransitionReceipt(
            schema_version="1.0",
            context=context.payload(),
            previous=previous,
            current=current,
            evidence_ledger_root=root,
            ledger_verification=verification,
            blockers=tuple(blockers),
            receipt_hash="",
        )
        return replace(unsigned, receipt_hash=transition_receipt_hash(unsigned))
