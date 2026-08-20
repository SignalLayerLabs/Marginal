"""Typed, privacy-safe reports shared by the user-facing diagnostics commands."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .commons.config import CommonsMode, load_commons_config
from .commons.identity import is_canonical_namespace
from .commons.sync import SyncFailure
from .governance_ledger import GovernanceLedger
from .integrations.codex.evidence import (
    EvidenceStore,
    summarize_evidence,
    summarize_verified_evidence,
)
from .integrations.codex.identity import current_promotion_identity
from .integrations.codex.installer import inspect_codex
from .integrations.codex.promotion import (
    PromotionCriteria,
    PromotionIdentity,
    evaluate_promotion,
    read_promotion_receipt,
)
from .integrations.codex.service import _COMMONS_INGRESS_ORIGIN, read_mode

_PERSISTED_CATEGORIES = (
    "derived_enums",
    "counts_and_metrics",
    "pseudonymous_hashes",
    "integrity_receipts",
)
_NEVER_PERSISTED = (
    "prompt",
    "prompt_hash",
    "source",
    "command",
    "tool_input",
    "tool_response",
    "transcript",
    "credentials",
    "auth",
)
_BENCHMARK_BLOCKERS = (
    "BENCHMARK_EXECUTION_BACKEND_UNAVAILABLE",
    "BENCHMARK_EVIDENCE_DAG_NOT_IMPLEMENTED",
)


@dataclass(frozen=True, slots=True)
class StatusReport:
    """A complete local state snapshot; all values originate in local evidence."""

    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return dict(self.payload)


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """A read-only health report that augments the status report with runtime checks."""

    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return dict(self.payload)


@dataclass(frozen=True, slots=True)
class DecisionExplanationReport:
    """The deterministic, redacted explanation for one persisted decision."""

    decision_id: str
    found: bool
    reason_code: str
    decision: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        base: dict[str, object] = {
            "decision_id": self.decision_id,
            "found": self.found,
            "reason_code": self.reason_code,
        }
        if self.decision is not None:
            base["decision"] = dict(self.decision)
        return base


@dataclass(frozen=True, slots=True)
class PrivacyInspectionReport:
    """The local persistence contract, without inspecting user content."""

    commons: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        commons = self.commons or {
            "mode": CommonsMode.LOCAL_ONLY.value,
            "endpoint": _COMMONS_INGRESS_ORIGIN,
            "model_namespace": None,
            "sharing_allowed": False,
            "safe_queue_count": 0,
            "last_sync_status": "not_attempted",
            "cache_revision": None,
            "schema_version": "1.0",
        }
        return {
            "persisted_categories": list(_PERSISTED_CATEGORIES),
            "never_persisted": list(_NEVER_PERSISTED),
            "local_only": commons["mode"] == CommonsMode.LOCAL_ONLY.value,
            "commons": dict(commons),
            "dictionary_attack_limit": (
                "Derived hashes can reveal low-entropy inputs to a party with local ledger access."
            ),
        }


def status_report(
    *,
    data_root: str | Path,
    workspace: str | Path,
    plugin_root: str | Path | None = None,
) -> StatusReport:
    """Build the shared status surface without executing repository code."""

    root = Path(data_root).resolve()
    selected_workspace = Path(workspace).resolve()
    identity = current_promotion_identity(selected_workspace, plugin_root=plugin_root)
    evidence_store = EvidenceStore(root / "evidence" / identity.repository_hash)
    summary, ledger = summarize_verified_evidence(evidence_store)
    raw_records = _safe_records(evidence_store)
    if not ledger.valid:
        summary = summarize_evidence(raw_records)
    receipt = evaluate_promotion(
        summary,
        PromotionCriteria(),
        identity=identity,
        evidence_root=ledger.root_hash if ledger.valid else "",
        ledger_records=ledger.records,
        ledger_path=evidence_store.governance_ledger_path,
    )
    state = read_mode(root, repository_hash=identity.repository_hash)
    counters = _autopilot_counters(root, identity.repository_hash)
    active_sessions, stale_sessions = _active_session_counts(root, identity.repository_hash)
    hooks_observed = any(
        record.get("event") in {"session_start", "decision", "outcome", "session_end"}
        for record in raw_records
    )
    hooks_active = active_sessions > 0
    configured_mode = _configured_mode(state)
    effective_level, effective_blockers = _effective_authority(
        root,
        identity,
        configured_mode=configured_mode,
        ledger_path=evidence_store.governance_ledger_path,
    )
    eligible_level = "L3" if receipt.is_ready else "L0"
    coverage_ratio = (
        summary.covered_actions / summary.coverable_actions if summary.coverable_actions else 0.0
    )
    trust_components: dict[str, int | float | bool] = {
        "covered_actions": summary.covered_actions,
        "coverable_actions": summary.coverable_actions,
        "coverage_ratio": coverage_ratio,
        "completed_sessions": summary.completed_sessions,
        "reviewed_candidates": summary.reviewed_candidates,
        "intervention_candidates": summary.intervention_candidates,
        "false_stops": summary.false_stops,
        "integration_failures": summary.integration_failures,
        "pending_actions": summary.pending_actions,
        "unknown_enforceable_outcomes": summary.unknown_enforceable_outcomes,
        "enforceable_outcomes_observable": summary.enforceable_outcomes_observable,
    }
    payload: dict[str, object] = {
        **state,
        "capability": "Tool Enforcement",
        "repository_hash": identity.repository_hash,
        "hook_state": "active"
        if hooks_active
        else "observed"
        if hooks_observed
        else "not_observed",
        "hooks_observed": hooks_observed,
        "hooks_active": hooks_active,
        "active_hook_sessions": active_sessions,
        "stale_session_receipts": stale_sessions,
        "evidence_records": _evidence_record_count(evidence_store),
        "covered_actions": summary.covered_actions,
        "coverable_actions": summary.coverable_actions,
        "coverage_ratio": coverage_ratio,
        "authority": {
            "configured_mode": configured_mode,
            "current": effective_level,
            "effective": effective_level,
            "effective_blockers": list(effective_blockers),
            "eligible": eligible_level,
            "ceiling": "L3",
        },
        "trust": {"components": trust_components},
        "next_promotion_blockers": list(receipt.blocking_reasons),
        "ledger": {
            "valid": ledger.valid,
            "records": ledger.records,
            "root_hash": ledger.root_hash,
            "first_invalid_sequence": ledger.first_invalid_sequence,
            "error_codes": list(ledger.error_codes),
        },
        "plugin_runtime_provenance": _runtime_provenance(plugin_root),
        "permissions": _permissions(root, evidence_store, identity.repository_hash),
        "benchmark_readiness": {"ready": False, "blocking_reasons": list(_BENCHMARK_BLOCKERS)},
        "counters": counters,
    }
    return StatusReport(payload)


def doctor_report(
    *, data_root: str | Path, workspace: str | Path, plugin_root: str | Path | None = None
) -> DoctorReport:
    """Combine public Codex capability discovery with the same typed local status."""

    runtime = inspect_codex().to_dict()
    root = Path(data_root).resolve()
    selected_workspace = Path(workspace).resolve()
    identity = current_promotion_identity(selected_workspace, plugin_root=plugin_root)
    evidence_store = EvidenceStore(root / "evidence" / identity.repository_hash)
    state = read_mode(root, repository_hash=identity.repository_hash)
    configured_mode = _configured_mode(state)
    effective_level, effective_blockers = _effective_authority(
        root,
        identity,
        configured_mode=configured_mode,
        ledger_path=evidence_store.governance_ledger_path,
    )
    provenance = _runtime_provenance(plugin_root)
    return DoctorReport(
        {
            **runtime,
            "status": status_report(
                data_root=data_root, workspace=workspace, plugin_root=plugin_root
            ).to_dict(),
            "schemas": _schema_validation(),
            "effective_policy": {
                "configured_mode": configured_mode,
                "effective": effective_level == "L3",
                "identity": asdict(identity),
                "provenance": provenance,
                "blocking_reasons": list(effective_blockers),
            },
            "permissions": _permissions(root, evidence_store, identity.repository_hash),
        }
    )


def decision_explanation(
    decision_id: str,
    *,
    data_root: str | Path,
    workspace: str | Path,
    plugin_root: str | Path | None = None,
) -> DecisionExplanationReport:
    """Find one action hash in verified evidence and expose only its allowed fields."""

    if not isinstance(decision_id, str) or not decision_id:
        raise ValueError("decision_id must be a non-empty string")
    identity = current_promotion_identity(Path(workspace).resolve(), plugin_root=plugin_root)
    store = EvidenceStore(Path(data_root).resolve() / "evidence" / identity.repository_hash)
    records, ledger = store.verified_records()
    if not ledger.valid:
        reason = (
            "EVIDENCE_INTEGRITY_INVALID"
            if store.governance_ledger_path.exists()
            else "DECISION_NOT_FOUND"
        )
        return DecisionExplanationReport(decision_id, False, reason)
    for record in records:
        if record.get("event") != "decision" or record.get("action_hash") != decision_id:
            continue
        decision: dict[str, object] = {
            key: record[key]
            for key in (
                "action_hash",
                "semantic_key",
                "state_hash",
                "evidence_hash",
                "outcome",
                "reason_code",
                "latency_ms",
                "covered",
                "coverable",
                "recommended_stop",
                "reviewed",
                "false_stop",
                "pending",
            )
            if key in record
        }
        return DecisionExplanationReport(
            decision_id,
            True,
            str(record.get("reason_code", "UNSPECIFIED")),
            decision,
        )
    return DecisionExplanationReport(decision_id, False, "DECISION_NOT_FOUND")


def inspect_privacy(*, data_root: str | Path | None = None) -> PrivacyInspectionReport:
    if data_root is None:
        return PrivacyInspectionReport()
    root = Path(data_root).resolve()
    try:
        configured_mode = load_commons_config(root).mode
    except Exception:
        configured_mode = CommonsMode.LOCAL_ONLY
    try:
        raw = json.loads((root / "commons" / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    try:
        mode = CommonsMode.parse(raw.get("mode", configured_mode.value))
    except (TypeError, ValueError):
        mode = configured_mode
    namespace = raw.get("model_namespace")
    if not is_canonical_namespace(namespace):
        namespace = None
    queue_count = raw.get("safe_queue_count")
    if (
        isinstance(queue_count, bool)
        or not isinstance(queue_count, int)
        or not 0 <= queue_count <= 100
    ):
        queue_count = 0
    revision = raw.get("cache_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        revision = None
    sync_status = raw.get("last_sync_status")
    allowed_statuses = {"not_attempted", "ok"} | {failure.value for failure in SyncFailure}
    if not isinstance(sync_status, str) or any(
        part not in allowed_statuses for part in sync_status.split("+")
    ):
        sync_status = "not_attempted"
    commons = {
        "mode": mode.value,
        "endpoint": _COMMONS_INGRESS_ORIGIN,
        "model_namespace": namespace,
        "sharing_allowed": mode is CommonsMode.CONTRIBUTOR and namespace is not None,
        "safe_queue_count": queue_count,
        "last_sync_status": sync_status,
        "cache_revision": revision,
        "schema_version": "1.0",
    }
    return PrivacyInspectionReport(commons)


def render_human(payload: dict[str, object]) -> str:
    """Render any typed report with a stable, readable, content-free representation."""

    return "\n".join(f"{key}: {_human_value(value)}" for key, value in payload.items()) + "\n"


def _human_value(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _safe_records(store: EvidenceStore) -> list[dict[str, Any]]:
    try:
        return store.read_all()
    except (OSError, ValueError, json.JSONDecodeError):
        return []


def _evidence_record_count(store: EvidenceStore) -> int:
    return len(_safe_records(store))


def _active_session_counts(root: Path, repository_hash: str) -> tuple[int, int]:
    from .integrations.codex.commands import _active_hook_sessions

    return _active_hook_sessions(root, repository_hash=repository_hash)


def _autopilot_counters(root: Path, repository_hash: str) -> dict[str, int]:
    path = root / "autopilot" / f"{repository_hash}.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        state = {}
    return {
        "avoided_actions": _non_negative_int(state.get("avoided_actions")),
        "recoveries": _non_negative_int(state.get("recoveries")),
    }


def _non_negative_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _runtime_provenance(plugin_root: str | Path | None) -> dict[str, object]:
    root = (
        Path(plugin_root).resolve() if plugin_root is not None else _plugin_root_from_environment()
    )
    if root is None:
        return {"present": False, "reason": "PLUGIN_ARTIFACT_NOT_DISCOVERED"}
    path = root / "runtime" / "provenance.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"present": False, "reason": "RUNTIME_PROVENANCE_UNAVAILABLE"}
    if not isinstance(payload, dict):
        return {"present": False, "reason": "RUNTIME_PROVENANCE_INVALID"}
    return {"present": True, "provenance": payload}


def _plugin_root_from_environment() -> Path | None:
    configured = os.environ.get("PLUGIN_ROOT")
    if configured:
        return Path(configured).resolve()
    candidate = Path.cwd() / "plugins" / "marginal"
    return candidate if candidate.is_dir() else None


def _effective_authority(
    root: Path,
    identity: PromotionIdentity,
    *,
    configured_mode: str,
    ledger_path: Path,
) -> tuple[str, tuple[str, ...]]:
    """Validate configured enforcement without mutating its persisted state."""

    if configured_mode != "enforce":
        return "L0", ()
    try:
        receipt = read_promotion_receipt(root, identity.repository_hash)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return "L0", ("PROMOTION_RECEIPT_INVALID",)
    if receipt is None:
        return "L0", ("PROMOTION_RECEIPT_MISSING",)
    state = read_mode(root, repository_hash=identity.repository_hash)
    if state.get("receipt_hash") != receipt.receipt_hash:
        return "L0", ("PROMOTION_RECEIPT_STATE_MISMATCH",)
    if not receipt.is_ready or not receipt.verify_hash():
        return "L0", ("PROMOTION_RECEIPT_INVALID",)
    if receipt.identity != identity:
        return "L0", ("POLICY_IDENTITY_MISMATCH",)
    report = GovernanceLedger(ledger_path).verify_prefix(
        receipt.ledger_records,
        expected_root=receipt.evidence_root,
    )
    if not report.valid or report.root_hash != receipt.evidence_root:
        return "L0", ("EVIDENCE_PREFIX_INVALID",)
    return "L3", ()


def _configured_mode(state: dict[str, Any]) -> str:
    value = state.get("mode")
    return value if isinstance(value, str) else "shadow"


def _schema_validation() -> dict[str, object]:
    root = Path(__file__).resolve().parents[2] / "schemas"
    packaged = Path(__file__).resolve().parent / "schemas"
    root_names = {path.name for path in root.glob("*.json")}
    packaged_names = {path.name for path in packaged.glob("*.json")}
    names = sorted(root_names | packaged_names)
    errors: list[str] = []
    for name in names:
        root_path = root / name
        packaged_path = packaged / name
        if not root_path.is_file():
            errors.append(f"ROOT_SCHEMA_MISSING:{name}")
            continue
        if not packaged_path.is_file():
            errors.append(f"PACKAGED_SCHEMA_MISSING:{name}")
            continue
        try:
            root_schema = json.loads(root_path.read_text(encoding="utf-8"))
            packaged_schema = json.loads(packaged_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            errors.append(f"SCHEMA_JSON_INVALID:{name}")
            continue
        if not isinstance(root_schema, dict) or not isinstance(packaged_schema, dict):
            errors.append(f"SCHEMA_NOT_OBJECT:{name}")
        elif root_schema != packaged_schema:
            errors.append(f"SCHEMA_CONTENT_MISMATCH:{name}")
        elif not isinstance(root_schema.get("$schema"), str):
            errors.append(f"SCHEMA_DIALECT_MISSING:{name}")
    return {"valid": not errors, "names": names, "error_codes": errors}


def _permissions(root: Path, store: EvidenceStore, repository_hash: str) -> dict[str, str]:
    return {
        "data_root": _permission_status(root),
        "evidence": _permission_status(store.path),
        "governance_ledger": _permission_status(store.governance_ledger_path),
        "autopilot_consent": _permission_status(root / "user-config.json"),
        "enforcement_receipt": _permission_status(
            root / "repositories" / f"{repository_hash}.receipt.json"
        ),
        "enforcement_state": _permission_status(root / "repositories" / f"{repository_hash}.json"),
    }


def _permission_status(path: Path) -> str:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return "not_created"
    if os.name != "posix":
        return "platform_not_posix"
    return "owner_only" if mode & 0o077 == 0 else "too_permissive"
