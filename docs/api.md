# API reference

## Core values

```python
Cost(tokens=0, usd=0.0, latency_ms=0, risk=0.0)
TokenUsage(
    input_tokens=0,
    cached_input_tokens=0,
    output_tokens=0,
    reasoning_tokens=0,
)
Action(name="run tests", kind="verification", cost=Cost(tokens=500))
Decision(allowed=True, reason="approved")
```

`TokenUsage` components are additive. `input_tokens` means uncached input. When a provider reports reasoning as a subset of total output, the common extractor normalizes `output_tokens` to non-reasoning output.

`Decision.allowed` is the behavior applied by the current mode. `Decision.recommended` is the policy recommendation before a Shadow or Recommend override. The original v0.1 fields and constructors remain supported.

## Execution modes

```python
ExecutionMode.SHADOW
ExecutionMode.RECOMMEND
ExecutionMode.ENFORCE
```

- `shadow`: execute proposed work while recording recommendations;
- `recommend`: execute proposed work and surface advisory decisions;
- `enforce`: apply policy and hard-budget denials.

`fund_best` is an explicit allocation operation and remains selective in every mode.

## Estimation

```python
ValueEstimator(
    default_gain=0.05,
    name="historical-mean",
    version="2.0.0",
    context_fields=("engine", "phase", "task_type", "language", "model"),
)
```

Primary methods:

- `estimate(action) -> float`;
- `estimate_detail(action) -> ValueEstimate`;
- `observe(kind, realized_gain)` for v0.1 compatibility;
- `observe_action(action, realized_gain)` for contextual observations.

Every action observation updates both its contextual bucket and the action-kind fallback. The estimator identity includes a stable configuration hash and a training-data fingerprint that changes when online observations change.

`EstimatorRegistry.register(estimator)` and `resolve(name, version)` provide explicit name/version resolution. The registry key remains stable while `identity.training_data_fingerprint` identifies current learned state.

## Policy

`MarginalPolicy` accepts `PolicyConfig`, an estimator, and optional policy name/version. `identity` contains a stable configuration hash. `build_policy(profile)` creates transparent reference policies:

- `quality-first`;
- `balanced`;
- `token-saver`;
- `strict-budget`.

Profiles are reference defaults, not universal calibrations.

## Treasury

```python
Treasury(limits, policy=..., trace_sink=..., mode="shadow")
```

Primary methods:

- `evaluate(action) -> Decision` without reservation;
- `authorize(action) -> Decision`;
- `fund_best(actions) -> Allocation | None`;
- `commit(action) -> BudgetUsage`;
- `settle_failure(action, actual_cost, reason=...) -> BudgetUsage`;
- `abort(action, reason=...)`;
- `observe_value(action, realized_gain)`;
- `record_outcome(outcome)`;
- `child(name, limits) -> Treasury`;
- `summary() -> dict`.

Failed settlements record spend but do not mark an action as a completed duplicate, allowing a legitimate retry. Non-blocking modes can hold multiple concurrent reservations for the same semantic fingerprint without dropping accounting.

## Decision Ledger

```python
JsonlDecisionLedger(
    path,
    context=DecisionLedgerContext(run_id="..."),
    privacy_profile="safe_telemetry",
    privacy_key_path=".marginal/privacy.key",
)
read_decision_ledger(path)
summarize_decision_ledger(records)
export_decision_ledger(
    source,
    destination,
    privacy_profile="aggregate_export",
    minimum_group_size=5,
)
```

Ledger v2 requires a valid schema version, event ID, monotonically increasing sequence, timestamp, run ID, and event name. Reserved envelope fields cannot be overridden by caller events. When the ledger context contains a task ID, outcome records must match it.

## Privacy API

Public privacy values and functions:

- `PrivacyProfile`: `LOCAL_FULL`, `SAFE_TELEMETRY`, and `AGGREGATE_EXPORT`;
- `PrivacyClass`: safe-by-default, pseudonymous, and potentially sensitive;
- `FIELD_CLASSIFICATION`: published classification for representative ledger fields;
- `LocalPseudonymizer(key)`: field-separated HMAC-SHA-256 pseudonyms;
- `generate_local_identifier(namespace)`: opaque random local correlation IDs;
- `load_or_create_privacy_key(path)`: local 256-bit key management;
- `sanitize_ledger_record(record, profile=..., pseudonymizer=...)`;
- `validate_safe_telemetry_record(record)`: reject malformed pseudonyms, unreviewed fields, free text, and noncanonical strict records;
- `aggregate_ledger_records(records, minimum_group_size=5)`;
- `export_decision_ledger(source, destination, privacy_profile=..., minimum_group_size=5)`.
  Aggregate groups below the threshold are suppressed. Destinations are created exclusively and
  are never overwritten.

