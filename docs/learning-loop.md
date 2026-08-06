# Learning Loop Foundation

MARGINAL's defensible direction is not a static ROI formula. It is a disciplined evidence loop:

```text
observe proposed actions
→ record recommendations and applied behavior
→ measure actual cost and verified outcome
→ estimate action value with uncertainty
→ replay and compare policies
→ validate before stronger enforcement
```

## Why Shadow Mode comes first

A policy that immediately denies actions observes only what it chose to execute. This creates selection bias. Shadow Mode records would-deny decisions while the underlying agent continues unchanged, producing evidence about the action and trajectory.

Shadow data still does not prove causal value. Actions occur in sequences, outcomes are delayed, and successful tasks may contain unnecessary actions. Future causal work requires paired runs, controlled exploration, propensity logging, deterministic verifiers, and careful off-policy evaluation.

## Evidence types

### Decision evidence

What the policy knew, estimated, recommended, and applied.

### Usage evidence

Estimated and actual tokens, direct cost, latency, and risk, including failed calls and conservative fallback accounting when usage extraction fails.

### Outcome evidence

Task-level verifier result, reward, metrics, and supporting evidence.

### Action-level realized gain

Explicit application-provided evidence that one action changed success probability. This is never inferred automatically from a task outcome.


## Privacy boundary

Learning evidence can contain quasi-identifiers even without prompts or outputs. A task ID,
action name, model name, repository label, verifier, exception, or exact timestamp may identify
a customer or project. `LOCAL_FULL` keeps the complete trusted operational record.
`SAFE_TELEMETRY` removes potentially sensitive content, pseudonymizes identifiers with a local
key, and retains structured learning fields. `AGGREGATE_EXPORT` groups generalized rows and
removes identifiers and timestamps.

Strict privacy profiles preserve policy and estimator versions, decisions, reason codes, cost,
confidence, uncertainty, and structured outcomes while dropping provenance and free text. This
lets calibration and policy analysis continue without treating caller metadata as shareable.
Pseudonymization is not anonymization; small or unusual groups can remain identifiable.

## Estimator versioning and learned state

Every useful learning record needs policy and estimator identity. Estimator identity contains:

- implementation name;
- semantic version;
- configuration hash;
- training-data fingerprint.

Online action observations update the training-data fingerprint. This separates two estimator instances that use the same code and configuration but have learned from different evidence.

Contextual observations also update the action-kind fallback, allowing new contexts to benefit from broader evidence while still preferring exact contextual history when available.

## Replay limits

Replay can estimate how a policy would classify recorded proposed actions and their recorded costs. It cannot know whether denied actions would have changed later state or quality. Reports therefore use “estimated selected/avoided cost,” never “causal savings.”

Malformed authorization evidence is rejected rather than coerced or silently skipped.
