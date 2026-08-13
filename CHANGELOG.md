# Changelog

All notable changes to MARGINAL are documented here. The project follows Semantic Versioning.

## [Unreleased]

### Added

- opt-in, provider-neutral `DiminishingReturnDetector` with same-state/evidence-aware gain decay;
- `GovernanceTracker` for MARGINAL decision latency and external governance tokens, USD and latency;
- explicit counterfactual stop review through `Treasury.record_stop_review(...)` without inferring action causality from task outcomes;
- public-evaluation fields for repeated calls, governance overhead, reviewed stops and false stops;
- gross-versus-net savings and intervention status including Graceful Irrelevance through `pass_through`;
- governance evidence standard, Codex benchmark-readiness guide and Community Feedback Log;
- structured documentation information architecture by user intent.
- native Codex plugin marketplace `marginal@marginal` with reproducible dependency-free runtime;
- one-command native install/remove plus `status`, `doctor`, `review`, `promote`, and `demote`;
- strict Codex lifecycle contracts, privacy-safe normalization, Git state hashing, and conservative structured outcome classification;
- authenticated per-session loopback service with bounded messages and fail-open demotion;
- provider-neutral No Progress evidence control and versioned Earned Enforcement promotion receipts;
- isolated Codex 0.147.0 marketplace/lifecycle/privacy/removal smoke and universal directory review packet;
- public privacy, terms, support, Codex integration, and submission documentation.

### Changed

- public benchmark efficiency counts governance overhead in effective tokens/USD while retaining agent-only metrics and backward-compatible rows;
- `MarginalPolicy` can optionally discount or reject repeated semantic same-state work;
- `Treasury` records policy-decision latency and exposes governance evidence in summaries/traces;
- website and README now lead with a concrete illustrative trace and proof standard before architecture theory;
- roadmap now treats governance tax, false-stop rate, matched OFF/ON evaluation and pass-through as first-class success criteria;
- the 10-task Codex canary is explicitly classified as integration validation rather than public performance evidence.
- website and README now lead with native Codex install/remove and the measured n=3 `pass_through` result.

### Scientific limitations

- diminishing-return thresholds are transparent heuristics until calibrated on representative engine telemetry;
- false stops require external review/counterfactual labels and are not automatically causal estimates;
- Graceful Irrelevance classifies the measured configuration, not the universal usefulness of MARGINAL;
- the Codex plugin supports local Tool Enforcement paths, not Full Compute Enforcement;
- the n=3 result remains integration telemetry and does not establish general token savings;
- universal directory availability depends on external review and release.

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

- redesigned the repository README as a concise technical landing page;
- added a dependency-free, responsive, accessible GitHub Pages product website;
- consolidated product website, hero asset and Killer Demo into one Pages deployment;
- `Decision` carries recommendation, mode, reason-code, uncertainty, confidence and estimator metadata;
- `MarginalPolicy` has stable identity and supports versioned/legacy custom estimators;
- `Treasury.summary()` includes mode, policy, estimator, observed overruns, failed settlements, outcomes and estimator observations;
- child treasuries inherit parent execution mode;
- traces include execution mode plus policy and estimator identity;
- strict public-benchmark parsing rejects string-like booleans.

### Compatibility

- existing v0.1 constructors, enforced execution, `JsonlTraceSink`, synchronous/asynchronous wrappers, demos and CLI commands remain supported;
- new dataclass fields have backward-compatible defaults;
- runtime core continues to have zero mandatory dependencies.

### Scientific limitations

- historical estimates are observational and do not establish causal action value;
- policy replay does not simulate unobserved trajectories or prove quality preservation;
- vendor-specific Codex, Claude Code, GitHub Copilot and OpenCode adapters remain future milestones;
- reference profiles are transparent defaults, not universal calibrations.

## [0.1.0] - 2026-08-04

### Added

- provider-neutral `Action`, `Cost`, `Decision`, and `Allocation` value objects;
- deterministic candidate ranking, authorization, reservation, settlement, and abort;
- hard token, USD, latency and risk budgets;
- pending reservations and hierarchical accounting;
- protected verification reserves;
- marginal-value policy with token, latency and risk shadow prices;
- exact action/callable-input fingerprinting;
- synchronous/asynchronous guarded-call adapters;
- append-only JSONL traces and CLI reporting;
- synthetic benchmark, public comparison utility and Killer Demo;
- Python 3.10–3.13 CI, CodeQL, packaging and community documentation.
