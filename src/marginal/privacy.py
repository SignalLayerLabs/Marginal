"""Privacy controls for MARGINAL decision evidence and telemetry exports."""

from __future__ import annotations

import copy
import errno
import hashlib
import hmac
import math
import os
import re
import secrets
import stat
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol


class PrivacyProfile(str, Enum):
    """Privacy posture applied to operational ledgers or exported evidence."""

    LOCAL_FULL = "local_full"
    SAFE_TELEMETRY = "safe_telemetry"
    AGGREGATE_EXPORT = "aggregate_export"

    @classmethod
    def parse(cls, value: PrivacyProfile | str) -> PrivacyProfile:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError("privacy profile must be a string or PrivacyProfile")
        normalized = value.strip().lower().replace("-", "_")
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"unknown privacy profile: {value}") from exc


class PrivacyClass(str, Enum):
    """Classification assigned to fields before they are persisted or exported."""

    SAFE_BY_DEFAULT = "safe_by_default"
    PSEUDONYMOUS = "pseudonymous"
    POTENTIALLY_SENSITIVE = "potentially_sensitive"


FIELD_CLASSIFICATION: Mapping[str, PrivacyClass] = MappingProxyType(
    {
        "schema_version": PrivacyClass.SAFE_BY_DEFAULT,
        "privacy_profile": PrivacyClass.SAFE_BY_DEFAULT,
        "event": PrivacyClass.SAFE_BY_DEFAULT,
        "sequence": PrivacyClass.SAFE_BY_DEFAULT,
        "engine": PrivacyClass.SAFE_BY_DEFAULT,
        "mode": PrivacyClass.SAFE_BY_DEFAULT,
        "action.kind": PrivacyClass.SAFE_BY_DEFAULT,
        "action.cost": PrivacyClass.SAFE_BY_DEFAULT,
        "action.estimated_cost": PrivacyClass.SAFE_BY_DEFAULT,
        "action.token_usage": PrivacyClass.SAFE_BY_DEFAULT,
        "action.expected_gain": PrivacyClass.SAFE_BY_DEFAULT,
        "action.current_success_probability": PrivacyClass.SAFE_BY_DEFAULT,
        "action.is_verification": PrivacyClass.SAFE_BY_DEFAULT,
        "action.retry_number": PrivacyClass.SAFE_BY_DEFAULT,
        "action.deduplication_scope": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.allowed": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.recommended": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.reason_code": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.recommendation_reason_code": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.confidence": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.uncertainty": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.score": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.expected_gain": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.estimated_cost_value": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.mode": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.directive": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.recommended_directive": PrivacyClass.SAFE_BY_DEFAULT,
        "decision.estimator_version": PrivacyClass.SAFE_BY_DEFAULT,
        "usage": PrivacyClass.SAFE_BY_DEFAULT,
        "reserved": PrivacyClass.SAFE_BY_DEFAULT,
        "budget_overrun": PrivacyClass.SAFE_BY_DEFAULT,
        "realized_gain": PrivacyClass.SAFE_BY_DEFAULT,
        "outcome.reward": PrivacyClass.SAFE_BY_DEFAULT,
        "outcome.resolved": PrivacyClass.SAFE_BY_DEFAULT,
        "policy.version": PrivacyClass.SAFE_BY_DEFAULT,
        "estimator.version": PrivacyClass.SAFE_BY_DEFAULT,
        "event_id": PrivacyClass.PSEUDONYMOUS,
        "run_id": PrivacyClass.PSEUDONYMOUS,
        "task_id": PrivacyClass.PSEUDONYMOUS,
        "trajectory_id": PrivacyClass.PSEUDONYMOUS,
        "action_id": PrivacyClass.PSEUDONYMOUS,
        "action.fingerprint": PrivacyClass.PSEUDONYMOUS,
        "action.action_id": PrivacyClass.PSEUDONYMOUS,
        "action.state_hash": PrivacyClass.PSEUDONYMOUS,
        "outcome.task_id": PrivacyClass.PSEUDONYMOUS,
        "outcome.trajectory_id": PrivacyClass.PSEUDONYMOUS,
        "engine_instance": PrivacyClass.PSEUDONYMOUS,
        "timestamp": PrivacyClass.PSEUDONYMOUS,
        "action.name": PrivacyClass.POTENTIALLY_SENSITIVE,
        "action.metadata": PrivacyClass.POTENTIALLY_SENSITIVE,
        "action.tags": PrivacyClass.POTENTIALLY_SENSITIVE,
        "action.tool_arguments": PrivacyClass.POTENTIALLY_SENSITIVE,
        "model": PrivacyClass.POTENTIALLY_SENSITIVE,
        "metadata": PrivacyClass.POTENTIALLY_SENSITIVE,
        "tags": PrivacyClass.POTENTIALLY_SENSITIVE,
        "reason": PrivacyClass.POTENTIALLY_SENSITIVE,
        "error": PrivacyClass.POTENTIALLY_SENSITIVE,
        "exception": PrivacyClass.POTENTIALLY_SENSITIVE,
        "outcome.verifier": PrivacyClass.POTENTIALLY_SENSITIVE,
        "outcome.evidence": PrivacyClass.POTENTIALLY_SENSITIVE,
        "outcome.metrics": PrivacyClass.POTENTIALLY_SENSITIVE,
        "policy.name": PrivacyClass.POTENTIALLY_SENSITIVE,
        "policy.config_hash": PrivacyClass.POTENTIALLY_SENSITIVE,
        "estimator.name": PrivacyClass.POTENTIALLY_SENSITIVE,
        "estimator.config_hash": PrivacyClass.POTENTIALLY_SENSITIVE,
        "estimator.training_data_fingerprint": PrivacyClass.POTENTIALLY_SENSITIVE,
        "treasury": PrivacyClass.POTENTIALLY_SENSITIVE,
        "tool_arguments": PrivacyClass.POTENTIALLY_SENSITIVE,
    }
)


