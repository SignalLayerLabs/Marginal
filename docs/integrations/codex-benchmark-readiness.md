# Codex Benchmark Readiness

This document records the v0.3 Codex benchmark contract and the remaining evidence gates. The
native adapter and one-command plugin path are implemented; the larger repeated canary remains a
future scientific gate.

## Target user experience

The release provides both the native Codex marketplace path and a Python CLI transaction:

```bash
codex plugin marketplace add SignalLayerLabs/Marginal --ref main && codex plugin add marginal@marginal
marginal install codex
```

The benchmark command and native plugin are part of v0.3.0.

## Adapter responsibilities

The Codex adapter should translate native Codex events into the existing Universal Agent Protocol rather than reimplement economic policy. It needs to provide, where the official integration surface permits:

- stable session and task correlation;
- normalized tool/model/retry/verification actions;
- workspace state hashes;
- evidence hashes when a deterministic evidence boundary exists;
- measured input, cached input, output, reasoning and total tokens;
- actual USD when available or a clearly labeled derived estimate;
- action latency and tool-call counts;
- repeated-call classification under a documented definition;
- outcome/verifier correlation;
- explicit capability negotiation for observe versus block/stop behavior.

## Safe rollout

The recommended sequence is:

1. install in Shadow Mode;
2. validate event completeness and token accounting;
3. run the 10-task canary as integration validation;
4. inspect deny recommendations and manually review false-stop candidates;
5. freeze the adapter/policy configuration;
6. preregister the public benchmark protocol;
7. run matched OFF/ON evaluation;
8. consider enforcement only if the evidence gate is satisfied.

## One-command installer requirements

`marginal install codex` now:

- detect a supported Codex installation/version;
- explain the detected capability level;
- uses native plugin transactions instead of editing user configuration;
- install the thin adapter without source-code edits to user projects;
- default to Shadow Mode;
- exposes repository-scoped status and diagnostics;
- uninstall cleanly and restore prior configuration;
- fail without leaving Codex unusable.

The exact mechanism must follow the official Codex integration surface available at implementation time. Do not rely on undocumented hooks solely to satisfy the one-command goal.

## Canary exit criteria

The 10-task canary passes only when:

- every task has a matched baseline and MARGINAL run;
- token telemetry is measured rather than declared;
- action/session/state correlation is complete enough to explain repeated-work decisions;
- governance overhead is captured separately;
- no adapter crash or orphaned reservation occurs;
- raw paired JSONL can reproduce the report;
- negative or pass-through results are preserved rather than filtered out.

Passing the canary means the measurement system is ready for larger evaluation. It does not mean MARGINAL has demonstrated a savings claim.

## Public benchmark gate

The public protocol should define before execution:

- benchmark/version and any exclusions;
- model and agent version;
- run limits and environment;
- number of matched tasks and repeat count;
- quality non-inferiority margin;
- maximum false-stop rate;
- minimum net token-savings threshold;
- verifier and failure handling;
- statistical reporting method.

SWE-bench Pro can be included because the community explicitly requested it. A targeted MARGINAL repetition suite should run alongside it so the claimed mechanism can be inspected directly.
