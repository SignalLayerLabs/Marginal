"""Validate frozen SWE-bench Lite OFF-vs-ON evidence before paid verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

DATASET = "princeton-nlp/SWE-bench_Lite"
SPLIT = "dev"
BENCHMARK = "swe-bench-lite-dev-canary"

# Frozen from the public Hugging Face dev viewer on 2026-08-07.
ALL_DEV_INSTANCE_IDS = (
    "sqlfluff__sqlfluff-1625",
    "sqlfluff__sqlfluff-2419",
    "sqlfluff__sqlfluff-1733",
    "sqlfluff__sqlfluff-1517",
    "sqlfluff__sqlfluff-1763",
    "marshmallow-code__marshmallow-1359",
    "marshmallow-code__marshmallow-1343",
    "pvlib__pvlib-python-1707",
    "pvlib__pvlib-python-1072",
    "pvlib__pvlib-python-1606",
    "pvlib__pvlib-python-1854",
    "pvlib__pvlib-python-1154",
    "pylint-dev__astroid-1978",
    "pylint-dev__astroid-1333",
    "pylint-dev__astroid-1196",
    "pylint-dev__astroid-1866",
    "pylint-dev__astroid-1268",
    "pyvista__pyvista-4315",
    "pydicom__pydicom-1694",
    "pydicom__pydicom-1413",
    "pydicom__pydicom-901",
    "pydicom__pydicom-1139",
    "pydicom__pydicom-1256",
)


def _sha_rank(instance_id: str) -> str:
    return hashlib.sha256(instance_id.encode("utf-8")).hexdigest()


SMOKE_INSTANCE_IDS = tuple(sorted(ALL_DEV_INSTANCE_IDS, key=_sha_rank)[:3])
CANARY_INSTANCE_IDS = tuple(item for item in ALL_DEV_INSTANCE_IDS if item not in SMOKE_INSTANCE_IDS)

_INTEGER_FIELDS = (
    "tokens",
    "latency_ms",
    "tool_calls",
    "repeated_calls",
    "governance_tokens",
    "governance_latency_ms",
    "reviewed_stops",
    "false_stops",
)
_FLOAT_FIELDS = ("usd", "governance_usd")
_BASELINE_GOVERNANCE_FIELDS = (
    "governance_tokens",
    "governance_usd",
    "governance_latency_ms",
    "reviewed_stops",
    "false_stops",
)
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class ProtocolError(ValueError):
    """Raised when benchmark evidence violates the preregistered protocol."""


def task_ids(task_set: str) -> tuple[str, ...]:
    """Return the frozen instance IDs for ``smoke`` or ``canary``."""

    if task_set == "smoke":
        return SMOKE_INSTANCE_IDS
    if task_set == "canary":
        return CANARY_INSTANCE_IDS
    raise ProtocolError("task_set must be 'smoke' or 'canary'")


def task_set_sha256(task_set: str) -> str:
    """Return a stable digest of the ordered task IDs."""

    payload = "\n".join(task_ids(task_set)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise ProtocolError(f"JSON file must contain an object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProtocolError(f"missing evidence file: {path}") from exc
    for line_number, raw in enumerate(raw_lines, start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(row, dict):
            raise ProtocolError(f"JSONL row must be an object at {path}:{line_number}")
        rows.append(row)
    if not rows:
        raise ProtocolError(f"evidence file is empty: {path}")
    return rows


def _ordered_ids(rows: list[dict[str, Any]], path: Path) -> tuple[str, ...]:
    ids: list[str] = []
    for row in rows:
        instance_id = row.get("instance_id")
        if not isinstance(instance_id, str) or not instance_id:
            raise ProtocolError(f"every row needs a non-empty instance_id: {path}")
        ids.append(instance_id)
    if len(ids) != len(set(ids)):
        raise ProtocolError(f"duplicate instance IDs: {path}")
    return tuple(ids)


def _require_nonnegative_number(row: dict[str, Any], name: str, *, integer: bool) -> None:
    value = row.get(name, 0)
    if isinstance(value, bool):
        raise ProtocolError(f"{name} must be numeric")
    if integer:
        if not isinstance(value, int):
            raise ProtocolError(f"{name} must be an integer")
    elif not isinstance(value, (int, float)):
        raise ProtocolError(f"{name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ProtocolError(f"{name} must be finite and non-negative")


def _validate_metrics(rows: list[dict[str, Any]], lane: str) -> None:
    for row in rows:
        if "resolved" in row:
            raise ProtocolError("resolved is verifier-owned and must not appear in telemetry")
        if "tokens" not in row:
            raise ProtocolError("metrics rows must contain tokens")
        for field in _INTEGER_FIELDS:
            _require_nonnegative_number(row, field, integer=True)
        for field in _FLOAT_FIELDS:
            _require_nonnegative_number(row, field, integer=False)
        if int(row.get("false_stops", 0)) > int(row.get("reviewed_stops", 0)):
            raise ProtocolError("false_stops cannot exceed reviewed_stops")
        baseline_has_governance = any(
            float(row.get(field, 0)) != 0.0 for field in _BASELINE_GOVERNANCE_FIELDS
        )
        if lane == "baseline" and baseline_has_governance:
            raise ProtocolError("baseline governance overhead and stop-review fields must be zero")


def _validate_predictions(rows: list[dict[str, Any]], model: str) -> None:
    for row in rows:
        if row.get("model_name_or_path") != model:
            raise ProtocolError("prediction model_name_or_path must match manifest model")
        patch = row.get("model_patch")
        if not isinstance(patch, str):
            raise ProtocolError("model_patch must be a string; use an empty string for no patch")


def _validate_manifest(manifest: dict[str, Any], expected_task_set: str) -> None:
    expected = {
        "schema_version": 1,
        "benchmark": BENCHMARK,
        "dataset": DATASET,
        "split": SPLIT,
        "task_set": expected_task_set,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise ProtocolError(f"manifest {field} must equal {value!r}")
    for field in ("agent", "agent_version", "model"):
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ProtocolError(f"manifest {field} must be a non-empty string")
    prompt_hash = manifest.get("prompt_sha256")
    if not isinstance(prompt_hash, str) or _HEX_64.fullmatch(prompt_hash) is None:
        raise ProtocolError("manifest prompt_sha256 must be a lowercase SHA-256 hex digest")
    limits = manifest.get("limits")
    if not isinstance(limits, dict) or not limits:
        raise ProtocolError("manifest limits must be a non-empty object")
    marginal = manifest.get("marginal")
    if not isinstance(marginal, dict):
        raise ProtocolError("manifest marginal must be an object")
    for field in ("version", "mode", "policy"):
        value = marginal.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ProtocolError(f"manifest marginal.{field} must be a non-empty string")
    commit = marginal.get("commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ProtocolError("manifest marginal.commit must be a 40-character lowercase git SHA")
    declared_digest = manifest.get("task_set_sha256")
    if declared_digest is not None and declared_digest != task_set_sha256(expected_task_set):
        raise ProtocolError("manifest task_set_sha256 does not match the frozen task set")


def validate_evidence_dir(run_dir: Path, expected_task_set: str) -> tuple[str, ...]:
    """Validate matched prediction + telemetry evidence before Modal spend."""

    expected_ids = task_ids(expected_task_set)
    manifest = _read_json(run_dir / "manifest.json")
    _validate_manifest(manifest, expected_task_set)
    model = str(manifest["model"])

    files = {
        "baseline_predictions": _read_jsonl(run_dir / "baseline_predictions.ndjson"),
        "marginal_predictions": _read_jsonl(run_dir / "marginal_predictions.ndjson"),
        "baseline_metrics": _read_jsonl(run_dir / "baseline_metrics.ndjson"),
        "marginal_metrics": _read_jsonl(run_dir / "marginal_metrics.ndjson"),
    }
    for name, rows in files.items():
        ids = _ordered_ids(rows, run_dir / f"{name}.ndjson")
        if ids != expected_ids:
            raise ProtocolError(
                f"{name} instance IDs/order must exactly match the frozen {expected_task_set} set"
            )

    _validate_predictions(files["baseline_predictions"], model)
    _validate_predictions(files["marginal_predictions"], model)
    _validate_metrics(files["baseline_metrics"], "baseline")
    _validate_metrics(files["marginal_metrics"], "marginal")
    return expected_ids


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ids_parser = sub.add_parser("ids", help="print frozen instance IDs")
    ids_parser.add_argument("--task-set", choices=("smoke", "canary"), required=True)
    validate_parser = sub.add_parser("validate", help="validate an evidence directory")
    validate_parser.add_argument("--task-set", choices=("smoke", "canary"), required=True)
    validate_parser.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "ids":
        print(" ".join(task_ids(args.task_set)))
        return 0
    validate_evidence_dir(args.run_dir, args.task_set)
    print(f"validated {args.task_set}: {len(task_ids(args.task_set))} matched tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
