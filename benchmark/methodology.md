# Frozen Methodology

Status: preregistered before any Codex OFF/ON benchmark execution.

Feasibility amendment (2026-08-11, before inference): the pinned Codex 0.147 hook payload
does not expose shell exit status. Shell and verification actions therefore cannot be
counted as successful without guessing and are conservatively failure-settled. Because
those actions are the intended repeat-control surface, comparative execution remains
blocked pending a success-observable interception boundary. The official per-instance
SWE-bench execution environment is also mandatory, not only the final verifier.

## Hypotheses

Primary: enabling the frozen MARGINAL integration does not reduce independently verified
task correctness and may change paired resolution outcomes.

Secondary: when correctness is preserved, MARGINAL may reduce effective tokens, actions,
wall time, and repeated same-state work after including governance overhead.

A negative, mixed, pass-through, or underpowered result is valid.

## Conditions

| Dimension | Baseline | MARGINAL |
|---|---|---|
| Codex CLI | `0.147.0` | `0.147.0` |
| Model | `gpt-5.6-sol` | `gpt-5.6-sol` |
| Reasoning effort | `high` | `high` |
| Task checkout | task `base_commit` | same task `base_commit` |
| Prompt template | frozen SHA-256 | identical |
| Sandbox | `workspace-write` | `workspace-write` |
| Timeout | 1,800 seconds | 1,800 seconds |
| Hosted tools | disabled | disabled |
| JSONL observer | enabled | enabled |
| MARGINAL | absent | hook adapter + daemon |

The ON policy is `balanced` plus `DiminishingReturnDetector()` defaults, unlimited hard
budgets, and `enforce` mode. Tool cost is zero at authorization because no defensible
future-token forecast is available at the hook boundary. The measured experiment therefore
tests repetition control rather than a calibrated economic-ROI claim.

## Isolation

Each task, condition, and repetition starts in a separately materialized checkout at the
task's base commit. Runtime directories, Codex session state, MARGINAL ledger, generated
patches, and test caches are unique. No lane may read another lane's trajectory, patch,
notes, or result.

Codex tool execution must occur in the official pinned per-instance SWE-bench environment.
A bare host checkout is insufficient because missing or divergent dependencies can change
the debugging trajectory and MARGINAL interventions.

Task order is frozen. Where concurrency is used, condition is alternated within task and
the scheduling record is retained. An ON checkout is never created from an OFF checkout.

## Smoke task selection

Dataset: `princeton-nlp/SWE-bench_Lite`, split `dev`, frozen 2026-08-07.

The smoke set is the three lexicographically lowest SHA-256 digests of `instance_id`:

1. `pvlib__pvlib-python-1072`
2. `pvlib__pvlib-python-1707`
3. `pylint-dev__astroid-1978`

Selection occurred before any OFF/ON outcome. Smoke results validate the pipeline and are
not headline performance evidence.

## Primary outcome

The official SWE-bench verifier supplies `resolved`. A task pair is classified as:

- `BOTH_SOLVE`
- `BASELINE_ONLY`
- `MARGINAL_ONLY`
- `NEITHER`

Resolution counts and rate appear before all efficiency metrics. Empty patches, timeouts,
Codex failures, premature stops, integration failures, and evaluation errors remain
unresolved unless the official verifier reports resolution.

## Secondary metrics

Measured when available:

- input, cached input, output, reasoning, and total tokens;
- agent tokens and effective tokens including governance;
- wall-clock and tool latency;
- direct and governance USD when actually observable;
- tool calls, shell commands, file operations, searches, and test executions;
- repeated equivalent actions;
- files modified and diff line counts;
- MARGINAL decisions, deny recommendations, applied denies, and decision index;
- hook/adapter failures and model reroutes.

Unavailable fields are `null`, never estimated as zero unless zero is directly known.
For Codex CLI telemetry, `total tokens` is `input_tokens + output_tokens`; cached input is
reported as a subset of input and reasoning output as a subset of output, so neither is added
again. This accounting rule is frozen before execution.

## Frozen repeat definition

A proposed action is an unproductive-repeat candidate when all conditions hold:

1. its canonical tool name and normalized input produce the same semantic key;
2. the previous equivalent action completed successfully;
3. the observable workspace state hash is unchanged;
4. no new evidence hash exists;
5. executing it produces no verifier-relevant progress.

Conditions 1-4 are machine-detected. Condition 5 is retained for retrospective review and
is not used to change detector thresholds.

Under Codex 0.147, a shell `PostToolUse` response lacks the exit status needed for condition
2. Shell and verification calls are therefore failure-settled and excluded from successful
repeat history; this limitation is a full-preflight blocker, not a benchmark result.

## Intervention review

Every applied or would-apply deny is reviewed after execution using frozen labels:

- `BENEFICIAL`: explicit evidence shows the skipped action was redundant and the required
  outcome was preserved or reached without replacement cost exceeding the saving;
- `NEUTRAL`: no material trajectory, correctness, or effective-cost change is supported;
- `HARMFUL`: explicit evidence shows the action would have contributed to correctness or
  the denial caused greater replacement cost;
- `INDETERMINATE`: counterfactual evidence is insufficient.

Task success alone cannot label an intervention beneficial. Task failure alone cannot
label it harmful. Reviewers should not see aggregate condition results while labeling.

## Analysis

The three-task smoke and 20-task canary are exploratory. They do not support statistical
significance or a one-percentage-point non-inferiority claim.

For the later repeated experiment, report task-clustered paired bootstrap intervals for
resolution delta and continuous metrics. Report an exact paired binary analysis for the
predeclared task-level correctness summary. Continuous metrics include mean, median, p25,
p75, minimum, and maximum. Efficiency is shown overall and separately for `BOTH_SOLVE`.

## Stop rules

Stop before larger runs if any smoke task has missing token telemetry, an orphaned
reservation, a hook failure, unmatched configuration, cross-lane contamination, a missing
prediction row, or a verifier pipeline failure. Do not remove the failing task.

After the smoke, project the 20-task canary cost from measured effective tokens and elapsed
time. No larger run begins without a complete smoke report.
