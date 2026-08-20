"""Verified, model-isolated local cache for deterministic Commons packs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ._storage import atomic_replace_at, locked_directory, read_bounded_at
from .evidence import (
    ActionKind,
    AggregateReasonCode,
    DecisionClass,
    OutcomeClass,
    RecordType,
    ValueBucket,
)
from .identity import is_canonical_namespace

_PACK_NAME = "commons-pack-v1.json"
_MODEL_NAMESPACES = {
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-luna",
}
_MAX_PACK_BYTES = 2 * 1024 * 1024


class CommonsLifecycle(str, Enum):
    """Non-authoritative lifecycle label carried by a Commons prior."""

    CANDIDATE = "candidate"
    SUPPORTED = "supported"
    VALIDATED = "validated"
    PROMOTED = "promoted"


@dataclass(frozen=True, slots=True)
class CommonsPrior:
    """One closed aggregate prior for exactly one canonical model namespace."""

    model_namespace: str
    record_type: RecordType
    action_kind: ActionKind
    cost_bucket: ValueBucket
    gain_bucket: ValueBucket
    recommendation: DecisionClass
    applied_decision: DecisionClass
    reason_code: AggregateReasonCode
    outcome_class: OutcomeClass
    count: int
    minimum_group_size: int
    lifecycle: CommonsLifecycle


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Commons pack contains a duplicate field")
        result[key] = value
    return result


def _exact_keys(payload: object, expected: set[str]) -> bool:
    return isinstance(payload, dict) and set(payload) == expected


def _positive_bounded_integer(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and 1 <= value <= 1_000


def _parse_aggregate(namespace: str, raw: object) -> CommonsPrior:
    expected = {
        "record_type",
        "action_kind",
        "cost_bucket",
        "gain_bucket",
        "recommendation",
        "applied_decision",
        "reason_code",
        "outcome_class",
        "count",
        "minimum_group_size",
        "lifecycle",
    }
    if not _exact_keys(raw, expected):
        raise ValueError("Commons aggregate has an invalid shape")
    assert isinstance(raw, dict)
    if not _positive_bounded_integer(raw["count"]) or not _positive_bounded_integer(
        raw["minimum_group_size"]
    ):
        raise ValueError("Commons aggregate count is invalid")
    try:
        return CommonsPrior(
            model_namespace=namespace,
            record_type=RecordType(raw["record_type"]),
            action_kind=ActionKind(raw["action_kind"]),
            cost_bucket=ValueBucket(raw["cost_bucket"]),
            gain_bucket=ValueBucket(raw["gain_bucket"]),
            recommendation=DecisionClass(raw["recommendation"]),
            applied_decision=DecisionClass(raw["applied_decision"]),
            reason_code=AggregateReasonCode(raw["reason_code"]),
            outcome_class=OutcomeClass(raw["outcome_class"]),
            count=raw["count"],
            minimum_group_size=raw["minimum_group_size"],
            lifecycle=CommonsLifecycle(raw["lifecycle"]),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Commons aggregate contains an invalid value") from exc


def _parse_pack(raw: bytes, *, expected_source_commit: str) -> dict[str, Any]:
    try:
        payload: Any = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Commons pack is not valid JSON") from exc
    expected = {
        "schema_version",
        "source_commit",
        "commons_revision",
        "compatibility",
        "models",
        "integrity",
    }
    if not _exact_keys(payload, expected):
        raise ValueError("Commons pack has an invalid shape")
    assert isinstance(payload, dict)
    revision = payload["commons_revision"]
    if (
        payload["schema_version"] != "1.0"
        or payload["source_commit"] != expected_source_commit
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
        or payload["compatibility"] != {"evidence_envelope_schema_version": "1.0"}
    ):
        raise ValueError("Commons pack is incompatible")
    models = payload["models"]
    if not isinstance(models, dict) or set(models) != _MODEL_NAMESPACES:
        raise ValueError("Commons pack model registry is invalid")
    for namespace, model in models.items():
        if not _exact_keys(model, {"aggregates"}):
            raise ValueError("Commons pack model has an invalid shape")
        assert isinstance(model, dict)
        aggregates = model["aggregates"]
        if not isinstance(aggregates, list) or len(aggregates) > 10_000:
            raise ValueError("Commons pack model aggregates are invalid")
        for aggregate in aggregates:
            _parse_aggregate(namespace, aggregate)
    integrity = payload["integrity"]
    if not _exact_keys(integrity, {"sha256"}):
        raise ValueError("Commons pack integrity is invalid")
    assert isinstance(integrity, dict)
    digest = integrity["sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("Commons pack integrity is invalid")
    canonical_payload = {key: value for key, value in payload.items() if key != "integrity"}
    canonical = json.dumps(
        canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if not hashlib.sha256(canonical).hexdigest() == digest:
        raise ValueError("Commons pack integrity mismatch")
    return payload


class CommonsCache:
    """Persist and load only verified priors for one exact canonical model."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        model_namespace: str,
        expected_source_commit: str,
        max_pack_bytes: int = _MAX_PACK_BYTES,
    ) -> None:
        if not is_canonical_namespace(model_namespace):
            raise ValueError("Commons cache requires a canonical model namespace")
        if (
            not isinstance(expected_source_commit, str)
            or len(expected_source_commit) != 40
            or any(character not in "0123456789abcdef" for character in expected_source_commit)
        ):
            raise ValueError("Commons cache requires an exact source commit")
        if (
            isinstance(max_pack_bytes, bool)
            or not isinstance(max_pack_bytes, int)
            or max_pack_bytes < 1
        ):
            raise ValueError("Commons cache byte limit must be positive")
        root = Path(data_dir)
        if ".." in root.parts:
            raise ValueError("Commons cache path must not contain traversal")
        self.model_namespace = model_namespace
        self.expected_source_commit = expected_source_commit
        self.max_pack_bytes = max_pack_bytes
        self.path = (
            (root if root.is_absolute() else Path.cwd() / root) / "commons" / "cache" / _PACK_NAME
        )

    def refresh(self, raw: bytes) -> bool:
        """Atomically replace the cache only when every frozen-pack check succeeds."""

        if not isinstance(raw, bytes) or len(raw) > self.max_pack_bytes:
            return False
        try:
            _parse_pack(raw, expected_source_commit=self.expected_source_commit)
            with locked_directory(
                self.path.parent, create=True, lock_name=".cache.lock"
            ) as directory:
                atomic_replace_at(
                    directory,
                    _PACK_NAME,
                    raw,
                    temporary_prefix=".commons-pack-",
                    label="Commons cache",
                )
        except (OSError, ValueError):
            return False
        return True

    def _load_pack(self) -> dict[str, Any] | None:
        try:
            with locked_directory(
                self.path.parent, create=False, lock_name=".cache.lock"
            ) as directory:
                raw, _ = read_bounded_at(
                    directory,
                    _PACK_NAME,
                    maximum_bytes=self.max_pack_bytes,
                    label="Commons cache",
                )
            return _parse_pack(raw, expected_source_commit=self.expected_source_commit)
        except (FileNotFoundError, OSError, ValueError):
            return None

    def load_prior(self) -> tuple[CommonsPrior, ...]:
        """Return only this cache instance's exact-model priors, or nothing on failure."""

        payload = self._load_pack()
        if payload is None:
            return ()
        model = payload["models"][self.model_namespace]
        return tuple(_parse_aggregate(self.model_namespace, raw) for raw in model["aggregates"])

    @property
    def revision(self) -> int | None:
        """Return the verified cached revision without granting it any authority."""

        payload = self._load_pack()
        return payload["commons_revision"] if payload is not None else None
