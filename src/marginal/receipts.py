"""Immutable, hash-bound governance decision receipts."""

from __future__ import annotations

import hmac
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from .canonical import canonical_hash
from .reason_codes import REASON_CODE_VERSION, ReasonCode

RECEIPT_SCHEMA_VERSION = "1.0"
PROGRESS_EVIDENCE_SCHEMA_VERSION = "1.0"

_PRIVATE_PAYLOAD_TERMS = frozenset(
    {
        "auth",
        "authorization",
        "command",
        "commands",
        "credential",
        "credentials",
        "output",
        "outputs",
        "prompt",
        "prompts",
        "raw",
        "response",
        "responses",
        "secret",
        "secrets",
        "source",
        "sources",
        "transcript",
        "transcripts",
    }
)
_SHA256_HEX_LENGTH = 64
_LOWER_HEX_DIGITS = frozenset("0123456789abcdef")


class ProgressLevel(str, Enum):
    """The strongest kind of evidence observed for a unit of work."""

    ACTIVITY = "activity"
    INFORMATION = "information"
    PROGRESS = "progress"
    VERIFIED_PROGRESS = "verified_progress"


def _validate_confidence(value: float, name: str = "confidence") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{name} must be a finite value between 0 and 1")
    return normalized


def _validate_non_negative_number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return normalized


def _validate_non_negative_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _private_key(key: str) -> bool:
    camel_separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    terms = (term for term in re.split(r"[^a-z0-9]+", camel_separated.casefold()) if term)
    return any(term in _PRIVATE_PAYLOAD_TERMS for term in terms)


def _valid_sha256_digest(value: str) -> bool:
    return len(value) == _SHA256_HEX_LENGTH and all(
        character in _LOWER_HEX_DIGITS for character in value
    )


def _freeze_json_value(value: Any, name: str) -> Any:
    """Validate JSON-only evidence values without relying on ``repr`` coercion."""

    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{name} must not contain non-finite numbers")
        return value
    if isinstance(value, list):
        return tuple(_freeze_json_value(item, name) for item in value)
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{name} mapping keys must be strings")
            if _private_key(key):
                raise ValueError(f"{name} must not contain raw private payload field {key!r}")
            frozen[key] = _freeze_json_value(item, name)
        return MappingProxyType(frozen)
    raise TypeError(f"{name} must contain only canonical JSON values")


def _freeze_mapping(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    frozen = _freeze_json_value(value, name)
    assert isinstance(frozen, Mapping)
    return frozen


def _json_value(value: Any) -> Any:
    """Convert frozen attestation data back to ordinary JSON-compatible containers."""

    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class ProgressEvidence:
    """Derived evidence that keeps activity and verified progress distinct."""

    schema_version: str
    level: ProgressLevel
    state_hash: str
    evidence_hash: str
    confidence: float
    verifier: str | None

    def __post_init__(self) -> None:
        if self.schema_version != PROGRESS_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported progress evidence schema version")
        if not isinstance(self.level, ProgressLevel):
            raise TypeError("level must be ProgressLevel")
        _required_text(self.state_hash, "state_hash")
        _required_text(self.evidence_hash, "evidence_hash")
        object.__setattr__(self, "confidence", _validate_confidence(self.confidence))
        if self.verifier is not None:
            _required_text(self.verifier, "verifier")

    def payload(self) -> dict[str, object]:
        """Return the schema-shaped, privacy-safe progress payload."""

        return {
            "schema_version": self.schema_version,
            "level": self.level.value,
            "state_hash": self.state_hash,
            "evidence_hash": self.evidence_hash,
            "confidence": self.confidence,
            "verifier": self.verifier,
        }


@dataclass(frozen=True, slots=True)
class GovernanceCost:
    """Measured governance overhead, with ``None`` reserved for unavailable measurements."""

    wall_clock_ms: float
    cpu_ms: float | None
    memory_peak_bytes: int | None
    storage_bytes: int
    tokens: int
    model_calls: int
    additional_tool_calls: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "wall_clock_ms",
            _validate_non_negative_number(self.wall_clock_ms, "wall_clock_ms"),
        )
        if self.cpu_ms is not None:
            object.__setattr__(self, "cpu_ms", _validate_non_negative_number(self.cpu_ms, "cpu_ms"))
        if self.memory_peak_bytes is not None:
            _validate_non_negative_int(self.memory_peak_bytes, "memory_peak_bytes")
        for name in ("storage_bytes", "tokens", "model_calls", "additional_tool_calls"):
            _validate_non_negative_int(getattr(self, name), name)

    def payload(self) -> dict[str, float | int | None]:
        """Return explicit measurements suitable for a receipt payload."""

        return {
            "wall_clock_ms": self.wall_clock_ms,
            "cpu_ms": self.cpu_ms,
            "memory_peak_bytes": self.memory_peak_bytes,
            "storage_bytes": self.storage_bytes,
            "tokens": self.tokens,
            "model_calls": self.model_calls,
            "additional_tool_calls": self.additional_tool_calls,
        }