_KNOWN_ACTION_KINDS = frozenset(
    {
        "command",
        "file_read",
        "file_write",
        "generation",
        "llm",
        "model_call",
        "reasoning",
        "research",
        "review",
        "search",
        "subagent",
        "test",
        "tool",
        "verification",
    }
)

_KNOWN_REASON_CODES = frozenset(
    {
        "APPROVED",
        "BUDGET_REJECTED",
        "DENY",
        "DUPLICATE_ACTION",
        "DUPLICATE_PENDING",
        "EXPECTED_GAIN_REJECTED",
        "FUNDED",
        "MARGINAL_ROI_REJECTED",
        "PARENT_BUDGET_REJECTED",
        "RECOMMEND_OVERRIDE",
        "SHADOW_OVERRIDE",
        "TARGET_REACHED",
        "UNSPECIFIED",
    }
)


def classify_field(field_path: str) -> PrivacyClass:
    """Classify a dotted field path, defaulting unknown fields to sensitive."""

    if not isinstance(field_path, str):
        raise TypeError("field_path must be a string")
    normalized = field_path.strip()
    if not normalized:
        raise ValueError("field_path must not be empty")
    candidates = [normalized]
    candidate_prefix = "candidates[]."
    if normalized.startswith(candidate_prefix):
        candidates.append(normalized[len(candidate_prefix) :])
    for candidate in candidates:
        current = candidate
        while current:
            classification = FIELD_CLASSIFICATION.get(current)
            if classification is not None:
                return classification
            if "." not in current:
                break
            current = current.rsplit(".", 1)[0]
    return PrivacyClass.POTENTIALLY_SENSITIVE


@dataclass(frozen=True, slots=True)
class PrivacyConfig:
    """Validated configuration for privacy-aware ledger persistence or export."""

    profile: PrivacyProfile | str = PrivacyProfile.LOCAL_FULL
    key: bytes | None = field(default=None, repr=False)
    key_path: str | Path | None = None

    def __post_init__(self) -> None:
        profile = PrivacyProfile.parse(self.profile)
        object.__setattr__(self, "profile", profile)
        if self.key is not None:
            _validate_key(self.key)
        if self.key_path is not None:
            object.__setattr__(self, "key_path", Path(self.key_path))
        if self.key is not None and self.key_path is not None:
            raise ValueError("provide privacy key or privacy key path, not both")
        if profile is PrivacyProfile.AGGREGATE_EXPORT and (
            self.key is not None or self.key_path is not None
        ):
            raise ValueError("aggregate_export does not use a pseudonymization key")


