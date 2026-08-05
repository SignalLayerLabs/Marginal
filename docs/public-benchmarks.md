# Public benchmark protocol

MARGINAL is evaluated as a runtime intervention, not as a model. The correct experiment runs the **same agent, model, prompt, tools, task order, and verifier** twice:

1. baseline runtime;
2. baseline runtime with MARGINAL authorization enabled.

The first supported public suites are:

- **Claw-SWE-Bench Lite-80**: 80 tasks, ten per language across Java, Go, Rust, JS/TS, C/C++, Ruby, PHP, and Python.
- **SWE-bench Verified**: 500 human-validated Python issue-resolution tasks.
- Any benchmark that exports one matched JSONL row per task.

## Required row schema

```json
{"instance_id":"django__django-11790","resolved":true,"tokens":48210,"usd":0.84,"latency_ms":182000,"tool_calls":27}
```

Only `instance_id`, `resolved`, and `tokens` are required. Missing optional metrics default to zero. Baseline and MARGINAL files must contain exactly the same instance IDs; the evaluator refuses unmatched samples.

## Run the comparison

```bash
marginal public-eval baseline.jsonl marginal.jsonl > PUBLIC_BENCHMARK.md
marginal public-eval baseline.jsonl marginal.jsonl --json > public-benchmark.json
```

The report includes:

- resolve rate and percentage-point delta;
- total token, USD, latency, and tool-call savings;
- regressions and recoveries;
- a 95% task-level bootstrap interval for token savings;
- a quality-preservation flag requiring no more than one percentage point of resolve-rate loss.

## Fairness requirements

- Freeze model version, agent code, prompt, temperature, tools, runtime limits, and task order.
- Do not drop failed, timed-out, or expensive tasks.
- Count premature MARGINAL stops as unresolved.
- Export actual provider usage rather than character-count estimates when available.
- Publish both JSONL inputs and the generated report.
- Use at least three runs per task when the agent is stochastic, then report paired means.

## Claw-SWE-Bench Lite-80

The public Lite subset contains 80 tasks selected from a 350-task multilingual set using a cost-aware, rank-aware calibration procedure. Install and load it with:

```bash
pip install datasets
python - <<'PY'
from datasets import load_dataset
rows = load_dataset("TokenRhythm/Claw-SWE-Bench", "lite", split="test")
print(len(rows))
PY
```

The benchmark runner is intentionally not bundled with provider credentials. Connect your agent's final verifier result and usage counters to the JSONL schema above, then run `marginal public-eval`.

## Interpretation

A publishable MARGINAL claim must report both axes together, for example:

> 38.4% fewer tokens (95% CI 34.1–42.7%) with a -0.4 percentage-point resolve-rate delta on Claw-SWE-Bench Lite-80.

A token reduction without preserved verified outcomes is not considered a successful result.
