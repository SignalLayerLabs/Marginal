# Governance Evidence Standard

MARGINAL is an intervention in an agent runtime. Its evaluation must therefore include the cost and mistakes introduced by the intervention itself.

## Core equation

The useful quantity is not raw token reduction. A benchmark should reason about net intervention value:

```text
net intervention value
  = workload benefit
  - governance overhead
  - quality loss
  - harmful false stops
  - added latency / direct cost
```

The implementation does not collapse those terms into one magic score. It reports them separately so a reviewer can inspect the tradeoff.

## Governance tax

`GovernanceTracker` separates local decision overhead from external overhead introduced by an adapter or auxiliary model call.

- local decision latency is measured by `Treasury` around policy recommendations;
- adapter-side governance tokens, USD and latency are recorded explicitly with `record_governance_overhead(...)`;
- the benchmark evaluator adds workload and governance cost into effective tokens, USD and latency;
- gross savings remain visible, but net savings are the primary claim surface.

A governor that reduces workload tokens while consuming more total effective tokens should not be described as an optimization.

## Graceful Irrelevance

`compare_runs(...)` can classify an otherwise quality-preserving result as `pass_through` when net token savings do not exceed a preregistered threshold.

This behavior is intentional. A future model, runtime or task may already be efficient enough that MARGINAL adds no material value. The correct behavior is to get out of the way, not to force intervention.

## Diminishing-return evidence

`DiminishingReturnDetector` is provider neutral and opt-in. It uses fields already available through normalized agent actions:

- semantic action identity;
- workspace/state hash;
- optional evidence hash;
- execution history.

The detector's `evaluate(...)` method does not mutate history. `observe(...)` is called only after actual successful execution. This prevents a denied proposal from being counted as if it consumed compute.

The default logic fails open when state is unavailable. A repeat is discounted only when the same semantic action is observed in the same state without new evidence. A changed state or evidence hash resets the pressure.

## False Stop Rate

A token optimizer can look excellent by simply preventing an agent from working. False-stop accounting exists to make that failure visible.

A false stop means:

> MARGINAL recommended denying an action, and an explicit external review concluded that the action would have helped.

The implementation deliberately does **not** infer false stops from task-level success or failure. `Treasury.record_stop_review(...)` accepts an explicit boolean label and refuses to label actions that were not previously recommended for denial.

Public reports expose:

```text
reviewed_stops
false_stops
false_stop_rate
```

The acceptable false-stop threshold should be preregistered for a public evaluation. A strict zero threshold is a reasonable starting point for early enforcement experiments; Shadow Mode should be used to gather evidence before blocking behavior.

## Matched OFF/ON protocol

A defensible runtime comparison holds constant:

- agent and agent version;
- model and model configuration;
- prompt / task input;
- tools and permissions;
- token and time limits;
- task ordering;
- repository/environment state;
- verifier and success criterion.

MARGINAL is the intervention. If other variables change, the result cannot cleanly attribute the difference to MARGINAL.

## Reported metrics

The minimum public report should include:

| Metric | Requirement |
|---|---|
| Verified resolution rate | Baseline and MARGINAL |
| Quality delta | Percentage points and preregistered non-inferiority margin |
| Agent tokens | Gross workload usage |
| Governance tokens | Added by MARGINAL / adapter |
| Effective tokens | Agent + governance |
| Effective tokens per resolved task | Primary efficiency metric |
| USD and latency | Gross and effective where measurable |
| Tool calls | Baseline and MARGINAL |
| Repeated calls | Same definition across both arms |
| Regressions / recoveries | Instance-level counts |
| Reviewed / false stops | Explicit counterfactual labels |
| Statistical uncertainty | Repeated runs and/or bootstrap interval |
| Intervention status | Supported, pass-through, quality regression or false-stop risk |

## Canary versus evidence

The v0.3 10-task Codex canary exists to answer engineering questions: does installation work, are events correlated correctly, are tokens measured correctly, and can runs finish without adapter failures?

It does not answer the product-performance question. A public result requires a larger preregistered sample and enough repeated execution to characterize variance.

## Benchmark selection

SWE-bench Pro is a useful community-requested evaluation surface because it gives an externally recognizable coding workload. It should not be the only surface. MARGINAL also needs targeted workloads that make its claimed mechanism observable, including repeated same-state verification and retry patterns.

For every benchmark, record the exact dataset version, verifier, exclusions and known task-quality limitations. A recognizable benchmark name is not a substitute for inspecting the evaluation instrument.

## Claim discipline

Allowed language after a measured run should resemble:

> Under the preregistered configuration, MARGINAL reduced effective tokens per verified successful task by X%, with a Y pp resolution-rate delta and Z reviewed false stops.

Avoid universal statements such as “MARGINAL cuts agent tokens by X%.” Results belong to a model, agent, benchmark version, policy configuration and date.
