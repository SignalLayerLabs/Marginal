#!/usr/bin/env python3
"""Run MARGINAL's bundled control plane against Codex plugin data."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _plugin_data() -> Path:
    configured = os.environ.get("PLUGIN_DATA")
    if configured:
        return Path(configured).expanduser().resolve()
    codex_home = os.environ.get("CODEX_HOME")
    home = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return (home / "plugins" / "data" / "marginal-marginal").resolve()


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] not in {
        "status",
        "doctor",
        "review",
        "promote",
        "demote",
    }:
        print(
            "usage: marginal_control.py {status|doctor|review|promote|demote} [options]",
            file=sys.stderr,
        )
        return 2

    plugin_root = Path(__file__).resolve().parents[1]
    runtime = plugin_root / "runtime" / "marginal_runtime.pyz"
    if not runtime.is_file():
        print(f"MARGINAL runtime not found: {runtime}", file=sys.stderr)
        return 1

    data = _plugin_data()
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = {
        name: value
        for name in ("PATH", "CODEX_HOME", "LANG", "LC_ALL", "SYSTEMROOT")
        if (value := os.environ.get(name)) is not None
    }
    environment["PLUGIN_DATA"] = str(data)
    environment["PLUGIN_ROOT"] = str(plugin_root)
    os.execve(
        sys.executable,
        [
            sys.executable,
            str(runtime),
            "codex",
            arguments[0],
            "--data-dir",
            str(data),
            *arguments[1:],
        ],
        environment,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
