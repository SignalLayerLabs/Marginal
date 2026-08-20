"""Bounded, local-only evidence storage for Codex governance receipts."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from marginal.governance_ledger import GovernanceLedger, LedgerVerificationReport

from .promotion import CoverageSummary

_ALLOWED_EVIDENCE_FIELDS = {
    "schema_version",
    "event",
    "session_hash",
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
    "integration_failure",
    "pending",
    "timestamp",
    "model_namespace",
    "action_kind",
    "cost_bucket",
    "gain_bucket",
    "recommendation",
    "applied_decision",
}
_FORBIDDEN_FIELDS = {
    "auth",
    "command",
    "credential",
    "prompt",
    "prompt_hash",
    "source",
    "tool_input",
    "tool_response",
    "transcript",
}

_COMMONS_FIELD_VALUES = {
    "action_kind": {
        "command",
        "file_read",
        "file_write",
        "generation",
        "llm",
        "model_call",
        "reasoning",
        "research",
        "review",
        "search",
        "subagent",
        "test",
        "tool",
        "verification",
        "unknown",
        "other",
    },
    "cost_bucket": {"low", "medium", "high", "unknown"},
    "gain_bucket": {"low", "medium", "high", "unknown"},
    "recommendation": {"allow", "deny", "unknown", "not_applicable"},
    "applied_decision": {"allow", "deny", "unknown", "not_applicable"},
    "outcome": {"success", "failure", "unknown"},
}


def _validate_commons_fields(record: Mapping[str, Any]) -> None:
    for field, allowed in _COMMONS_FIELD_VALUES.items():
        if field in record:
            value = record[field]
            if not isinstance(value, str) or value not in allowed:
                raise ValueError(f"invalid Commons evidence {field}")
    if "model_namespace" in record:
        from marginal.commons.identity import is_canonical_namespace

        if not is_canonical_namespace(record["model_namespace"]):
            raise ValueError("invalid Commons evidence model_namespace")


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("evidence must be canonical JSON") from exc


class EvidenceStore:
    """Append redacted JSONL records and atomically persist small checkpoints."""

    def __init__(self, root: str | Path, *, max_record_bytes: int = 16_384) -> None:
        if isinstance(max_record_bytes, bool) or not isinstance(max_record_bytes, int):
            raise TypeError("max_record_bytes must be an integer")
        if max_record_bytes < 128:
            raise ValueError("max_record_bytes must be at least 128")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            self.root.chmod(0o700)
        self.path = self.root / "evidence.jsonl"
        self.governance_ledger_path = self.root / "governance-v3.jsonl"
        self._governance_ledger = GovernanceLedger(self.governance_ledger_path)
        self.checkpoint_path = self.root / "checkpoint.json"
        self.max_record_bytes = max_record_bytes

    def append(self, record: Mapping[str, Any]) -> None:
        if not isinstance(record, Mapping):
            raise TypeError("evidence record must be a mapping")
        fields = set(record)
        forbidden = fields & _FORBIDDEN_FIELDS
        if forbidden:
            raise ValueError(f"forbidden evidence field: {sorted(forbidden)[0]}")
        unsupported = fields - _ALLOWED_EVIDENCE_FIELDS
        if unsupported:
            raise ValueError(f"unsupported evidence field: {sorted(unsupported)[0]}")
        _validate_commons_fields(record)
        serialized = _canonical_bytes(record)
        if len(serialized) > self.max_record_bytes:
            raise ValueError("evidence record is too large")
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, serialized + b"\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if os.name == "posix":
            self.path.chmod(0o600)
        self._governance_ledger.append({"event": "codex_evidence", "evidence": dict(record)})

    def verified_governance_root(self) -> LedgerVerificationReport:
        """Return the verified v3 root that can anchor an enforcement receipt."""

        return self._governance_ledger.verify()

    def verifies_governance_prefix(self, *, root_hash: str, records: int) -> bool:
        report = self._governance_ledger.verify_prefix(records, expected_root=root_hash)
        return report.valid and report.root_hash == root_hash

    def verified_records(self) -> tuple[list[dict[str, Any]], LedgerVerificationReport]:
        """Read only the evidence records committed by a verified v3 chain."""

        report, payloads = self._governance_ledger.read_verified_payloads()
        if not report.valid:
            return [], report
        records: list[dict[str, Any]] = []
        for payload in payloads:
            if payload.get("event") != "codex_evidence":
                continue
            evidence = payload.get("evidence")
            if not isinstance(evidence, dict):
                raise ValueError("Codex governance evidence payload is invalid")
            records.append(dict(evidence))
        return records, report

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("evidence record must decode to an object")
                records.append(value)
        return records

    def start_new_window(self, *, reason_code: str) -> None:
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise ValueError("reason_code must be a non-empty string")
        self.append(
            {
                "schema_version": 1,
                "event": "window_start",
                "reason_code": reason_code.strip(),
            }
        )

    def write_checkpoint(self, checkpoint: Mapping[str, Any]) -> None:
        if not isinstance(checkpoint, Mapping):
            raise TypeError("checkpoint must be a mapping")
        serialized = _canonical_bytes(checkpoint)
        if len(serialized) > self.max_record_bytes:
            raise ValueError("checkpoint is too large")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".checkpoint-", suffix=".tmp", dir=self.root
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            os.write(descriptor, serialized + b"\n")
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, self.checkpoint_path)
            if os.name == "posix":
                self.checkpoint_path.chmod(0o600)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)

    def read_checkpoint(self) -> dict[str, Any] | None:
        if not self.checkpoint_path.exists():
            return None
        value = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("checkpoint must decode to an object")
        return value


def summarize_evidence(records: list[dict[str, Any]]) -> CoverageSummary:
    """Reduce redacted evidence into the exact Earned Enforcement gate surface."""

    for index in range(len(records) - 1, -1, -1):
        if records[index].get("event") == "window_start":
            records = records[index + 1 :]
            break

    decisions = [record for record in records if record.get("event") == "decision"]
    completed_sessions = {
        str(record.get("session_hash"))
        for record in records
        if record.get("event") == "session_end" and record.get("session_hash")
    }
    outcomes_by_action = {
        str(record.get("action_hash")): str(record.get("outcome"))
        for record in decisions
        if record.get("outcome") in {"success", "failure", "unknown"} and record.get("action_hash")
    }
    outcomes_by_action.update(
        {
            str(record.get("action_hash")): str(record.get("outcome"))
            for record in records
            if record.get("event") == "outcome" and record.get("action_hash")
        }
    )
    candidates = {
        str(record.get("action_hash"))
        for record in decisions
        if record.get("recommended_stop") is True and record.get("action_hash")
    }
    reviewed = {
        str(record.get("action_hash"))
        for record in records
        if record.get("reviewed") is True and record.get("action_hash") in candidates
    }
    false_stops = {
        str(record.get("action_hash"))
        for record in records
        if record.get("false_stop") is True and record.get("action_hash") in reviewed
    }
    outcomes = [
        outcomes_by_action[str(record.get("action_hash"))]
        for record in decisions
        if str(record.get("action_hash")) in outcomes_by_action
    ]
    unknown_outcomes = sum(outcome == "unknown" for outcome in outcomes)
    latencies = tuple(
        float(record["latency_ms"])
        for record in decisions
        if isinstance(record.get("latency_ms"), (int, float))
        and not isinstance(record.get("latency_ms"), bool)
    )
    return CoverageSummary(
        covered_actions=sum(record.get("covered") is True for record in decisions),
        coverable_actions=sum(record.get("coverable") is True for record in decisions),
        completed_sessions=len(completed_sessions),
        reviewed_candidates=len(reviewed),
        false_stops=len(false_stops),
        integration_failures=sum(record.get("integration_failure") is True for record in records),
        pending_actions=sum(
            record.get("pending") is True
            and str(record.get("action_hash")) not in outcomes_by_action
            for record in decisions
        ),
        unknown_enforceable_outcomes=unknown_outcomes,
        decision_latencies_ms=latencies,
        enforceable_outcomes_observable=bool(outcomes) and unknown_outcomes == 0,
        intervention_candidates=len(candidates),
    )


def summarize_verified_evidence(
    store: EvidenceStore,
) -> tuple[CoverageSummary, LedgerVerificationReport]:
    """Summarize only records cryptographically committed to v3 governance evidence."""

    records, report = store.verified_records()
    return summarize_evidence(records), report
