# Concise README Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 354-line README with a concise, accurate landing page that explains MARGINAL, Codex Autopilot, safety boundaries, evidence limits, and installation in one pass.

**Architecture:** `README.md` remains the single repository landing page. Detailed architecture,
benchmark, privacy, and API material stays in existing linked documents; the README summarizes only
the product contract and current verified behavior.

**Tech Stack:** GitHub-flavored Markdown, repository CLI commands, existing documentation links.

## Global Constraints

- Target 180--220 lines.
- Use one installation section and short, concrete paragraphs.
- Do not claim causal token savings or Full Compute Enforcement.
- Describe effective authority as receipt- and ledger-gated.
- Preserve installation, removal, privacy, compatibility, evidence, contributing, and license information.
- Modify no runtime, policy, benchmark, schema, or Python source files.

---

### Task 1: Rewrite and verify the README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: current Codex commands and behavior documented in `src/marginal/cli.py`,
  `src/marginal/integrations/codex/runtime.py`, and the approved README design.
- Produces: a GitHub landing page with valid repository links and executable commands.

- [x] **Step 1: Record the current size and duplicated structure**

Run:

```bash
wc -l README.md
rg -n '^##|^###' README.md
```

Expected: 354 lines, two Codex installation sections, and theory before the primary usage path.

- [x] **Step 2: Replace the README with the approved structure**

Write these sections in order:

```text
Hero
What MARGINAL does
Install for Codex
How Autopilot works
Control and diagnostics
Enforcement boundary
Privacy and integrity
Measured evidence
Python library
Architecture
Documentation
Contributing
License
```

Keep the historical 0/3 versus 0/3 result and label the 24.93% token difference non-causal.

- [x] **Step 3: Verify product and command claims**

Run:

```bash
rg -n 'Full Compute|24\.93|status|doctor|explain|privacy inspect|read_file|Shadow Mode' README.md
rg -n 'status|doctor|explain|privacy' src/marginal/cli.py
```

Expected: no Full Compute Enforcement claim; commands and safety boundary match the implementation.

- [x] **Step 4: Verify internal links and document quality**

Extract local Markdown links and assert every target exists:

```bash
.venv/bin/python - <<'PY'
import pathlib
import re

root = pathlib.Path.cwd()
text = (root / "README.md").read_text(encoding="utf-8")
missing = []
for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
    if target.startswith(("http://", "https://", "#")):
        continue
    path = target.split("#", 1)[0]
    if path and not (root / path).exists():
        missing.append(path)
if missing:
    raise SystemExit(f"missing README links: {sorted(set(missing))}")
print("README local links: valid")
PY
```

Then run:

```bash
.venv/bin/ruff format --check README.md
git diff --check
wc -l README.md
```

Expected: all local links resolve, formatting and diff checks pass, and length is 180--220 lines.

- [x] **Step 5: Review the diff for slop**

Reject duplicated install commands, vague adjectives, community-response narrative, unsupported
claims, repeated concepts, and paragraphs longer than four sentences.

- [ ] **Step 6: Commit and publish**

```bash
git add README.md docs/superpowers/plans/2026-08-14-readme-rewrite.md
git commit -m "Rewrite README for Codex Autopilot"
git push origin codex/marginal-python-runtime-discovery
```

Wait for PR #18 checks, then merge only when GitHub reports the branch mergeable and required checks
green.
