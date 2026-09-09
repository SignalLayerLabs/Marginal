from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from benchmark.astra.lite.freeze import (
    MANIFEST_FIELDS,
    PUBLIC_SEED,
    FreezeError,
    load_safe_manifest,
)


def _order(instance_id: str) -> str:
    return hashlib.sha256(f"{PUBLIC_SEED}\0{instance_id}".encode()).hexdigest()


def _conditions(instance_id: str) -> list[str]:
    digest = hashlib.sha256(f"{PUBLIC_SEED}\0{instance_id}\0condition".encode()).digest()
    first = "marginal" if digest[-1] & 1 else "baseline"
    return [first, "baseline" if first == "marginal" else "marginal"]


def _row(position: int) -> dict[str, object]:
    instance_id = f"owner__repo-{position:04d}"
    return {
        "instance_id": instance_id,
        "repo": "owner/repo",
        "base_commit": f"{position:040x}",
        "official_image": f"swebench/sweb.eval.x86_64.owner_1776_repo-{position:04d}:latest",
        "problem_hash": hashlib.sha256(instance_id.encode("utf-8")).hexdigest(),
        "schedule_position": position,
        "condition_order": _conditions(instance_id),
    }


def _write_contract(directory: Path, rows: list[dict[str, object]]) -> Path:
    manifest = directory / "task-manifest.jsonl"
    text = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    manifest.write_text(text, encoding="utf-8")
    (directory / "protocol.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset": "SWE-bench/SWE-bench_Lite",
                "dataset_revision": "b0dde1093fe417d83b7184254edf8199c1f0dff5",
                "split": "test",
                "task_count": 300,
                "public_seed": PUBLIC_SEED,
                "task_manifest_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _valid_manifest(tmp_path: Path) -> Path:
    rows = sorted(
        (_row(position) for position in range(300)),
        key=lambda row: _order(str(row["instance_id"])),
    )
    for position, row in enumerate(rows):
        row["schedule_position"] = position
    return _write_contract(tmp_path, rows)


def test_load_safe_manifest_exports_only_the_frozen_solver_safe_contract(tmp_path: Path) -> None:
    tasks = load_safe_manifest(_valid_manifest(tmp_path))

    assert len(tasks) == 300
    assert len({task.instance_id for task in tasks}) == 300
    assert (
        len({(task.instance_id, condition) for task in tasks for condition in task.condition_order})
        == 600
    )
    assert tuple(tasks[0].__dataclass_fields__) == MANIFEST_FIELDS
    assert all(task.schedule_position == position for position, task in enumerate(tasks))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda rows: rows.pop(), "exactly 300"),
        (lambda rows: rows.__setitem__(1, dict(rows[0])), "duplicate"),
        (lambda rows: rows[0].__setitem__("hints_text", "do not expose"), "unsafe fields"),
        (lambda rows: rows[0].__setitem__("base_commit", "not-a-commit"), "base_commit"),
    ],
)
def test_load_safe_manifest_rejects_unsafe_or_incomplete_contracts(
    tmp_path: Path, mutate: object, message: str
) -> None:
    manifest = _valid_manifest(tmp_path)
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    assert callable(mutate)
    mutate(rows)
    _write_contract(tmp_path, rows)

    with pytest.raises(FreezeError, match=message):
        load_safe_manifest(manifest)


def test_load_safe_manifest_rejects_an_altered_manifest_hash(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path)
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    rows[0]["problem_hash"] = "0" * 64
    text = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    manifest.write_text(text, encoding="utf-8")

    with pytest.raises(FreezeError, match="SHA-256"):
        load_safe_manifest(manifest)


def test_load_safe_manifest_rejects_a_schedule_that_does_not_match_the_public_seed(
    tmp_path: Path,
) -> None:
    manifest = _valid_manifest(tmp_path)
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    rows[0]["condition_order"] = list(reversed(rows[0]["condition_order"]))
    _write_contract(tmp_path, rows)

    with pytest.raises(FreezeError, match="condition_order"):
        load_safe_manifest(manifest)
