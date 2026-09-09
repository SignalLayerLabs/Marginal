"""Internal exact-tree snapshot preparation shared by Astra solver lanes."""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True, slots=True)
class SnapshotProvenance:
    original_base_commit: str
    original_base_tree: str
    snapshot_commit: str
    snapshot_tree: str


def _git(
    worktree: Path,
    *args: str,
    env: dict[str, str] | None = None,
    text: bool = True,
    input_data: str | bytes | None = None,
) -> str | bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=worktree,
        env=env,
        capture_output=True,
        check=False,
        text=text,
        input=input_data,
        timeout=120,
    )
    if completed.returncode != 0:
        stderr = completed.stderr if text else completed.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr.strip()}")
    return completed.stdout


def _remove_tracked_files(worktree: Path) -> None:
    raw = _git(worktree, "ls-files", "-z", text=False)
    assert isinstance(raw, bytes)
    tracked = raw.decode("utf-8", errors="surrogateescape").split("\0")
    by_depth = sorted(
        (item for item in tracked if item), key=lambda item: item.count("/"), reverse=True
    )
    for relative in by_depth:
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts:
            raise RuntimeError(f"unsafe tracked path: {relative!r}")
        target = worktree.joinpath(*pure.parts)
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            with contextlib.suppress(OSError):
                target.rmdir()


def _extract_archive(archive: Path, worktree: Path) -> None:
    completed = subprocess.run(
        ["tar", "-xf", str(archive), "-C", str(worktree)],
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"base archive extraction failed: {completed.stderr.strip()}")


def _remove_git_metadata(metadata: Path) -> None:
    if metadata.is_dir() and not metadata.is_symlink():
        shutil.rmtree(metadata)
    elif metadata.exists() or metadata.is_symlink():
        metadata.unlink()


def _purge_git_metadata(worktree: Path) -> None:
    for root, directories, files in os.walk(worktree, topdown=True, followlinks=False):
        if ".git" in directories:
            _remove_git_metadata(Path(root) / ".git")
            directories.remove(".git")
        if ".git" in files:
            _remove_git_metadata(Path(root) / ".git")


def prepare_exact_tree(
    worktree: Path,
    base_commit: str,
    *,
    lane_name: str,
) -> SnapshotProvenance:
    """Replace a checkout with one detached commit containing only ``base_commit``'s tree."""

    original_tree = str(_git(worktree, "rev-parse", f"{base_commit}^{{tree}}")).strip()
    base_paths = _git(worktree, "ls-tree", "-r", "-z", "--name-only", base_commit, text=False)
    assert isinstance(base_paths, bytes)
    with tempfile.TemporaryDirectory(prefix=f"marginal-{lane_name.lower()}-base-") as temporary:
        archive = Path(temporary) / "base.tar"
        _git(worktree, "archive", "--format=tar", f"--output={archive}", base_commit)
        _git(worktree, "clean", "-ffd")
        _remove_tracked_files(worktree)
        _extract_archive(archive, worktree)
        _purge_git_metadata(worktree)

    _git(worktree, "init", "-q")
    _git(
        worktree,
        "--literal-pathspecs",
        "add",
        "-f",
        "--pathspec-from-file=-",
        "--pathspec-file-nul",
        text=False,
        input_data=base_paths,
    )
    commit_environment = dict(os.environ)
    commit_environment.update(
        {
            "GIT_AUTHOR_NAME": f"MARGINAL {lane_name.title()} Benchmark",
            "GIT_AUTHOR_EMAIL": "benchmark@example.invalid",
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": f"MARGINAL {lane_name.title()} Benchmark",
            "GIT_COMMITTER_EMAIL": "benchmark@example.invalid",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
        }
    )
    _git(
        worktree,
        "commit",
        "-qm",
        f"frozen SWE-bench {lane_name.title()} base",
        env=commit_environment,
    )
    _git(worktree, "checkout", "--detach", "-q", "HEAD")
    snapshot_commit = str(_git(worktree, "rev-parse", "HEAD")).strip()
    snapshot_tree = str(_git(worktree, "rev-parse", "HEAD^{tree}")).strip()
    if snapshot_tree != original_tree:
        raise RuntimeError(f"snapshot tree mismatch: expected {original_tree}, got {snapshot_tree}")
    if str(_git(worktree, "status", "--porcelain", "--untracked-files=all")):
        raise RuntimeError("fresh task snapshot is not clean")
    if str(_git(worktree, "rev-list", "--count", "--all")).strip() != "1":
        raise RuntimeError("fresh task snapshot contains more than one commit")
    return SnapshotProvenance(
        original_base_commit=base_commit,
        original_base_tree=original_tree,
        snapshot_commit=snapshot_commit,
        snapshot_tree=snapshot_tree,
    )
