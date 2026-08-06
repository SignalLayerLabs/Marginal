from __future__ import annotations

import json
from pathlib import Path

import pytest

from marginal.privacy import (
    FIELD_CLASSIFICATION,
    LocalPseudonymizer,
    PrivacyClass,
    PrivacyConfig,
    PrivacyProfile,
    aggregate_ledger_records,
    classify_field,
    generate_local_identifier,
    load_or_create_privacy_key,
    sanitize_ledger_record,
    validate_safe_telemetry_record,
)


def _sensitive_record() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "event_id": "event-123",
        "sequence": 1,
        "timestamp": "2026-08-06T08:37:42+00:00",
        "run_id": "customer-acme-contract-2026",
        "task_id": "customer-acme-contract-2026",
        "trajectory_id": "secret-trajectory",
        "engine": "codex",
        "model": "internal-legal-model",
        "event": "authorization",
        "mode": "shadow",
        "privacy_profile": "local_full",
        "policy": {"name": "balanced", "version": "2.0.0", "config_hash": "abc"},
        "estimator": {
            "name": "historical-mean",
            "version": "2.0.0",
            "config_hash": "def",
            "training_data_fingerprint": "training-secret",
        },
        "treasury": "customer-acme",
        "action": {
            "name": "review termination clause",
            "kind": "verification",
            "cost": {"tokens": 1200, "usd": 0.01, "latency_ms": 200, "risk": 0.0},
            "expected_gain": 0.2,
            "current_success_probability": 0.5,
            "is_verification": True,
            "fingerprint": "guessable-fingerprint",
            "metadata": {
                "repository": "secret-merger-project",
                "tool_arguments": {"file": "contracts/acme.txt"},
            },
        },
        "decision": {
            "allowed": True,
            "recommended": False,
            "reason": "shadow mode allowed confidential review",
            "reason_code": "SHADOW_OVERRIDE",
            "recommendation_reason": "expected value too low for Acme contract",
            "recommendation_reason_code": "ROI_BELOW_MINIMUM",
            "mode": "shadow",
            "score": -0.1,
            "expected_gain": 0.2,
            "estimated_cost_value": 0.3,
            "uncertainty": 0.05,
            "confidence": 0.8,
            "estimator_name": "historical-mean",
            "estimator_version": "2.0.0",
        },
        "usage": {"tokens": 1200, "usd": 0.01, "latency_ms": 200, "risk": 0.0},
        "reason": "RuntimeError: customer Acme file unavailable",
    }


def test_privacy_profile_parses_supported_values() -> None:
    assert PrivacyProfile.parse("local-full") is PrivacyProfile.LOCAL_FULL
    assert PrivacyProfile.parse("safe_telemetry") is PrivacyProfile.SAFE_TELEMETRY
    assert PrivacyProfile.parse(PrivacyProfile.AGGREGATE_EXPORT) is PrivacyProfile.AGGREGATE_EXPORT
    with pytest.raises(ValueError, match="unknown privacy profile"):
        PrivacyProfile.parse("anonymous")


def test_field_classification_covers_representative_categories() -> None:
    assert FIELD_CLASSIFICATION["action.kind"] is PrivacyClass.SAFE_BY_DEFAULT
    assert FIELD_CLASSIFICATION["task_id"] is PrivacyClass.PSEUDONYMOUS
    assert FIELD_CLASSIFICATION["action.name"] is PrivacyClass.POTENTIALLY_SENSITIVE
    assert FIELD_CLASSIFICATION["outcome.verifier"] is PrivacyClass.POTENTIALLY_SENSITIVE


def test_privacy_config_repr_does_not_expose_key_material() -> None:
    config = PrivacyConfig(profile="safe_telemetry", key=b"secret-key-material" * 2)
    assert "secret-key-material" not in repr(config)


def test_local_identifier_is_random_opaque_and_namespaced() -> None:
    first = generate_local_identifier("task")
    second = generate_local_identifier("task")
    assert first.startswith("task_")
    assert second.startswith("task_")
    assert first != second
    assert len(first) >= 24
    with pytest.raises(ValueError, match="namespace"):
        generate_local_identifier("customer acme")