@dataclass(frozen=True, slots=True)
class DecisionReceipt:
    """A canonical, immutable attestation of one governance decision."""

    schema_version: str
    decision_id: str
    timestamp: str
    context: Mapping[str, str]
    decision: str
    reason_code: str
    state_hash: str | None
    evidence_hash: str | None
    trajectory_hash: str | None
    policy_hash: str
    decision_hash: str
    confidence: float
    expected_utility: Mapping[str, Any] | None
    estimated_cost: Mapping[str, Any] | None
    enforcement_level: str
    trust_snapshot: Mapping[str, Any]
    governance_cost: GovernanceCost

    def __post_init__(self) -> None:
        if self.schema_version != RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported decision receipt schema version")
        for name in (
            "decision_id",
            "timestamp",
            "decision",
            "reason_code",
            "policy_hash",
            "enforcement_level",
        ):
            _required_text(getattr(self, name), name)
        if self.reason_code not in {code.value for code in ReasonCode}:
            raise ValueError(f"unsupported reason_code for registry version {REASON_CODE_VERSION}")
        if not isinstance(self.decision_hash, str):
            raise TypeError("decision_hash must be a string")
        for name in ("state_hash", "evidence_hash", "trajectory_hash"):
            value = getattr(self, name)
            if value is not None:
                _required_text(value, name)
        if not isinstance(self.context, Mapping):
            raise TypeError("context must be a mapping")
        for key, value in self.context.items():
            _required_text(key, "context key")
            if _private_key(key):
                raise ValueError(f"context must not contain raw private payload field {key!r}")
            _required_text(value, f"context[{key!r}]")
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))
        object.__setattr__(self, "confidence", _validate_confidence(self.confidence))
        for name in ("expected_utility", "estimated_cost", "trust_snapshot"):
            value = getattr(self, name)
            if value is None:
                if name == "trust_snapshot":
                    raise TypeError("trust_snapshot must be a mapping")
                continue
            object.__setattr__(self, name, _freeze_mapping(value, name))
        if not isinstance(self.governance_cost, GovernanceCost):
            raise TypeError("governance_cost must be GovernanceCost")


def canonical_decision_payload(receipt: DecisionReceipt) -> dict[str, Any]:
    """Return the exact receipt fields committed by ``decision_hash``."""

    if not isinstance(receipt, DecisionReceipt):
        raise TypeError("receipt must be DecisionReceipt")
    return {
        "schema_version": receipt.schema_version,
        "decision_id": receipt.decision_id,
        "timestamp": receipt.timestamp,
        "context": _json_value(receipt.context),
        "decision": receipt.decision,
        "reason_code": receipt.reason_code,
        "state_hash": receipt.state_hash,
        "evidence_hash": receipt.evidence_hash,
        "trajectory_hash": receipt.trajectory_hash,
        "policy_hash": receipt.policy_hash,
        "confidence": receipt.confidence,
        "expected_utility": _json_value(receipt.expected_utility),
        "estimated_cost": _json_value(receipt.estimated_cost),
        "enforcement_level": receipt.enforcement_level,
        "trust_snapshot": _json_value(receipt.trust_snapshot),
        "governance_cost": receipt.governance_cost.payload(),
    }


def decision_receipt_hash(receipt: DecisionReceipt) -> str:
    """Hash the canonical payload without accepting arbitrary object representations."""

    return canonical_hash(canonical_decision_payload(receipt))


def receipt_payload(receipt: DecisionReceipt) -> dict[str, Any]:
    """Return the complete, schema-shaped receipt including its binding hash."""

    payload = canonical_decision_payload(receipt)
    payload["decision_hash"] = receipt.decision_hash
    return payload


def verify_decision_receipt(receipt: DecisionReceipt) -> bool:
    """Return whether a receipt's current canonical payload matches its decision hash."""

    if not isinstance(receipt, DecisionReceipt) or not _valid_sha256_digest(receipt.decision_hash):
        return False
    return hmac.compare_digest(receipt.decision_hash, decision_receipt_hash(receipt))
