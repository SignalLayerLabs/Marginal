"""Privacy-safe workspace evidence for hook-based integrations.

The hash covers tracked changes against ``HEAD`` plus safe untracked content, so a
repeated action can be recognized as acting on unchanged state. Only the digest is
retained; file names and contents are never persisted.

Unlike the Codex integration, which requires the session directory to be a
repository root, this helper accepts any directory inside a Git work tree and
returns an empty string when state is not observable. An empty state hash makes
every repetition control fail open.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Protocol

_IGNORED_PARTS = frozenset(
    {
        ".claude",
        ".codex",
        ".git",
        ".marginal",
        ".mypy_cache",
        ".opencode",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "node_modules",
    }
)

EMPTY_TREE_OBJECT = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
"""Git's constant empty tree object, used when a repository has no commits yet."""

_EXCLUSIONS = (
    ":(exclude).claude/**",
    ":(exclude).codex/**",
    ":(exclude).marginal/**",
    ":(exclude).opencode/**",
    ":(exclude).venv/**",
    ":(exclude)**/__pycache__/**",
)


class _Hash(Protocol):
    def update(self, data: bytes, /) -> object: ...

    def hexdigest(self) -> str: ...


class WorkspaceNotObservable(RuntimeError):
    """Raised internally when Git cannot describe the workspace."""


def _git(repo: Path, *args: str) -> bytes:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo,
            env=environment,
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise WorkspaceNotObservable("git is not available") from exc
    if completed.returncode != 0:
        raise WorkspaceNotObservable("git could not describe the workspace")
    return completed.stdout


def _ignored(path: str) -> bool:
    return any(part in _IGNORED_PARTS for part in Path(path).parts)


def _update_untracked(digest: _Hash, repo: Path) -> None:
    output = _git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    for raw_path in sorted(filter(None, output.split(b"\0"))):
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if _ignored(path):
            continue
        target = repo / path
        if not target.is_file():
            continue
        try:
            content = target.read_bytes()
        except OSError:
            continue
        digest.update(b"untracked\0")
        digest.update(raw_path)
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")


def _base_revision(repo: Path) -> str:
    """Return the revision to diff against, tolerating a repository with no commits.

    A freshly initialized repository has no ``HEAD``. Diffing against the empty tree
    keeps such a workspace observable instead of discarding all state evidence for
    the whole session.
    """

    try:
        return _git(repo, "rev-parse", "HEAD").decode("utf-8").strip()
    except WorkspaceNotObservable:
        return EMPTY_TREE_OBJECT


def workspace_state_hash(workspace: str | Path) -> str:
    """Return a workspace state digest, or an empty string when unobservable."""

    try:
        directory = Path(workspace).resolve()
    except OSError:
        return ""
    if not directory.is_dir():
        return ""
    try:
        root = _git(directory, "rev-parse", "--show-toplevel").decode("utf-8").strip()
        repo = Path(root).resolve()
        digest = hashlib.sha256()
        base = _base_revision(repo)
        digest.update(base.encode("utf-8"))
        digest.update(_git(repo, "diff", "--binary", base, "--", ".", *_EXCLUSIONS))
        _update_untracked(digest, repo)
    except (WorkspaceNotObservable, OSError, UnicodeDecodeError):
        return ""
    return digest.hexdigest()
