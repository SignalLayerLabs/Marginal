#!/usr/bin/env python3
"""Credential-free install, hook lifecycle, privacy, and removal acceptance test."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CodexPluginSmokeResult:
    installed: bool
    shadow_block_count: int
    hook_coverage: float
    raw_secret_occurrences: int
    removed: bool
    codex_version: str


def _run(
    args: list[str],
    *,
    environment: dict[str, str],
    cwd: Path,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=cwd,
        env=environment,
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(args[:4])}")
    return completed


def _initialize_repository(path: Path, environment: dict[str, str]) -> None:
    path.mkdir(parents=True)
    for args in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "smoke@example.com"],
        ["git", "config", "user.name", "MARGINAL Smoke"],
    ):
        _run(args, environment=environment, cwd=path)
    (path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _run(["git", "add", "tracked.txt"], environment=environment, cwd=path)
    _run(["git", "commit", "-qm", "initial"], environment=environment, cwd=path)


def _hook_payloads(workspace: Path, secret: str) -> list[dict[str, Any]]:
    common: dict[str, Any] = {
        "session_id": "smoke-session",
        "transcript_path": None,
        "cwd": str(workspace),
        "model": "smoke-model",
        "permission_mode": "default",
    }
    tool = {
        **common,
        "turn_id": "smoke-turn",
        "tool_name": "Bash",
        "tool_use_id": "smoke-call",
        "tool_input": {"command": f"echo {secret}", "description": secret},
    }
    return [
        {**common, "hook_event_name": "SessionStart", "source": "startup"},
        {**tool, "hook_event_name": "PreToolUse"},
        {**tool, "hook_event_name": "PostToolUse", "tool_response": {"exit_code": 0}},
        {**common, "hook_event_name": "SessionEnd", "reason": "other"},
    ]


def _count_secret(root: Path, secret: str) -> int:
    occurrences = 0
    if not root.exists():
        return 0
    marker = secret.encode("utf-8")
    for path in root.rglob("*"):
        if path.is_file():
            occurrences += path.read_bytes().count(marker)
    return occurrences


def smoke_plugin(
    *,
    codex: Path,
    isolation_root: Path,
    marketplace: Path,
) -> CodexPluginSmokeResult:
    """Run the public install/remove path without using the caller's Codex home."""

    root = isolation_root.resolve()
    home = root / "home"
    codex_home = root / "codex"
    plugin_data = root / "plugin-data"
    workspace = root / "workspace"
    for directory in (home, codex_home, plugin_data):
        directory.mkdir(parents=True, exist_ok=True)
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "CODEX_HOME": str(codex_home),
        "LANG": "C",
        "LC_ALL": "C",
    }
    _initialize_repository(workspace, environment)
    version = _run([str(codex), "--version"], environment=environment, cwd=root).stdout.strip()
    _run(
        [str(codex), "plugin", "marketplace", "add", str(marketplace), "--json"],
        environment=environment,
        cwd=root,
    )
    add = _run(
        [str(codex), "plugin", "add", "marginal@marginal", "--json"],
        environment=environment,
        cwd=root,
    )
    installed_payload = json.loads(add.stdout)
    plugin_root = Path(installed_payload["installedPath"]).resolve()
    hook_script = plugin_root / "scripts" / "marginal_hook.py"
    hook_environment = {
        "PATH": environment["PATH"],
        "LANG": "C",
        "LC_ALL": "C",
        "PLUGIN_ROOT": str(plugin_root),
        "PLUGIN_DATA": str(plugin_data),
    }

    secret = "MARGINAL_SMOKE_SECRET_7fcd98"
    completed_hooks = 0
    shadow_blocks = 0
    removed = False
    try:
        for payload in _hook_payloads(workspace, secret):
            result = _run(
                [sys.executable, str(hook_script)],
                environment=hook_environment,
                cwd=workspace,
                input_text=json.dumps(payload),
            )
            completed_hooks += 1
            if payload["hook_event_name"] == "PreToolUse" and result.stdout.strip():
                hook_output = json.loads(result.stdout)
                decision = hook_output.get("hookSpecificOutput", {}).get("permissionDecision")
                shadow_blocks += int(decision == "deny")
        connection = plugin_data / "sessions" / "smoke-session.json"
        deadline = time.monotonic() + 2.0
        while connection.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        remove = _run(
            [str(codex), "plugin", "remove", "marginal@marginal", "--json"],
            environment=environment,
            cwd=root,
        )
        removed = json.loads(remove.stdout).get("pluginId") == "marginal@marginal"

    return CodexPluginSmokeResult(
        installed=True,
        shadow_block_count=shadow_blocks,
        hook_coverage=completed_hooks / 4,
        raw_secret_occurrences=_count_secret(plugin_data, secret),
        removed=removed,
        codex_version=version,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, default=Path("codex"))
    parser.add_argument("--isolation-root", type=Path, required=True)
    parser.add_argument("--marketplace", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = smoke_plugin(
        codex=args.codex,
        isolation_root=args.isolation_root,
        marketplace=args.marketplace,
    )
    if args.json:
        print(json.dumps(asdict(result), sort_keys=True))
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
