"""Export attested private Codex runs into verifier-safe SWE-bench evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class EvidenceError(ValueError):
    """Raised when private run artifacts cannot support a public comparison."""


@dataclass(frozen=True, slots=True)
class EvidenceExportConfig:
    raw_root: Path
    output_dir: Path
    task_set: str
    instance_ids: tuple[str, ...]
    task_set_sha256: str
    prompt_template_sha256: str
    source_commit: str
    model: str = "gpt-5.6-sol"
    agent_version: str = "0.147.0"
    timeout_seconds: int = 1800

    def __post_init__(self) -> None:
        if self.task_set not in {"smoke", "canary"}:
            raise ValueError("task_set must be smoke or canary")
        if not self.instance_ids or len(self.instance_ids) != len(set(self.instance_ids)):
            raise ValueError("instance_ids must be non-empty and unique")
        if re.fullmatch(r"[0-9a-f]{64}", self.task_set_sha256) is None:
            raise ValueError("task_set_sha256 must be a SHA-256 digest")
        if re.fullmatch(r"[0-9a-f]{64}", self.prompt_template_sha256) is None:
            raise ValueError("prompt_template_sha256 must be a SHA-256 digest")
        if re.fullmatch(r"[0-9a-f]{40}", self.source_commit) is None:
            raise ValueError("source_commit must be a commit SHA")


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid or missing artifact: {path}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"artifact must contain an object: {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _validated_run(
    config: EvidenceExportConfig,
    instance_id: str,
    condition: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    run_dir = config.raw_root / instance_id / condition
    record = _object(run_dir / "run-record.json")
    provenance = _object(run_dir / "run-provenance.json")
    if record.get("instance_id") != instance_id or record.get("condition") != condition:
        raise EvidenceError(f"run identity mismatch: {instance_id}/{condition}")
    if record.get("run_status") != "completed" or record.get("error_code") is not None:
        raise EvidenceError(f"run is not completed: {instance_id}/{condition}")
    if record.get("resolved") is not None:
        raise EvidenceError("resolved must remain verifier-owned before export")
    if provenance.get("source_commit") != config.source_commit:
        raise EvidenceError(f"source commit mismatch: {instance_id}/{condition}")
    patch_path = run_dir / "model.patch"
    try:
        patch_bytes = patch_path.read_bytes()
        patch = patch_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise EvidenceError(f"model patch is unavailable or non-UTF-8: {patch_path}") from exc
    if hashlib.sha256(patch_bytes).hexdigest() != record.get("patch_sha256"):
        raise EvidenceError(f"patch digest mismatch: {instance_id}/{condition}")
    tokens = record.get("tokens")
    if not isinstance(tokens, dict) or not isinstance(tokens.get("total"), int):
        raise EvidenceError(f"token telemetry missing: {instance_id}/{condition}")
    return record, provenance, patch


def export_evidence(config: EvidenceExportConfig) -> Path:
    """Export matched predictions/metrics and public provenance in frozen order."""

    output = config.output_dir.resolve()
    if output.exists():
        raise EvidenceError(f"output directory already exists: {output}")
    output.mkdir(parents=True)
    predictions: dict[str, list[dict[str, Any]]] = {"baseline": [], "marginal": []}
    metrics: dict[str, list[dict[str, Any]]] = {"baseline": [], "marginal": []}
    public_records: list[dict[str, Any]] = []
    task_provenance: list[dict[str, Any]] = []

    for instance_id in config.instance_ids:
        lane_provenance: dict[str, dict[str, Any]] = {}
        for condition in ("baseline", "marginal"):
            record, provenance, patch = _validated_run(config, instance_id, condition)
            lane_provenance[condition] = provenance
            governance = record.get("governance")
            interventions = record.get("interventions")
            if not isinstance(governance, dict) or not isinstance(interventions, dict):
                raise EvidenceError(f"accounting objects missing: {instance_id}/{condition}")
            predictions[condition].append(
                {
                    "instance_id": instance_id,
                    "model_name_or_path": config.model,
                    "model_patch": patch,
                }
            )
            metrics[condition].append(
                {
                    "instance_id": instance_id,
                    "tokens": int(record["tokens"]["total"]),
                    "latency_ms": int(record["wall_time_ms"]),
                    "tool_calls": int(record["tool_calls"]),
                    "repeated_calls": int(record["repeated_calls"]),
                    "usd": 0.0,
                    "governance_tokens": int(governance.get("tokens", 0)),
                    "governance_usd": float(governance.get("usd", 0.0)),
                    "governance_latency_ms": round(float(governance.get("latency_ms", 0.0))),
                    "reviewed_stops": int(interventions.get("reviewed", 0)),
                    "false_stops": int(interventions.get("false_stops", 0)),
                    "applied_denies": int(interventions.get("applied_denies", 0)),
                }
            )
            public_records.append(record)
        baseline_provenance = lane_provenance["baseline"]
        marginal_provenance = lane_provenance["marginal"]
        for field in ("base_commit", "task_image", "prompt_sha256"):
            if baseline_provenance.get(field) != marginal_provenance.get(field):
                raise EvidenceError(f"lane provenance mismatch for {instance_id}: {field}")
        task_provenance.append(
            {
                "instance_id": instance_id,
                "base_commit": baseline_provenance["base_commit"],
                "task_image": baseline_provenance["task_image"],
                "baseline_overlay_image": baseline_provenance["overlay_image"],
                "marginal_overlay_image": marginal_provenance["overlay_image"],
                "prompt_sha256": baseline_provenance["prompt_sha256"],
            }
        )

    manifest = {
        "schema_version": 1,
        "benchmark": "swe-bench-lite-dev-canary",
        "dataset": "princeton-nlp/SWE-bench_Lite",
        "split": "dev",
        "task_set": config.task_set,
        "task_set_sha256": config.task_set_sha256,
        "agent": "codex-cli",
        "agent_version": config.agent_version,
        "model": config.model,
        "prompt_sha256": config.prompt_template_sha256,
        "limits": {"timeout_seconds": config.timeout_seconds, "repetitions": 1},
        "marginal": {
            "version": "0.2.0+unreleased",
            "commit": config.source_commit,
            "mode": "enforce",
            "policy": "balanced+diminishing-defaults",
        },
    }
    _write_json(output / "manifest.json", manifest)
    for condition in ("baseline", "marginal"):
        _write_jsonl(output / f"{condition}_predictions.ndjson", predictions[condition])
        _write_jsonl(output / f"{condition}_metrics.ndjson", metrics[condition])
    _write_jsonl(output / "run-records.ndjson", public_records)
    _write_json(output / "provenance.json", {"tasks": task_provenance})
    return output
