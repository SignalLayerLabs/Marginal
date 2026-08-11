# What MARGINAL Actually Does

## Scope inspected

This description is based on repository commit
`4c8856401b4c752d5c214df5e84b9632d9897ec9`, including the implementation under
`src/marginal`, tests, Universal Agent Protocol, governance controls, and benchmark code.

MARGINAL is a provider-neutral Python decision, accounting, and evidence layer for agent
runtimes. It is not itself a coding agent, prompt compressor, model router, or completed
Codex integration.

## Implemented pipeline

```text
engine adapter proposes normalized action
  -> Treasury prepares identity and checks pending work
  -> hard child/parent budget checks
  -> MarginalPolicy requests ValueEstimator estimate
  -> optional DiminishingReturnDetector adjustment/rejection
  -> expected value, cost value, score, and ROI decision
  -> execution mode applies or overrides recommendation
  -> reserve
  -> external action executes or is skipped
  -> commit actual usage, settle measured failure, or abort
  -> trace/Decision Ledger/outcome/governance evidence
```

## Inputs and signals

An `Action` contains a name, kind, estimated `Cost`, optional expected success gain,
current success probability, verification flag, fingerprint, and metadata. `Cost` has
tokens, direct USD, latency, and application-defined risk. The core does not inspect a
Codex transcript or infer these fields from native Codex events; an adapter must supply
them.

The reference `ValueEstimator` uses, in priority order:

1. explicit `Action.expected_gain`;
2. contextual historical observations;
3. action-kind historical observations;
4. a default expected gain of `0.05` with zero confidence.

Action-level realized gain is accepted only through an explicit observation call. Task
success is not automatically assigned as causal credit to every action in a trajectory.

## Policy

The policy computes:

```text
expected value = capped expected gain * configured outcome value
cost value = direct USD + token shadow cost + latency shadow cost + risk shadow cost
score = expected value - cost value
ROI = expected value / cost value
```

It can reject work because the target success probability is reached, the action is an
executed or pending duplicate, a budget/reserve would be breached, expected gain is too
low, or score/ROI does not clear the configured threshold. `fund_best` ranks a caller-
provided candidate set; it does not invent alternatives for a single action proposed by
an external agent.

## Diminishing returns

The opt-in detector derives a semantic key from
`metadata.marginal_semantic_key`, or from normalized kind/name/phase. It also reads
`state_hash` and optional `evidence_hash` metadata.

It fails open when state is absent. At the default `gain_decay=0.5` and
`max_same_state_repeats=2`, one successful same-state execution causes the next proposal's
gain to be halved; after two such executions, the next proposal receives a stop
recommendation. A changed state or changed non-empty evidence hash resets the repetition
pressure. Only successful execution advances detector history.

This is exact adapter-defined semantic repetition, not fuzzy recognition of arbitrary
reasoning loops or hypothesis oscillation.

## State and evidence

`Treasury` maintains committed usage, reservations, pending semantic identities, executed
fingerprints, counts, outcomes, estimator observations, and a shared governance tracker.
The Decision Ledger records run/task/trajectory/engine/model identity, recommendation
versus applied behavior, policy and estimator identity, cost, failures, and outcomes.

Governance evidence separates local policy-decision latency from external adapter tokens,
USD, and latency. False stops require explicit external review; they are not inferred from
final task outcomes.

## Modes

- `shadow`: recommendations are recorded but proposed actions execute.
- `recommend`: currently non-blocking like shadow at the Treasury authorization boundary.
- `enforce`: denials prevent guarded work from executing.

`fund_best` remains an active selection API in every mode.

## Codex integration status

The repository supplies Universal Agent Protocol and a generic runtime, but no completed
Codex adapter. The existing SWE-bench workflow verifies already-generated patches and
merges telemetry; it does not run Codex or inject MARGINAL into its loop.

For this experiment, the missing integration is implemented outside the core through
official Codex `PreToolUse` and `PostToolUse` hooks. Therefore the tested variable is the
current MARGINAL policy applied to hook-covered local tool actions. Hosted tools and model
calls are outside the initial enforcement boundary.

The pinned Codex 0.147 stable response for unified shell execution omits process exit
status from `PostToolUse`. The adapter therefore cannot faithfully identify successful
shell/test/search executions. It failure-settles them conservatively and the mandatory
preflight blocks comparative inference until a tested success-observable boundary exists.

## OFF and ON conditions

**OFF:** Codex runs with the external JSONL collector but without MARGINAL imports,
processes, hooks, state, messages, or configuration.

**ON:** the identical Codex invocation additionally loads the tested hook adapter and a
per-task MARGINAL daemon configured with the released balanced profile, default
diminishing-return detector, unlimited hard budgets, and enforce mode.

No core behavior or threshold may be changed after comparative outcomes are observed.
