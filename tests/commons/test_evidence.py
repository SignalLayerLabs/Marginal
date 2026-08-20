from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from marginal.commons.evidence import (
    CommonsEvidenceAtom,
    compile_verified_evidence,
)
from marginal.commons.identity import resolve_canonical_model
from marginal.governance_ledger import GovernanceLedger
from marginal.integrations.codex.evidence import EvidenceStore

CANARY = "privacy-canary-customer-acme-repository-secret"


def _identity(model: str = "gpt-5.6-sol"):
    identity = resolve_canonical_model(provider="openai", model=model)
    assert identity is not None
    return identity


def _decision(namespace: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event": "decision",
        "session_hash": CANARY,
        "action_hash": f"{CANARY}-action",
        "semantic_key": f"{CANARY}-semantic",
        "state_hash": f"{CANARY}-state",
        "evidence_hash": f"{CANARY}-evidence",
        "model_namespace": namespace,
        "action_kind": "tool",
        "cost_bucket": "low",
        "gain_bucket": "medium",
        "recommendation": "allow",
        "applied_decision": "allow",
        "reason_code": "APPROVED",
        "latency_ms": 1.0,
        "covered": True,
        "coverable": True,
        "recommended_stop": False,
        "reviewed": False,
        "false_stop": False,
    }


def _outcome(namespace: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event": "outcome",
        "session_hash": CANARY,
        "action_hash": f"{CANARY}-action",
        "semantic_key": f"{CANARY}-semantic",
        "state_hash": f"{CANARY}-state",
        "evidence_hash": f"{CANARY}-evidence",
        "model_namespace": namespace,
        "outcome": "success",
        "pending": False,
    }


def test_compiler_reads_real_verified_records_and_emits_only_closed_atoms(tmp_path: Path) -> None:
    identity = _identity()
    store = EvidenceStore(tmp_path)
    store.append(_decision(identity.namespace))
    store.append(_outcome(identity.namespace))

    batch = compile_verified_evidence(store, model_identity=identity, minimum_group_size=1)

    assert batch is not None
    assert batch.identity == identity
    assert batch.model_namespace == identity.namespace
    with pytest.raises(ValueError, match="same canonical model"):
        dataclasses.replace(batch, identity=_identity("gpt-5.6-terra"))
    assert [atom.to_dict() for atom in batch.atoms] == [
        {
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
        },
        {
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
    serialized = json.dumps([atom.to_dict() for atom in batch.atoms], sort_keys=True)
    assert CANARY not in serialized
    for forbidden in (
        "hash",
        "prompt",
        "command",
        "path",
        "filename",
        "repository",
        "identity",
        "url",
        "secret",
        "timestamp",
        "pseudonym",
        "metadata",
    ):
        assert forbidden not in serialized.casefold()


def test_atoms_are_immutable_and_counts_are_bounded(tmp_path: Path) -> None:
    identity = _identity()
    store = EvidenceStore(tmp_path)
    for index in range(1_001):
        record = _decision(identity.namespace)
        record["action_hash"] = f"action-{index}"
        store.append(record)

    batch = compile_verified_evidence(store, model_identity=identity, minimum_group_size=1)

    assert batch is not None
    assert len(batch.atoms) == 1
    assert batch.atoms[0].count == 1_000
    with pytest.raises(dataclasses.FrozenInstanceError):
        batch.atoms[0].count = 2  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        batch.identity = _identity("gpt-5.6-terra")  # type: ignore[misc]


def test_compiler_rejects_arbitrary_caller_mappings_and_unverified_chains(tmp_path: Path) -> None:
    identity = _identity()
    with pytest.raises(TypeError, match="EvidenceStore"):
        compile_verified_evidence([_decision(identity.namespace)], model_identity=identity)  # type: ignore[arg-type]

    store = EvidenceStore(tmp_path)
    store.append(_decision(identity.namespace))
    ledger = store.governance_ledger_path
    tampered = ledger.read_text(encoding="utf-8").replace("APPROVED", "DENIED")
    ledger.write_text(tampered, encoding="utf-8")
    assert compile_verified_evidence(store, model_identity=identity, minimum_group_size=1) is None


def test_compiler_fails_closed_on_a_verified_non_record_payload(tmp_path: Path) -> None:
    identity = _identity()
    store = EvidenceStore(tmp_path)
    GovernanceLedger(store.governance_ledger_path).append(
        {"event": "codex_evidence", "evidence": [CANARY, {"nested": CANARY}]}
    )

    assert compile_verified_evidence(store, model_identity=identity, minimum_group_size=1) is None


def test_conflicting_or_wrong_model_attribution_compiles_nothing(tmp_path: Path) -> None:
    sol = _identity("gpt-5.6-sol")
    terra = _identity("gpt-5.6-terra")
    store = EvidenceStore(tmp_path)
    store.append(_decision(sol.namespace))
    store.append(_decision(terra.namespace))

    assert compile_verified_evidence(store, model_identity=sol, minimum_group_size=1) is None
    assert compile_verified_evidence(store, model_identity=None, minimum_group_size=1) is None

    isolated = EvidenceStore(tmp_path / "isolated")
    isolated.append(_decision(sol.namespace))
    assert compile_verified_evidence(isolated, model_identity=terra, minimum_group_size=1) is None


def test_small_groups_are_suppressed_and_boundaries_are_validated(tmp_path: Path) -> None:
    identity = _identity()
    store = EvidenceStore(tmp_path)
    store.append(_decision(identity.namespace))

    assert compile_verified_evidence(store, model_identity=identity) is None
    with pytest.raises(TypeError, match="minimum_group_size"):
        compile_verified_evidence(store, model_identity=identity, minimum_group_size=True)
    with pytest.raises(ValueError, match="between 1 and 1000"):
        compile_verified_evidence(store, model_identity=identity, minimum_group_size=1_001)


def test_local_evidence_rejects_nested_or_unbounded_commons_values(tmp_path: Path) -> None:
    identity = _identity()
    store = EvidenceStore(tmp_path)
    with pytest.raises(ValueError, match="outcome"):
        store.append({**_outcome(identity.namespace), "outcome": {"canary": CANARY}})
    with pytest.raises(ValueError, match="action_kind"):
        store.append({**_decision(identity.namespace), "action_kind": CANARY})
    with pytest.raises(ValueError, match="model_namespace"):
        store.append({**_decision(identity.namespace), "model_namespace": "private/custom-model"})


def test_atom_constructor_accepts_typed_fields_not_arbitrary_nested_values() -> None:
    with pytest.raises(TypeError, match="record_type"):
        CommonsEvidenceAtom(  # type: ignore[arg-type]
            model_identity=_identity(),
            record_type={"canary": CANARY},
            action_kind="tool",
            cost_bucket="low",
            gain_bucket="medium",
            recommendation="allow",
            applied_decision="allow",
            reason_code="APPROVED",
            outcome_class="not_applicable",
            count=1,
            minimum_group_size=1,
        )
