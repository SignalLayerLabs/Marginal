from __future__ import annotations

from pathlib import Path

from marginal.diagnostics import (
    decision_explanation,
    doctor_report,
    inspect_privacy,
    status_report,
)
from marginal.integrations.codex.evidence import EvidenceStore
from marginal.integrations.codex.identity import current_promotion_identity


def test_status_exposes_only_observed_authority_trust_and_exact_blockers(tmp_path: Path) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    data_root = tmp_path / "data"
    identity = current_promotion_identity(workspace, codex_version="test")
    store = EvidenceStore(data_root / "evidence" / identity.repository_hash)
    store.append(
        {
            "schema_version": 1,
            "event": "decision",
            "session_hash": "session",
            "action_hash": "decision-1",
            "semantic_key": "repeat",
            "state_hash": "state",
            "evidence_hash": "evidence",
            "outcome": "success",
            "reason_code": "APPROVED",
            "latency_ms": 4.0,
            "covered": True,
            "coverable": True,
            "recommended_stop": False,
            "reviewed": False,
            "false_stop": False,
            "pending": False,
        }
    )

    report = status_report(data_root=data_root, workspace=workspace)
    payload = report.to_dict()

    assert payload["authority"]["current"] == "L0"
    assert payload["authority"]["eligible"] == "L0"
    assert payload["trust"]["components"]["coverage_ratio"] == 1.0
    assert "MINIMUM_ACTIONS" in payload["next_promotion_blockers"]
    assert payload["ledger"]["valid"] is True
    assert payload["counters"] == {"avoided_actions": 0, "recoveries": 0}


def test_decision_explanation_is_deterministic_and_uses_redacted_evidence(tmp_path: Path) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    data_root = tmp_path / "data"
    identity = current_promotion_identity(workspace, codex_version="test")
    EvidenceStore(data_root / "evidence" / identity.repository_hash).append(
        {
            "schema_version": 1,
            "event": "decision",
            "session_hash": "session",
            "action_hash": "decision-1",
            "semantic_key": "repeat",
            "state_hash": "state",
            "evidence_hash": "evidence",
            "reason_code": "NO_PROGRESS_RECOMMENDED_UNKNOWN",
            "latency_ms": 4.0,
            "covered": True,
            "coverable": True,
            "recommended_stop": True,
            "reviewed": False,
            "false_stop": False,
            "pending": True,
        }
    )

    first = decision_explanation("decision-1", data_root=data_root, workspace=workspace).to_dict()
    second = decision_explanation("decision-1", data_root=data_root, workspace=workspace).to_dict()

    assert first == second
    assert first["found"] is True
    assert first["reason_code"] == "NO_PROGRESS_RECOMMENDED_UNKNOWN"
    assert "command" not in first
    assert "prompt" not in first


def test_privacy_inspection_lists_persisted_categories_and_exclusions() -> None:
    payload = inspect_privacy().to_dict()

    assert payload["persisted_categories"] == [
        "derived_enums",
        "counts_and_metrics",
        "pseudonymous_hashes",
        "integrity_receipts",
    ]
    assert "prompt" in payload["never_persisted"]
    assert "credentials" in payload["never_persisted"]


def test_status_reports_unvalidated_enforcement_as_configured_but_not_effective(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    data_root = tmp_path / "data"
    identity = current_promotion_identity(workspace)
    state_path = data_root / "repositories" / f"{identity.repository_hash}.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        '{"mode":"enforce","receipt_hash":"missing","schema_version":1}\n',
        encoding="utf-8",
    )

    payload = status_report(data_root=data_root, workspace=workspace).to_dict()

    assert payload["authority"]["configured_mode"] == "enforce"
    assert payload["authority"]["current"] == "L0"
    assert payload["authority"]["effective"] == "L0"
    assert payload["authority"]["effective_blockers"] == ["PROMOTION_RECEIPT_MISSING"]


def test_doctor_checks_schema_policy_provenance_and_all_governance_permissions(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    data_root = tmp_path / "data"
    identity = current_promotion_identity(workspace)
    consent = data_root / "user-config.json"
    consent.parent.mkdir()
    consent.write_text('{"autopilot_consent":true,"schema_version":1}\n', encoding="utf-8")
    consent.chmod(0o600)
    state = data_root / "repositories" / f"{identity.repository_hash}.json"
    state.parent.mkdir()
    state.write_text('{"mode":"shadow","schema_version":1}\n', encoding="utf-8")
    state.chmod(0o600)

    payload = doctor_report(data_root=data_root, workspace=workspace).to_dict()

    assert payload["schemas"]["valid"] is True
    assert payload["effective_policy"]["identity"]["repository_hash"] == identity.repository_hash
    assert payload["effective_policy"]["provenance"]["present"] is True
    assert payload["permissions"]["autopilot_consent"] == "owner_only"
    assert payload["permissions"]["enforcement_state"] == "owner_only"
    assert payload["permissions"]["enforcement_receipt"] == "not_created"
