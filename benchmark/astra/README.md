# GPT-6 Astra evaluation status — updated 2026-09-08

**No complete Astra OFF/ON benchmark has been executed. No token-saving claim is supported.**

This directory records preflight facts, not benchmark results. Product integration tests and a
successful model request do not demonstrate improved task quality or lower token use.

The active experiment is [SWE-bench Pro](pro/README.md). Its complete 731-task manifest,
protocol and first official reference-validation artifacts are published there. HumanEval+
preparation was withdrawn before any scored model inference.

## Frozen public benchmark inputs

- Dataset: [ScaleAI/SWE-bench_Pro](https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro),
  revision `7ab5114912baf22bb098818e604c02fe7ad2c11f`, complete `test` split: **731 tasks**.
- Evaluator: [scaleapi/SWE-bench_Pro-os](https://github.com/scaleapi/SWE-bench_Pro-os),
  commit `ca10a60a5fcae51e6948ffe1485d4153d421e6c5`.
- A single complete OFF/ON comparison requires **1,462 independent task executions**, followed
  by official grading. It is not equivalent to 1,462 unit tests or grading empty patches.
- Intended model: `gpt-6-astra`, with identical reasoning effort, prompts, tools, limits and
  independent state in both conditions. No task has been selected based on its model outcome.

## Observed preflight

| Check | Observation |
| --- | --- |
| Codex 0.147.0 + Astra | Provider rejected the request and required a newer Codex version |
| Codex 0.153.4 + Astra | Minimal no-tool request completed successfully |
| Successful request usage | 16,474 input; 11,520 cached input; 7 output; 0 reasoning output |
| Docker | Existing local benchmark VM started; Docker 29.5.2, 6 CPUs, about 12 GiB RAM |
| Existing task images | Three historical Lite smoke images retained; first Pro image downloaded |
| First deterministic Pro image | Pinned in [Pro preflight](pro/preflight.json); actual OS is Alpine 3.18.3 |
| Official Pro grading | First reference patch passed; 1,350.20 seconds under x86 QEMU |
| Scored Astra task trajectories | **0 baseline / 0 MARGINAL** |

The successful no-tool request is an API/CLI compatibility probe only. Its input token count
includes the Codex scaffold and cannot be extrapolated into a reliable per-task cost estimate.
Cached input and reasoning output are subsets, not additional tokens to sum twice.

## Required before results can be published

1. Adapt and validate the runner against current Codex and official Pro task environments.
   The historical Lite adapter is not a verified Pro execution backend.
2. Pin images and prompts; validate the evaluator on reference patches in isolated containers.
3. Publish the executable protocol before scored inference. The dataset pins above alone are
   **not** a complete preregistration.
4. Run all 731 tasks in each condition without exposing reference patches or grading tests
   to the solving agent. Preserve failures, timeouts and every task ID.
5. Publish sanitized predictions, per-task usage, official grading, intervention traces,
   environment hashes and analysis. Report correctness and governance overhead together.

The sprint reserves 20% of the short Codex quota window for validation and publication. A
quota stop must remain visibly incomplete; it cannot become a fabricated full benchmark,
a smaller benchmark labelled Pro, or a claim that default Shadow Mode saves reasoning tokens.

HumanEval+ was considered as a lower-cost alternative but has not been run or substituted
for the requested real-repository comparison. No external leaderboard certification is claimed.
