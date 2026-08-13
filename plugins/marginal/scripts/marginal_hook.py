#!/usr/bin/env python3
"""Tiny dependency-free launcher for the generated MARGINAL runtime."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    plugin_root = os.environ.get("PLUGIN_ROOT")
    plugin_data = os.environ.get("PLUGIN_DATA")
    if not plugin_root or not plugin_data:
        return 0
    runtime = Path(plugin_root).resolve() / "runtime" / "marginal_runtime.pyz"
    if not runtime.is_file():
        return 0
    environment = {
        name: value
        for name in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT")
        if (value := os.environ.get(name)) is not None
    }
    environment["PLUGIN_DATA"] = str(Path(plugin_data).resolve())
    environment["PLUGIN_ROOT"] = str(Path(plugin_root).resolve())
    os.execve(sys.executable, [sys.executable, str(runtime)], environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
