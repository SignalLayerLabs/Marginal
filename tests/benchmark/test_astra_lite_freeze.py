from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from benchmark.astra.lite.freeze import (
    CANONICAL_MANIFEST_SHA256,
    CANONICAL_PROTOCOL,
    CANONICAL_PROTOCOL_SHA256,
    MANIFEST_FIELDS,
    FreezeError,
    _task_from_row,
    load_pinned_test_metadata,
    load_safe_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
LITE = ROOT / "benchmark" / "astra" / "lite"
MANIFEST = LITE / "task-manifest.jsonl"
PROTOCOL = LITE / "protocol.json"


def _copy_contract(tmp_path: Path) -> Path:
    shutil.copy2(MANIFEST, tmp_path / MANIFEST.name)
    shutil.copy2(PROTOCOL, tmp_path / PROTOCOL.name)
    return tmp_path / MANIFEST.name


def test_committed_artifacts_are_the_canonical_full_solver_safe_contract() -> None:
    tasks = load_safe_manifest(MANIFEST)
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))

    assert hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() == CANONICAL_PROTOCOL_SHA256
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == CANONICAL_MANIFEST_SHA256
    assert protocol == CANONICAL_PROTOCOL
    assert len(tasks) == 300
    assert len({task.instance_id for task in tasks}) == 300
    assert (
        len({(task.instance_id, condition) for task in tasks for condition in task.condition_order})
        == 600
    )
    assert tuple(tasks[0].__dataclass_fields__) == MANIFEST_FIELDS


def test_committed_manifest_exactly_matches_pinned_safe_dataset_projection() -> None:
    tasks = load_safe_manifest(MANIFEST)
    projected = load_pinned_test_metadata()

    assert {(task.instance_id, task.repo, task.base_commit) for task in tasks} == {
        (row.instance_id, row.repo, row.base_commit) for row in projected
    }


@pytest.mark.parametrize(
    ("file_name", "mutate", "message"),
    [
        (
            "protocol.json",
            lambda value: value.__setitem__("model", "forged-model"),
            "protocol SHA-256",
        ),
        (
            "task-manifest.jsonl",
            lambda value: value[0].__setitem__("base_commit", "0" * 40),
            "protocol SHA-256",
        ),
    ],
)
def test_loader_rejects_a_changed_artifact_even_when_its_sibling_is_updated(
    tmp_path: Path, file_name: str, mutate: object, message: str
) -> None:
    manifest = _copy_contract(tmp_path)
    assert callable(mutate)
    changed = tmp_path / file_name
    if file_name == "protocol.json":
        value = json.loads(changed.read_text(encoding="utf-8"))
        mutate(value)
        changed.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    else:
        rows = [json.loads(line) for line in changed.read_text(encoding="utf-8").splitlines()]
        mutate(rows)
        text = "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows
        )
        changed.write_text(text, encoding="utf-8")
        protocol = json.loads((tmp_path / "protocol.json").read_text(encoding="utf-8"))
        protocol["task_manifest_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        (tmp_path / "protocol.json").write_text(
            json.dumps(protocol, sort_keys=True), encoding="utf-8"
        )

    with pytest.raises(FreezeError, match=message):
        load_safe_manifest(manifest)


def test_malformed_condition_order_raises_freeze_error() -> None:
    row = json.loads(MANIFEST.read_text(encoding="utf-8").splitlines()[0])
    row["condition_order"] = [["baseline"], "marginal"]

    with pytest.raises(FreezeError, match="condition_order"):
        _task_from_row(row)
