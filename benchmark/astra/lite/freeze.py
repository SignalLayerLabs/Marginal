"""Freeze and validate the solver-safe SWE-bench Lite test manifest.

The manifest deliberately contains no benchmark outcomes, tests, hints, patches, or issue text.
Issue text is hashed while freezing and is acquired later through the isolated task boundary.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PUBLIC_SEED = "81b598cbff3bff863cbbb4a3dea1489ce9dd3f2070e6bf766befb25cd436cd9b"
DATASET = "SWE-bench/SWE-bench_Lite"
DATASET_REVISION = "b0dde1093fe417d83b7184254edf8199c1f0dff5"
TASK_COUNT = 300
CANONICAL_MANIFEST_SHA256 = "7a687df2baf842757e90e4b2805a1cf094e4462b10961ec5e90db48a0c9595f7"
CANONICAL_PROTOCOL_SHA256 = "e0c994a3179fc99a93af84349e7d07ec8a3905a380c2a02ffee2cb5a21bc8ff3"
MANIFEST_FIELDS = (
    "instance_id",
    "repo",
    "base_commit",
    "official_image",
    "problem_hash",
    "schedule_position",
    "condition_order",
)
CANONICAL_PROTOCOL: dict[str, object] = {
    "schema_version": 1,
    "experiment": "astra-swe-bench-lite-full-20260909",
    "status": "frozen_no_test_inference",
    "dataset": DATASET,
    "dataset_revision": DATASET_REVISION,
    "split": "test",
    "task_count": TASK_COUNT,
    "task_manifest_sha256": CANONICAL_MANIFEST_SHA256,
    "manifest_fields": list(MANIFEST_FIELDS),
    "public_seed": PUBLIC_SEED,
    "task_order": "ascending sha256(seed + NUL + instance_id UTF-8)",
    "condition_order": (
        "first condition from low bit of sha256(seed + NUL + instance_id + NUL + condition); "
        "other condition follows"
    ),
    "conditions": ["baseline", "marginal"],
    "repetitions": 1,
    "required_lanes": 600,
    "evaluator_repository": "https://github.com/SWE-bench/SWE-bench",
    "evaluator_commit": "02e7a74ffd0b707aab73d203fe87bdc7c76afc8e",
    "evaluator": "v5 local Docker CLI",
    "marginal_commit": "71c8eae",
    "marginal_product_commit": "71c8eae5ef1321c45c3d5c7aa8af1ffcded719b1",
    "marginal_product_subtree": "8b99ca79a11133117f538add2bf474851183de89",
    "marginal_product_archive_sha256": (
        "2050e4cbe1b233633ed016637a687e4d674aa970338fe5fc24e480cb3e313bbd"
    ),
    "agent": "Codex CLI 0.153.4",
    "model": "gpt-6-astra",
    "reasoning_effort": "medium",
    "timeout_seconds": 900,
    "prompt_path": "benchmark/prompt_template.txt",
    "prompt_sha256": "3a2ced1afb7e9a74176090db264259c52b6ebcf383d787a1030f83ecb6d67416",
    "solver_input": "only issue text and a one-commit base-tree snapshot",
    "solver_prohibitions": [
        "hints",
        "gold patches",
        "benchmark tests",
        "FAIL_TO_PASS",
        "PASS_TO_PASS",
        "evaluator feedback",
        "other lane artifacts",
    ],
    "cost": "zero euros; existing Codex ChatGPT authentication only; no OpenAI API key",
}
_PINNED_TEST_PARQUET = (
    "https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite/resolve/"
    f"{DATASET_REVISION}/data/test-00000-of-00001.parquet"
)

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_INSTANCE_ID = re.compile(r"^[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-[0-9]+$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class FreezeError(ValueError):
    """Raised when a purported frozen contract does not match the public protocol."""


@dataclass(frozen=True, slots=True)
class LiteTask:
    """The complete and intentionally minimal solver-facing task identity."""

    instance_id: str
    repo: str
    base_commit: str
    official_image: str
    problem_hash: str
    schedule_position: int
    condition_order: tuple[str, str]


@dataclass(frozen=True, slots=True)
class LiteSourceMetadata:
    """Safe identity metadata projected from the pinned public dataset."""

    instance_id: str
    repo: str
    base_commit: str


def _sha256(value: str | bytes) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _task_order(instance_id: str) -> str:
    return _sha256(f"{PUBLIC_SEED}\0{instance_id}")


def _condition_order(instance_id: str) -> tuple[str, str]:
    digest = hashlib.sha256(f"{PUBLIC_SEED}\0{instance_id}\0condition".encode()).digest()
    first = "marginal" if digest[-1] & 1 else "baseline"
    return first, "baseline" if first == "marginal" else "marginal"


def official_instance_image(instance_id: str) -> str:
    """Return the public official-image reference for a classic SWE-bench Lite task."""

    if _INSTANCE_ID.fullmatch(instance_id) is None:
        raise FreezeError("instance_id is not a valid SWE-bench Lite instance ID")
    return f"swebench/sweb.eval.x86_64.{instance_id.lower().replace('__', '_1776_')}:latest"


def _require_text(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise FreezeError(f"{field} must be a non-empty string")
    return value


def _task_from_row(row: Mapping[str, Any]) -> LiteTask:
    if set(row) != set(MANIFEST_FIELDS):
        raise FreezeError("manifest contains unsafe fields or is missing required fields")
    instance_id = _require_text(row, "instance_id")
    repo = _require_text(row, "repo")
    base_commit = _require_text(row, "base_commit")
    official_image = _require_text(row, "official_image")
    problem_hash = _require_text(row, "problem_hash")
    position = row.get("schedule_position")
    conditions = row.get("condition_order")
    if _INSTANCE_ID.fullmatch(instance_id) is None:
        raise FreezeError("instance_id is not a valid SWE-bench Lite instance ID")
    if _REPO.fullmatch(repo) is None:
        raise FreezeError("repo is invalid")
    if _COMMIT.fullmatch(base_commit) is None:
        raise FreezeError("base_commit must be a lowercase 40-character SHA")
    if _HASH.fullmatch(problem_hash) is None:
        raise FreezeError("problem_hash must be a lowercase SHA-256")
    if official_image != official_instance_image(instance_id):
        raise FreezeError("official_image does not match the official SWE-bench image reference")
    if isinstance(position, bool) or not isinstance(position, int):
        raise FreezeError("schedule_position must be an integer")
    if (
        not isinstance(conditions, list)
        or len(conditions) != 2
        or not all(isinstance(condition, str) for condition in conditions)
        or set(conditions) != {"baseline", "marginal"}
    ):
        raise FreezeError("condition_order must contain baseline and marginal exactly once")
    return LiteTask(
        instance_id=instance_id,
        repo=repo,
        base_commit=base_commit,
        official_image=official_image,
        problem_hash=problem_hash,
        schedule_position=position,
        condition_order=(conditions[0], conditions[1]),
    )


def _load_protocol(path: Path, manifest_text: str) -> None:
    protocol_path = path.with_name("protocol.json")
    try:
        protocol_text = protocol_path.read_text(encoding="utf-8")
        protocol = json.loads(protocol_text)
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeError(f"protocol is unreadable: {protocol_path}") from exc
    if not isinstance(protocol, dict):
        raise FreezeError("protocol must be a JSON object")
    if _sha256(protocol_text) != CANONICAL_PROTOCOL_SHA256:
        raise FreezeError("protocol SHA-256 does not match the canonical Lite contract")
    if protocol != CANONICAL_PROTOCOL:
        raise FreezeError("protocol does not match the frozen SWE-bench Lite contract")
    if _sha256(manifest_text) != CANONICAL_MANIFEST_SHA256:
        raise FreezeError("manifest SHA-256 does not match the canonical Lite contract")
    prompt_path = Path(__file__).resolve().parents[3] / "benchmark" / "prompt_template.txt"
    try:
        prompt_hash = _sha256(prompt_path.read_bytes())
    except OSError as exc:
        raise FreezeError("pinned benchmark prompt is unreadable") from exc
    if prompt_hash != CANONICAL_PROTOCOL["prompt_sha256"]:
        raise FreezeError("prompt SHA-256 does not match the frozen Lite contract")


def load_pinned_test_metadata() -> tuple[LiteSourceMetadata, ...]:
    """Read only identity columns from the exact pinned Lite test parquet.

    PyArrow decodes solely the named safe columns; hints, patches, tests, and outcome fields are
    neither projected nor returned.
    """

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise FreezeError("PyArrow is required for safe pinned-dataset projection") from exc
    request = urllib.request.Request(_PINNED_TEST_PARQUET, headers={"User-Agent": "marginal/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            parquet = io.BytesIO(response.read())
        table = pq.ParquetFile(parquet).read(columns=["instance_id", "repo", "base_commit"])
    except (OSError, ValueError) as exc:
        raise FreezeError("pinned SWE-bench Lite metadata projection failed") from exc
    metadata: list[LiteSourceMetadata] = []
    for row in table.to_pylist():
        if not isinstance(row, dict):
            raise FreezeError("pinned SWE-bench Lite metadata row is invalid")
        metadata.append(
            LiteSourceMetadata(
                instance_id=_require_text(row, "instance_id"),
                repo=_require_text(row, "repo"),
                base_commit=_require_text(row, "base_commit"),
            )
        )
    if len(metadata) != TASK_COUNT or len({row.instance_id for row in metadata}) != TASK_COUNT:
        raise FreezeError("pinned SWE-bench Lite metadata is not the 300-task test split")
    return tuple(metadata)


def load_safe_manifest(path: str | Path) -> tuple[LiteTask, ...]:
    """Load exactly the verified, public solver-safe 300-task schedule."""

    manifest_path = Path(path)
    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FreezeError(f"manifest is unreadable: {manifest_path}") from exc
    _load_protocol(manifest_path, manifest_text)
    try:
        rows = [json.loads(line) for line in manifest_text.splitlines()]
    except json.JSONDecodeError as exc:
        raise FreezeError("task manifest contains invalid JSON") from exc
    if len(rows) != TASK_COUNT:
        raise FreezeError("task manifest must contain exactly 300 tasks")
    if not all(isinstance(row, dict) for row in rows):
        raise FreezeError("task manifest rows must be JSON objects")
    tasks = tuple(_task_from_row(row) for row in rows)
    ids = [task.instance_id for task in tasks]
    if len(ids) != len(set(ids)):
        raise FreezeError("task manifest contains duplicate instance IDs")
    ordered_ids = sorted(ids, key=_task_order)
    if ids != ordered_ids:
        raise FreezeError("task schedule does not match the public seed")
    for position, task in enumerate(tasks):
        if task.schedule_position != position:
            raise FreezeError("schedule_position does not match the public seed schedule")
        if task.condition_order != _condition_order(task.instance_id):
            raise FreezeError("condition_order does not match the public seed")
    return tasks


def freeze_safe_records(records: Iterable[Mapping[str, Any]]) -> tuple[dict[str, object], ...]:
    """Project allowlisted source columns into rows suitable for the immutable manifest.

    Callers must pass only ``instance_id``, ``repo``, ``base_commit``, and
    ``problem_statement`` values from the pinned dataset. This function neither accepts nor
    returns hints, patches, tests, or evaluator outcome fields.
    """

    rows: list[dict[str, object]] = []
    for record in records:
        allowed = {"instance_id", "repo", "base_commit", "problem_statement"}
        if set(record) != allowed:
            raise FreezeError("freeze input must contain only allowlisted source fields")
        instance_id = _require_text(record, "instance_id")
        repo = _require_text(record, "repo")
        base_commit = _require_text(record, "base_commit")
        problem_statement = _require_text(record, "problem_statement")
        if _REPO.fullmatch(repo) is None or _COMMIT.fullmatch(base_commit) is None:
            raise FreezeError("freeze input has an invalid repository identity")
        rows.append(
            {
                "instance_id": instance_id,
                "repo": repo,
                "base_commit": base_commit,
                "official_image": official_instance_image(instance_id),
                "problem_hash": _sha256(problem_statement),
            }
        )
    if len(rows) != TASK_COUNT or len({str(row["instance_id"]) for row in rows}) != TASK_COUNT:
        raise FreezeError("freeze input must contain exactly 300 unique tasks")
    rows.sort(key=lambda row: _task_order(str(row["instance_id"])))
    for position, row in enumerate(rows):
        instance_id = str(row["instance_id"])
        row["schedule_position"] = position
        row["condition_order"] = list(_condition_order(instance_id))
    return tuple(rows)