`JsonlDecisionLedger` accepts `privacy_profile`, `privacy_key`, and `privacy_key_path`.
`aggregate_export` is rejected as an operational profile and must use the export API. Export
destinations are not overwritten. See [`privacy.md`](privacy.md) for field behavior and threat
model.

## Universal protocol

Public protocol values:

- `AgentAction`;
- `AgentEvent` and `AgentEventType`;
- `AgentDecision`;
- `AgentDirective`;
- `AgentCapabilities`;
- `DeduplicationScope`;
- `UniversalRuntime`.

`AgentAction`, `AgentEvent`, `AgentDecision`, and `AgentCapabilities` provide strict dictionary serialization and parsing where applicable. Protocol metadata used for fingerprinting must be JSON serializable.

Protocol v1 directives are:

```text
allow · deny · modify · defer · reuse · stop · force_verify
```

The v0.2 reference runtime maps core decisions to `allow` or `deny`. The richer directives and replacement payload are stable adapter-extension contracts; MARGINAL does not claim the reference policy automatically generates them.

`UniversalRuntime` in Enforce Mode requires `AgentCapabilities(block_actions=True)`. Observe-only adapters cannot be represented as enforced integrations.

## Wrappers

`budgeted_call`, `async_budgeted_call`, `funded_call`, and `async_funded_call` accept:

- `usage_extractor(result, estimated_cost) -> Cost`;
- `failure_usage_extractor(error, estimated_cost) -> Cost | None`.

A failure extractor returning `None` means no spend was observed and releases the reservation. Returning `Cost` settles measured or best-known failed spend. If the extractor itself fails, MARGINAL conservatively settles the reserved estimate and keeps the original execution exception primary, with the extraction error chained as its cause.

## Usage extraction

- `extract_common_llm_usage(result, estimate) -> Cost` preserves v0.1 total-token accounting;
- `extract_common_token_usage(result) -> TokenUsage` returns an additive breakdown.

Provider schemas differ. Test the exact SDK response shape used by an integration and preserve raw provider evidence outside the core when detailed auditability is required.

## Packaged schemas

```python
from marginal import available_schemas, load_schema

for name in available_schemas():
    schema = load_schema(name)
```

The public schema API reads immutable JSON resources bundled in the installed wheel. Names are restricted to known basenames; path traversal and unknown resources are rejected. The same source contracts remain available under [`schemas/`](../schemas/).

Privacy-specific contracts include `safe-telemetry-v1.json`, which recursively rejects unreviewed fields from strict event-level exports, and `aggregate-export-v1.json`, which accepts only grouped generalized rows.

## Public benchmark comparison

```python
compare_runs(
    baseline,
    marginal,
    bootstrap_samples=2_000,
    seed=42,
    confidence_level=0.95,
    quality_margin_pp=1.0,
)
```

The comparator requires matched task IDs, rejects type-coerced booleans and numbers, reports configurable task-level bootstrap uncertainty, applies the caller-provided non-inferiority margin, and computes tokens and USD per resolved task. The margin must be chosen before inspecting final results.

## Trace sinks

- `JsonlTraceSink`: legacy v0.1-compatible JSONL;
- `JsonlDecisionLedger`: strict v0.2 evidence;
- `CompositeTraceSink`: deterministic fan-out to multiple sinks.

Composite fan-out is sequential, not an atomic distributed write across sinks. Choose one authoritative ledger when cross-sink atomicity is required.

## Outcomes

`Outcome` stores task-level reward, optional resolved status, verifier identity, trajectory identity, metrics, and evidence. It does not assign causal credit to individual actions.

## Replay

```python
result = replay_ledger("ledger.jsonl", policy, limits)
report = render_replay_report(result)
```

Replay is an off-policy recommendation diagnostic over recorded actions and estimated costs. It does not simulate unobserved trajectories, infer preserved quality, or establish causal savings.
