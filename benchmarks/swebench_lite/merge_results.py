"""Merge official SWE-bench per-instance outcomes with measured MARGINAL telemetry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class MergeError(ValueError):
    """Raised when verifier output cannot be matched safely to telemetry."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MergeError(f"cannot read {path}") from exc
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MergeError(f"invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(row, dict):
            raise MergeError(f"JSONL row must be an object at {path}:{line_number}")
        rows.append(row)
    if not rows:
        raise MergeError(f"empty JSONL file: {path}")
    return rows


def _instance_id(row: dict[str, Any]) -> str:
    value = row.get("instance_id")
    if isinstance(value, str) and value:
        return value
    if len(row) == 1:
        key, nested = next(iter(row.items()))
        if isinstance(key, str) and "__" in key and isinstance(nested, dict):
            return key
    raise MergeError("verifier row is missing instance_id")


def _resolved(row: dict[str, Any], instance_id: str) -> bool:
    candidates: list[Any] = [row.get("resolved")]
    for key in ("report", "result"):
        nested = row.get(key)
        if isinstance(nested, dict):
            candidates.append(nested.get("resolved"))
    keyed = row.get(instance_id)
    if isinstance(keyed, dict):
        candidates.append(keyed.get("resolved"))
    boolean_values = [value for value in candidates if isinstance(value, bool)]
    if boolean_values:
        if any(value != boolean_values[0] for value in boolean_values[1:]):
            raise MergeError(f"conflicting resolved outcomes for {instance_id}")
        return boolean_values[0]
    status = row.get("status")
    if status == "resolved":
        return True
    if status == "unresolved":
        return False
    raise MergeError(f"verifier row has no boolean resolved outcome for {instance_id}")


def _index_metrics(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    order: list[str] = []
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        instance_id = row.get("instance_id")
        if not isinstance(instance_id, str) or not instance_id:
            raise MergeError("metrics row is missing instance_id")
        if instance_id in indexed:
            raise MergeError(f"duplicate metrics instance_id: {instance_id}")
        if "resolved" in row:
            raise MergeError("resolved must come from SWE-bench, not metrics")
        order.append(instance_id)
        indexed[instance_id] = row
    return order, indexed


def _index_verifier(rows: list[dict[str, Any]]) -> dict[str, bool]:
    indexed: dict[str, bool] = {}
    for row in rows:
        instance_id = _instance_id(row)
        if instance_id in indexed:
            raise MergeError(f"duplicate verifier instance_id: {instance_id}")
        indexed[instance_id] = _resolved(row, instance_id)
    return indexed


def _index_aggregate_report(report: dict[str, Any]) -> dict[str, bool]:
    submitted = report.get("submitted_ids")
    resolved = report.get("resolved_ids")
    if not isinstance(submitted, list) or not isinstance(resolved, list):
        raise MergeError("aggregate verifier report needs submitted_ids and resolved_ids lists")
    if not all(isinstance(item, str) and item for item in submitted):
        raise MergeError("aggregate submitted_ids must contain non-empty strings")
    if len(submitted) != len(set(submitted)):
        raise MergeError("aggregate submitted_ids contains duplicates")
    if not all(isinstance(item, str) and item for item in resolved):
        raise MergeError("aggregate resolved_ids must contain non-empty strings")
    submitted_set = set(submitted)
    resolved_set = set(resolved)
    if not resolved_set <= submitted_set:
        raise MergeError("aggregate resolved_ids must be a subset of submitted_ids")
    return {instance_id: instance_id in resolved_set for instance_id in submitted}


def _load_verifier(path: Path) -> dict[str, bool]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MergeError(f"cannot read {path}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _index_verifier(_read_jsonl(path))
    if isinstance(parsed, dict) and "submitted_ids" in parsed:
        return _index_aggregate_report(parsed)
    if isinstance(parsed, dict):
        return _index_verifier([parsed])
    raise MergeError("verifier JSON must be an object or newline-delimited objects")


def merge_results(metrics_path: Path, verifier_path: Path, output_path: Path) -> None:
    """Write public-eval rows using verifier-owned ``resolved`` booleans."""

    order, metrics = _index_metrics(_read_jsonl(metrics_path))
    verifier = _load_verifier(verifier_path)
    if set(metrics) != set(verifier):
        missing = sorted(set(metrics) ^ set(verifier))
        raise MergeError(f"metrics and verifier instance IDs differ: {missing[:5]}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        for instance_id in order:
            row = dict(metrics[instance_id])
            row["resolved"] = verifier[instance_id]
            stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--verifier", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    merge_results(args.metrics, args.verifier, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
