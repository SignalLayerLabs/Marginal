from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from marginal.integrations.codex.evidence import EvidenceStore


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

