#!/usr/bin/env python3
"""Focused structural checks for the community-evidence hardening overlay."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

required_files = [
    "src/marginal/controls/__init__.py",
    "src/marginal/controls/diminishing.py",
    "src/marginal/controls/governance.py",
    "docs/evaluation/governance-evidence.md",
    "docs/project/community-feedback.md",
    "docs/integrations/codex-benchmark-readiness.md",
    "docs/operations/website-review-2026-08-07.md",
]
missing = [item for item in required_files if not (ROOT / item).is_file()]
assert not missing, f"missing hardening files: {missing}"

public_eval = (ROOT / "src/marginal/public_eval.py").read_text(encoding="utf-8")
for token in [
    "governance_tokens",
    "repeated_calls",
    "false_stops",
    "gross_savings",
    "net_savings",
    '"pass_through"',
    '"false_stop_risk"',
]:
    assert token in public_eval, token

treasury = (ROOT / "src/marginal/treasury.py").read_text(encoding="utf-8")
for token in [
    "GovernanceTracker",
    "record_governance_overhead",
    "record_stop_review",
    "observe_execution",
]:
    assert token in treasury, token

policy = (ROOT / "src/marginal/policy.py").read_text(encoding="utf-8")
for token in ["diminishing_detector", "diminishing.reason_code", "observe_execution"]:
    assert token in policy, token

roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
for token in [
    "Graceful irrelevance",
    "governance tokens",
    "false-stop",
    "10-task",
    "SWE-bench Pro",
]:
    assert token.lower() in roadmap.lower(), token

old_paths = [
    "docs/quickstart.md",
    "docs/concepts.md",
    "docs/architecture.md",
    "docs/api.md",
    "docs/integrations.md",
    "docs/public-benchmarks.md",
]
for old in old_paths:
    legacy_path = ROOT / old
    if not legacy_path.exists():
        continue
    text = legacy_path.read_text(encoding="utf-8")
    if "compatibility shim" in text.lower() and "moved to" in text.lower():
        continue
    assert not legacy_path.exists(), f"old documentation path still exists: {old}"

# Validate local Markdown file links. External links and anchors are intentionally skipped.
link_re = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
errors: list[str] = []
for path in ROOT.rglob("*.md"):
    if ".git" in path.parts:
        continue
    text = path.read_text(encoding="utf-8")
    for raw in link_re.findall(text):
        target = raw.split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (path.parent / target).resolve()
        if not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)} -> {raw}")
assert not errors, "broken Markdown links:\n" + "\n".join(errors[:30])

print("Community hardening structure: PASS")
print("Core evidence hooks: PASS")
print("Documentation migration: PASS")
print("Markdown links: PASS")