def test_local_pseudonymizer_is_deterministic_and_field_separated() -> None:
    pseudonymizer = LocalPseudonymizer(b"a" * 32)
    first = pseudonymizer.pseudonymize("task_id", "customer-acme")
    second = pseudonymizer.pseudonymize("task_id", "customer-acme")
    different_field = pseudonymizer.pseudonymize("run_id", "customer-acme")

    assert first == second
    assert first != different_field
    assert first.startswith("psn_")
    assert "customer" not in first


def test_different_keys_produce_unlinkable_pseudonyms() -> None:
    left = LocalPseudonymizer(b"a" * 32)
    right = LocalPseudonymizer(b"b" * 32)
    assert left.pseudonymize("task_id", "same") != right.pseudonymize("task_id", "same")


def test_safe_telemetry_removes_free_text_and_pseudonymizes_identifiers() -> None:
    sanitized = sanitize_ledger_record(
        _sensitive_record(),
        profile=PrivacyProfile.SAFE_TELEMETRY,
        pseudonymizer=LocalPseudonymizer(b"k" * 32),
    )

    encoded = json.dumps(sanitized, sort_keys=True)
    assert sanitized["privacy_profile"] == "safe_telemetry"
    assert sanitized["run_id"].startswith("psn_")
    assert sanitized["task_id"].startswith("psn_")
    assert sanitized["trajectory_id"].startswith("psn_")
    assert sanitized["event_id"].startswith("psn_")
    assert sanitized["timestamp"] == "2026-08-06T00:00:00+00:00"
    assert sanitized["engine"] == "codex"
    assert "model" not in sanitized
    assert "treasury" not in sanitized
    assert "name" not in sanitized["action"]
    assert "metadata" not in sanitized["action"]
    assert sanitized["action"]["fingerprint"].startswith("psn_")
    assert "reason" not in sanitized["decision"]
    assert "recommendation_reason" not in sanitized["decision"]
    assert sanitized["decision"]["reason_code"] == "SHADOW_OVERRIDE"
    assert "reason" not in sanitized
    for secret in (
        "customer-acme",
        "internal-legal-model",
        "termination clause",
        "secret-merger-project",
        "RuntimeError",
    ):
        assert secret not in encoded


def test_safe_telemetry_keeps_outcome_structure_but_removes_verifier_and_evidence() -> None:
    record = {
        **_sensitive_record(),
        "event": "outcome",
        "outcome": {
            "task_id": "customer-acme-contract-2026",
            "reward": 1.0,
            "resolved": True,
            "verifier": "internal legal verifier",
            "trajectory_id": "secret-trajectory",
            "evidence": {"document": "merger.pdf"},
            "metrics": {"clauses_reviewed": 12},
        },
    }
    sanitized = sanitize_ledger_record(
        record,
        profile="safe_telemetry",
        pseudonymizer=LocalPseudonymizer(b"k" * 32),
    )
    outcome = sanitized["outcome"]
    assert outcome == {
        "task_id": sanitized["task_id"],
        "reward": 1.0,
        "resolved": True,
        "trajectory_id": sanitized["trajectory_id"],
    }


def test_local_full_returns_an_independent_complete_copy() -> None:
    original = _sensitive_record()
    sanitized = sanitize_ledger_record(original, profile="local_full")
    assert sanitized == original
    assert sanitized is not original


def test_safe_telemetry_requires_a_pseudonymizer() -> None:
    with pytest.raises(ValueError, match="pseudonymizer"):
        sanitize_ledger_record(_sensitive_record(), profile="safe_telemetry")


def test_local_key_is_created_once_with_32_bytes(tmp_path: Path) -> None:
    path = tmp_path / "privacy.key"
    first = load_or_create_privacy_key(path)
    second = load_or_create_privacy_key(path)
    assert first == second
    assert len(first) == 32
    assert path.read_bytes() == first
    if hasattr(path.stat(), "st_mode"):
        assert path.stat().st_mode & 0o077 == 0


