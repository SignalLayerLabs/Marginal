from __future__ import annotations

import subprocess
from pathlib import Path

from marginal.integrations.codex.state import workspace_state_hash


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repository(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-qm", "initial")
    return tmp_path


def test_state_hash_changes_for_material_workspace_progress(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    before = workspace_state_hash(repo)

    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")

    assert workspace_state_hash(repo) != before


def test_state_hash_ignores_governor_and_codex_runtime_data(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    before = workspace_state_hash(repo)

    for directory in (".marginal", ".codex", ".venv", "__pycache__"):
        target = repo / directory
        target.mkdir()
        (target / "runtime.json").write_text("changed\n", encoding="utf-8")

    assert workspace_state_hash(repo) == before


def test_state_hash_rejects_non_repository(tmp_path: Path) -> None:
    try:
        workspace_state_hash(tmp_path)
    except ValueError as exc:
        assert "usable Git repository" in str(exc)
    else:
        raise AssertionError("non-repository path was accepted")
