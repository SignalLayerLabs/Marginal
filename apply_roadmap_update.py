#!/usr/bin/env python3
"""Apply the approved MARGINAL roadmap update to a repository checkout."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys


README_MARKER = """The next validation milestone is a public benchmark across real agent frameworks and task
sets, measuring cost per verified outcome rather than cost alone.

## Documentation
"""

README_REPLACEMENT = """The next validation milestone is a public benchmark across real agent frameworks and task
sets, measuring cost per verified outcome rather than cost alone.

## Roadmap

MARGINAL `v0.1.0` established the dependency-free reference allocator. Development is now
focused on **v0.2 — Universal Agent Foundation**: one shared protocol and local runtime for
Codex, Claude Code, GitHub Copilot, OpenCode, and future compatible development agents.

The next measured milestone is a paired Codex evaluation comparing the same model, tasks,
tools, limits, and verifier with and without MARGINAL, using real token telemetry and
quality-preservation criteria.

[View the full product roadmap →](ROADMAP.md)

## Documentation
"""


def main() -> int:
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    readme = repo / "README.md"
    source_roadmap = Path(__file__).with_name("ROADMAP.md")
    target_roadmap = repo / "ROADMAP.md"

    if not readme.is_file():
        raise SystemExit(f"README.md not found in {repo}")
    if not source_roadmap.is_file():
        raise SystemExit(f"ROADMAP.md not found beside {Path(__file__).name}")

    current = readme.read_text(encoding="utf-8")
    if "[View the full product roadmap →](ROADMAP.md)" in current:
        raise SystemExit("README.md already contains the roadmap section")
    if README_MARKER not in current:
        raise SystemExit("README insertion marker not found; review README changes manually")

    updated = current.replace(README_MARKER, README_REPLACEMENT, 1)
    readme.write_text(updated, encoding="utf-8")
    if source_roadmap.resolve() != target_roadmap.resolve():
        shutil.copyfile(source_roadmap, target_roadmap)
        roadmap_message = f"Created {target_roadmap}"
    else:
        roadmap_message = f"Using existing {target_roadmap}"

    print(f"Updated {readme}")
    print(roadmap_message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