def test_aggregate_export_groups_generalized_records_without_identifiers() -> None:
    first = _sensitive_record()
    second = _sensitive_record()
    second["event_id"] = "event-456"
    outcome = {
        **_sensitive_record(),
        "event_id": "event-outcome",
        "event": "outcome",
        "outcome": {
            "task_id": "customer-acme-contract-2026",
            "reward": 1.0,
            "resolved": True,
            "verifier": "pytest customer suite",
            "trajectory_id": "secret-trajectory",
            "evidence": {"repository": "secret-merger-project"},
            "metrics": {},
        },
    }

    rows = aggregate_ledger_records([first, second, outcome], minimum_group_size=1)

    assert rows == [
        {
            "schema_version": "1.0",
            "privacy_profile": "aggregate_export",
            "record_type": "decision",
            "action_kind": "verification",
            "cost_bucket": "low",
            "gain_bucket": "medium",
            "recommendation": "deny",
            "applied_decision": "allow",
            "reason_code": "SHADOW_OVERRIDE",
            "outcome_class": "not_applicable",
            "count": 2,
            "minimum_group_size": 1,
        },
        {
            "schema_version": "1.0",
            "privacy_profile": "aggregate_export",
            "record_type": "outcome",
            "action_kind": "unknown",
            "cost_bucket": "unknown",
            "gain_bucket": "unknown",
            "recommendation": "not_applicable",
            "applied_decision": "not_applicable",
            "reason_code": "not_applicable",
            "outcome_class": "verified_success",
            "count": 1,
            "minimum_group_size": 1,
        },
    ]
    encoded = json.dumps(rows)
    for secret in (
        "customer-acme",
        "secret-trajectory",
        "internal-legal-model",
        "termination clause",
        "secret-merger-project",
    ):
        assert secret not in encoded


def test_aggregate_export_suppresses_small_groups_by_default() -> None:
    records = [_sensitive_record() for _ in range(4)]
    for index, record in enumerate(records):
        record["event_id"] = f"event-{index}"

    assert aggregate_ledger_records(records) == []


def test_aggregate_export_records_and_validates_minimum_group_size() -> None:
    records = [_sensitive_record() for _ in range(2)]
    for index, record in enumerate(records):
        record["event_id"] = f"event-{index}"

    rows = aggregate_ledger_records(records, minimum_group_size=2)

    assert rows[0]["count"] == 2
    assert rows[0]["minimum_group_size"] == 2
    with pytest.raises(TypeError, match="minimum_group_size"):
        aggregate_ledger_records(records, minimum_group_size=True)
    with pytest.raises(ValueError, match="at least 1"):
        aggregate_ledger_records(records, minimum_group_size=0)


def test_existing_privacy_key_rejects_symlink_and_weak_permissions(tmp_path: Path) -> None:
    import os

    target = tmp_path / "target.key"
    target.write_bytes(b"k" * 32)
    target.chmod(0o600)
    link = tmp_path / "link.key"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available")
    with pytest.raises(ValueError, match="symbolic link"):
        load_or_create_privacy_key(link)

    if os.name != "nt":
        target.chmod(0o644)
        with pytest.raises(PermissionError, match="group or others"):
            load_or_create_privacy_key(target)


def test_existing_privacy_key_rejects_short_material(tmp_path: Path) -> None:
    path = tmp_path / "short.key"
    path.write_bytes(b"short")
    path.chmod(0o600)
    with pytest.raises(ValueError, match="at least 32 bytes"):
        load_or_create_privacy_key(path)


def test_safe_telemetry_generalizes_unrecognized_labels_and_numeric_keys() -> None:
    record = _sensitive_record()
    record["event"] = "customer_acme_incident"
    record["action"]["kind"] = "customer_acme_contract"  # type: ignore[index]
    record["action"]["cost"]["customer_id"] = 42  # type: ignore[index]
    record["decision"]["reason_code"] = "CUSTOMER_ACME"  # type: ignore[index]
    record["decision"]["score"] = "secret-score"  # type: ignore[index]
    record["policy"]["version"] = "customer acme policy"  # type: ignore[index]

    sanitized = sanitize_ledger_record(
        record,
        profile="safe_telemetry",
        pseudonymizer=LocalPseudonymizer(b"k" * 32),
    )

    assert sanitized["event"] == "custom"
    assert sanitized["action"]["kind"] == "other"
    assert "customer_id" not in sanitized["action"]["cost"]
    assert sanitized["decision"]["reason_code"] == "OTHER"
    assert "score" not in sanitized["decision"]
    assert sanitized["policy"]["version"] == "unknown"
    assert "customer" not in json.dumps(sanitized).lower()


def test_every_field_has_a_classification_and_unknown_fields_default_sensitive() -> None:
    from marginal.privacy import classify_field

    assert classify_field("decision.score") is PrivacyClass.SAFE_BY_DEFAULT
    assert classify_field("run_id") is PrivacyClass.PSEUDONYMOUS
    assert classify_field("custom.customer_name") is PrivacyClass.POTENTIALLY_SENSITIVE
    with pytest.raises(TypeError):
        FIELD_CLASSIFICATION["custom"] = PrivacyClass.SAFE_BY_DEFAULT  # type: ignore[index]


