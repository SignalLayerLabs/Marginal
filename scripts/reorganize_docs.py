#!/usr/bin/env python3
"""Reorganize MARGINAL docs while preserving Git history and relative Markdown links."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOVES = {
    "docs/quickstart.md": "docs/getting-started/quickstart.md",
    "docs/concepts.md": "docs/product/concepts.md",
    "docs/architecture.md": "docs/product/architecture.md",
    "docs/faq.md": "docs/product/faq.md",
    "docs/api.md": "docs/reference/api.md",
    "docs/integrations.md": "docs/integrations/overview.md",
    "docs/benchmarking.md": "docs/evaluation/benchmarking.md",
    "docs/public-benchmarks.md": "docs/evaluation/public-benchmarks.md",
    "docs/research.md": "docs/evaluation/research.md",
    "docs/privacy.md": "docs/operations/privacy.md",
    "docs/website.md": "docs/operations/website.md",
    "docs/governance.md": "docs/project/governance.md",
}

LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
TEXT_SUFFIXES = {".md", ".py", ".html", ".yml", ".yaml", ".toml", ".json", ".txt"}
REWRITE_EXCLUSIONS = {
    "MIGRATION_MANIFEST.json",
    "scripts/reorganize_docs.py",
    "scripts/validate_community_hardening.py",
    "scripts/validate_readme_pages.py",
}


def _repo_relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _new_path(path: Path) -> Path:
    relative = _repo_relative(path)
    return ROOT / MOVES.get(relative, relative)


def _rewrite_markdown_links(path: Path, text: str) -> str:
    old_source = path
    new_source = _new_path(path)

    def replace(match: re.Match[str]) -> str:
        label, raw_target = match.groups()
        if raw_target.startswith(("http://", "https://", "mailto:", "#")):
            return match.group(0)
        target_part, hash_mark, fragment = raw_target.partition("#")
        if not target_part or not target_part.lower().endswith(".md"):
            return match.group(0)
        old_target = (old_source.parent / target_part).resolve()
        try:
            old_relative = old_target.relative_to(ROOT).as_posix()
        except ValueError:
            return match.group(0)
        new_target = ROOT / MOVES.get(old_relative, old_relative)
        new_relative = Path(os.path.relpath(new_target, start=new_source.parent)).as_posix()
        rewritten = new_relative + (f"#{fragment}" if hash_mark else "")
        return f"[{label}]({rewritten})"

    return LINK_RE.sub(replace, text)


def _rewrite_exact_paths(path: Path, text: str) -> str:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return text
    for old, new in MOVES.items():
        text = text.replace(old, new)
    return text


def _rewrite_references_before_move() -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if _repo_relative(path) in REWRITE_EXCLUSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = _rewrite_exact_paths(path, text)
        if path.suffix.lower() == ".md":
            updated = _rewrite_markdown_links(path, updated)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def _move(old: str, new: str) -> None:
    source = ROOT / old
    target = ROOT / new
    if target.exists() and not source.exists():
        return
    if source.exists() and target.exists():
        raise RuntimeError(f"both source and target exist: {old} -> {new}")
    if not source.exists():
        raise FileNotFoundError(f"expected documentation source is missing: {old}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if (ROOT / ".git").exists():
        subprocess.run(["git", "mv", old, new], cwd=ROOT, check=True)
    else:
        source.replace(target)


def main() -> int:
    _rewrite_references_before_move()
    for old, new in MOVES.items():
        _move(old, new)
    print(f"Reorganized {len(MOVES)} documentation files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
