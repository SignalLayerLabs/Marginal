from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from marginal.receipts import (
    DecisionReceipt,
    GovernanceCost,
    ProgressEvidence,
    ProgressLevel,
    decision_receipt_hash,
    receipt_payload,
    verify_decision_receipt,
)

ROOT = Path(__file__).resolve().parents[1]


def _cost() -> GovernanceCost:
    return GovernanceCost(
        wall_clock_ms=12.5,
        cpu_ms=None,
        memory_peak_bytes=None,
        storage_bytes=0,
        tokens=0,
        model_calls=0,
        additional_tool_calls=1,
    )


def _receipt(*, decision_hash: str = "") -> DecisionReceipt:
    return DecisionReceipt(
        schema_version="1.0",
        decision_id="decision-1",
        timestamp="2026-08-14T12:00:00+00:00",
        context={"repository": "repo-identity", "agent": "unknown"},
        decision="deny",
        reason_code="no_progress",
        state_hash=None,
        evidence_hash=None,
        trajectory_hash="trajectory-digest",
        policy_hash="policy-digest",
        decision_hash=decision_hash,
        confidence=0.8,
        expected_utility=None,
        estimated_cost=None,
        enforcement_level="tool_gate",
        trust_snapshot={"eligible_authority": "tool_gate", "observed": 3},
        governance_cost=_cost(),
    )


def test_receipt_hash_binds_the_canonical_payload_and_detects_tampering() -> None:
    """Catches verifying a stale hash after an applied decision has been edited."""

    unsigned = _receipt()
    receipt = replace(unsigned, decision_hash=decision_receipt_hash(unsigned))

    assert verify_decision_receipt(receipt)
    assert not verify_decision_receipt(replace(receipt, decision="allow"))


def test_receipt_payload_keeps_unavailable_measurements_explicit_and_mappings_immutable() -> None:
    """Catches omitting unavailable evidence or retaining a caller-mutable attestation map."""

    unsigned = _receipt()
    receipt = replace(unsigned, decision_hash=decision_receipt_hash(unsigned))
    payload = receipt_payload(receipt)

    assert payload["state_hash"] is None
    assert payload["evidence_hash"] is None
    assert payload["expected_utility"] is None
    assert payload["governance_cost"]["cpu_ms"] is None
    with pytest.raises(TypeError):
        receipt.context["repository"] = "changed"  # type: ignore[index]


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("nan")])
def test_receipts_and_progress_evidence_reject_invalid_confidence(confidence: float) -> None:
    """Catches accepting confidence outside the bounded, finite evidence scale."""

    with pytest.raises(ValueError):
        replace(_receipt(), confidence=confidence)
    with pytest.raises(ValueError):
        ProgressEvidence(
            schema_version="1.0",
            level=ProgressLevel.ACTIVITY,
            state_hash="state-digest",
            evidence_hash="evidence-digest",
            confidence=confidence,
            verifier=None,
        )


def test_receipt_rejects_values_that_cannot_be_canonically_attested() -> None:
    """Catches silently coercing arbitrary object representations into a decision receipt."""

    with pytest.raises(TypeError):
        replace(_receipt(), expected_utility={"score": object()})


@pytest.mark.parametrize(
    "field",
    ["prompt_hash", "promptHash", "raw_command", "raw_output"],
)
def test_receipt_rejects_qualified_private_payload_keys(field: str) -> None:
    """Catches persisting private payloads behind qualified or camel-case field names."""

    with pytest.raises(ValueError, match="raw private payload"):
        replace(_receipt(), expected_utility={field: "must-not-persist"})


@pytest.mark.parametrize(
    "decision_hash",
    ["é" * 64, "not-a-sha256-digest", "g" * 64, "a" * 63],
)
def test_malformed_decision_hash_verifies_false_without_raising(decision_hash: str) -> None:
    """Catches untrusted malformed receipt hashes escaping verification as exceptions."""

    assert not verify_decision_receipt(_receipt(decision_hash=decision_hash))


def test_real_receipt_and_progress_examples_validate_against_published_schemas() -> None:
    """Catches schema drift that rejects the values emitted by the public receipt models."""

    unsigned = _receipt()
    receipt = replace(unsigned, decision_hash=decision_receipt_hash(unsigned))
    progress = ProgressEvidence(
        schema_version="1.0",
        level=ProgressLevel.VERIFIED_PROGRESS,
        state_hash="state-digest",
        evidence_hash="evidence-digest",
        confidence=1.0,
        verifier="test-suite",
    )

    for name, example in (
        ("decision-receipt-v1.json", receipt_payload(receipt)),
        ("progress-evidence-v1.json", progress.payload()),
    ):
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(example)
