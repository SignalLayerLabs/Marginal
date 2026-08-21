from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import time
from pathlib import Path

import pytest
from tests.commons_signing import root_document, signed_download

from marginal.commons import _storage as storage_module
from marginal.commons import cache as cache_module
from marginal.commons.cache import CommonsCache
from marginal.commons.trust import verify_signed_pack_with_root

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
    return CommonsCache(tmp_path, model_namespace=MODEL_NAMESPACE)


@pytest.fixture(autouse=True)
def _use_test_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cache_module,
        "verify_signed_pack",
        lambda pack, signature: verify_signed_pack_with_root(pack, signature, root_document()),
    )


def test_refresh_loads_only_the_selected_model_from_a_canonical_pack(tmp_path: Path) -> None:
    cache = _cache(tmp_path)

    assert cache.refresh(signed_download(_pack_bytes())) is True

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
        _pack_bytes(source_commit="B" * 40),
        _pack_bytes(extra=("privacy-canary", "customer-acme")),
    ],
)
def test_rejected_refresh_preserves_and_uses_the_last_valid_pack(
    tmp_path: Path, candidate: bytes
) -> None:
    cache = _cache(tmp_path)
    assert cache.refresh(signed_download(_pack_bytes(count=7))) is True
    before = cache.path.read_bytes()

    assert cache.refresh(signed_download(candidate)) is False

    assert cache.path.read_bytes() == before
    assert [prior.count for prior in cache.load_prior()] == [7]


def test_digest_is_over_canonical_payload_and_detects_post_digest_mutation(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    parsed = json.loads(_pack_bytes())
    parsed["models"][MODEL_NAMESPACE]["aggregates"][0]["count"] = 999
    attacked = json.dumps(parsed, separators=(",", ":")).encode("utf-8")

    assert cache.refresh(signed_download(attacked)) is False
    assert cache.load_prior() == ()


def test_refresh_rejects_oversized_and_cross_model_or_incomplete_packs(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    missing_model = json.loads(_pack_bytes())
    missing_model["models"].pop("openai/gpt-5.6-terra")
    without_integrity = {key: value for key, value in missing_model.items() if key != "integrity"}
    canonical = json.dumps(without_integrity, sort_keys=True, separators=(",", ":")).encode()
    missing_model["integrity"] = {"sha256": hashlib.sha256(canonical).hexdigest()}

    assert cache.refresh(signed_download(json.dumps(missing_model).encode())) is False
    assert cache.refresh(signed_download(b"{" + b" " * (cache.max_pack_bytes + 1))) is False


def test_refresh_rejects_recursive_json_as_a_bounded_parser_failure(tmp_path: Path) -> None:
    cache = _cache(tmp_path)

    assert cache.refresh(signed_download(("[" * 2_000 + "]" * 2_000).encode())) is False
    assert cache.load_prior() == ()


def test_refresh_rejects_revision_rollback_under_the_cache_lock(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    assert cache.refresh(signed_download(_pack_bytes(count=8, revision=2))) is True
    before = cache.path.read_bytes()

    assert cache.refresh(signed_download(_pack_bytes(count=7, revision=1))) is False

    assert cache.path.read_bytes() == before
    assert cache.revision == 2
    assert [prior.count for prior in cache.load_prior()] == [8]


@pytest.mark.skipif(os.name == "nt", reason="POSIX advisory locks are required")
def test_cache_lock_contention_returns_fail_open_within_a_bound(tmp_path: Path) -> None:
    import fcntl

    cache = _cache(tmp_path)
    assert cache.refresh(signed_download(_pack_bytes())) is True
    lock = (cache.path.parent / ".cache.lock").open("r+b")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

    def release_later() -> None:
        time.sleep(0.5)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    release = threading.Thread(target=release_later, daemon=True)
    release.start()
    started = time.monotonic()
    refreshed = cache.refresh(signed_download(_pack_bytes(count=8, revision=2)))
    elapsed = time.monotonic() - started
    release.join(timeout=1)
    lock.close()

    assert refreshed is False
    assert elapsed < 0.4


def test_cache_rejects_symlink_leaf_without_touching_its_target(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.path.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    cache.path.symlink_to(outside)

    assert cache.refresh(signed_download(_pack_bytes())) is False
    assert outside.read_bytes() == b"outside"


def test_atomic_cache_write_retries_short_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache(tmp_path)
    original_write = os.write

    def short_write(descriptor: int, data: bytes) -> int:
        return original_write(descriptor, data[: max(1, len(data) // 3)])

    monkeypatch.setattr(storage_module.os, "write", short_write)

    assert cache.refresh(signed_download(_pack_bytes())) is True
    assert [prior.count for prior in cache.load_prior()] == [7]


def test_partial_cache_write_failure_keeps_previous_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache(tmp_path)
    assert cache.refresh(signed_download(_pack_bytes(count=7))) is True
    before = cache.path.read_bytes()

    def fail_after_partial_write(descriptor: int, data: bytes) -> None:
        os.write(descriptor, data[: len(data) // 2])
        raise OSError("synthetic partial write")

    monkeypatch.setattr(storage_module, "_write_all", fail_after_partial_write)

    assert cache.refresh(signed_download(_pack_bytes(count=8, revision=2))) is False
    assert cache.path.read_bytes() == before
    assert [prior.count for prior in cache.load_prior()] == [7]


def test_tampered_pack_or_signature_is_rejected(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    valid = signed_download(_pack_bytes())

    assert cache.refresh(type(valid)(pack=valid.pack + b" ", signature=valid.signature)) is False
    assert (
        cache.refresh(type(valid)(pack=valid.pack, signature=valid.signature[:-1] + b" ")) is False
    )
    assert cache.load_prior() == ()


def test_certificate_revision_bounds_are_enforced(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    candidate = signed_download(
        _pack_bytes(revision=11), not_before_revision=1, not_after_revision=10
    )

    assert cache.refresh(candidate) is False
    assert cache.revision is None


def test_same_revision_requires_byte_identical_signed_artifact(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    original = signed_download(_pack_bytes(revision=3))
    different = signed_download(_pack_bytes(revision=3, source_commit="b" * 40))

    assert cache.refresh(original) is True
    before = cache.path.read_bytes()
    assert cache.refresh(original) is True
    assert cache.path.read_bytes() == before
    assert cache.refresh(different) is False
    assert cache.path.read_bytes() == before


def test_old_unsigned_cache_grants_zero_priors(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    legacy = cache.path.parent / "commons-pack-v1.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(_pack_bytes())
    legacy.chmod(0o600)

    assert cache.load_prior() == ()
    assert cache.revision is None


def test_rejected_candidate_preserves_old_valid_signed_cache(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    old = signed_download(_pack_bytes(revision=4))
    assert cache.refresh(old) is True
    before = cache.path.read_bytes()
    tampered = type(old)(pack=old.pack + b" ", signature=old.signature)

    assert cache.refresh(tampered) is False
    assert cache.path.read_bytes() == before
    assert cache.revision == 4


def test_pack_source_commit_is_provenance_not_a_hardcoded_pin(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    assert cache.refresh(signed_download(_pack_bytes(source_commit="b" * 40))) is True
