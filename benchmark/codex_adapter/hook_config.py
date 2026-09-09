"""Install the project-local Codex hook declaration used only in the ON lane."""

from __future__ import annotations

import json
import shlex
from pathlib import Path


def _install_hooks(
    config_path: Path,
    *,
    python_executable: str | Path,
    hook_client: str | Path,
    timeout_seconds: int = 60,
) -> Path:
    python_path = Path(python_executable).resolve()
    client_path = Path(hook_client).resolve()
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
        raise TypeError("timeout_seconds must be an integer")
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be positive")
    if not config_path.parent.is_dir():
        raise ValueError(f"hook config directory does not exist: {config_path.parent}")
    if not python_path.is_file():
        raise ValueError(f"Python executable does not exist: {python_path}")
    if not client_path.is_file():
        raise ValueError(f"hook client does not exist: {client_path}")

    def handler(operation: str) -> dict[str, object]:
        command = shlex.join((str(python_path), str(client_path), operation))
        return {
            "hooks": [
                {
                    "type": "command",
                    "command": command,
                    "timeout": timeout_seconds,
                    "async": False,
                }
            ]
        }

    config = {
        "description": "MARGINAL benchmark adapter; generated per ON-lane task.",
        "hooks": {
            "PreToolUse": [handler("pre")],
            "PostToolUse": [handler("post")],
        },
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return config_path


def install_project_hooks(
    worktree: str | Path,
    *,
    python_executable: str | Path,
    hook_client: str | Path,
    timeout_seconds: int = 60,
) -> Path:
    """Write deterministic synchronous hooks in a project's Codex layer."""

    root = Path(worktree).resolve()
    if not root.is_dir():
        raise ValueError(f"worktree is not a directory: {root}")
    config_dir = root / ".codex"
    config_dir.mkdir(parents=True, exist_ok=True)
    return _install_hooks(
        config_dir / "hooks.json",
        python_executable=python_executable,
        hook_client=hook_client,
        timeout_seconds=timeout_seconds,
    )


def install_codex_home_hooks(
    codex_home: str | Path,
    *,
    python_executable: str | Path,
    hook_client: str | Path,
    timeout_seconds: int = 60,
) -> Path:
    """Write deterministic synchronous hooks in an isolated Codex home."""

    config_dir = Path(codex_home).resolve()
    return _install_hooks(
        config_dir / "hooks.json",
        python_executable=python_executable,
        hook_client=hook_client,
        timeout_seconds=timeout_seconds,
    )
