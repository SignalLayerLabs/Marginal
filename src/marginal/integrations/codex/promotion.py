"""Evidence gate that earns and continuously validates Codex enforcement."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class PromotionIdentity:
    repository_hash: str
    codex_version: str
    plugin_version: str
    adapter_version: str
    policy_hash: str
    hook_hash: str


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    covered_actions: int
    coverable_actions: int
    completed_sessions: int
    reviewed_candidates: int
    false_stops: int
    integration_failures: int
    pending_actions: int
    unknown_enforceable_outcomes: int
    decision_latencies_ms: tuple[float, ...]
    enforceable_outcomes_observable: bool

    def __post_init__(self) -> None:
        for name in (
            "covered_actions",
            "coverable_actions",
            "completed_sessions",
            "reviewed_candidates",
            "false_stops",
            "integration_failures",
            "pending_actions",
            "unknown_enforceable_outcomes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        normalized: list[float] = []
        for value in self.decision_latencies_ms:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError("decision latency must be numeric")
            measured = float(value)
            if not math.isfinite(measured) or measured < 0:
                raise ValueError("decision latency must be finite and non-negative")
            normalized.append(measured)
        object.__setattr__(self, "decision_latencies_ms", tuple(normalized))


@dataclass(frozen=True, slots=True)
class PromotionCriteria:
    minimum_actions: int = 100
    minimum_sessions: int = 5
    minimum_coverage_ratio: float = 0.99
    minimum_reviewed_candidates: int = 5
    maximum_false_stops: int = 0
    maximum_p95_latency_ms: float = 75.0


@dataclass(frozen=True, slots=True)
class PromotionReceipt:
    schema_version: int
    identity: PromotionIdentity
    criteria: PromotionCriteria
    summary: CoverageSummary
    coverage_ratio: float
    p95_latency_ms: float
    blocking_reasons: tuple[str, ...]
    is_ready: bool
    receipt_hash: str

    def _hash_payload(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("receipt_hash", None)
        return payload

    def verify_hash(self) -> bool:
        return self.receipt_hash == _hash(self._hash_payload())

    def valid_for(self, identity: PromotionIdentity) -> bool:
        return self.is_ready and self.verify_hash() and identity == self.identity

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "identity": asdict(self.identity),
            "criteria": asdict(self.criteria),
            "summary": asdict(self.summary),
            "coverage_ratio": self.coverage_ratio,
            "p95_latency_ms": self.p95_latency_ms,
            "blocking_reasons": list(self.blocking_reasons),
            "is_ready": self.is_ready,
            "receipt_hash": self.receipt_hash,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PromotionReceipt:
        summary_data = dict(payload["summary"])
        summary_data["decision_latencies_ms"] = tuple(summary_data["decision_latencies_ms"])
        return cls(
            schema_version=int(payload["schema_version"]),
            identity=PromotionIdentity(**payload["identity"]),
            criteria=PromotionCriteria(**payload["criteria"]),
            summary=CoverageSummary(**summary_data),
            coverage_ratio=float(payload["coverage_ratio"]),
            p95_latency_ms=float(payload["p95_latency_ms"]),
            blocking_reasons=tuple(payload["blocking_reasons"]),
            is_ready=bool(payload["is_ready"]),
            receipt_hash=str(payload["receipt_hash"]),
        )


def _hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _p95(values: tuple[float, ...]) -> float:
    if not values:
        return math.inf
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def evaluate_promotion(
    summary: CoverageSummary,
    criteria: PromotionCriteria,
    *,
    identity: PromotionIdentity,
) -> PromotionReceipt:
    """Create a self-verifying receipt for the conservative default evidence gate."""

    ratio = (
        summary.covered_actions / summary.coverable_actions
        if summary.coverable_actions
        else 0.0
    )
    latency = _p95(summary.decision_latencies_ms)
    reasons: list[str] = []
    if summary.covered_actions < criteria.minimum_actions:
        reasons.append("MINIMUM_ACTIONS")
    if summary.completed_sessions < criteria.minimum_sessions:
        reasons.append("MINIMUM_SESSIONS")
    if ratio < criteria.minimum_coverage_ratio:
        reasons.append("COVERAGE")
    if summary.reviewed_candidates < criteria.minimum_reviewed_candidates:
        reasons.append("MINIMUM_REVIEWS")
    if summary.false_stops > criteria.maximum_false_stops:
        reasons.append("FALSE_STOPS")
    if summary.integration_failures:
        reasons.append("INTEGRATION_FAILURES")
    if summary.pending_actions:
        reasons.append("PENDING_ACTIONS")
    if latency > criteria.maximum_p95_latency_ms:
        reasons.append("LATENCY")
    if not summary.enforceable_outcomes_observable:
        reasons.append("OUTCOME_UNOBSERVABLE")
    if summary.unknown_enforceable_outcomes:
        reasons.append("UNKNOWN_ENFORCEABLE_OUTCOMES")

    provisional = PromotionReceipt(
        schema_version=1,
        identity=identity,
        criteria=criteria,
        summary=summary,
        coverage_ratio=ratio,
        p95_latency_ms=latency,
        blocking_reasons=tuple(reasons),
        is_ready=not reasons,
        receipt_hash="",
    )
    return replace(provisional, receipt_hash=_hash(provisional._hash_payload()))
