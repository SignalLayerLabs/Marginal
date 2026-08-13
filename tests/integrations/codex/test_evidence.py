from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from marginal.integrations.codex.evidence import EvidenceStore, summarize_evidence


def _record() -> dict[str, object]:
    return {
        "schema_version": 1,
        "event": "decision",
        "session_hash": "session-hash",
        "action_hash": "action-hash",
        "semantic_key": "semantic-key",
        "state_hash": "state-hash",
        "evidence_hash": "evidence-hash",
        "outcome": "unknown",
        "reason_code": "ALLOW",
        "latency_ms": 1.25,
        "covered": True,
        "coverable": True,
        "recommended_stop": False,
        "reviewed": False,
        "false_stop": False,
    }


@pytest.mark.parametrize("field", ["tool_input", "tool_response", "prompt", "command", "source"])
def test_store_rejects_raw_payload_fields(tmp_path: Path, field: str) -> None:
    with pytest.raises(ValueError, match="forbidden evidence field"):
        EvidenceStore(tmp_path).append({**_record(), field: "secret"})


def test_store_round_trip_is_canonical_and_private(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    store.append(_record())

    assert store.read_all() == [_record()]
    assert json.loads(store.path.read_text(encoding="utf-8")) == _record()
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_store_rejects_unknown_fields_and_oversized_records(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path, max_record_bytes=256)
    with pytest.raises(ValueError, match="unsupported evidence field"):
        store.append({**_record(), "surprise": True})
    with pytest.raises(ValueError, match="too large"):
        store.append({**_record(), "reason_code": "X" * 1_000})


def test_checkpoint_is_atomic_canonical_and_private(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    checkpoint = {"schema_version": 1, "mode": "shadow", "receipt_hash": "abc"}

    store.write_checkpoint(checkpoint)

    assert store.read_checkpoint() == checkpoint
    assert stat.S_IMODE(store.checkpoint_path.stat().st_mode) == 0o600


def test_redacted_records_build_a_promotion_summary(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    for index in range(100):
        store.append(
            {
                **_record(),
                "session_hash": f"session-{index % 5}",
                "action_hash": f"action-{index}",
                "outcome": "success",
                "latency_ms": 2.0,
                "recommended_stop": index < 5,
                "reviewed": index < 5,
            }
        )
    for index in range(5):
        store.append(
            {
                "schema_version": 1,
                "event": "session_end",
                "session_hash": f"session-{index}",
            }
        )

    summary = summarize_evidence(store.read_all())

    assert summary.covered_actions == 100
    assert summary.coverable_actions == 100
    assert summary.completed_sessions == 5
    assert summary.reviewed_candidates == 5
    assert summary.false_stops == 0
    assert summary.enforceable_outcomes_observable is True


def test_new_window_preserves_audit_history_but_requires_fresh_evidence(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    store.append(
        {
            "schema_version": 1,
            "event": "integration_failure",
            "reason_code": "SERVICE_UNAVAILABLE",
            "integration_failure": True,
        }
    )

    store.start_new_window(reason_code="SERVICE_UNAVAILABLE")

    records = store.read_all()
    summary = summarize_evidence(records)
    assert any(record.get("integration_failure") is True for record in records)
    assert records[-1]["event"] == "window_start"
    assert summary.integration_failures == 0
    assert summary.covered_actions == 0
