"""Verified, model-isolated local cache for deterministic Commons packs."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ._storage import atomic_replace_at, locked_directory, read_bounded_at
from .client import CommonsPackDownload
from .evidence import (
    ActionKind,
    AggregateReasonCode,
    DecisionClass,
    OutcomeClass,
    RecordType,
    ValueBucket,
)
from .identity import is_canonical_namespace
from .trust import verify_signed_pack

_CACHE_NAME = "commons-signed-cache-v1.json"
_MODEL_NAMESPACES = {
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-luna",
}
_MAX_PACK_BYTES = 2 * 1024 * 1024
_MAX_SIGNATURE_BYTES = 64 * 1024
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+\Z")


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


def _reject_constant(_value: str) -> None:
    raise ValueError("Commons pack contains a non-finite number")


def _parse_pack(raw: bytes) -> dict[str, Any]:
    try:
        payload: Any = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
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
        or not isinstance(payload["source_commit"], str)
        or len(payload["source_commit"]) != 40
        or any(character not in "0123456789abcdef" for character in payload["source_commit"])
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
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    if not hashlib.sha256(canonical).hexdigest() == digest:
        raise ValueError("Commons pack integrity mismatch")
    return payload


def _encode_base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_base64url(value: object, *, maximum_bytes: int) -> bytes:
    if (
        not isinstance(value, str)
        or not value
        or not _BASE64URL.fullmatch(value)
        or len(value) % 4 == 1
    ):
        raise ValueError("Commons signed cache is invalid")
    try:
        decoded = base64.b64decode(value + "=" * ((-len(value)) % 4), altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Commons signed cache is invalid") from None
    if len(decoded) > maximum_bytes or _encode_base64url(decoded) != value:
        raise ValueError("Commons signed cache is invalid")
    return decoded


def _cache_bytes(download: CommonsPackDownload) -> bytes:
    return (
        json.dumps(
            {
                "schema_version": "1.0",
                "pack": _encode_base64url(download.pack),
                "signature": _encode_base64url(download.signature),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _parse_cache(raw: bytes) -> CommonsPackDownload:
    try:
        payload: Any = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Commons signed cache is invalid") from exc
    if not _exact_keys(payload, {"schema_version", "pack", "signature"}):
        raise ValueError("Commons signed cache is invalid")
    assert isinstance(payload, dict)
    if payload["schema_version"] != "1.0":
        raise ValueError("Commons signed cache is invalid")
    return CommonsPackDownload(
        pack=_decode_base64url(payload["pack"], maximum_bytes=_MAX_PACK_BYTES),
        signature=_decode_base64url(payload["signature"], maximum_bytes=_MAX_SIGNATURE_BYTES),
    )


def _verified_download(download: CommonsPackDownload) -> dict[str, Any]:
    certificate = verify_signed_pack(download.pack, download.signature)
    payload = _parse_pack(download.pack)
    revision = payload["commons_revision"]
    if not certificate.not_before_revision <= revision <= certificate.not_after_revision:
        raise ValueError("Commons pack revision is outside its certificate")
    return payload


class CommonsCache:
    """Persist and load only verified priors for one exact canonical model."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        model_namespace: str,
        max_pack_bytes: int = _MAX_PACK_BYTES,
    ) -> None:
        if not is_canonical_namespace(model_namespace):
            raise ValueError("Commons cache requires a canonical model namespace")
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
        self.max_pack_bytes = max_pack_bytes
        self.path = (
            (root if root.is_absolute() else Path.cwd() / root) / "commons" / "cache" / _CACHE_NAME
        )

    def refresh(self, download: CommonsPackDownload) -> bool:
        """Atomically replace the cache only when every frozen-pack check succeeds."""

        if (
            not isinstance(download, CommonsPackDownload)
            or len(download.pack) > self.max_pack_bytes
            or len(download.signature) > _MAX_SIGNATURE_BYTES
        ):
            return False
        try:
            candidate = _verified_download(download)
            candidate_cache = _cache_bytes(download)
            with locked_directory(
                self.path.parent, create=True, lock_name=".cache.lock"
            ) as directory:
                try:
                    existing_cache, _ = read_bounded_at(
                        directory,
                        _CACHE_NAME,
                        maximum_bytes=(self.max_pack_bytes * 2) + _MAX_SIGNATURE_BYTES,
                        label="Commons cache",
                    )
                except FileNotFoundError:
                    existing = None
                    existing_download = None
                else:
                    try:
                        existing_download = _parse_cache(existing_cache)
                        existing = _verified_download(existing_download)
                    except (ValueError, RecursionError, MemoryError, OverflowError):
                        existing = None
                        existing_download = None
                if (
                    existing is not None
                    and candidate["commons_revision"] < existing["commons_revision"]
                ):
                    return False
                if (
                    existing is not None
                    and candidate["commons_revision"] == existing["commons_revision"]
                ):
                    return existing_download == download
                atomic_replace_at(
                    directory,
                    _CACHE_NAME,
                    candidate_cache,
                    temporary_prefix=".commons-pack-",
                    label="Commons cache",
                )
        except (OSError, ValueError, RecursionError, MemoryError, OverflowError):
            return False
        return True

    def _load_pack(self) -> dict[str, Any] | None:
        try:
            with locked_directory(
                self.path.parent, create=False, lock_name=".cache.lock"
            ) as directory:
                raw, _ = read_bounded_at(
                    directory,
                    _CACHE_NAME,
                    maximum_bytes=(self.max_pack_bytes * 2) + _MAX_SIGNATURE_BYTES,
                    label="Commons cache",
                )
            return _verified_download(_parse_cache(raw))
        except (
            FileNotFoundError,
            OSError,
            ValueError,
            RecursionError,
            MemoryError,
            OverflowError,
        ):
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
