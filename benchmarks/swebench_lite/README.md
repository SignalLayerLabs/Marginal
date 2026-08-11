# SWE-bench Lite matched canary

This directory defines MARGINAL's first public external benchmark harness. It does **not** bundle a coding model and it does not treat SWE-bench as a MARGINAL dependency.

The experiment compares the same coding agent under two matched conditions:

- **baseline / OFF** — MARGINAL is absent;
- **marginal / ON** — the same agent, model, prompt, tools, limits, task order, and verifier run with MARGINAL intervention enabled.

The official SWE-bench evaluator supplies task correctness. Inference telemetry supplies cost and behavior metrics. Those evidence sources stay separate until `merge_results.py` combines them.

## Frozen task set

Dataset: `princeton-nlp/SWE-bench_Lite`, split `dev`.

The public dev split contains 23 instances. `canary.json` freezes the IDs visible in the public dataset viewer on 2026-08-07. To avoid cherry-picking, the three instance IDs with the lexicographically lowest `SHA-256(instance_id)` digests are the smoke set. The remaining 20 instances, in dataset-viewer order, are the canary set.

The smoke set validates the pipeline. It is not performance evidence. The 20-task canary is still an engineering canary, not a headline benchmark claim.

## Evidence directory

Create a directory below `benchmarks/swebench_lite/evidence/`, for example:

```text
benchmarks/swebench_lite/evidence/canary-001/
  manifest.json
  baseline_predictions.ndjson
  marginal_predictions.ndjson
  baseline_metrics.ndjson
  marginal_metrics.ndjson
```

`manifest.json` records the frozen execution contract:

```json
{
  "schema_version": 1,
  "benchmark": "swe-bench-lite-dev-canary",
  "dataset": "princeton-nlp/SWE-bench_Lite",
  "split": "dev",
  "task_set": "canary",
  "agent": "codex-cli",
  "agent_version": "<exact version>",
  "model": "<exact model>",
  "prompt_sha256": "<64 lowercase hex chars>",
  "limits": {
    "max_turns": 20,
    "timeout_seconds": 1800
  },
  "marginal": {
    "version": "0.2.0+unreleased",
    "commit": "<40 lowercase git SHA>",
    "mode": "enforce",
    "policy": "balanced+diminishing-return"
  }
}
```

You may also add `task_set_sha256` using the digest printed in `canary.json`.

### Predictions

SWE-bench expects one JSON object per task:

```json
{"instance_id":"owner__repo-123","model_name_or_path":"same-model","model_patch":"diff --git ..."}
```

Keep failed, timed-out, or stopped tasks in the file using an empty `model_patch` when no patch exists. Never drop expensive or unsuccessful tasks after seeing the outcome.

**Rule: gold patches are not MARGINAL evidence.** They are useful for validating the SWE-bench installation, but they cannot show whether MARGINAL improved an agent trajectory.

### Metrics

Each metrics JSONL row contains measured inference/runtime telemetry. `resolved` is deliberately forbidden because correctness belongs to the independent SWE-bench verifier.

```json
{
  "instance_id": "owner__repo-123",
  "tokens": 48210,
  "usd": 0.84,
  "latency_ms": 182000,
  "tool_calls": 27,
  "repeated_calls": 4,
  "governance_tokens": 0,
  "governance_usd": 0.0,
  "governance_latency_ms": 0,
  "reviewed_stops": 0,
  "false_stops": 0
}
```

Baseline governance and stop-review fields must all be zero. MARGINAL telemetry may report non-zero governance overhead and explicit reviewed false stops.

## Validate before spending Modal compute

```bash
python benchmarks/swebench_lite/protocol.py validate \
  --run-dir benchmarks/swebench_lite/evidence/canary-001 \
  --task-set canary
```

The validator checks the manifest, task order, prediction model identity, lane matching, metric types, verifier ownership of `resolved`, and zero baseline governance overhead.

## Run from GitHub

The workflow is intentionally manual:

1. Open **Actions → SWE-bench Lite Canary → Run workflow**.
2. Keep `task_set=smoke` for the first infrastructure validation.
3. Set `run_dir` to the committed evidence directory.
4. Run the 20-task `canary` only after the smoke workflow succeeds.

GitHub Actions authenticates to Modal through the repository secrets `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`. No coding-model credential is required by this verification workflow.

The workflow runs the official SWE-bench evaluator with `--split dev --modal true` for both lanes, merges verifier outcomes into telemetry, runs `marginal public-eval`, adds the Markdown comparison to the Actions job summary, and uploads the complete evidence bundle as an artifact.

The verifier adapter accepts both SWE-bench result layouts currently encountered in the public harness: per-instance `instance_results.jsonl` and the aggregate schema-v2 `<model>.<run_id>.json` report containing `submitted_ids` / `resolved_ids`. Empty patches remain unresolved. `error_ids` and `incomplete_ids` fail closed: infrastructure failures cannot be silently scored as model failures.

## Interpretation

A valid run can conclude `supported`, `pass_through`, `quality_regression`, or `false_stop_risk`. A lower token count is not considered a win if verified quality regresses or MARGINAL's own governance overhead removes the apparent saving.

## First completed smoke

The evidence bundle in [`evidence/smoke-2026-08-11-dbce533/`](evidence/smoke-2026-08-11-dbce533/) contains the first matched Codex OFF/ON run. The authoritative SWE-bench 4.1 Docker verifier completed 3/3 tasks per lane with zero infrastructure errors; both lanes resolved 0/3. The resulting intervention status is `pass_through`, even though ON used 24.93% fewer measured tokens, because no successful task exists from which to calculate effective compute per resolved task.

The associated [Modal workflow run](https://github.com/SignalLayerLabs/Marginal/actions/runs/31474500980) completed but reported a symmetric build failure for one task in each lane. Those reports are retained as `verifier_modal_*.json` for audit and are not used as correctness evidence. See `verification.json` for the verifier chain and report digests.
