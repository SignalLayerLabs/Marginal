# Astra × MARGINAL — full HumanEval+ protocol

**Withdrawn before scored inference.** The user requires SWE-bench Pro. No model samples
were generated for this suite. The reference-only evaluator check passed 163/164 tasks;
its remaining failure was not investigated after the scope correction. This directory is
retained for traceability, not as a performance result or an active preregistration.

This is a **function-level** OFF/ON experiment, not SWE-bench Pro. No result is claimed
until all 164 tasks have both a real model run and official grading.

## What is being tested

The same Codex 0.153.4 agent and GPT-6 Astra (`low` reasoning) implement every HumanEval+
v0.1.10 function twice, in separate clean workspaces. Baseline has no MARGINAL benchmark
adapter; ON uses the existing balanced/diminishing-return experimental enforcement adapter.
The installed plugin's default Shadow Mode is **not** this intervention.

Each task starts with only its public function prompt in `solution.py`. Reference solutions
and official base/extra test inputs are not provided to the solver. The solver may perform
local checks, but may not use the network or files outside its workspace. Execution traces
must be audited for violations before any results are admitted. No extra repetition is
requested to make MARGINAL look effective.

## Frozen conditions

The machine-readable [protocol](protocol.json) records task/data hashes, order, model,
reasoning, timeout, concurrency, analysis and stop rules. Runner source revision, evaluator
image digest and exact prompt hash are recorded and published before scored inference.
All original tasks and all extra tests are included; neither `mini` nor `noextreme` is used.

Correctness is primary: official base **and** extra tests must pass. Failed, timed-out,
missing-usage and infrastructure-invalid lanes remain visible. They are never silently
replaced with another attempt. The complete experiment requires 328 recorded lanes.

Token accounting uses provider-reported totals and includes all calls, including recovery
work. Cached input is part of input, and reasoning output is part of output. They are not
added twice. Subscription quota is not a dollar bill. Unavailable costs stay unavailable.

## Reading the eventual result

Report paired correctness, token use, tool calls, elapsed time, intervention counts and
governance overhead together. Report overall results and the both-solve subset separately.
A zero-regression sample is an observation, not a statistical proof of equivalence. One
sample per task cannot establish production reliability; a public function benchmark may
also be saturated or present in model training data.

Negative, zero-effect and inconclusive results are valid. This experiment cannot justify
claiming that installing the default plugin reduces Astra's internal reasoning tokens.

Sources: [EvalPlus v0.3.1](https://github.com/evalplus/evalplus/tree/e5d0ed0bab96280b60b637ec7f15b5e4841b0cb2),
[HumanEval+ v0.1.10](https://github.com/evalplus/humanevalplus_release/releases/tag/v0.1.10).
