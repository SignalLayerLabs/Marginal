"""Frozen SWE-bench Lite task acquisition without exposing gold artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DATASET = "princeton-nlp/SWE-bench_Lite"
_CONFIG = "default"
_SPLIT = "dev"
_VIEWER = "https://datasets-server.huggingface.co"
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class DatasetError(ValueError):
    """Raised when live viewer data no longer matches the preregistered task manifest."""


@dataclass(frozen=True, slots=True)
class FrozenTask:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    hints_text: str


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _text(mapping: dict[str, Any], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str):
        raise DatasetError(f"{field} must be a string")
    return value


def task_specs_from_viewer(
    manifest: dict[str, Any], viewer_rows: list[dict[str, Any]]
) -> tuple[FrozenTask, ...]:
    """Build an allowlisted task tuple after matching every frozen identity and hash."""

    if manifest.get("dataset") != _DATASET or manifest.get("split") != _SPLIT:
        raise DatasetError("dataset and split must match the frozen SWE-bench Lite dev set")
    task_ids = manifest.get("task_ids")
    details = manifest.get("task_details")
    if not isinstance(task_ids, list) or not all(
        isinstance(item, str) and item for item in task_ids
    ):
        raise DatasetError("task_ids must contain non-empty strings")
    if len(task_ids) != len(set(task_ids)):
        raise DatasetError("task_ids contains duplicate IDs")
    if not isinstance(details, list) or not all(isinstance(item, dict) for item in details):
        raise DatasetError("task_details must contain objects")
    detail_ids = [item.get("instance_id") for item in details]
    if detail_ids != task_ids:
        raise DatasetError("task_details order must exactly match task_ids")

    indexed_rows: dict[str, dict[str, Any]] = {}
    for row in viewer_rows:
        instance_id = row.get("instance_id")
        if isinstance(instance_id, str) and instance_id in task_ids:
            if instance_id in indexed_rows:
                raise DatasetError(f"duplicate viewer row: {instance_id}")
            indexed_rows[instance_id] = row
    if set(indexed_rows) != set(task_ids):
        missing = sorted(set(task_ids) - set(indexed_rows))
        raise DatasetError(f"viewer rows are missing frozen tasks: {missing}")

    tasks: list[FrozenTask] = []
    for detail in details:
        instance_id = _text(detail, "instance_id")
        row = indexed_rows[instance_id]
        repo = _text(detail, "repo")
        base_commit = _text(detail, "base_commit")
        problem_hash = _text(detail, "problem_statement_sha256")
        hints_hash = _text(detail, "hints_text_sha256")
        if _REPO.fullmatch(repo) is None:
            raise DatasetError(f"invalid repo for {instance_id}")
        if _HEX_40.fullmatch(base_commit) is None:
            raise DatasetError(f"invalid base_commit for {instance_id}")
        if _HEX_64.fullmatch(problem_hash) is None or _HEX_64.fullmatch(hints_hash) is None:
            raise DatasetError(f"invalid frozen text hash for {instance_id}")
        if row.get("repo") != repo or row.get("base_commit") != base_commit:
            raise DatasetError(f"repository identity changed for {instance_id}")
        problem = _text(row, "problem_statement")
        hints = _text(row, "hints_text")
        if _sha(problem) != problem_hash:
            raise DatasetError(f"problem_statement_sha256 mismatch for {instance_id}")
        if _sha(hints) != hints_hash:
            raise DatasetError(f"hints_text_sha256 mismatch for {instance_id}")
        tasks.append(FrozenTask(instance_id, repo, base_commit, problem, hints))
    return tuple(tasks)


def _viewer_json(endpoint: str, **parameters: str | int) -> Any:
    query = urllib.parse.urlencode(parameters)
    request = urllib.request.Request(
        f"{_VIEWER}/{endpoint}?{query}",
        headers={"User-Agent": "marginal-codex-benchmark/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetError(f"Hugging Face Dataset Viewer {endpoint} request failed") from exc


def fetch_frozen_tasks(manifest_path: str | Path) -> tuple[FrozenTask, ...]:
    """Fetch public dev rows through Dataset Viewer and verify the frozen allowlist."""

    path = Path(manifest_path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetError(f"invalid task manifest: {path}") from exc
    if not isinstance(manifest, dict):
        raise DatasetError("task manifest must be a JSON object")

    validity = _viewer_json("is-valid", dataset=_DATASET)
    if not isinstance(validity, dict) or validity.get("viewer") is not True:
        raise DatasetError("SWE-bench Lite Dataset Viewer is unavailable")
    split_data = _viewer_json("splits", dataset=_DATASET)
    splits = split_data.get("splits") if isinstance(split_data, dict) else None
    if not isinstance(splits, list) or not any(
        isinstance(item, dict) and item.get("config") == _CONFIG and item.get("split") == _SPLIT
        for item in splits
    ):
        raise DatasetError("frozen default/dev split is unavailable")
    row_data = _viewer_json(
        "rows",
        dataset=_DATASET,
        config=_CONFIG,
        split=_SPLIT,
        offset=0,
        length=100,
    )
    wrapped_rows = row_data.get("rows") if isinstance(row_data, dict) else None
    if not isinstance(wrapped_rows, list):
        raise DatasetError("Dataset Viewer rows response is malformed")
    rows: list[dict[str, Any]] = []
    for item in wrapped_rows:
        row = item.get("row") if isinstance(item, dict) else None
        if not isinstance(row, dict):
            raise DatasetError("Dataset Viewer returned a malformed row")
        rows.append(row)
    return task_specs_from_viewer(manifest, rows)


def render_prompt(template_path: str | Path, problem_statement: str) -> str:
    template = Path(template_path).read_text(encoding="utf-8")
    marker = "{{problem_statement}}"
    if template.count(marker) != 1:
        raise DatasetError("prompt template must contain exactly one problem marker")
    if not isinstance(problem_statement, str) or not problem_statement.strip():
        raise DatasetError("problem_statement must not be empty")
    return template.replace(marker, problem_statement)


def _run(command: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        raise DatasetError(f"command failed ({' '.join(command)}): {detail}")
    return completed.stdout.strip()


def materialize_task(
    task: FrozenTask,
    destination: str | Path,
    *,
    repository_url: str | None = None,
) -> Path:
    """Create a detached depth-one checkout containing only the frozen base commit."""

    target = Path(destination).resolve()
    if target.exists():
        raise DatasetError(f"destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()
    url = repository_url or f"https://github.com/{task.repo}.git"
    _run(["git", "init", "-q"], cwd=target)
    _run(["git", "remote", "add", "origin", url], cwd=target)
    _run(
        ["git", "fetch", "--depth", "1", "--filter=blob:none", "origin", task.base_commit],
        cwd=target,
    )
    _run(["git", "checkout", "--detach", "-q", "FETCH_HEAD"], cwd=target)
    actual = _run(["git", "rev-parse", "HEAD"], cwd=target)
    if actual != task.base_commit:
        raise DatasetError(f"materialized commit mismatch: {actual}")
    _run(["git", "remote", "remove", "origin"], cwd=target)
    reachable = _run(["git", "rev-list", "--all", "--count"], cwd=target)
    if reachable != "1":
        raise DatasetError("materialized checkout exposes commits beyond the frozen base")
    if _run(["git", "status", "--porcelain"], cwd=target):
        raise DatasetError("materialized checkout is not clean")
    return target
