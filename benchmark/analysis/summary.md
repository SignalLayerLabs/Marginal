# Codex OFF versus Codex + MARGINAL: Smoke Report

## Executive Summary

No Codex OFF/ON trajectory was executed. The integration-only preflight passes for the
frozen three-task set, Codex 0.147.0, `gpt-5.6-sol`, and `high` reasoning effort. The
mandatory full preflight stops before inference because successful shell executions are
not observable through the pinned hook contract and no official per-instance SWE-bench
execution backend is implemented. An official verifier is also unavailable on this host.

Running anyway would spend tokens on an experiment that cannot faithfully test the frozen
mechanism or produce admissible correctness. There are therefore no performance claims.

## What MARGINAL Actually Does

MARGINAL is a provider-neutral action-governance library built around a `Treasury`, policy,
budgets, decision ledger, and optional state-aware diminishing-return detector. It does not
natively modify Codex prompts or model calls. The benchmark adapter maps official Codex
tool hooks to MARGINAL actions and can deny a proposed action in enforce mode. The baseline
has no MARGINAL process, hook, state, or context.

## Methodology

The preregistered smoke uses three deterministically selected SWE-bench Lite `dev` tasks,
one run per condition, separate exact-base-commit checkouts, identical frozen prompt/model/
reasoning/sandbox/timeout settings, raw JSONL telemetry, and the official SWE-bench
resolution criterion. Correctness is primary. The smoke is an integration check and does
not support population-level performance inference.

## Correctness Results

| Metric | Codex baseline | Codex + MARGINAL | Delta |
|---|---:|---:|---:|
| Executed tasks | 0 | 0 | 0 |
| Resolved tasks | unavailable | unavailable | unavailable |
| Resolution rate | unavailable | unavailable | unavailable |

## Paired Results

- `BOTH_SOLVE`: unavailable
- `BASELINE_ONLY`: unavailable
- `MARGINAL_ONLY`: unavailable
- `NEITHER`: unavailable

## Efficiency

Tokens, time, actions, tool calls, repeated behavior, files modified, and diff size are all
unavailable because no comparative trajectory was launched.

## Intervention Analysis

No benchmark intervention occurred. Beneficial, neutral, harmful, indeterminate, and
false-positive rates are unavailable.

## Regressions

No regression was observed because no paired outcome exists. This is not evidence of no
regressions.

## Failure Analysis

The blocking observations and their interpretation are recorded in `failure_analysis.md`.
They are infrastructure and measurement failures, not model/task outcomes.

## Limitations

- Codex 0.147 unified-shell `PostToolUse` omits exit status, preventing defensible
  successful-repeat history for the main search/test/debugging surface.
- Codex is not provisioned inside an official pinned per-instance SWE-bench environment.
- No official verifier backend is available locally.
- The frozen set contains only three tasks and one repetition even after feasibility is
  restored; any future smoke result will remain exploratory.
- Agent and environment nondeterminism require larger repeated paired runs for credible
  generalization.

## Conclusion

The evidence is insufficient to answer whether MARGINAL improves task completion, reduces
unproductive behavior or cost, intervenes incorrectly, helps or hurts particular task
classes, or generalizes beyond stress tests. The current evidence is not strong enough to
justify enabling MARGINAL with Codex on the basis of this benchmark.
