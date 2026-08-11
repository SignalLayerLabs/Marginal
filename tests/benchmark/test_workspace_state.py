from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from benchmark.codex_adapter.workspace import workspace_state_hash


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "benchmark@example.invalid")
    _git(repo, "config", "user.name", "Benchmark")
    (repo / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "tracked.py")
    _git(repo, "commit", "-qm", "fixture")
    return repo


def test_hash_changes_for_tracked_and_untracked_workspace_content(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    clean = workspace_state_hash(repo)

    (repo / "tracked.py").write_text("VALUE = 2\n", encoding="utf-8")
    tracked_change = workspace_state_hash(repo)
    assert tracked_change != clean

    (repo / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    assert workspace_state_hash(repo) == clean

    (repo / "new.py").write_text("NEW = True\n", encoding="utf-8")
    assert workspace_state_hash(repo) != clean


def test_hash_is_stable_and_ignores_adapter_runtime_files(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = workspace_state_hash(repo)

    runtime = repo / ".codex" / "marginal"
    runtime.mkdir(parents=True)
    (runtime / "events.jsonl").write_text("runtime noise\n", encoding="utf-8")

    assert workspace_state_hash(repo) == before
    assert workspace_state_hash(repo) == before


def test_non_repository_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Git repository"):
        workspace_state_hash(tmp_path)