class _Pseudonymizer(Protocol):
    def pseudonymize(self, field_name: str, value: str) -> str: ...


class LocalPseudonymizer:
    """Create stable, field-separated pseudonyms with a caller-controlled local key."""

    _DOMAIN = b"marginal-privacy-v1\x00"

    def __init__(self, key: bytes) -> None:
        self._key = _validate_key(key)

    def pseudonymize(self, field_name: str, value: str) -> str:
        if not isinstance(field_name, str) or not field_name.strip():
            raise ValueError("field_name must not be empty")
        if not isinstance(value, str):
            raise TypeError("pseudonymized values must be strings")
        if not value:
            return ""
        payload = self._DOMAIN + field_name.encode("utf-8") + b"\x00" + value.encode("utf-8")
        digest = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return f"psn_{digest[:32]}"


def generate_local_identifier(namespace: str = "id") -> str:
    """Return a random local identifier that carries no caller-provided meaning."""

    if not isinstance(namespace, str):
        raise TypeError("namespace must be a string")
    normalized = namespace.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", normalized):
        raise ValueError("namespace must be a simple lowercase identifier")
    return f"{normalized}_{secrets.token_urlsafe(18)}"


def load_or_create_privacy_key(path: str | Path) -> bytes:
    """Load a local 256-bit key or atomically create one with owner-only permissions."""

    key_path = Path(path)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.is_symlink():
        raise ValueError("privacy key path must not be a symbolic link")
    if key_path.exists():
        return _read_existing_key(key_path)

    key = secrets.token_bytes(32)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(key_path, flags, 0o600)
    except FileExistsError:
        return _read_existing_key(key_path)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(key)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        key_path.unlink(missing_ok=True)
        raise
    return key


def sanitize_ledger_record(
    record: Mapping[str, Any],
    *,
    profile: PrivacyProfile | str,
    pseudonymizer: _Pseudonymizer | None = None,
) -> dict[str, Any]:
    """Apply a privacy profile to one JSON-compatible Decision Ledger record."""

    if not isinstance(record, Mapping):
        raise TypeError("ledger record must be a mapping")
    selected = PrivacyProfile.parse(profile)
    if selected is PrivacyProfile.LOCAL_FULL:
        return copy.deepcopy(dict(record))
    if selected is PrivacyProfile.AGGREGATE_EXPORT:
        raise ValueError("aggregate_export requires aggregate_ledger_records")
    if pseudonymizer is None:
        raise ValueError("safe_telemetry requires a pseudonymizer")

    sanitized: dict[str, Any] = {
        "schema_version": "2.0",
        "privacy_profile": PrivacyProfile.SAFE_TELEMETRY.value,
    }
    sequence = record.get("sequence")
    if not isinstance(sequence, bool) and isinstance(sequence, int):
        sanitized["sequence"] = sequence
    event = record.get("event")
    if isinstance(event, str):
        sanitized["event"] = _generalize_event(event)
    mode = record.get("mode")
    if isinstance(mode, str):
        sanitized["mode"] = _generalize_mode(mode)
    budget_overrun = record.get("budget_overrun")
    if isinstance(budget_overrun, bool):
        sanitized["budget_overrun"] = budget_overrun
    realized_gain = record.get("realized_gain")
    realized_gain_value = _finite_float(realized_gain)
    if realized_gain_value is not None and 0.0 <= realized_gain_value <= 1.0:
        sanitized["realized_gain"] = realized_gain_value

    for name in (
        "event_id",
        "run_id",
        "task_id",
        "trajectory_id",
        "action_id",
        "engine_instance",
    ):
        value = record.get(name)
        if isinstance(value, str):
            sanitized[name] = pseudonymizer.pseudonymize(name, value)

    timestamp = record.get("timestamp")
    if isinstance(timestamp, str) and timestamp:
        sanitized["timestamp"] = _generalize_timestamp(timestamp)

    engine = record.get("engine")
    if isinstance(engine, str):
        sanitized["engine"] = _generalize_engine(engine)

    policy = record.get("policy")
    if isinstance(policy, Mapping):
        sanitized["policy"] = _sanitize_identity(policy)
    estimator = record.get("estimator")
    if isinstance(estimator, Mapping):
        sanitized["estimator"] = _sanitize_identity(estimator)

    action = record.get("action")
    if isinstance(action, Mapping):
        sanitized["action"] = _sanitize_action(action, pseudonymizer)
    decision = record.get("decision")
    if isinstance(decision, Mapping):
        sanitized["decision"] = _sanitize_decision(decision)
    outcome = record.get("outcome")
    if isinstance(outcome, Mapping):
        sanitized["outcome"] = _sanitize_outcome(outcome, pseudonymizer)

    candidates = record.get("candidates")
    if isinstance(candidates, list):
        sanitized["candidates"] = _sanitize_candidates(candidates, pseudonymizer)

    for name in ("usage", "reserved"):
        value = record.get(name)
        if isinstance(value, Mapping):
            sanitized[name] = _sanitize_numeric_mapping(value)
    return sanitized


