"""Deterministically fingerprint the task workspace observed by Codex hooks."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path, PurePosixPath
from typing import Protocol

_IGNORED_PARTS = frozenset(
    {
        ".codex",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
    }
)


def _git(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        timeout=30,
        env={**os.environ, "LC_ALL": "C"},
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"workspace is not a usable Git repository: {detail}")
    return completed.stdout


def _root(path: Path) -> Path:
    if not path.is_dir():
        raise ValueError(f"workspace path is not a directory: {path}")
    output = _git(path, "rev-parse", "--show-toplevel")
    return Path(output.decode("utf-8").strip()).resolve()


def _ignored(relative_path: str) -> bool:
    return bool(_IGNORED_PARTS.intersection(PurePosixPath(relative_path).parts))


def _update_chunk(digest: AnyHash, label: bytes, value: bytes) -> None:
    digest.update(len(label).to_bytes(8, "big"))
    digest.update(label)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


class AnyHash(Protocol):
    """Small structural type substitute compatible with hashlib objects on Python 3.10."""

    def update(self, value: bytes) -> None: ...


def workspace_state_hash(path: str | Path) -> str:
    """Hash HEAD, tracked changes, and material untracked files for one Git worktree."""

    repo = _root(Path(path).resolve())
    head = _git(repo, "rev-parse", "HEAD").strip()
    tracked_diff = _git(repo, "diff", "--binary", "HEAD", "--")
    untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z")

    digest = hashlib.sha256()
    _update_chunk(digest, b"head", head)
    _update_chunk(digest, b"tracked-diff", tracked_diff)
    for encoded_path in sorted(filter(None, untracked.split(b"\0"))):
        relative = encoded_path.decode("utf-8", errors="surrogateescape")
        if _ignored(relative):
            continue
        file_path = repo / relative
        if file_path.is_symlink():
            contents = os.readlink(file_path).encode("utf-8", errors="surrogateescape")
        elif file_path.is_file():
            contents = file_path.read_bytes()
        else:
            continue
        _update_chunk(digest, b"untracked-path", encoded_path)
        _update_chunk(digest, b"untracked-content", contents)
    return digest.hexdigest()
