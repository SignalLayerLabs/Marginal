# Marginal SWE-bench Lite Full Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce, grade, publish, and submit a complete 300-task paired SWE-bench Lite benchmark.

**Architecture:** A frozen safe manifest drives an immutable checkpointed schedule. Each OFF/ON
lane runs once in a disposable derivative of the same official image; exporters feed the official
v5 evaluator, paired analysis, public artifact repository, and submission CLI.

**Tech Stack:** Python 3.10+, Codex CLI 0.153.4, Docker amd64, official SWE-bench v5 CLI, pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-marginal-swebench-lite-full-design.md`

## Global Constraints

- Exactly 300 test tasks and 600 single-attempt lanes; no outcome-based exclusion or retry.
- Zero euros, ChatGPT-authenticated Codex CLI only, no `OPENAI_API_KEY`.
- Never expose benchmark tests, hints, gold data, another lane, auth material, or private reasoning.
- Preserve incomplete attempts and distinguish infrastructure failures from task failures.
- Do not claim completion, savings, submission acceptance, or leaderboard acceptance without evidence.

---

### Task 1: Freeze the full public contract

**Files:**
- Create: `benchmark/astra/lite/protocol.json`
- Create: `benchmark/astra/lite/task-manifest.jsonl`
- Create: `benchmark/astra/lite/status.json`
- Create: `benchmark/astra/lite/freeze.py`
- Test: `tests/benchmark/test_astra_lite_freeze.py`

**Interfaces:**
- Produces: `load_safe_manifest(path) -> tuple[LiteTask, ...]` and the exact 300-task schedule.

- [ ] Write tests that reject fewer than 300 IDs, duplicate IDs, unsafe fields, invalid commits,
  altered hashes, and a schedule that does not match the public seed.
- [ ] Run the focused test and verify it fails because the loader is absent.
- [ ] Implement the safe frozen loader/generator; export only identity, repository, base commit,
  official image reference, problem hash, and schedule position/condition order.
- [ ] Generate the manifest from the pinned dataset without reading outcome fields into solver data.
- [ ] Verify 300 unique tasks, 600 unique scheduled lanes, JSON validity, Ruff, and focused tests.
- [ ] Commit the frozen contract before any test-split inference.

### Task 2: Add one generic Lite lane and image

**Files:**
- Create: `benchmark/astra/lite_lane.py`
- Create: `benchmark/astra/lite/Dockerfile.solver`
- Modify: `benchmark/astra/pro_lane.py`
- Test: `tests/benchmark/test_astra_lite_lane.py`

**Interfaces:**
- Consumes: `LiteTask` identity/base commit and public rendered prompt.
- Produces: `run_lane(LiteLaneConfig) -> dict[str, object]` plus exact-tree provenance.

- [ ] Write tests proving classic IDs are accepted, Pro/path traversal IDs are rejected, the
  original tree is recreated without future Git history, and OFF/ON pass identical RunConfig.
- [ ] Verify RED, extract the already-tested snapshot logic into a shared internal function, and
  keep the Pro lane behavior unchanged.
- [ ] Add the `/testbed` Lite entry point and derivative image using pinned Codex/Python builders.
- [ ] Verify focused Pro and Lite tests, Ruff, and a no-provider exact-tree image smoke.
- [ ] Commit the lane and image.

### Task 3: Implement immutable campaign resume

**Files:**
- Create: `benchmark/astra/lite_campaign.py`
- Create: `benchmark/astra/lite/checkpoint.py`
- Test: `tests/benchmark/test_astra_lite_campaign.py`

**Interfaces:**
- Produces: `init`, `next`, `run --max-lanes N`, `status`, and `export` CLI commands.

- [ ] Write tests for deterministic ordering, attempt-before-launch, crash preservation, skip of
  attempted lanes, quota-stop behavior, exact OFF/ON pairing, and explicit image cleanup targets.
- [ ] Verify RED and implement atomic checkpoint records derived from immutable lane directories.
- [ ] Build/pull one task at a time, pin the resolved image digest, run both scheduled conditions,
  then remove only the explicit local overlay/task image after artifacts are durable.
- [ ] Verify no auth marker appears in any public/exportable artifact.
- [ ] Commit the resumable campaign.

### Task 4: Validate without touching the test score

**Files:**
- Create: `benchmark/astra/lite/validation.json`
- Modify: `benchmark/astra/lite/status.json`

- [x] Freeze one Lite dev ID and build its exact solver image.
- [x] Run one OFF and one ON validation attempt with ChatGPT authentication.
- [x] Confirm Codex 0.153.4, Astra identity, token telemetry, trajectory, patch extraction, MARGINAL
  coverage, identical base tree, and absence of auth material.
- [x] Grade both validation patches with the pinned official evaluator and record every outcome.
- [x] Publish validation evidence as pipeline evidence only; do not tune MARGINAL from task quality.

### Task 5: Execute and grade all 600 lanes

**Files:**
- Update: `benchmark/astra/lite/status.json`
- Generate outside Git: immutable raw run root and official evaluation directories.

- [ ] Run the campaign until account quota exhaustion; preserve the final attempt and stop.
- [ ] Resume after each reset from the first untouched schedule entry.
- [ ] Verify all 300 OFF and 300 ON attempt records exist before export.
- [ ] Export complete prediction JSONL and public trajectories without secrets.
- [ ] Evaluate OFF and ON under distinct run IDs with the official v5 local Docker harness.
- [ ] Verify 300 reports per lane and no missing, duplicate, or silently dropped instance.

### Task 6: Analyze, publish, and register

**Files:**
- Create: `benchmark/astra/lite/analyze.py`
- Create: `benchmark/astra/lite/PUBLIC_BENCHMARK.md`
- Modify: `README.md`
- Test: `tests/benchmark/test_astra_lite_analysis.py`

- [ ] Write literal-fixture tests for the paired table, exact McNemar result, bootstrap seed,
  confidence intervals, non-inferiority, intervention metrics, and failure separation.
- [ ] Verify RED, implement analysis, and reproduce every Markdown value from machine JSON.
- [ ] Run `swebench submit package` for the finished ON evaluation and complete all metadata/assets.
- [ ] Run submission dry-runs and local `swebench submit verify`; scan for TODOs and secrets.
- [ ] Publish `SignalLayerLabs/Marginal-SWE-bench-Lite`, then run `submit register` to open the PR.
- [ ] Update Marginal README only with measured results and direct artifact/submission links.
- [ ] Run full tests, Ruff, runtime provenance check, and GitHub CI; commit and push.
