# Codex + MARGINAL End-to-End Benchmark Plan

> Execute test-first with `superpowers:test-driven-development`, diagnose failures with
> `superpowers:systematic-debugging`, and require fresh evidence under
> `superpowers:verification-before-completion`.

**Goal:** Produce an independently verifiable paired Codex OFF versus Codex+MARGINAL
benchmark in official SWE-bench environments, publish the exact outcome at the top of the
README and website, and preserve machine-readable reproduction artifacts.

**Architecture:** A host orchestrator launches pinned Codex inside each official
per-instance SWE-bench image. OFF contains only Codex and telemetry collection; ON adds a
per-run MARGINAL daemon and official hooks. Strict run records feed the repository's
SWE-bench evidence protocol and GitHub Actions/Modal verifier.

**Stack:** Python 3.10+, pytest, Docker/Colima, SWE-bench, Modal, Codex CLI 0.147.0,
GitHub Actions, static HTML/CSS/JavaScript.

## Frozen constraints

- MARGINAL source commit: `4c8856401b4c752d5c214df5e84b9632d9897ec9`.
- Codex CLI/model/effort: `0.147.0`, `gpt-5.6-sol`, `high`.
- Correctness is assigned only by the official SWE-bench verifier.
- No credentials, prompts, task source, or raw tool output enter public artifacts.
- OFF has no MARGINAL process, hook, prompt text, configuration, or state.
- ON failures are explicit and cannot degrade silently to pass-through.
- No policy, prompt, timeout, or task-set tuning after comparative outcomes are observed.
- A token-saving headline requires preserved paired correctness and positive verified data.

## Task 1: Preserve and re-baseline the existing feasibility adapter

**Files:** `benchmark/**`, `tests/benchmark/**`, design and plan documents.

- [ ] Create a dedicated benchmark branch without discarding the feasibility work.
- [ ] Run the current full unit/type/lint suite and record the starting evidence.
- [ ] Commit the reviewed feasibility baseline so later runtime changes remain auditable.
- [ ] Confirm result JSONL files contain no inference outcomes before the design amendment.

## Task 2: Correct completed-action semantics test-first

**Files:**
- Modify: `benchmark/codex_adapter/engine.py`
- Modify: `benchmark/codex_adapter/daemon.py`
- Test: `tests/benchmark/test_governance_engine.py`
- Test: `tests/benchmark/test_daemon_protocol.py`

- [ ] Add a failing test where a shell `PostToolUse` commits evidence and the third exact,
      unchanged proposal is denied.
- [ ] Add failing tests for malformed, duplicate, missing, and identity-mismatched post
      events and pending actions at shutdown.
- [ ] Observe the intended red failures before editing production code.
- [ ] Implement the frozen completion semantics without inferring command exit status.
- [ ] Confirm exact decision accounting and the targeted tests pass.

## Task 3: Add official task-image resolution and overlay build test-first

**Files:**
- Create: `benchmark/codex_adapter/container_runtime.py`
- Create: `benchmark/container/Dockerfile.tools`
- Create: `benchmark/container/entrypoint.sh`
- Test: `tests/benchmark/test_container_runtime.py`

- [ ] Add failing tests for deterministic official image names/digests, platform, mount
      paths, read-only tool layer, model credential injection, and environment allowlist.
- [ ] Add failing tests proving the task worktree/run directory cannot alias and no user
      home or auth file is mounted.
- [ ] Implement a subprocess argument builder with no shell interpolation.
- [ ] Build a pinned tool layer containing Linux Codex 0.147.0 and an isolated MARGINAL
      environment; record its content digest.
- [ ] Inspect the built image and verify it contains no credentials or task content.
- [ ] Confirm all container-runtime tests pass.

## Task 4: Integrate container execution into the runner test-first

**Files:**
- Modify: `benchmark/codex_adapter/runner.py`
- Modify: `benchmark/codex_adapter/preflight.py`
- Modify: `benchmark/scripts/run_codex_task.py`
- Modify: `benchmark/environment.json`
- Test: `tests/benchmark/test_codex_runner.py`
- Test: `tests/benchmark/test_preflight.py`

- [ ] Add a fake-container failing test proving OFF/ON receive identical runtime inputs and
      ON alone receives hooks/daemon configuration.
- [ ] Add failing tests for wrong image digest, unavailable engine, architecture mismatch,
      missing model auth, missing sandbox network isolation, and dirty base commit.
- [ ] Implement container lifecycle, timeouts, signal cleanup, bind mounts, raw-event
      collection, and patch extraction.
- [ ] Replace the obsolete unconditional preflight block with concrete runtime checks.
- [ ] Require full preflight inside the callable runner, not only the CLI.
- [ ] Confirm targeted runner/preflight tests pass.

## Task 5: Prove a deterministic container integration fixture

**Files:**
- Create: `benchmark/fixtures/container_task/**`
- Create: `benchmark/scripts/container_smoke.py`
- Test: `tests/benchmark/test_container_integration.py`

- [ ] Write a fixture whose fake model stream performs a shell action, repeats it, edits a
      file, and emits a final patch.
