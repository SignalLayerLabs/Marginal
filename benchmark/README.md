# Codex baseline versus Codex + MARGINAL

This directory contains the preregistration, runner, raw evidence, and analysis for a
correctness-first paired evaluation of Codex with MARGINAL OFF and ON.

No synthetic MARGINAL demo result is accepted as evidence for this comparison. Task
correctness comes only from the benchmark's independent verifier. Failed, timed-out,
empty-patch, and integration-failed runs remain in the dataset.

## Frozen smoke set

- Dataset: `princeton-nlp/SWE-bench_Lite`
- Split: `dev`
- Selection rule: the three lexicographically lowest SHA-256 digests of `instance_id`
- Task-set digest: `1c8c06935484fd57f4c27c363418884542bcfb06c69d02f480b61fe7687b58eb`
- Repetitions: one engineering run per condition
- Conditions: `baseline` and `marginal`

The smoke is an integration check, not publication-grade performance evidence. The
20-task canary and larger repeated experiment remain gated on complete smoke telemetry.

## Commands

Run the non-verifier integration gate (this does not launch Codex inference):

```bash
.venv/bin/python -m benchmark.scripts.preflight --skip-verifier
```

Run the mandatory full gate before any benchmark trajectory:

```bash
.venv/bin/python -m benchmark.scripts.preflight
```

The full gate currently stops before inference for two scientific blockers:

- Codex 0.147 does not expose shell exit status in `PostToolUse`, so the preregistered
  successful shell-repeat mechanism cannot distinguish passing from failing commands; and
- Codex is not yet running inside a pinned official per-instance SWE-bench environment.

An official verifier backend is also required after those blockers are resolved. The task
materializer and single-run adapter remain available for test-only integration work, but
must not be used for benchmark inference on a bare host checkout.

The future matched layout uses distinct worktrees for each lane:

```bash
.venv/bin/python -m benchmark.scripts.prepare_swebench_tasks \
  --destination benchmark/runs/worktrees/baseline
.venv/bin/python -m benchmark.scripts.prepare_swebench_tasks \
  --destination benchmark/runs/worktrees/marginal
.venv/bin/python -m benchmark.scripts.run_codex_task \
  --instance-id pvlib__pvlib-python-1072 \
  --condition baseline \
  --worktree benchmark/runs/worktrees/baseline/pvlib__pvlib-python-1072 \
  --run-dir benchmark/runs/pvlib__pvlib-python-1072/baseline
```

Run the MARGINAL condition against its separate checkout under
`benchmark/runs/worktrees/marginal/`, then repeat for the other frozen instance IDs. The
runner rejects a dirty tree, an attached branch, or a commit other than the frozen base.
Do not begin the 20-task canary until all six smoke trajectories have complete raw
telemetry and independent verifier results.

The frozen design and implementation plan are under `docs/superpowers/`. The full
preflight remains the authority: do not launch a trajectory unless it passes.

## Safety

- Do not place API keys, Codex authentication files, prompts containing secrets, source
  content, or raw tool output in tracked results.
- The runner isolates `HOME`, gives tool subprocesses an allowlisted environment, keeps
  `CODEX_HOME` out of that environment, and fails closed if exact authentication material
  appears in any changed file or extracted patch.
- Local runtime data belongs under `benchmark/runs/` and is ignored.
- Do not commit or push benchmark work unless explicitly authorized.
