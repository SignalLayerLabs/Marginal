# MARGINAL v0.2 Learning Loop Foundation Design

## Goal

Transform MARGINAL from a static marginal-value policy engine into a versioned, observable learning-loop foundation while preserving its deterministic, dependency-free core and backward-compatible v0.1 execution APIs.

## Product boundary

This release implements the universal foundation used by future Codex, Claude Code, GitHub Copilot, OpenCode, and other adapters. It does not claim that vendor-specific adapters or causal value estimation are complete. It creates the runtime, protocol, evidence, shadow evaluation, replay, and estimator interfaces required to build and validate those integrations honestly.

## Architecture

The existing `Action -> Policy -> Treasury -> Trace` flow remains intact. New modules add:

- `ExecutionMode` for shadow, recommend, and enforce behavior;
- `TokenUsage` for measured token breakdowns while `Cost.tokens` remains backward compatible;
- enriched `Decision` fields separating recommendations from applied behavior;
- a versioned `ValueEstimator` and `EstimatorRegistry`;
- `Outcome` as a provider-neutral verifier result;
- `JsonlDecisionLedger` as a schema-versioned trace sink;
- `UniversalRuntime` and protocol values for thin engine adapters;
- policy replay over ledger evidence without making causal claims;
- explicit failed-action settlement when external work consumed resources.

## Mode semantics

- **enforce:** policy and hard-budget decisions control execution; overruns remain errors.
- **shadow:** every proposed action executes, while the would-allow/would-deny recommendation is recorded. Budget violations are measured but do not change the caller's behavior.
- **recommend:** identical non-blocking accounting semantics to shadow mode, but intended for integrations that surface recommendations to the user or agent.

Candidate selection through `fund_best` remains an active allocation API. Shadow mode applies to guarded proposed actions, not to inventing a baseline candidate choice when no external choice exists.

## Decision ledger

Every ledger event receives:

- schema version;
- event ID and monotonic sequence;
- timestamp;
- run, task, trajectory, engine, and model identity;
- execution mode;
- policy and estimator identity;
- normalized action, decision, usage, and outcome payloads.

The ledger is append-only JSONL, local-first, thread-safe, and does not record prompts or model outputs unless callers explicitly place data in metadata.

## Estimation and learning

The estimator remains transparent. Explicit action estimates take priority. Historical observations are keyed by action kind and selected context fields, return uncertainty/confidence metadata, and expose a stable identity containing name, semantic version, configuration hash, and optional training-data fingerprint.

`Treasury.observe_value(action, realized_gain)` is the explicit learning hook. Outcomes and action-level realized gains are deliberately separate because a successful task does not prove that every preceding action caused the success.

## Replay

Replay re-evaluates historical authorization events under a selected policy and reports counterfactual policy decisions and estimated selected/avoided cost. It is an off-policy diagnostic, not causal proof and not a task-quality simulation.

## Compatibility

Existing constructors and methods continue to work. New dataclass fields have defaults. Existing `JsonlTraceSink`, wrappers, demos, public evaluator, and CLI commands remain supported. The package version advances to `0.2.0`.

## Security and privacy

No mandatory network service is introduced. Ledger paths are caller-controlled. Metadata remains caller-controlled and must be treated as potentially sensitive. Fingerprints are identifiers, not secrets. Failure accounting preserves the original execution exception as the primary error.

## Validation

The release requires:

- backward-compatibility tests for v0.1 policy, treasury, and adapters;
- red-green tests for every new public primitive;
- shadow-mode no-block behavior and measured overrun tests;
- ledger schema, sequence, and privacy tests;
- protocol round-trip and runtime lifecycle tests;
- estimator versioning, contextual observations, and registry tests;
- failure settlement tests;
- replay tests with explicit non-causal labeling;
- Ruff, mypy strict, pytest, build, and twine validation.
