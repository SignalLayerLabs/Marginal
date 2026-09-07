# Astra compatibility and public benchmark implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Support Astra operational memory and publish a genuine public OFF/ON evaluation.

**Architecture:** Extend the existing exact model registry and lifecycle evidence path.
Use the existing isolated benchmark scaffold where compatible, with official task grading.
Keep integration tests separate from experimental evidence.

**Tech Stack:** Python 3.10+, Codex CLI, Docker/Colima, official SWE-bench Pro evaluator.

**Spec:** docs/superpowers/specs/2026-09-07-astra-public-benchmark-design.md

## Global Constraints

- Exact identity: `gpt-6-astra` maps to `openai/gpt-6-astra`; unknown identifiers stay local.
- Preserve local-only defaults, signed Commons trust, and enforcement evidence gates.
- Do not publish credentials, private source, prompts, commands or transcripts as operational memory.
- Benchmark evidence covers public benchmark tasks only, sanitized before publication.
- Reserve 20% of the short quota window; do not redeem resets or purchase compute.
- A partial, failed, or unexecuted benchmark must never be labelled complete or a savings result.

### Task 1: Astra identity and operational memory

**Files:** `src/marginal/commons/identity.py`, registry/schema/contract mirrors,
`tests/commons/test_identity.py`, `tests/integrations/codex/test_service.py`, and the
corresponding model contracts in the sibling Commons and Ingress repositories.

**Interfaces:** Existing `resolve_canonical_model(provider=..., model=...)` returns a
`CanonicalModelIdentity`; lifecycle evidence retains `model_namespace` on decisions/outcomes.

- [ ] Write a failing resolver test asserting the Astra namespace and rejection of ambiguous variants.

```python
identity = resolve_canonical_model(provider="openai", model="gpt-6-astra")
assert identity is not None
assert identity.namespace == "openai/gpt-6-astra"
assert resolve_canonical_model(provider="openai", model="gpt-6-astra-private") is None
```

- [ ] Run `.venv/bin/pytest tests/commons/test_identity.py -q`; verify the missing identity failure.
- [ ] Add Astra to reviewed registries and strict contract enums without widening unknown identity handling.
- [ ] Exercise real lifecycle pre/post events with Astra and verify model-specific persisted evidence,
  mixed-model exclusion, and restart persistence using existing service test fixtures.
- [ ] Run focused Commons and Codex integration tests; regenerate contract digests mechanically.
- [ ] Commit only task-owned source/tests/contracts; leave runtime rebuild to final packaging.

### Task 2: Real execution and benchmark protocol

**Files:** `benchmark/astra/` protocol/environment and execution artifacts; runner modules only
where actual preflight identifies a compatibility defect; `tests/benchmark/` regression tests.

**Interfaces:** Official dataset instance IDs and grader outcomes join one-to-one with measured
Codex usage and intervention records. Missing metrics stay null, never zero by assumption.

- [ ] Verify Astra on a current available Codex executable with a minimal no-tool request.
- [ ] Start the existing benchmark VM and inventory official image/evaluator availability.
- [ ] Freeze the public dataset/evaluator revisions and full task manifest before inference.
- [ ] For each runner defect, first add a failing regression at the boundary, then implement and test.
- [ ] Publish the protocol commit before scored inference; run an evaluator gold-patch check.
- [ ] Execute independent OFF/ON lanes for every frozen task, recording actual usage and failures.
- [ ] Stop launching work at the reserved quota threshold and report any incompleteness explicitly.

### Task 3: Analysis, verification and GitHub delivery

**Files:** benchmark report and sanitized raw artifacts, `README.md`, plugin runtime/provenance.

**Interfaces:** Complete paired rows feed the existing public comparator; incomplete runs retain
their failure records but produce no headline savings claim.

- [ ] Verify coverage and provider usage accounting; report correctness, interventions, token and time deltas.
- [ ] Scan public artifacts for secrets/private data and retain only benchmark-scoped evidence.
- [ ] Rebuild with `.venv/bin/python scripts/build_codex_plugin.py` and verify with `--check`.
- [ ] Run `.venv/bin/ruff check .`, `.venv/bin/mypy src/marginal`, and `.venv/bin/pytest -q`.
- [ ] Obtain independent code/claims review, then publish commits and PR with reproducible commands.
- [ ] Report exact shipped functionality, evidence, limits and remaining blockers.
