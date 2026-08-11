from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
from benchmark.codex_adapter.dataset import (
    DatasetError,
    FrozenTask,
    materialize_task,
    render_prompt,
    task_specs_from_viewer,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _manifest(problem: str = "Fix it.") -> dict[str, object]:
    return {
        "schema_version": 1,
        "dataset": "princeton-nlp/SWE-bench_Lite",
        "split": "dev",
        "task_ids": ["owner__repo-1"],
        "task_details": [
            {
                "instance_id": "owner__repo-1",
                "repo": "owner/repo",
                "base_commit": "a" * 40,
                "problem_statement_sha256": _sha(problem),
                "hints_text_sha256": _sha(""),
            }
        ],
    }


def _viewer_row(problem: str = "Fix it.") -> dict[str, object]:
    return {
        "instance_id": "owner__repo-1",
        "repo": "owner/repo",
        "base_commit": "a" * 40,
        "problem_statement": problem,
        "hints_text": "",
        "patch": "SECRET GOLD PATCH",
        "test_patch": "SECRET GOLD TEST",
    }


def test_viewer_rows_are_allowlisted_and_hash_verified() -> None:
    tasks = task_specs_from_viewer(_manifest(), [_viewer_row()])

    assert tasks == (
        FrozenTask(
            instance_id="owner__repo-1",
            repo="owner/repo",
            base_commit="a" * 40,
            problem_statement="Fix it.",
            hints_text="",
        ),
    )
    assert not hasattr(tasks[0], "patch")
    assert "SECRET" not in repr(tasks[0])


def test_duplicate_ids_and_changed_problem_are_rejected() -> None:
    duplicate = _manifest()
    duplicate["task_ids"] = ["owner__repo-1", "owner__repo-1"]
    with pytest.raises(DatasetError, match="duplicate"):
        task_specs_from_viewer(duplicate, [_viewer_row()])

    with pytest.raises(DatasetError, match="problem_statement_sha256"):
        task_specs_from_viewer(_manifest(), [_viewer_row("Changed after freeze")])


def test_prompt_has_exactly_one_frozen_insertion(tmp_path: Path) -> None:
    template = tmp_path / "prompt.txt"
    template.write_text("Before\n{{problem_statement}}\nAfter\n", encoding="utf-8")

    prompt = render_prompt(template, "Issue text")

    assert prompt == "Before\nIssue text\nAfter\n"


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_materialization_fetches_only_base_commit_and_removes_remote(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.email", "benchmark@example.invalid")
    _git(source, "config", "user.name", "Benchmark")
    (source / "code.py").write_text("BASE = True\n", encoding="utf-8")
    _git(source, "add", "code.py")
    _git(source, "commit", "-qm", "base")
    base_commit = _git(source, "rev-parse", "HEAD")
    (source / "gold.py").write_text("SOLUTION = True\n", encoding="utf-8")
    _git(source, "add", "gold.py")
    _git(source, "commit", "-qm", "future solution")

    destination = tmp_path / "task"
    task = FrozenTask("owner__repo-1", "owner/repo", base_commit, "Fix it.", "")
    materialize_task(task, destination, repository_url=f"file://{source}")

    assert _git(destination, "rev-parse", "HEAD") == base_commit
    assert _git(destination, "rev-list", "--all", "--count") == "1"
    assert _git(destination, "remote") == ""
    assert not (destination / "gold.py").exists()
    assert _git(destination, "status", "--porcelain") == ""
