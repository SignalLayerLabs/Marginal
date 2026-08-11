from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from benchmark.codex_adapter.evidence import EvidenceError, EvidenceExportConfig, export_evidence

_SOURCE = "c" * 40
_PROMPT = "d" * 64
_TASK_SET = "e" * 64


def _raw_run(root: Path, instance_id: str, condition: str, tokens: int) -> None:
    run = root / instance_id / condition
    run.mkdir(parents=True)
    patch = f"diff --git a/{instance_id}.py b/{instance_id}.py\n"
    (run / "model.patch").write_text(patch)
    record = {
        "schema_version": 1,
        "instance_id": instance_id,
        "condition": condition,
        "repetition": 1,
        "run_status": "completed",
        "resolved": None,
        "configuration_sha256": "a" * 64,
        "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
        "tokens": {
            "input": tokens - 10,
            "cached_input": 0,
            "output": 10,
            "reasoning": 2,
            "total": tokens,
        },
        "wall_time_ms": 1000,
        "tool_calls": 2,
        "repeated_calls": 1,
        "interventions": {
            "recommended_denies": int(condition == "marginal"),
            "applied_denies": int(condition == "marginal"),
            "reviewed": 0,
            "false_stops": 0,
        },
        "governance": {
            "tokens": 0,
            "usd": 0.0,
            "latency_ms": 2.5 if condition == "marginal" else 0.0,
        },
        "error_code": None,
    }
    (run / "run-record.json").write_text(json.dumps(record) + "\n")
    (run / "run-provenance.json").write_text(
        json.dumps(
            {
                "base_commit": "f" * 40,
                "source_commit": _SOURCE,
                "task_image": "swebench/task@sha256:" + "1" * 64,
                "overlay_image": "sha256:" + "2" * 64,
                "prompt_sha256": "3" * 64,
            }
        )
        + "\n"
    )


def _config(tmp_path: Path) -> EvidenceExportConfig:
    raw = tmp_path / "raw"
    for instance_id in ("owner__repo-1", "owner__repo-2"):
        _raw_run(raw, instance_id, "baseline", 100)
        _raw_run(raw, instance_id, "marginal", 80)
    return EvidenceExportConfig(
        raw_root=raw,
        output_dir=tmp_path / "public",
        task_set="smoke",
        instance_ids=("owner__repo-1", "owner__repo-2"),
        task_set_sha256=_TASK_SET,
        prompt_template_sha256=_PROMPT,
        source_commit=_SOURCE,
    )


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_export_maps_attested_pairs_to_predictions_and_metrics(tmp_path: Path) -> None:
    config = _config(tmp_path)

    export_evidence(config)

    baseline = _jsonl(config.output_dir / "baseline_metrics.ndjson")
    marginal = _jsonl(config.output_dir / "marginal_metrics.ndjson")
    predictions = _jsonl(config.output_dir / "marginal_predictions.ndjson")
    assert [row["instance_id"] for row in baseline] == list(config.instance_ids)
    assert [row["tokens"] for row in baseline] == [100, 100]
    assert [row["tokens"] for row in marginal] == [80, 80]
    assert marginal[0]["governance_latency_ms"] == 2
    assert predictions[0]["model_name_or_path"] == "gpt-5.6-sol"
    assert "diff --git" in str(predictions[0]["model_patch"])
    manifest = json.loads((config.output_dir / "manifest.json").read_text())
    assert manifest["marginal"]["commit"] == _SOURCE
    assert manifest["task_set_sha256"] == _TASK_SET


def test_export_rejects_patch_hash_mismatch(tmp_path: Path) -> None:
    config = _config(tmp_path)
    patch = config.raw_root / config.instance_ids[0] / "baseline" / "model.patch"
    patch.write_text("tampered\n")

    with pytest.raises(EvidenceError, match="patch digest"):
        export_evidence(config)


def test_export_rejects_noncompleted_or_wrong_source_run(tmp_path: Path) -> None:
    config = _config(tmp_path)
    provenance_path = config.raw_root / config.instance_ids[0] / "marginal" / "run-provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["source_commit"] = "0" * 40
    provenance_path.write_text(json.dumps(provenance))

    with pytest.raises(EvidenceError, match="source commit"):
        export_evidence(config)
