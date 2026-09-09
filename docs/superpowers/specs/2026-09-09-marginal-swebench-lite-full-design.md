# Marginal SWE-bench Lite Full Benchmark Design

Status: approved by the user mandate dated 2026-09-09.

## Outcome

Run every task in the 300-instance SWE-bench Lite test split once with Codex alone and once
with the experimental MARGINAL benchmark adapter. Produce 600 immutable attempts, grade both
prediction sets with the official local Docker harness, publish independently verifiable
artifacts, and open a real Lite submission PR for the ON lane.

Completion has four distinct states: benchmark complete, submission packaged, submission PR
opened, and leaderboard accepted. Only maintainers can establish the last state.

## Frozen contract

- Dataset: `SWE-bench/SWE-bench_Lite`, `test`, repository revision
  `b0dde1093fe417d83b7184254edf8199c1f0dff5`, all 300 instances.
- Evaluator: `SWE-bench/SWE-bench` commit
  `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` using its v5 local Docker CLI.
- Product under test: MARGINAL commit `71c8eae` and packaged runtime provenance at that commit.
- Agent: Codex CLI `0.153.4`, model `gpt-6-astra`, reasoning effort `medium`.
- One attempt per condition and task; 900-second model timeout; no hints, gold patches,
  `FAIL_TO_PASS`, `PASS_TO_PASS`, or evaluator feedback in inference.
- Prompt: `benchmark/prompt_template.txt`, SHA-256
  `3a2ced1afb7e9a74176090db264259c52b6ebcf383d787a1030f83ecb6d67416`.
- Public randomization seed:
  `81b598cbff3bff863cbbb4a3dea1489ce9dd3f2070e6bf766befb25cd436cd9b`.
- Cost: zero euros. Authentication is the existing Codex CLI ChatGPT session. No OpenAI API
  key is requested, copied, logged, or published.

The 300 tasks are ordered by SHA-256 of `seed + NUL + instance_id`. Within each task, the first
condition is selected by the low bit of SHA-256 of `seed + NUL + instance_id + NUL + "condition"`;
the other condition follows. This schedule is committed before test inference.

## Execution boundary

Each condition runs in a fresh derivative of the official per-instance Docker image. The common
tooling layer contains Codex 0.153.4, a pinned standalone Python, the product-under-test source,
and the benchmark adapter. The solver receives only the issue text and its one-commit base-tree
snapshot. Git history, benchmark tests, hints, reference patches, the other lane, and prior
artifacts are absent. Tool network access is disabled while Codex transport retains network access.

OFF uses the same binary, model, prompt, timeout, image, and resource limits with MARGINAL absent.
ON uses the experimental synchronous PreToolUse/PostToolUse adapter in enforce mode. Native plugin
status remains Shadow/L0 and is reported separately; ON is not described as default plugin behavior.

## Checkpoint and failure semantics

The orchestrator writes an immutable attempt marker before launching a lane and never overwrites
an existing lane directory. A completed lane contains raw Codex events, stderr, patch, run record,
environment provenance, and ON governance evidence. An interrupted, timed-out, quota-limited, or
failed attempt remains represented with an empty patch when necessary. It is not retried or removed.

Resume selects only schedule entries with no attempt marker. When Codex reports exhausted account
capacity, execution stops after preserving that attempt. Subsequent invocations continue from the
next untouched entry; no cherry-picking or outcome-dependent ordering is possible.

The validation phase uses one preregistered Lite `dev` task and is excluded from the 300-task score.
Pipeline fixes may address transport, packaging, telemetry, or evaluator defects, but the MARGINAL
policy cannot be tuned from validation outcomes.

## Evaluation and analysis

Export complete OFF and ON `all_preds.jsonl` files, including empty patches. Use distinct evaluator
run IDs and the official Docker harness. Preserve per-instance reports and test output. Separate
task failures from infrastructure failures.

The report includes resolved counts, absolute and relative deltas, the paired 2x2 table, exact
McNemar analysis, paired bootstrap confidence intervals, preregistered non-inferiority, token,
wall-time and tool-call deltas, intervention and effective-intervention rates, false-stop rate,
governance overhead, repository breakdowns, and timeout/error breakdowns. A token-saving claim is
allowed only if quality and governance tax are reported beside it.

## Publication and submission

The Marginal repository publishes the protocol, frozen manifest, runner, validation, status, and
analysis code. Completed public artifacts go to `SignalLayerLabs/Marginal-SWE-bench-Lite` with all
predictions, official logs, patches, reports, compressed test output, and available public Codex
event trajectories. Authentication material and private chain-of-thought are never included.

Use the current official workflow against the finished ON evaluation directory:

```sh
swebench submit package <on-evaluation-directory> --trajs <trajectory-directory>
swebench submit publish <on-evaluation-directory> -r SignalLayerLabs/Marginal-SWE-bench-Lite
swebench submit verify <on-evaluation-directory>
swebench submit register <on-evaluation-directory>
```

Complete metadata identifies `Marginal + Codex` as the agent system, GPT-6 Astra as the model,
attempts `1`, SignalLayerLabs as the organization, the public technical report, author Renato
Vinai, source code, exact commits, and experimental governance mode. The PR checklist explicitly
attests no test knowledge, hints, solution lookup, or repeated attempts.

