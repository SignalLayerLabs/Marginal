"""Privacy-safe Git workspace evidence for the Codex integration."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Protocol

_IGNORED_PARTS = {
    ".codex",
    ".git",
    ".marginal",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
}


class _Hash(Protocol):
    def update(self, data: bytes, /) -> object: ...

    def hexdigest(self) -> str: ...


def _git(repo: Path, *args: str) -> bytes:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=environment,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ValueError("path is not a usable Git repository")
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
        digest.update(b"untracked\0")
        digest.update(raw_path)
        digest.update(b"\0")
        digest.update(target.read_bytes())
        digest.update(b"\0")


def workspace_state_hash(workspace: str | Path) -> str:
    """Hash material tracked changes and safe untracked content in a Git workspace."""

    repo = Path(workspace).resolve()
    if not repo.is_dir():
        raise ValueError("path is not a usable Git repository")
    root = _git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    if Path(root).resolve() != repo:
        raise ValueError("path must be the root of a usable Git repository")

    digest = hashlib.sha256()
    digest.update(_git(repo, "rev-parse", "HEAD"))
    exclusions = [
        ":(exclude).codex/**",
        ":(exclude).marginal/**",
        ":(exclude).venv/**",
        ":(exclude)**/__pycache__/**",
    ]
    digest.update(_git(repo, "diff", "--binary", "HEAD", "--", ".", *exclusions))
    _update_untracked(digest, repo)
    return digest.hexdigest()
