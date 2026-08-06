# Changelog

All notable changes to MARGINAL are documented here. The project follows Semantic Versioning.

## [0.2.0] - 2026-08-06

### Added

- `shadow`, `recommend`, and `enforce` execution modes;
- applied-versus-recommended decision fields and stable reason codes;
- additive `TokenUsage` breakdown for uncached input, cached input, output, reasoning, and total tokens;
- common token-breakdown extraction for provider-like usage objects;
- versioned `EstimatorIdentity`, `ValueEstimate`, contextual historical observations, uncertainty, confidence, sample size, provenance, and deterministic training-data fingerprints;
- `EstimatorRegistry` for explicit estimator name/version resolution;
- versioned `PolicyIdentity` and four transparent reference policy profiles;
- non-blocking unchecked reservations and separate internal reservation identities for accurate concurrent Shadow Mode observation;
- measured overrun accounting in non-blocking modes;
- explicit failed-action settlement through sync and async wrappers, while keeping failed work retryable;
- provider-neutral `Outcome` contract separated from action-level realized gain;
- schema-versioned `JsonlDecisionLedger` with strict envelope validation, run/task/trajectory/engine/model correlation, task/outcome consistency checks, and monotonic sequencing;
- `PrivacyProfile` with `local_full`, keyed `safe_telemetry`, and separate `aggregate_export` modes;
- privacy-preserving aggregate export with a configurable minimum group size of five by default;
- field classification for safe-by-default, pseudonymous, and potentially sensitive evidence;
- HMAC-SHA-256 identifier pseudonymization, UTC-day timestamp generalization, strict free-text removal, and local 256-bit key management;
- opaque random local identifier generation for runs, tasks, and other caller-defined namespaces;
- grouped aggregate exports with deterministic cost/gain buckets, no identifiers, and no timestamps;
- `ledger-export` CLI, overwrite protection, aggregate JSON Schema, privacy guide, and executable privacy example;
- Universal Agent Protocol v1 values, strict round-trip parsing, capability negotiation, directives, state-aware deduplication scopes, and `UniversalRuntime`;
- off-policy decision replay with explicit non-causal reporting;
- ledger validation, ledger reporting, and replay CLI commands;
- JSON schemas for events, decisions, capabilities, outcomes, token usage, and ledger records, plus an installed-resource API through `available_schemas()` and `load_schema()`;
- configurable public-benchmark confidence level, non-inferiority margin, random seed, and cost-per-resolved efficiency metrics;
- executable Shadow Mode and universal-runtime examples;
- complete Learning Loop Foundation, universal-runtime, API, architecture, benchmarking, security, and roadmap documentation.

### Changed

- `Decision` is backward compatible but now carries recommendation, mode, reason-code, uncertainty, confidence, and estimator metadata;
- `MarginalPolicy` now has a stable identity and supports both versioned and legacy custom estimators;
- `Treasury.summary()` includes mode, policy, estimator, observed overruns, failed settlements, outcomes, and estimator observations;
- child treasuries inherit the parent execution mode;
- trace events include execution mode plus policy and estimator identity;
- Decision Ledger records now declare their privacy profile; `local_full` remains backward compatible while strict profiles are opt-in;
- actual failed-call spend can be accounted without replacing the original execution exception; extraction failures conservatively settle the reserved estimate and remain chained as secondary errors;
- strict public-benchmark parsing rejects string-like booleans instead of silently coercing them;
- project description and documentation now consistently describe MARGINAL as a learning-loop foundation rather than only a static wrapper.

### Compatibility

- existing v0.1 constructors, enforced execution, `JsonlTraceSink`, synchronous and asynchronous wrappers, demos, and CLI commands remain supported;
- new dataclass fields have backward-compatible defaults;
- the runtime core continues to have zero mandatory dependencies.

### Scientific limitations

- historical estimates are observational and do not establish causal action value;
- policy replay does not simulate unobserved trajectories or prove quality preservation;
- vendor-specific Codex, Claude Code, GitHub Copilot, and OpenCode adapters remain future milestones;
- reference profiles are transparent defaults, not universal calibrations.

## [0.1.0] - 2026-08-04

### Added

- provider-neutral `Action`, `Cost`, `Decision`, and `Allocation` value objects;
- deterministic candidate ranking, authorization, reservation, settlement, and abort;
- hard budgets for tokens, direct USD, latency, and risk;
- pending reservations and hierarchical parent/child accounting;
- protected verification reserves;
- marginal-value policy with token, latency, and risk shadow prices;
- exact action and callable-input fingerprinting;
- synchronous and asynchronous guarded-call adapters;
- append-only JSONL traces and CLI reporting;
- synthetic benchmark, public comparison utility, and Killer Demo;
- Python 3.10–3.13 CI, CodeQL, packaging, and community documentation.
