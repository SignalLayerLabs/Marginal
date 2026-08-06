# MARGINAL v0.2 Learning Loop Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build a dependency-free, versioned learning-loop foundation with non-blocking shadow evaluation, decision evidence, outcome recording, policy replay, and a universal adapter runtime.

**Architecture:** Preserve the v0.1 core contracts and extend them through focused modules. `Treasury` remains the transactional authority, `JsonlDecisionLedger` enriches trace events, `UniversalRuntime` translates protocol actions into core actions, and replay consumes the same ledger format without claiming causal effects.

**Tech Stack:** Python 3.10-3.13, standard library only at runtime, dataclasses, JSONL, pytest, Ruff, mypy strict, setuptools.

## Global Constraints

- Keep zero mandatory runtime dependencies.
- Preserve v0.1 public APIs unless a new optional field or method is additive.
- Shadow and recommend modes must not prevent execution.
- Enforce mode must preserve transactional reservation and overrun behavior.
- Never infer causal action value from a task outcome alone.
- Do not record prompts or outputs by default.
- All public identities and schemas must be explicitly versioned.
- All documentation must describe implemented behavior and limitations consistently.

---

## Execution status

Tasks 1–9 have been implemented and covered by the repository test suite. Task 10 has passed all verification available in the isolated environment. Ruff, mypy strict, and Twine remain explicit Visual Studio/CI gates because their executables could not be installed without network access.

### Task 1: Versioned decision and token primitives

**Files:**
- Modify: `src/marginal/models.py`
- Create: `src/marginal/modes.py`
- Test: `tests/test_models_v2.py`

**Produces:** `TokenUsage`, enriched `Decision`, and `ExecutionMode`.

- [x] Write failing validation and compatibility tests.
- [x] Run the focused tests and confirm missing imports/fields fail.
- [x] Implement immutable validated primitives with backward-compatible defaults.
- [x] Run focused and existing model tests.

### Task 2: Versioned estimator and registry

**Files:**
- Modify: `src/marginal/estimator.py`
- Create: `src/marginal/registry.py`
- Test: `tests/test_estimator_v2.py`

**Produces:** `EstimatorIdentity`, `ValueEstimate`, enhanced `ValueEstimator`, `EstimatorRegistry`.

- [x] Write failing tests for explicit, historical, contextual, uncertainty, identity, and registry behavior.
- [x] Confirm RED failures.
- [x] Implement transparent estimates and deterministic hashes.
- [x] Run focused and legacy policy tests.

### Task 3: Versioned policy identities and profiles

**Files:**
- Modify: `src/marginal/policy.py`
- Create: `src/marginal/profiles.py`
- Test: `tests/test_policy_v2.py`

**Produces:** `PolicyIdentity`, structured reason codes, reference profiles.

- [x] Write failing tests for identity stability, estimator metadata, reason codes, and profiles.
- [x] Confirm RED failures.
- [x] Implement additive policy behavior.
- [x] Run focused and legacy policy tests.

### Task 4: Shadow-safe transactional accounting

**Files:**
- Modify: `src/marginal/budget.py`
- Modify: `src/marginal/treasury.py`
- Test: `tests/test_shadow_mode.py`

**Produces:** non-blocking shadow/recommend authorization, unchecked reservations for observation, explicit outcome/value hooks.

- [x] Write failing tests for policy denial override, hard-budget override, pending accounting, overrun measurement, enforce preservation, and learning hooks.
- [x] Confirm RED failures.
- [x] Implement mode-aware authorization and settlement.
- [x] Run focused and legacy treasury tests.

### Task 5: Failed-action usage settlement

**Files:**
- Modify: `src/marginal/adapters.py`
- Test: `tests/test_failure_settlement.py`

**Produces:** optional failure usage extraction and primary-exception preservation.

- [x] Write failing sync and async tests.
- [x] Confirm RED failures.
- [x] Implement failure settlement without replacing the original callable error.
- [x] Run focused and legacy adapter tests.

### Task 6: Outcome contract and decision ledger v2

**Files:**
- Create: `src/marginal/outcomes.py`
- Create: `src/marginal/ledger.py`
- Modify: `src/marginal/trace.py`
- Test: `tests/test_decision_ledger.py`

**Produces:** `Outcome`, `DecisionLedgerContext`, `JsonlDecisionLedger`, ledger readers and summaries.

- [x] Write failing schema, sequence, validation, outcome, and privacy tests.
- [x] Confirm RED failures.
- [x] Implement append-only thread-safe evidence.
- [x] Run focused trace and ledger tests.

### Task 7: Universal Agent Protocol and local runtime

**Files:**
- Create: `src/marginal/protocol.py`
- Create: `src/marginal/runtime.py`
- Test: `tests/test_protocol.py`
- Test: `tests/test_runtime.py`

**Produces:** protocol values, capability negotiation, and an engine-neutral lifecycle runtime.

- [x] Write failing round-trip, fingerprint-scope, lifecycle, failure, and outcome tests.
- [x] Confirm RED failures.
- [x] Implement protocol serialization and runtime mapping.
- [x] Run focused tests.

### Task 8: Policy replay and CLI

**Files:**
- Create: `src/marginal/replay.py`
- Modify: `src/marginal/cli.py`
- Test: `tests/test_replay.py`
- Test: `tests/test_cli_v2.py`

**Produces:** replay summaries, Markdown rendering, ledger validate/report and replay commands.

- [x] Write failing replay and CLI tests.
- [x] Confirm RED failures.
- [x] Implement replay with explicit non-causal language.
- [x] Run focused and legacy CLI tests.

### Task 9: Public API, schemas, examples, and complete documentation alignment

**Files:**
- Modify: `src/marginal/__init__.py`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `CONTRIBUTING.md`
- Modify: `SECURITY.md`
- Modify: `docs/api.md`
- Modify: `docs/architecture.md`
- Modify: `docs/concepts.md`
- Modify: `docs/integrations.md`
- Modify: `docs/benchmarking.md`
- Modify: `docs/quickstart.md`
- Modify: `docs/faq.md`
- Create: `docs/learning-loop.md`
- Create: `docs/universal-runtime.md`
- Create: `ROADMAP.md`
- Create: `schemas/agent-event-v1.json`
- Create: `schemas/agent-decision-v1.json`
- Create: `schemas/decision-ledger-v2.json`
- Create: `schemas/outcome-v1.json`
- Create: `examples/shadow_mode.py`
- Create: `examples/universal_runtime.py`
- Test: `tests/test_public_api_v2.py`

**Produces:** one consistent v0.2 product surface and documentation set.

- [x] Write failing public-export, version, schema, and documentation consistency tests.
- [x] Confirm RED failures.
- [x] Update every public reference and example together.
- [x] Run focused documentation consistency tests.

### Task 10: Full verification and delivery

**Files:** all changed files plus delivery prompt and manifest.

- [ ] Run Ruff format and lint.
- [ ] Run mypy strict.
- [x] Run the complete pytest suite.
- [x] Build wheel and sdist.
- [ ] Run twine checks.
- [x] Run security-oriented scans for accidental secrets, prompt logging, TODOs, and inconsistent versions.
- [x] Generate a clean repository-overlay ZIP, SHA-256 manifest, change summary, and Visual Studio commit/push prompt.
