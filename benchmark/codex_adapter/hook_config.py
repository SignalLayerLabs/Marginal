"""Install the project-local Codex hook declaration used only in the ON lane."""

from __future__ import annotations

import json
import shlex
from pathlib import Path


def install_project_hooks(
    worktree: str | Path,
    *,
    python_executable: str | Path,
    hook_client: str | Path,
    timeout_seconds: int = 60,
) -> Path:
    """Write deterministic synchronous PreToolUse/PostToolUse command hooks."""

    root = Path(worktree).resolve()
    python_path = Path(python_executable).resolve()
    client_path = Path(hook_client).resolve()
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
        raise TypeError("timeout_seconds must be an integer")
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be positive")
    if not root.is_dir():
        raise ValueError(f"worktree is not a directory: {root}")
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
    config_path = root / ".codex" / "hooks.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return config_path
