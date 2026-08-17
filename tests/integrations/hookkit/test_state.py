import subprocess
from pathlib import Path

from marginal.integrations.hookkit.state import workspace_state_hash


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(repo),
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        },
    )


def _repository(root: Path, *, commit: bool = True) -> Path:
    _git(root, "init", "-q")
    (root / "tracked.txt").write_text("first\n", encoding="utf-8")
    if commit:
        _git(root, "add", "tracked.txt")
        _git(root, "commit", "-qm", "initial")
    return root


def test_state_hash_is_stable_for_an_unchanged_workspace(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    assert workspace_state_hash(repo) == workspace_state_hash(repo)
    assert len(workspace_state_hash(repo)) == 64


def test_state_hash_changes_when_tracked_content_changes(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    before = workspace_state_hash(repo)
    (repo / "tracked.txt").write_text("second\n", encoding="utf-8")
    assert workspace_state_hash(repo) != before


def test_state_hash_changes_when_untracked_content_changes(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    before = workspace_state_hash(repo)
    (repo / "untracked.txt").write_text("new\n", encoding="utf-8")
    assert workspace_state_hash(repo) != before


def test_a_repository_without_commits_is_still_observable(tmp_path: Path) -> None:
    repo = _repository(tmp_path, commit=False)
    first = workspace_state_hash(repo)
    assert first != ""
    (repo / "untracked.txt").write_text("new\n", encoding="utf-8")
    assert workspace_state_hash(repo) != first


def test_a_subdirectory_resolves_to_its_work_tree(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    nested = repo / "nested"
    nested.mkdir()
    assert workspace_state_hash(nested) == workspace_state_hash(repo)


def test_state_is_unobservable_outside_a_repository(tmp_path: Path) -> None:
    assert workspace_state_hash(tmp_path / "not-a-repository") == ""


def test_ignored_directories_do_not_change_state(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    before = workspace_state_hash(repo)
    marginal_state = repo / ".marginal"
    marginal_state.mkdir()
    (marginal_state / "ledger.jsonl").write_text("{}\n", encoding="utf-8")
    assert workspace_state_hash(repo) == before
