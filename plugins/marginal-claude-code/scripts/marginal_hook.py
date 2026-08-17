#!/usr/bin/env python3
"""Dependency-free launcher for the MARGINAL Claude Code hook.

The launcher never installs anything and never fails a hook. If the ``marginal``
package cannot be imported, it exits 0 with no output and Claude Code proceeds
exactly as if MARGINAL were not present.

Resolution order:

1. ``MARGINAL_RUNTIME`` — a directory or zipapp added to ``sys.path``;
2. ``runtime/marginal_runtime.pyz`` bundled next to this script, when present;
3. the ambient interpreter's own ``marginal`` installation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _candidate_paths() -> list[str]:
    candidates: list[str] = []
    override = os.environ.get("MARGINAL_RUNTIME")
    if override:
        candidates.append(override)
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    root = Path(plugin_root) if plugin_root else Path(__file__).resolve().parent.parent
    bundled = root / "runtime" / "marginal_runtime.pyz"
    if bundled.is_file():
        candidates.append(str(bundled))
    return candidates


def main() -> int:
    if sys.version_info < (3, 10):  # noqa: UP036 - plugin bootstrap must fail open on unsupported Python
        return 0
    for candidate in _candidate_paths():
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    try:
        from marginal.integrations.claude_code.service import hook_main
    except Exception:
        return 0
    try:
        return hook_main([])
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