class _ExistingPseudonymValidator:
    """Validate already-pseudonymized identifiers without changing correlation."""

    _PATTERN = re.compile(r"^psn_[0-9a-f]{32}$")

    def pseudonymize(self, field_name: str, value: str) -> str:
        del field_name
        if not isinstance(value, str):
            raise TypeError("safe telemetry pseudonyms must be strings")
        if value and self._PATTERN.fullmatch(value) is None:
            raise ValueError("safe telemetry contains an invalid pseudonym")
        return value


def validate_safe_telemetry_record(record: Mapping[str, Any]) -> None:
    """Validate that a record is the canonical output of the strict privacy profile."""

    if not isinstance(record, Mapping):
        raise TypeError("safe telemetry record must be a mapping")
    try:
        canonical = sanitize_ledger_record(
            record,
            profile=PrivacyProfile.SAFE_TELEMETRY,
            pseudonymizer=_ExistingPseudonymValidator(),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid safe telemetry record: {exc}") from exc
    if canonical != dict(record):
        raise ValueError(
            "invalid safe telemetry record: unreviewed, noncanonical, or sensitive fields"
        )


def aggregate_ledger_records(
    records: Iterable[Mapping[str, Any]],
    *,
    minimum_group_size: int = 5,
) -> list[dict[str, Any]]:
    """Group generalized rows and suppress groups smaller than the privacy threshold."""

    if isinstance(minimum_group_size, bool) or not isinstance(minimum_group_size, int):
        raise TypeError("minimum_group_size must be an integer")
    if minimum_group_size < 1:
        raise ValueError("minimum_group_size must be at least 1")

    counter: Counter[tuple[str, str, str, str, str, str, str, str]] = Counter()
    for record in records:
        if not isinstance(record, Mapping):
            raise TypeError("aggregate source records must be mappings")
        event = record.get("event")
        if event == "authorization":
            action = record.get("action", {})
            decision = record.get("decision", {})
            if not isinstance(action, Mapping) or not isinstance(decision, Mapping):
                continue
            key = (
                "decision",
                _generalize_action_kind(action.get("kind")),
                _cost_bucket(action.get("cost")),
                _gain_bucket(decision.get("expected_gain")),
                _boolean_decision(decision.get("recommended")),
                _boolean_decision(decision.get("allowed")),
                _safe_reason_code(decision.get("reason_code")),
                "not_applicable",
            )
            counter[key] += 1
        elif event == "outcome":
            outcome = record.get("outcome", {})
            if not isinstance(outcome, Mapping):
                continue
            key = (
                "outcome",
                "unknown",
                "unknown",
                "unknown",
                "not_applicable",
                "not_applicable",
                "not_applicable",
                _outcome_class(outcome),
            )
            counter[key] += 1

    order = {"decision": 0, "outcome": 1}
    rows: list[dict[str, Any]] = []
    for key, count in sorted(counter.items(), key=lambda item: (order[item[0][0]], item[0])):
        if count < minimum_group_size:
            continue
        (
            record_type,
            action_kind,
            cost_bucket,
            gain_bucket,
            recommendation,
            applied_decision,
            reason_code,
            outcome_class,
        ) = key
        rows.append(
            {
                "schema_version": "1.0",
                "privacy_profile": PrivacyProfile.AGGREGATE_EXPORT.value,
                "record_type": record_type,
                "action_kind": action_kind,
                "cost_bucket": cost_bucket,
                "gain_bucket": gain_bucket,
                "recommendation": recommendation,
                "applied_decision": applied_decision,
                "reason_code": reason_code,
                "outcome_class": outcome_class,
                "count": count,
                "minimum_group_size": minimum_group_size,
            }
        )
    return rows


def _validate_key(key: bytes) -> bytes:
    if not isinstance(key, bytes):
        raise TypeError("privacy key must be bytes")
    if len(key) < 32:
        raise ValueError("privacy key must contain at least 32 bytes")
    return key


def _read_existing_key(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError("privacy key path must not be a symbolic link") from exc
        raise
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("privacy key path must be a regular file")
        if os.name != "nt" and details.st_mode & 0o077:
            raise PermissionError("privacy key file must not be accessible by group or others")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            material = stream.read()
    finally:
        os.close(descriptor)
    return _validate_key(material)


def _generalize_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("ledger timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    day = parsed.astimezone(timezone.utc).date()
    return f"{day.isoformat()}T00:00:00+00:00"


def _generalize_engine(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    known = {
        "aider",
        "claude-code",
        "cline",
        "codex",
        "continue",
        "gemini-cli",
        "github-copilot",
        "opencode",
        "roo-code",
    }
    return normalized if normalized in known else "other"


def _sanitize_identity(payload: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    version = payload.get("version")
    if isinstance(version, str):
        result["version"] = _safe_version(version)
    return result


def _sanitize_action(payload: Mapping[str, Any], pseudonymizer: _Pseudonymizer) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "kind" in payload:
        result["kind"] = _generalize_action_kind(payload.get("kind"))
    for name in ("expected_gain", "current_success_probability"):
        value = payload.get(name)
        numeric_value = _finite_float(value)
        if numeric_value is not None and 0.0 <= numeric_value <= 1.0:
            result[name] = numeric_value
    is_verification = payload.get("is_verification")
    if isinstance(is_verification, bool):
        result["is_verification"] = is_verification
    retry_number = payload.get("retry_number")
    if not isinstance(retry_number, bool) and isinstance(retry_number, int) and retry_number >= 0:
        result["retry_number"] = retry_number
    deduplication_scope = payload.get("deduplication_scope")
    if isinstance(deduplication_scope, str):
        result["deduplication_scope"] = _generalize_deduplication_scope(deduplication_scope)
    for name in ("cost", "estimated_cost", "token_usage"):
        value = payload.get(name)
        if isinstance(value, Mapping):
            result[name] = _sanitize_numeric_mapping(value)
    for name in ("fingerprint", "action_id", "state_hash"):
        value = payload.get(name)
        if isinstance(value, str):
            result[name] = pseudonymizer.pseudonymize(f"action.{name}", value)
    return result


def _sanitize_decision(payload: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in ("allowed", "recommended"):
        value = payload.get(name)
        if isinstance(value, bool):
            result[name] = value
    score = payload.get("score")
    score_value = _finite_float(score)
    if score_value is not None:
        result["score"] = score_value
    expected_gain = payload.get("expected_gain")
    expected_gain_value = _finite_float(expected_gain)
    if expected_gain_value is not None and 0.0 <= expected_gain_value <= 1.0:
        result["expected_gain"] = expected_gain_value
    estimated_cost_value = payload.get("estimated_cost_value")
    estimated_cost_value_float = _finite_float(estimated_cost_value)
    if estimated_cost_value_float is not None and estimated_cost_value_float >= 0.0:
        result["estimated_cost_value"] = estimated_cost_value_float
    uncertainty = payload.get("uncertainty")
    uncertainty_value = _finite_float(uncertainty)
    if uncertainty_value is not None and uncertainty_value >= 0.0:
        result["uncertainty"] = uncertainty_value
    confidence = payload.get("confidence")
    confidence_value = _finite_float(confidence)
    if confidence_value is not None and 0.0 <= confidence_value <= 1.0:
        result["confidence"] = confidence_value
    for name in ("reason_code", "recommendation_reason_code"):
        if name in payload:
            result[name] = _safe_reason_code(payload.get(name))
    if "mode" in payload:
        result["mode"] = _generalize_mode(payload.get("mode"))
    for name in ("directive", "recommended_directive"):
        if name in payload:
            result[name] = _generalize_directive(payload.get(name))
    if "estimator_version" in payload:
        result["estimator_version"] = _safe_version(payload.get("estimator_version"))
    return result


def _sanitize_outcome(payload: Mapping[str, Any], pseudonymizer: _Pseudonymizer) -> dict[str, Any]:
    result: dict[str, Any] = {}
    reward = payload.get("reward")
    if (
        not isinstance(reward, bool)
        and isinstance(reward, (int, float))
        and math.isfinite(float(reward))
    ):
        result["reward"] = reward
    resolved = payload.get("resolved")
    if isinstance(resolved, bool) or resolved is None:
        result["resolved"] = resolved
    for name in ("task_id", "trajectory_id"):
        value = payload.get(name)
        if isinstance(value, str):
            result[name] = pseudonymizer.pseudonymize(name, value)
    return result


def _sanitize_candidates(payload: list[Any], pseudonymizer: _Pseudonymizer) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for candidate in payload:
        if not isinstance(candidate, Mapping):
            continue
        item: dict[str, Any] = {}
        action = candidate.get("action")
        if isinstance(action, Mapping):
            item["action"] = _sanitize_action(action, pseudonymizer)
        decision = candidate.get("decision")
        if isinstance(decision, Mapping):
            item["decision"] = _sanitize_decision(decision)
        result.append(item)
    return result


def _sanitize_numeric_mapping(payload: Mapping[str, Any]) -> dict[str, int | float]:
    allowed = {
        "tokens",
        "usd",
        "latency_ms",
        "risk",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
    }
    result: dict[str, int | float] = {}
    for name, value in payload.items():
        if (
            name in allowed
            and not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
            and float(value) >= 0.0
        ):
            result[name] = value
    return result


def _generalize_action_kind(value: Any) -> str:
    if not isinstance(value, str):
        return "other"
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in _KNOWN_ACTION_KINDS else "other"


def _generalize_event(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    known = {
        "abort",
        "authorization",
        "candidate_ranking",
        "commit",
        "estimator_observation",
        "failure_settlement",
        "outcome",
        "session_end",
        "session_start",
    }
    return normalized if normalized in known else "custom"


def _generalize_mode(value: Any) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower().replace("-", "_")
    return normalized if normalized in {"shadow", "recommend", "enforce"} else "unknown"


def _generalize_directive(value: Any) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower().replace("-", "_")
    known = {"allow", "deny", "modify", "defer", "reuse", "stop", "force_verify"}
    return normalized if normalized in known else "unknown"


def _generalize_deduplication_scope(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    known = {"exact", "once_per_state", "once_per_phase", "allow_retry"}
    return normalized if normalized in known else "unknown"


def _safe_version(value: Any) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip()
    if normalized in {"unknown", "unversioned"}:
        return normalized
    if re.fullmatch(
        r"v?\d+(?:\.\d+){0,3}(?:[-+][0-9A-Za-z.-]{1,24})?",
        normalized,
    ):
        return normalized
    return "unknown"


def _safe_reason_code(value: Any) -> str:
    if not isinstance(value, str):
        return "UNSPECIFIED"
    normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
    return normalized if normalized in _KNOWN_REASON_CODES else "OTHER"


def _cost_bucket(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "unknown"
    tokens = _number(value.get("tokens"), default=0.0)
    usd = _number(value.get("usd"), default=0.0)
    latency = _number(value.get("latency_ms"), default=0.0)
    if tokens <= 2_000 and usd <= 0.02 and latency <= 1_000:
        return "low"
    if tokens <= 10_000 and usd <= 0.20 and latency <= 10_000:
        return "medium"
    return "high"


def _gain_bucket(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "unknown"
    gain = float(value)
    if not math.isfinite(gain):
        return "unknown"
    if gain < 0.1:
        return "low"
    if gain < 0.3:
        return "medium"
    return "high"


def _boolean_decision(value: Any) -> str:
    if value is True:
        return "allow"
    if value is False:
        return "deny"
    return "unknown"


def _outcome_class(payload: Mapping[str, Any]) -> str:
    resolved = payload.get("resolved")
    if resolved is True:
        return "verified_success"
    if resolved is False:
        return "verified_failure"
    reward = payload.get("reward")
    if not isinstance(reward, bool) and isinstance(reward, (int, float)):
        return "positive_reward" if float(reward) > 0 else "non_positive_reward"
    return "unknown"


def _is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return float(value)


def _number(value: Any, *, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)
