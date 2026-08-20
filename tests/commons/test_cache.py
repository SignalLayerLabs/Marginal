from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from marginal.commons import _storage as storage_module
from marginal.commons.cache import CommonsCache

SOURCE_COMMIT = "a" * 40
MODEL_NAMESPACE = "openai/gpt-5.6-sol"


def _aggregate(*, count: int = 7) -> dict[str, object]:
    return {
        "record_type": "decision",
        "action_kind": "test",
        "cost_bucket": "low",
        "gain_bucket": "high",
        "recommendation": "allow",
        "applied_decision": "allow",
        "reason_code": "APPROVED",
        "outcome_class": "not_applicable",
        "count": count,
        "minimum_group_size": 5,
        "lifecycle": "candidate",
    }


def _pack_bytes(
    *,
    count: int = 7,
    source_commit: str = SOURCE_COMMIT,
    revision: int = 1,
    compatibility: str = "1.0",
    extra: tuple[str, object] | None = None,
) -> bytes:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "source_commit": source_commit,
        "commons_revision": revision,
        "compatibility": {"evidence_envelope_schema_version": compatibility},
        "models": {
            "openai/gpt-5.6-sol": {"aggregates": [_aggregate(count=count)]},
            "openai/gpt-5.6-terra": {"aggregates": []},
            "openai/gpt-5.6-luna": {"aggregates": []},
        },
    }
    if extra is not None:
        payload[extra[0]] = extra[1]
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    payload["integrity"] = {"sha256": hashlib.sha256(canonical).hexdigest()}
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _cache(tmp_path: Path) -> CommonsCache:
    return CommonsCache(
        tmp_path,
        model_namespace=MODEL_NAMESPACE,
        expected_source_commit=SOURCE_COMMIT,
    )


def test_refresh_loads_only_the_selected_model_from_a_canonical_pack(tmp_path: Path) -> None:
    cache = _cache(tmp_path)

    assert cache.refresh(_pack_bytes()) is True

    priors = cache.load_prior()
    assert len(priors) == 1
    assert priors[0].model_namespace == MODEL_NAMESPACE
    assert priors[0].action_kind.value == "test"
    assert priors[0].count == 7
    assert priors[0].lifecycle.value == "candidate"
    assert cache.revision == 1
    assert stat.S_IMODE(cache.path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "candidate",
    [
        b"not-json",
        _pack_bytes(revision=0),
        _pack_bytes(compatibility="2.0"),
        _pack_bytes(source_commit="b" * 40),
        _pack_bytes(extra=("privacy-canary", "customer-acme")),
    ],
)
def test_rejected_refresh_preserves_and_uses_the_last_valid_pack(
    tmp_path: Path, candidate: bytes
) -> None:
    cache = _cache(tmp_path)
    assert cache.refresh(_pack_bytes(count=7)) is True
    before = cache.path.read_bytes()

    assert cache.refresh(candidate) is False

    assert cache.path.read_bytes() == before
    assert [prior.count for prior in cache.load_prior()] == [7]


def test_digest_is_over_canonical_payload_and_detects_post_digest_mutation(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    parsed = json.loads(_pack_bytes())
    parsed["models"][MODEL_NAMESPACE]["aggregates"][0]["count"] = 999
    attacked = json.dumps(parsed, separators=(",", ":")).encode("utf-8")

    assert cache.refresh(attacked) is False
    assert cache.load_prior() == ()


def test_refresh_rejects_oversized_and_cross_model_or_incomplete_packs(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    missing_model = json.loads(_pack_bytes())
    missing_model["models"].pop("openai/gpt-5.6-terra")
    without_integrity = {key: value for key, value in missing_model.items() if key != "integrity"}
    canonical = json.dumps(without_integrity, sort_keys=True, separators=(",", ":")).encode()
    missing_model["integrity"] = {"sha256": hashlib.sha256(canonical).hexdigest()}

    assert cache.refresh(json.dumps(missing_model).encode()) is False
    assert cache.refresh(b"{" + b" " * (cache.max_pack_bytes + 1)) is False


def test_cache_rejects_symlink_leaf_without_touching_its_target(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.path.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    cache.path.symlink_to(outside)

    assert cache.refresh(_pack_bytes()) is False
    assert outside.read_bytes() == b"outside"


def test_atomic_cache_write_retries_short_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache(tmp_path)
    original_write = os.write

    def short_write(descriptor: int, data: bytes) -> int:
        return original_write(descriptor, data[: max(1, len(data) // 3)])

    monkeypatch.setattr(storage_module.os, "write", short_write)

    assert cache.refresh(_pack_bytes()) is True
    assert [prior.count for prior in cache.load_prior()] == [7]


def test_partial_cache_write_failure_keeps_previous_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache(tmp_path)
    assert cache.refresh(_pack_bytes(count=7)) is True
    before = cache.path.read_bytes()

    def fail_after_partial_write(descriptor: int, data: bytes) -> None:
        os.write(descriptor, data[: len(data) // 2])
        raise OSError("synthetic partial write")

    monkeypatch.setattr(storage_module, "_write_all", fail_after_partial_write)

    assert cache.refresh(_pack_bytes(count=8)) is False
    assert cache.path.read_bytes() == before
    assert [prior.count for prior in cache.load_prior()] == [7]
