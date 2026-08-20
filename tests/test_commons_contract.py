from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from marginal.privacy import aggregate_ledger_records

ROOT = Path(__file__).resolve().parents[1]
NAMESPACES = (
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-luna",
)
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def _schema(name: str) -> dict[str, object]:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _valid_atom() -> dict[str, object]:
    return {
        "record_type": "decision",
        "action_kind": "tool",
        "cost_bucket": "low",
        "gain_bucket": "medium",
        "recommendation": "allow",
        "applied_decision": "allow",
        "reason_code": "APPROVED",
        "outcome_class": "not_applicable",
        "count": 1,
        "minimum_group_size": 1,
    }


def _valid_envelope() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "model_namespace": NAMESPACES[0],
        "atoms": [_valid_atom()],
    }


def _validator(schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(_schema(schema_name))


def _assert_invalid(validator: Draft202012Validator, payload: object) -> None:
    with pytest.raises(ValidationError):
        validator.validate(payload)


def test_envelope_accepts_only_closed_aggregate_atoms() -> None:
    _validator("commons-evidence-envelope-v1.json").validate(_valid_envelope())


def test_envelope_accepts_unknown_action_kind_from_real_aggregate_outcome() -> None:
    rows = aggregate_ledger_records(
        [{"event": "outcome", "outcome": {"resolved": True, "reward": 1.0}}],
        minimum_group_size=1,
    )
    atom = {
        key: value
        for key, value in rows[0].items()
        if key not in {"schema_version", "privacy_profile"}
    }
    assert atom["action_kind"] == "unknown"
    _validator("commons-evidence-envelope-v1.json").validate(
        {"schema_version": "1.0", "model_namespace": NAMESPACES[0], "atoms": [atom]}
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"idempotency_key": "a" * 32}),
        lambda value: value.update({"privacy_canary": "customer-acme"}),
        lambda value: value.update({"url": "https://example.invalid/private"}),
        lambda value: value.update({"path": "/private/customer/acme"}),
        lambda value: value.update({"sha256": "a" * 64}),
        lambda value: value["atoms"][0].update({"metadata": {"canary": "customer-acme"}}),
        lambda value: value["atoms"][0].update({"url": "https://example.invalid/private"}),
        lambda value: value["atoms"][0].update({"path": "/private/customer/acme"}),
        lambda value: value["atoms"][0].update({"sha256": "a" * 64}),
        lambda value: value.update({"model_namespace": "openai/gpt-5.6-sol-custom"}),
        lambda value: value.update({"model_namespace": "https://example.invalid/model"}),
        lambda value: value.update({"atoms": []}),
        lambda value: value["atoms"][0].update({"action_kind": "customer-acme"}),
        lambda value: value["atoms"][0].update({"reason_code": "https://example.invalid/reason"}),
        lambda value: value["atoms"][0].update({"count": 1001}),
        lambda value: value["atoms"][0].update({"minimum_group_size": 1001}),
    ],
)
def test_envelope_rejects_unsafe_or_out_of_contract_values(mutate: object) -> None:
    payload = _valid_envelope()
    mutate(payload)  # type: ignore[operator]
    _assert_invalid(_validator("commons-evidence-envelope-v1.json"), payload)


@pytest.mark.parametrize("key", ["a" * 31, "a" * 65, "a" * 32 + "+", "a" * 31 + "="])
def test_idempotency_key_header_is_base64url_and_bounded(key: str) -> None:
    assert IDEMPOTENCY_KEY_PATTERN.fullmatch(key) is None


@pytest.mark.parametrize("key", ["a" * 32, "_" * 64])
def test_idempotency_key_header_accepts_base64url_boundary_lengths(key: str) -> None:
    assert IDEMPOTENCY_KEY_PATTERN.fullmatch(key) is not None


def test_idempotency_key_is_not_an_envelope_property() -> None:
    _assert_invalid(
        _validator("commons-evidence-envelope-v1.json"),
        {**_valid_envelope(), "Idempotency-Key": "a" * 32},
    )


def test_marginal_root_and_packaged_contract_mirrors_are_byte_identical() -> None:
    for name in (
        "commons-evidence-envelope-v1.json",
        "commons-pack-v1.json",
    ):
        assert (ROOT / "schemas" / name).read_bytes() == (
            ROOT / "src" / "marginal" / "schemas" / name
        ).read_bytes()


def test_registry_contains_only_the_reviewed_exact_model_mapping() -> None:
    registry = json.loads((ROOT / "models" / "canonical-model-registry-v1.json").read_text())
    assert registry == {
        "schema_version": "1.0",
        "models": {
            "gpt-5.6-sol": "openai/gpt-5.6-sol",
            "gpt-5.6-terra": "openai/gpt-5.6-terra",
            "gpt-5.6-luna": "openai/gpt-5.6-luna",
        },
    }


def test_contract_digest_fixtures_detect_schema_and_registry_drift() -> None:
    envelope_digest = (ROOT / "schemas" / "commons-evidence-envelope-v1.sha256").read_text().strip()
    assert (
        hashlib.sha256(
            (ROOT / "schemas" / "commons-evidence-envelope-v1.json").read_bytes()
        ).hexdigest()
        == envelope_digest
    )
    assert not (ROOT / "schemas" / "commons-contract-v1.manifest.json").exists()
    manifest = json.loads((ROOT / "contracts" / "commons-contract-v1.manifest.json").read_text())
    for name, expected in manifest["sha256"].items():
        base = ROOT / ("models" if name.startswith("canonical-model") else "schemas")
        assert hashlib.sha256((base / name).read_bytes()).hexdigest() == expected


def test_pack_rejects_noncanonical_or_open_content() -> None:
    pack = {
        "schema_version": "1.0",
        "source_commit": "a" * 40,
        "commons_revision": 1,
        "compatibility": {"evidence_envelope_schema_version": "1.0"},
        "models": {
            namespace: {"aggregates": [{**_valid_atom(), "lifecycle": "candidate"}]}
            for namespace in NAMESPACES
        },
        "integrity": {"sha256": "b" * 64},
    }
    validator = _validator("commons-pack-v1.json")
    validator.validate(pack)
    for mutation in (
        lambda value: value.update({"metadata": "customer-acme"}),
        lambda value: value.update({"source_commit": "A" * 40}),
        lambda value: value["compatibility"].update({"url": "https://example.invalid"}),
        lambda value: value["models"].update({"custom/model": {"aggregates": []}}),
        lambda value: value["integrity"].update({"sha256": "b" * 63}),
    ):
        candidate = copy.deepcopy(pack)
        mutation(candidate)
        _assert_invalid(validator, candidate)
