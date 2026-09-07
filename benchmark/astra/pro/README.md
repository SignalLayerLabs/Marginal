# GPT-6 Astra × MARGINAL on SWE-bench Pro

**Execution in progress, not a completed performance benchmark.** The full experiment needs
731 problems × two independent conditions = 1,462 model executions and official grading.
A passing reference patch is not evidence that MARGINAL improves quality or reduces tokens.

## Published evidence

- [Protocol](protocol.json): model, limits, task order, accounting and failure rules.
- [All 731 task IDs](task-manifest.jsonl), ordered by SHA256 of instance ID before inference.
- [Preflight](preflight.json): the first official environment and measured validation facts.
- [Official reference verdict](gold-eval-results.json) and [parsed tests](gold-test-results.json).

The first reference patch passed official grading in 1,350.20 seconds on an Apple Silicon
Mac running the x86 image under QEMU. This is an infrastructure check, not an Astra score.
The actual pinned image uses Alpine 3.18.3, although its published Dockerfile specifies
Ubuntu 20.04. Solver tooling must match the actual image ABI; no repository dependency
upgrade is used to hide that difference.

## What the comparison can establish

OFF is Codex without MARGINAL. ON uses the existing benchmark adapter with balanced policy,
the default diminishing-return detector and experimental enforcement. Both use Astra,
medium reasoning and a 900-second model-run limit, with fresh state and the same issue.

**This is not the installed plugin's default Shadow Mode.** Findings cannot justify a claim
that simply installing the default plugin saves tokens or reduces internal reasoning.
Correctness, provider token totals, cached-token subsets, tool calls, elapsed time and
governance overhead must be reported together. Missing data and failures remain visible.
Public and independently regradable does not mean independently certified.

## Reproduce the reference check

1. Fetch `ScaleAI/SWE-bench_Pro`, revision
   `7ab5114912baf22bb098818e604c02fe7ad2c11f`, complete `test` split. Export it as CSV.
   The downloaded parquet SHA256 is recorded in the protocol.
2. Check out the [official evaluator](https://github.com/scaleapi/SWE-bench_Pro-os) at
   `ca10a60a5fcae51e6948ffe1485d4153d421e6c5` and install its local-Docker dependencies.
3. Create a prediction JSON array using the first manifest ID and its dataset `patch` field:
   `[{"instance_id": "...", "patch": "...", "prefix": "gold"}]`.
4. From the official evaluator checkout, run:

```sh
python swe_bench_pro_eval.py \
  --raw_sample_path=dataset.csv --patch_path=gold-first.json \
  --output_dir=gold-evaluation --scripts_dir=run_scripts \
  --num_workers=1 --dockerhub_username=jefzda \
  --use_local_docker --block_network --docker_platform=linux/amd64
```

Verify the downloaded task image digest matches `preflight.json`. The upstream evaluator
uses a tag; record its resolved digest before and after grading. Keep reference data and
test scripts outside solver mounts.

## Solver boundary

[Dockerfile.solver](Dockerfile.solver) adds pinned tools to an official task image.
[pro_lane.py](../pro_lane.py) executes one condition using the shared Codex runner. The
container must be disposable: the lane removes its original Git history and verifies a
single-commit snapshot with the exact base tree. Unsupported gitlinks fail closed.

Mount only the public rendered prompt at `/marginal-input/prompt.txt`, a fresh output
directory at `/marginal-output`, and the existing Codex login read-only at
`/run/secrets/codex-auth.json`. Never mount the host workspace, other lane output, reference
data or Docker socket. Never publish authentication files. Preserve failed attempts and
their usage; do not rerun solved or failed model attempts to select a better result.

No complete benchmark score or measured token-saving percentage is available yet.
