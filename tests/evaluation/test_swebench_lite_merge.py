from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.swebench_lite.merge_results import MergeError, merge_results  # noqa: E402


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_merge_uses_verifier_resolved_and_preserves_metrics(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    verifier = tmp_path / "verifier.jsonl"
    output = tmp_path / "out.jsonl"
    _write_jsonl(
        metrics,
        [
            {
                "instance_id": "repo__project-1",
                "tokens": 123,
                "usd": 0.02,
                "latency_ms": 500,
                "tool_calls": 3,
                "repeated_calls": 1,
                "governance_tokens": 4,
                "governance_usd": 0.001,
                "governance_latency_ms": 10,
                "reviewed_stops": 1,
                "false_stops": 0,
            }
        ],
    )
    _write_jsonl(verifier, [{"instance_id": "repo__project-1", "resolved": True}])
    merge_results(metrics, verifier, output)
    row = json.loads(output.read_text().strip())
    assert row["resolved"] is True
    assert row["tokens"] == 123
    assert row["governance_tokens"] == 4


def test_merge_supports_nested_report_shape(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    verifier = tmp_path / "verifier.jsonl"
    output = tmp_path / "out.jsonl"
    _write_jsonl(metrics, [{"instance_id": "repo__project-1", "tokens": 10}])
    _write_jsonl(
        verifier,
        [{"instance_id": "repo__project-1", "report": {"resolved": False}}],
    )
    merge_results(metrics, verifier, output)
    row = json.loads(output.read_text().strip())
    assert row["resolved"] is False


def test_merge_rejects_missing_verifier_outcome(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    verifier = tmp_path / "verifier.jsonl"
    output = tmp_path / "out.jsonl"
    _write_jsonl(metrics, [{"instance_id": "repo__project-1", "tokens": 10}])
    _write_jsonl(verifier, [{"instance_id": "repo__project-1", "status": "completed"}])
    try:
        merge_results(metrics, verifier, output)
    except MergeError as exc:
        assert "resolved" in str(exc)
    else:
        raise AssertionError("expected missing verifier outcome to be rejected")


def test_merge_rejects_id_mismatch(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    verifier = tmp_path / "verifier.jsonl"
    output = tmp_path / "out.jsonl"
    _write_jsonl(metrics, [{"instance_id": "repo__project-1", "tokens": 10}])
    _write_jsonl(verifier, [{"instance_id": "repo__project-2", "resolved": True}])
    try:
        merge_results(metrics, verifier, output)
    except MergeError as exc:
        assert "instance IDs" in str(exc)
    else:
        raise AssertionError("expected ID mismatch to be rejected")


def test_merge_rejects_swebench_infrastructure_errors(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.ndjson"
    verifier = tmp_path / "model.run.json"
    output = tmp_path / "out.ndjson"
    _write_jsonl(
        metrics,
        [
            {"instance_id": "repo__project-1", "tokens": 10},
            {"instance_id": "repo__project-2", "tokens": 20},
            {"instance_id": "repo__project-3", "tokens": 30},
        ],
    )
    verifier.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "submitted_ids": [
                    "repo__project-1",
                    "repo__project-2",
                    "repo__project-3",
                ],
                "resolved_ids": ["repo__project-1"],
                "unresolved_ids": ["repo__project-2"],
                "error_ids": ["repo__project-3"],
                "empty_patch_ids": [],
                "incomplete_ids": [],
            }
        ),
        encoding="utf-8",
    )
    try:
        merge_results(metrics, verifier, output)
    except MergeError as exc:
        assert "infrastructure" in str(exc)
        assert "repo__project-3" in str(exc)
    else:
        raise AssertionError("expected verifier infrastructure errors to be rejected")


def test_merge_supports_completed_swebench_aggregate_report(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.ndjson"
    verifier = tmp_path / "model.run.json"
    output = tmp_path / "out.ndjson"
    _write_jsonl(
        metrics,
        [
            {"instance_id": "repo__project-1", "tokens": 10},
            {"instance_id": "repo__project-2", "tokens": 20},
        ],
    )
    verifier.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "submitted_ids": ["repo__project-1", "repo__project-2"],
                "resolved_ids": ["repo__project-1"],
                "unresolved_ids": ["repo__project-2"],
                "error_ids": [],
                "empty_patch_ids": [],
                "incomplete_ids": [],
            }
        ),
        encoding="utf-8",
    )
    merge_results(metrics, verifier, output)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert [row["resolved"] for row in rows] == [True, False]
