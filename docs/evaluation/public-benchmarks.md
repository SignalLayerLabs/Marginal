# Public benchmark protocol

MARGINAL is evaluated as a runtime intervention, not as a model. The correct experiment
runs the **same agent, model, prompt, tools, task order, runtime limits, and verifier** under
matched conditions:

1. the unmodified baseline runtime;
2. the same runtime with MARGINAL enabled.

The release includes a provider-neutral comparator. It does not bundle provider credentials
or claim that a vendor-specific benchmark runner is already complete.

## Required row schema

Each JSONL file contains one object per matched task:

```json
{"instance_id":"django__django-11790","resolved":true,"tokens":48210,"usd":0.84,"latency_ms":182000,"tool_calls":27}
```

`instance_id`, `resolved`, and `tokens` are required. Optional metrics default to zero.
`resolved` must be a real JSON boolean; strings such as `"false"` are rejected. Baseline
and MARGINAL files must contain exactly the same instance IDs.

## Run the comparison

```bash
marginal public-eval baseline.jsonl marginal.jsonl \
  --confidence-level 0.95 --quality-margin-pp 1.0 \
  > PUBLIC_BENCHMARK.md
marginal public-eval baseline.jsonl marginal.jsonl \
  --confidence-level 0.95 --quality-margin-pp 1.0 --json \
  > public-benchmark.json
```

The generated comparison reports:

- resolve rate and percentage-point delta;
- total token, USD, latency, and tool-call savings;
- regressions and recoveries;
- a configurable task-level bootstrap interval for token savings;
- tokens and USD per resolved task;
- whether the preregistered non-inferiority criterion is met.

## Fairness requirements

- Freeze the model version, agent code, prompt, temperature, tools, limits, and task order.
- Do not drop failed, timed-out, prematurely stopped, or expensive tasks.
- Count premature MARGINAL stops as unresolved.
- Export actual runtime or provider usage rather than character-count estimates.
- Publish both JSONL inputs, environment metadata, and the generated report.
- Use repeated paired runs when the agent is stochastic.
- Preregister the quality non-inferiority margin before inspecting the final result.
- Keep synthetic demonstrations separate from measured runtime claims.

## Token telemetry

Where the runtime exposes it, collect and publish:

- uncached input tokens;
- cached input tokens;
- output tokens;
- reasoning tokens;
- total tokens.

The current public comparator consumes the total token field. Decision Ledger v2 and
`TokenUsage` preserve the richer breakdown for engine-specific runners and future reports.

## Interpretation

A publishable claim must report cost and quality together, for example:

> 38.4% fewer tokens with a -0.4 percentage-point resolve-rate delta under the preregistered evaluation protocol.

A token reduction without preserved verified outcomes is not considered a successful
MARGINAL result. Policy replay is not a substitute for paired execution: replay cannot
simulate state changes or outcomes from actions that another policy would have skipped.
