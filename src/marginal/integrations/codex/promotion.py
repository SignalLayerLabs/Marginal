"""Evidence gate that earns and continuously validates Codex enforcement."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from marginal.governance_ledger import GovernanceLedger


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
    intervention_candidates: int = 0

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
            "intervention_candidates",
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
    evidence_root: str = ""
    ledger_records: int = 0

    def _hash_payload(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("receipt_hash", None)
        return payload

    def verify_hash(self) -> bool:
        return self.receipt_hash == _hash(self._hash_payload())

    def valid_for(self, identity: PromotionIdentity) -> bool:
        return (
            self.is_ready
            and self.verify_hash()
            and identity == self.identity
            and _valid_root_range(self.evidence_root, self.ledger_records)
        )

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
            "evidence_root": self.evidence_root,
            "ledger_records": self.ledger_records,
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
            evidence_root=str(payload.get("evidence_root", "")),
            ledger_records=int(payload.get("ledger_records", 0)),
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
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def evaluate_promotion(
    summary: CoverageSummary,
    criteria: PromotionCriteria,
    *,
    identity: PromotionIdentity,
    evidence_root: str | None = None,
    ledger_records: int = 0,
    ledger_path: str | Path | None = None,
) -> PromotionReceipt:
    """Create a self-verifying receipt for the conservative default evidence gate."""

    ratio = (
        summary.covered_actions / summary.coverable_actions if summary.coverable_actions else 0.0
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
    if summary.reviewed_candidates < summary.intervention_candidates:
        reasons.append("UNREVIEWED_CANDIDATES")
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
    if not _verified_root_range(evidence_root, ledger_records, ledger_path):
        reasons.append("EVIDENCE_ROOT_UNVERIFIED")

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
        evidence_root=evidence_root if isinstance(evidence_root, str) else "",
        ledger_records=ledger_records if isinstance(ledger_records, int) else 0,
    )
    return replace(provisional, receipt_hash=_hash(provisional._hash_payload()))


def _repositories_root(data_root: str | Path) -> Path:
    root = Path(data_root).resolve() / "repositories"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        root.chmod(0o700)
    return root


def _receipt_path(data_root: str | Path, repository_hash: str) -> Path:
    return _repositories_root(data_root) / f"{repository_hash}.receipt.json"


def _state_path(data_root: str | Path, repository_hash: str) -> Path:
    return _repositories_root(data_root) / f"{repository_hash}.json"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, serialized.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    if os.name == "posix":
        path.chmod(0o600)


def write_promotion_receipt(data_root: str | Path, receipt: PromotionReceipt) -> Path:
    if not receipt.verify_hash():
        raise ValueError("promotion receipt hash is invalid")
    path = _receipt_path(data_root, receipt.identity.repository_hash)
    _atomic_json(path, receipt.to_dict())
    return path


def read_promotion_receipt(
    data_root: str | Path,
    repository_hash: str,
) -> PromotionReceipt | None:
    path = _receipt_path(data_root, repository_hash)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("promotion receipt must be a JSON object")
    return PromotionReceipt.from_dict(payload)


def _valid_evidence_anchor(receipt: PromotionReceipt, ledger_path: str | Path | None) -> bool:
    return _verified_root_range(receipt.evidence_root, receipt.ledger_records, ledger_path)


def _verified_root_range(
    root: object,
    records: object,
    ledger_path: str | Path | None,
) -> bool:
    if not _valid_root_range(root, records) or ledger_path is None:
        return False
    assert isinstance(root, str)
    assert isinstance(records, int) and not isinstance(records, bool)
    report = GovernanceLedger(ledger_path).verify_prefix(records, expected_root=root)
    return report.valid and report.root_hash == root


def _valid_root_range(root: object, records: object) -> bool:
    return bool(
        isinstance(root, str)
        and len(root) == 64
        and all(character in "0123456789abcdef" for character in root)
        and not isinstance(records, bool)
        and isinstance(records, int)
        and records >= 1
    )


def activate_enforcement(
    data_root: str | Path,
    receipt: PromotionReceipt,
    *,
    ledger_path: str | Path | None = None,
) -> Path:
    if not receipt.is_ready or not receipt.verify_hash():
        raise ValueError("a ready, hash-valid receipt is required for enforcement")
    if not _valid_evidence_anchor(receipt, ledger_path):
        raise ValueError("a verified v3 evidence root is required for enforcement")
    stored = read_promotion_receipt(data_root, receipt.identity.repository_hash)
    if stored != receipt:
        raise ValueError("promotion receipt must be persisted before enforcement")
    path = _state_path(data_root, receipt.identity.repository_hash)
    _atomic_json(
        path,
        {
            "schema_version": 1,
            "mode": "enforce",
            "reason": "EARNED_ENFORCEMENT_PROMOTED",
            "receipt_hash": receipt.receipt_hash,
            "identity": asdict(receipt.identity),
            "evidence_root": receipt.evidence_root,
            "ledger_records": receipt.ledger_records,
        },
    )
    return path


def demote_enforcement(
    data_root: str | Path,
    *,
    repository_hash: str,
    reason: str,
) -> Path:
    path = _state_path(data_root, repository_hash)
    _atomic_json(
        path,
        {"schema_version": 1, "mode": "shadow", "reason": reason},
    )
    return path


def enforcement_is_active(
    data_root: str | Path,
    *,
    identity: PromotionIdentity,
    summary: CoverageSummary | None = None,
    ledger_path: str | Path | None = None,
) -> bool:
    state_path = _state_path(data_root, identity.repository_hash)
    if not state_path.exists():
        return False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("mode") != "enforce":
            return False
        receipt = read_promotion_receipt(data_root, identity.repository_hash)
        if (
            receipt is None
            or state.get("receipt_hash") != receipt.receipt_hash
            or not receipt.valid_for(identity)
            or not _valid_evidence_anchor(
                receipt,
                ledger_path
                or Path(data_root).resolve()
                / "evidence"
                / identity.repository_hash
                / "governance-v3.jsonl",
            )
        ):
            demote_enforcement(
                data_root,
                repository_hash=identity.repository_hash,
                reason="IDENTITY_DRIFT",
            )
            return False
        if summary is not None:
            coverage_ratio = (
                summary.covered_actions / summary.coverable_actions
                if summary.coverable_actions
                else 0.0
            )
            evidence_drift = (
                coverage_ratio < receipt.criteria.minimum_coverage_ratio
                or summary.false_stops > receipt.summary.false_stops
                or summary.integration_failures > 0
                or summary.unknown_enforceable_outcomes > 0
                or summary.reviewed_candidates < summary.intervention_candidates
                or _p95(summary.decision_latencies_ms) > receipt.criteria.maximum_p95_latency_ms
            )
            if evidence_drift:
                demote_enforcement(
                    data_root,
                    repository_hash=identity.repository_hash,
                    reason="EVIDENCE_DRIFT",
                )
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        demote_enforcement(
            data_root,
            repository_hash=identity.repository_hash,
            reason="RECEIPT_INVALID",
        )
        return False
