# Community Evidence Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add model-independent repetition control, MARGINAL self-accounting, net-value benchmark evidence, community decision transparency, an evidence-first website and a clean documentation structure without claiming a completed Codex integration.

**Architecture:** New optional controls live in `src/marginal/controls`; existing policy and treasury APIs receive backward-compatible additive hooks. Public evaluation keeps old input rows valid while treating governance overhead as part of effective cost. Documentation is reorganized with history-preserving moves and the website remains static/dependency-free.

**Tech Stack:** Python 3.10–3.13 standard library, pytest, Ruff, mypy, static HTML/CSS/JS, GitHub Actions.

## Global Constraints

- Provider neutral; no GPT-5.6 or Markdown-specific runtime branch.
- Zero mandatory runtime dependencies.
- No fabricated benchmark numbers.
- False stops require explicit review labels.
- Diminishing-return enforcement remains opt-in until representative evidence exists.
- Codex adapter remains a v0.3 target, not a completed capability.

---

### Task 1: State-aware diminishing-return control

**Files:**
- Create: `src/marginal/controls/diminishing.py`
- Create: `src/marginal/controls/__init__.py`
- Modify: `src/marginal/policy.py`
- Modify: `src/marginal/treasury.py`
- Test: `tests/controls/test_diminishing.py`
- Test: `tests/controls/test_policy_diminishing.py`

**Interfaces:**
- Produces: `DiminishingReturnConfig`, `DiminishingReturnSignal`, `DiminishingReturnDetector`.
- `MarginalPolicy(..., diminishing_detector=None)` remains backward compatible.
- `MarginalPolicy.observe_execution(action)` records successful execution.

- [ ] Write tests proving first execution has multiplier 1, same-state repeats decay, changed state/evidence resets, and missing state fails open.
- [ ] Run the focused tests and verify failure because the control does not exist.
- [ ] Implement the detector with pure `evaluate()` and explicit `observe()`.
- [ ] Integrate optional gain discount/deny behavior into `MarginalPolicy`.
- [ ] Make successful Treasury settlement call `observe_execution` while preserving legacy `mark_executed` fallback.
- [ ] Run focused tests until green.

### Task 2: Governance tax and false-stop evidence

**Files:**
- Create: `src/marginal/controls/governance.py`
- Modify: `src/marginal/treasury.py`
- Test: `tests/controls/test_governance.py`
- Test: `tests/controls/test_treasury_governance.py`

**Interfaces:**
- Produces: `GovernanceTracker.record_decision`, `record_external_overhead`, `record_stop_review`, `summary`.
- Treasury produces: `record_governance_overhead(...)`, `record_stop_review(...)`.

- [ ] Write tests for overhead separation and explicit false-stop rate.
- [ ] Verify tests fail before implementation.
- [ ] Measure policy recommendation wall latency separately from action usage.
- [ ] Add explicit adapter-side overhead accounting.
- [ ] Track prior deny recommendations and reject duplicate/unrelated counterfactual labels.
- [ ] Add governance evidence to Treasury summary/trace without changing enforcement semantics.
- [ ] Run focused tests until green.

### Task 3: Net-value public evaluation

**Files:**
- Modify: `src/marginal/public_eval.py`
- Test: `tests/evaluation/test_public_eval_governance.py`

**Interfaces:**
- `RunRecord` adds optional zero-default fields for repeated calls, governance overhead and false-stop evidence.
- `compare_runs` adds `gross_savings`, `net_savings`, `governance`, `intervention` while retaining `savings`, `quality`, `efficiency`.

- [ ] Write tests for 30% gross / 10% net, governance-driven pass-through, and false-stop risk.
- [ ] Verify tests fail before implementation.
- [ ] Add effective cost aggregation and bootstrap net-token interval.
- [ ] Keep legacy rows and strict type validation working.
- [ ] Render governance tax and intervention status in Markdown reports.
- [ ] Run old and new public-eval tests.

### Task 4: Evidence-first communication

**Files:**
- Modify: `README.md`
- Modify: `site/index.html`
- Modify: `site/styles.css`
- Create: `docs/operations/website-review-2026-08-07.md`
- Create: `docs/project/community-feedback.md`

- [ ] Replace abstract-first website narrative with a clearly labeled illustrative trace.
- [ ] Put matched evidence, governance tax and false-stop requirements before architecture theory.
- [ ] Add Graceful Irrelevance and explicit pass-through language.
- [ ] Publish accepted/partial/rejected community decisions.
- [ ] Remove provider-motive speculation and universal model-waste claims.
- [ ] Run website/README structural validation.

### Task 5: Documentation information architecture

**Files:**
- Create: `MIGRATION_MANIFEST.json`
- Create: `scripts/reorganize_docs.py`
- Modify: `docs/index.md`
- Create: `docs/evaluation/governance-evidence.md`
- Create: `docs/integrations/codex-benchmark-readiness.md`

- [ ] Move flat docs into responsibility-based directories with `git mv`.
- [ ] Rewrite local Markdown links relative to their post-move locations.
- [ ] Update exact old-path references repository-wide.
- [ ] Validate no legacy docs paths remain and all local Markdown links resolve.

### Task 6: Roadmap, changelog and full verification

**Files:**
- Modify: `ROADMAP.md`
- Modify: `CHANGELOG.md`
- Modify: `scripts/validate_readme_pages.py`
- Create: `scripts/validate_community_hardening.py`

- [ ] Add self-accounting, Graceful Irrelevance and false-stop principles to roadmap.
- [ ] Explicitly separate 10-task Codex canary from public performance evidence.
- [ ] Add governance/repetition/false-stop metrics to v0.3 benchmark deliverables.
- [ ] Add SWE-bench Pro as one evaluation surface, not ground truth.
- [ ] Record the hardening changes under `Unreleased` without changing package version.
- [ ] Run `python scripts/validate_community_hardening.py`.
- [ ] Run `python scripts/validate_readme_pages.py`.
- [ ] Run `ruff format --check .`.
- [ ] Run `ruff check .`.
- [ ] Run `mypy src/marginal`.
- [ ] Run `pytest -q`.
- [ ] Run `python -m build` and `python -m twine check dist/*`.
- [ ] Inspect `git diff` and confirm no ZIP, local prompt, fabricated benchmark artifact or duplicate Pages deploy is staged.