def test_existing_privacy_key_is_read_from_validated_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "descriptor.key"
    path.write_bytes(b"d" * 32)
    path.chmod(0o600)

    def reject_path_read(_path: Path) -> bytes:
        raise AssertionError("privacy keys must be read from the validated descriptor")

    monkeypatch.setattr(Path, "read_bytes", reject_path_read)

    assert load_or_create_privacy_key(path) == b"d" * 32


def test_safe_telemetry_accepts_only_version_like_identity_strings() -> None:
    record = _sensitive_record()
    record["policy"]["version"] = "customer_acme_policy"  # type: ignore[index]
    record["estimator"]["version"] = "internal-legal-v1"  # type: ignore[index]
    record["decision"]["estimator_version"] = "private_model_2026"  # type: ignore[index]

    sanitized = sanitize_ledger_record(
        record,
        profile="safe_telemetry",
        pseudonymizer=LocalPseudonymizer(b"k" * 32),
    )

    assert sanitized["policy"]["version"] == "unknown"
    assert sanitized["estimator"]["version"] == "unknown"
    assert sanitized["decision"]["estimator_version"] == "unknown"


def test_field_classification_inherits_from_reviewed_parent_paths() -> None:
    assert classify_field("action.cost.tokens") is PrivacyClass.SAFE_BY_DEFAULT
    assert classify_field("usage.reasoning_tokens") is PrivacyClass.SAFE_BY_DEFAULT
    assert classify_field("metadata.repository") is PrivacyClass.POTENTIALLY_SENSITIVE
    assert classify_field("outcome.evidence.document") is PrivacyClass.POTENTIALLY_SENSITIVE


def test_safe_telemetry_retains_only_reviewed_safe_or_pseudonymous_fields() -> None:
    record = _sensitive_record()
    record["candidates"] = [
        {
            "action": record["action"],
            "decision": record["decision"],
            "private_note": "customer-acme",
        }
    ]
    sanitized = sanitize_ledger_record(
        record,
        profile="safe_telemetry",
        pseudonymizer=LocalPseudonymizer(b"k" * 32),
    )

    def leaf_paths(value: object, prefix: str = "") -> list[str]:
        if isinstance(value, dict):
            paths: list[str] = []
            for name, item in value.items():
                child = f"{prefix}.{name}" if prefix else name
                paths.extend(leaf_paths(item, child))
            return paths
        if isinstance(value, list):
            paths = []
            for item in value:
                paths.extend(leaf_paths(item, f"{prefix}[]"))
            return paths
        return [prefix]

    retained = set(leaf_paths(sanitized))
    assert retained
    assert {
        path: classify_field(path)
        for path in retained
        if classify_field(path) is PrivacyClass.POTENTIALLY_SENSITIVE
    } == {}


def test_safe_telemetry_validator_rejects_out_of_range_numeric_values() -> None:
    base = sanitize_ledger_record(
        _sensitive_record(),
        profile="safe_telemetry",
        pseudonymizer=LocalPseudonymizer(b"k" * 32),
    )

    negative_usage = json.loads(json.dumps(base))
    negative_usage["usage"]["tokens"] = -1
    with pytest.raises(ValueError, match="safe telemetry"):
        validate_safe_telemetry_record(negative_usage)

    invalid_probability = json.loads(json.dumps(base))
    invalid_probability["action"]["expected_gain"] = 1.5
    with pytest.raises(ValueError, match="safe telemetry"):
        validate_safe_telemetry_record(invalid_probability)

    invalid_confidence = json.loads(json.dumps(base))
    invalid_confidence["decision"]["confidence"] = 2.0
    with pytest.raises(ValueError, match="safe telemetry"):
        validate_safe_telemetry_record(invalid_confidence)


def test_safe_telemetry_pseudonymizes_engine_instance_identifiers() -> None:
    record = {**_sensitive_record(), "engine_instance": "internal-runner-acme-01"}
    sanitized = sanitize_ledger_record(
        record,
        profile="safe_telemetry",
        pseudonymizer=LocalPseudonymizer(b"k" * 32),
    )

    assert sanitized["engine_instance"].startswith("psn_")
    assert "internal-runner-acme-01" not in json.dumps(sanitized)
