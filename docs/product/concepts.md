# Concepts

## Action, Cost, and TokenUsage

An `Action` is proposed work. `Cost` records total tokens, direct USD, latency, and application-defined risk. `TokenUsage` records additive uncached input, cached input, non-reasoning output, reasoning, and total tokens.

The provider-neutral hard ledger continues to use `Cost.tokens`. The detailed token breakdown is evidence for analysis, pricing, and benchmarks.

## Applied decision versus recommendation

`Decision.allowed` is what the execution mode applies. `Decision.recommended` is what the policy recommended before a non-blocking override.

- Enforce: applied equals recommended.
- Shadow: every proposed action is applied, but the recommendation is preserved.
- Recommend: non-blocking behavior intended for visible advisory integrations.

Stable reason codes support analytics without forcing integrations to parse human-readable strings.

## Directives

The universal protocol represents adapter instructions as `AgentDirective` values: allow, deny, modify, defer, reuse, stop, and force-verify. Core v0.2 decisions currently produce allow or deny. Other directives are explicit extension points for adapters and future policies.

## Capability negotiation

`AgentCapabilities` states what an adapter can observe or control. Capability level is derived rather than trusted from input. Enforce Mode requires real action-blocking capability; a prompt convention or advisory skill is not enforcement.

## Reservation and settlement

Authorization reserves estimated resources. Commit replaces the reservation with actual usage. Abort releases the reservation when no external spend occurred. Failure settlement records measured or conservatively estimated spend from a failed external action.

A failed action is accounted but not marked as a successfully completed duplicate. Concurrent semantic duplicates in non-blocking modes receive separate internal reservation identities so Shadow Mode does not alter agent behavior.

## Verification reserve

A verification reserve protects tokens or USD that only verification actions may consume. It prevents generation from exhausting the entire budget before tests or checks can run.

## Decision Ledger

The Decision Ledger is a schema-versioned JSONL evidence stream. It correlates actions, decisions, identities, costs, failures, observations, and outcomes. Avoiding prompt and output fields is not sufficient by itself because quasi-identifiers and free text can still reveal sensitive information.

Every new ledger declares `local_full` or `safe_telemetry`. `local_full` preserves the complete operational event. `safe_telemetry` uses a strict allowlist, removes potentially sensitive content, pseudonymizes identifiers with a local key, and generalizes exact timestamps. `aggregate_export` is a separate grouped export with no identifiers or timestamps and suppresses
groups smaller than five records by default.

It is append-only at the application level, not cryptographically tamper-proof and not multi-process transactional. Pseudonymization is not anonymization.

## Outcome

An `Outcome` describes a verified task-level result. It does not automatically assign causal credit to preceding actions. Outcome task identity must match the runtime or ledger context when one is declared.

## Value estimate and estimator state

`ValueEstimate` includes expected gain, uncertainty, confidence, sample size, provenance, and estimator identity. Explicit estimates remain supported. Historical estimates are observational.

Contextual observations also update the action-kind fallback. Online observations update `training_data_fingerprint`, so otherwise identical estimator versions with different learned state can be distinguished.

## Fingerprints and deduplication

Core guarded calls use deterministic semantic fingerprints. Universal actions add state-aware scopes:

- exact;
- once per state;
- once per phase;
- retry-number aware.

Protocol fingerprint metadata must be JSON serializable. Arbitrary object `repr` values are not accepted because they may be process-dependent.

## Replay

Replay asks what another policy would have recommended for recorded proposed actions. It does not know what unexecuted trajectories would have produced and is not causal proof.