- [ ] Observe the integration test fail before runtime wiring exists.
- [ ] Run OFF and ON in disposable containers.
- [ ] Prove tool execution occurs inside the container, ON has exact pre/post coverage,
      the third same-state repeat is denied, OFF has no MARGINAL footprint, and both patches
      are extracted outside `/testbed`.
- [ ] Prove secret scanning rejects credential-shaped fixture output.

## Task 6: Bridge run records to the existing SWE-bench evidence protocol

**Files:**
- Create: `benchmark/codex_adapter/evidence.py`
- Create: `benchmark/scripts/export_swebench_evidence.py`
- Modify: `benchmarks/swebench_lite/protocol.py` only if a backward-compatible schema field
  is required.
- Test: `tests/benchmark/test_evidence_export.py`

- [ ] Add failing tests mapping strict run records to baseline/ON predictions and metrics.
- [ ] Prove mismatched task IDs, commits, image digests, configs, failed integrity gates,
      duplicate rows, and secret findings abort export.
- [ ] Implement deterministic manifest/config hashes and NDJSON export.
- [ ] Validate output with the existing `validate` protocol command.
- [ ] Confirm legacy canary fixtures remain valid.

## Task 7: Freeze smoke and canary manifests

**Files:**
- Modify: `benchmark/tasks.json`
- Create: `benchmark/canary-tasks.json`
- Modify: `benchmark/methodology.md`
- Modify: `benchmark/environment.json`

- [ ] Preserve the three preregistered smoke task IDs and task-set hash.
- [ ] Select a deterministic twenty-task SWE-bench Lite subset without looking at model
      outcomes; record selection rule, IDs, base commits, dataset revision, and SHA-256.
- [ ] Record exact official image digests, overlay digest, host/engine details, timeouts,
      prompt/config hashes, and amendment history.
- [ ] Validate manifests and prove no gold patch or test patch enters prompts.

## Task 8: Fresh local verification before paid inference

- [ ] Run `ruff format --check .`.
- [ ] Run `ruff check .`.
- [ ] Run `mypy src/marginal benchmark` with the repository's supported configuration.
- [ ] Run `.venv/bin/python -m pytest -p no:cacheprovider -q`.
- [ ] Run the deterministic container integration fixture.
- [ ] Run full benchmark preflight and validate exact tool/image/model availability.
- [ ] Run `git diff --check` and a repository secret scan.
- [ ] Commit and push the implementation branch only after every local gate is green.

## Task 9: Execute and verify the frozen three-task smoke

- [ ] Materialize six independent clean runs: three OFF, then three ON.
- [ ] Persist raw private run artifacts and strict public records separately.
- [ ] Validate exact lane pairing and telemetry coverage before verifier spend.
- [ ] Export committed evidence under `benchmarks/swebench_lite/evidence/`.
- [ ] Push evidence and dispatch `.github/workflows/swebench-lite-canary.yml`.
- [ ] Wait for the official Modal verifier and download its artifact.
- [ ] Validate provenance and merge verifier outcomes into paired smoke results.
- [ ] If any integrity gate fails, fix the pipeline and rerun the affected stage from clean
      state; do not analyze partial outcomes.

## Task 10: Execute and verify the frozen twenty-task canary

- [ ] Promote only after smoke telemetry and official verification are complete.
- [ ] Materialize forty independent clean runs under the unchanged frozen configuration.
- [ ] Export, commit, push, dispatch, and wait for the official Modal verification.
- [ ] Validate and merge the canary artifact without dropping failures.
- [ ] Generate per-task rows, paired outcome counts, token deltas, latency, governance
      overhead, intervention counts, and bootstrap confidence intervals where defensible.

## Task 11: Publish evidence-first README and website

**Files:**
- Modify: `README.md`
- Modify: `site/index.html`
- Modify: `site/app.js`
- Modify: `site/styles.css`
- Create or update: `benchmarks/swebench_lite/PUBLIC_BENCHMARK.md`
- Create or update: `benchmarks/swebench_lite/public-benchmark.json`
- Test: site and public-artifact validation tests.

- [ ] Add a top-of-page benchmark strip showing correctness first, then verified token
      delta, actions prevented, and governance overhead.
- [ ] Label smoke/canary sample size and exploratory status visibly.
- [ ] Link the exact workflow run, machine-readable artifact, methodology, task manifest,
      source commit, and reproduction command.
- [ ] Render negative, neutral, or regressive outcomes without euphemism.
- [ ] Add responsive and reduced-motion behavior; keep the site dependency-free.
- [ ] Run local HTTP/browser checks for layout, links, console errors, and mobile viewport.

## Task 12: Final verification and publication

- [ ] Re-run all format, lint, type, unit, integration, schema, evidence, secret, and site
      checks from the final tree.
- [ ] Confirm README/site numbers are derived from the committed JSON artifact and contain
      no manually divergent totals.
- [ ] Commit intentionally, push the benchmark branch, and open a draft PR with exact test
      and verifier evidence.
- [ ] Confirm GitHub Actions CI, SWE-bench workflow, and Pages deployment pass.
- [ ] Report the branch/PR, workflow run, site URL, exact measured outcome, limitations, and
      reproduction path; only then mark the goal complete.
