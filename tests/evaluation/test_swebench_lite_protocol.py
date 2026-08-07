from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.swebench_lite.protocol import (  # noqa: E402
    ALL_DEV_INSTANCE_IDS,
    CANARY_INSTANCE_IDS,
    SMOKE_INSTANCE_IDS,
    ProtocolError,
    validate_evidence_dir,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _make_evidence(tmp_path: Path, ids: tuple[str, ...]) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest = {
        "schema_version": 1,
        "benchmark": "swe-bench-lite-dev-canary",
        "dataset": "princeton-nlp/SWE-bench_Lite",
        "split": "dev",
        "task_set": "canary" if len(ids) == 20 else "smoke",
        "agent": "codex-cli",
        "agent_version": "reference",
        "model": "same-model",
        "prompt_sha256": "a" * 64,
        "limits": {"max_turns": 20, "timeout_seconds": 1800},
        "marginal": {
            "version": "0.2.0+unreleased",
            "commit": "f" * 40,
            "mode": "enforce",
            "policy": "balanced+diminishing-return",
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    predictions = [
        {"instance_id": item, "model_name_or_path": "same-model", "model_patch": ""} for item in ids
    ]
    metrics = [
        {
            "instance_id": item,
            "tokens": 100,
            "usd": 0.01,
            "latency_ms": 1000,
            "tool_calls": 2,
            "repeated_calls": 0,
            "governance_tokens": 0,
            "governance_usd": 0.0,
            "governance_latency_ms": 0,
            "reviewed_stops": 0,
            "false_stops": 0,
        }
        for item in ids
    ]
    _write_jsonl(run_dir / "baseline_predictions.ndjson", predictions)
    _write_jsonl(run_dir / "marginal_predictions.ndjson", predictions)
    _write_jsonl(run_dir / "baseline_metrics.ndjson", metrics)
    _write_jsonl(run_dir / "marginal_metrics.ndjson", metrics)
    return run_dir


def test_frozen_dev_partition_is_complete_and_hash_selected() -> None:
    assert len(ALL_DEV_INSTANCE_IDS) == 23
    assert len(set(ALL_DEV_INSTANCE_IDS)) == 23
    assert len(SMOKE_INSTANCE_IDS) == 3
    assert len(CANARY_INSTANCE_IDS) == 20
    assert set(SMOKE_INSTANCE_IDS).isdisjoint(CANARY_INSTANCE_IDS)
    assert set(SMOKE_INSTANCE_IDS) | set(CANARY_INSTANCE_IDS) == set(ALL_DEV_INSTANCE_IDS)
    expected_smoke = tuple(
        sorted(
            ALL_DEV_INSTANCE_IDS,
            key=lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest(),
        )[:3]
    )
    assert SMOKE_INSTANCE_IDS == expected_smoke


def test_validate_evidence_accepts_matched_canary(tmp_path: Path) -> None:
    run_dir = _make_evidence(tmp_path, CANARY_INSTANCE_IDS)
    validated = validate_evidence_dir(run_dir, "canary")
    assert validated == CANARY_INSTANCE_IDS


def test_validate_evidence_rejects_mismatched_lane_ids(tmp_path: Path) -> None:
    run_dir = _make_evidence(tmp_path, CANARY_INSTANCE_IDS)
    rows = [
        json.loads(line) for line in (run_dir / "marginal_metrics.ndjson").read_text().splitlines()
    ]
    rows.pop()
    _write_jsonl(run_dir / "marginal_metrics.ndjson", rows)
    try:
        validate_evidence_dir(run_dir, "canary")
    except ProtocolError as exc:
        assert "instance IDs" in str(exc)
    else:
        raise AssertionError("expected mismatched IDs to be rejected")


def test_validate_evidence_rejects_baseline_governance_overhead(tmp_path: Path) -> None:
    run_dir = _make_evidence(tmp_path, CANARY_INSTANCE_IDS)
    rows = [
        json.loads(line) for line in (run_dir / "baseline_metrics.ndjson").read_text().splitlines()
    ]
    rows[0]["governance_tokens"] = 1
    _write_jsonl(run_dir / "baseline_metrics.ndjson", rows)
    try:
        validate_evidence_dir(run_dir, "canary")
    except ProtocolError as exc:
        assert "baseline governance" in str(exc)
    else:
        raise AssertionError("expected baseline governance overhead to be rejected")


def test_validate_evidence_rejects_resolved_in_telemetry(tmp_path: Path) -> None:
    run_dir = _make_evidence(tmp_path, CANARY_INSTANCE_IDS)
    rows = [
        json.loads(line) for line in (run_dir / "marginal_metrics.ndjson").read_text().splitlines()
    ]
    rows[0]["resolved"] = True
    _write_jsonl(run_dir / "marginal_metrics.ndjson", rows)
    try:
        validate_evidence_dir(run_dir, "canary")
    except ProtocolError as exc:
        assert "resolved" in str(exc)
    else:
        raise AssertionError("expected telemetry-supplied resolved to be rejected")


def test_validate_evidence_rejects_missing_marginal_identity(tmp_path: Path) -> None:
    run_dir = _make_evidence(tmp_path, CANARY_INSTANCE_IDS)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest.pop("marginal")
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    try:
        validate_evidence_dir(run_dir, "canary")
    except ProtocolError as exc:
        assert "manifest marginal" in str(exc)
    else:
        raise AssertionError("expected missing MARGINAL identity to be rejected")
