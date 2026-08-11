# Codex + MARGINAL Paired Benchmark Design

## Status and amendment record

This design is frozen before comparative inference. It supersedes the host-checkout
feasibility design written earlier on 2026-08-11. The feasibility review found two
scientific blockers: Codex 0.147 does not expose a shell exit code in `PostToolUse`, and a
host checkout does not reproduce the official SWE-bench task environment.

The approved amendment is:

1. run the whole Codex process inside the official per-instance SWE-bench image;
2. define an executed action as a tool invocation with an authoritative `PostToolUse`;
3. reserve `settle_failure` for an invocation that did not complete and therefore has no
   valid post event;
4. verify patches with the official SWE-bench harness on Modal;
5. publish no efficiency or correctness claim until both lanes pass integrity checks and
   the official verifier result has been merged.

This amendment is methodological, not outcome-driven: both public result files are empty
at freeze time.

## Objective

Measure whether the released MARGINAL diminishing-return policy changes Codex behavior,
token use, latency, and task resolution under a matched OFF/ON intervention. Correctness
is primary. Token savings count only when paired correctness is preserved. Integration
latency and policy overhead count against MARGINAL.

The implementation is pinned to MARGINAL commit
`4c8856401b4c752d5c214df5e84b9632d9897ec9`, Codex CLI `0.147.0`, model
`gpt-5.6-sol`, reasoning effort `high`, the frozen prompt hash, and a manifest of exact
SWE-bench instance IDs and base commits.

## Considered architectures

### A. Full container execution — selected

Codex, its shell tools, the MARGINAL daemon, and hooks run inside the official task image.
The task checkout is mounted at `/testbed`. A separate tool layer provides pinned Codex
and an isolated MARGINAL Python environment without changing the task dependency
environment. This gives the strongest execution parity and makes every local tool action
observable at the same boundary.

### B. Host Codex with a container shell bridge — rejected

Codex 0.147 resolves the default user shell from the passwd database; setting `$SHELL`
does not reliably redirect every command. A prompt instruction would not be an enforceable
experimental boundary.

### C. Cloud generation and verification — deferred

Running inference and verification entirely in GitHub Actions or Modal is reproducible but
adds credential provisioning and cloud-executor differences that are unnecessary to test
the intervention. Modal remains the authoritative verifier.

## Matched experimental boundary

Both lanes use:

- the same official task image digest and `/testbed` base commit;
- the same overlay image digest, Codex binary, model, effort, prompt, timeout, sandbox,
  network policy, environment allowlist, and host architecture;
- an independent fresh container, checkout, Codex home, and run directory;
- the same external JSONL collector and patch extraction logic.

The OFF lane has no MARGINAL process, hook, prompt text, configuration, state, or context.
The ON lane adds only the MARGINAL daemon and official `PreToolUse`/`PostToolUse` hooks.
Their CPU time, wall time, denials, errors, and token consequences are intervention cost.

Hosted tools that bypass the official hook surface are disabled symmetrically. The causal
estimand is therefore **MARGINAL control over hook-covered local Codex tool actions in an
official SWE-bench environment**, not governance of model inference or every hosted tool.

## Runtime architecture

```text
host orchestrator
  |-- materialize exact SWE-bench instance and official image digest
  |-- create clean OFF or ON worktree and isolated run directory
  `-- start one disposable task container with model API egress
        |-- codex exec --ephemeral --json in /testbed
        |     |-- local tools execute inside the task container
        |     `-- ON only: PreToolUse/PostToolUse hooks
        |                    `-- Unix socket --> MARGINAL daemon/Treasury
        `-- bind-mounted raw events, trace, metrics, and final patch

strict run records + predictions
  --> evidence protocol validation
  --> GitHub Actions SWE-bench workflow
  --> official Modal verification
  --> paired merge and public benchmark artifacts
```

The task container retains network access for the Codex parent process to reach the model
API. Codex `workspace-write` sandbox policy disables network for model-generated tool
subprocesses. Tool subprocesses receive only an allowlisted environment and never receive
model credentials.

Authentication preference is an ephemeral `OPENAI_API_KEY` injected only into the Codex
parent. If the pinned model cannot use API-key authentication, the run stops; it must not
fall back to copying a broadly readable user home or credential file into the task image.
No credential is serialized into a command, image layer, trace, patch, or public artifact.

## Action normalization

Each `PreToolUse` payload becomes one MARGINAL `Action`:

- `name`: canonical tool name plus a compact normalized operation label;
- `kind`: `shell`, `edit`, `mcp`, `verification`, or `tool`;
- `fingerprint`: the unique Codex tool invocation ID, settling a reservation once;
- `metadata.marginal_semantic_key`: SHA-256 of canonical tool name and normalized input;
- `metadata.state_hash`: observable workspace state immediately before execution;
- `metadata.evidence_hash`: last completed evidence for that semantic action;
- `metadata.phase`: stable `codex-tool-use` phase;
- `expected_gain`: omitted, selecting the shipped estimator default;
- `cost`: zero pre-execution tool cost because Codex hooks expose no defensible forecast of
  future model tokens.

The zero forecast cost means this experiment tests exact, state-aware repetition control,
not a synthetic economic ROI estimate. Actual tokens, latency, actions, and verifier result
are measured externally.

The workspace hash covers tracked content, staged and unstaged changes, and untracked task
files while excluding `.git`, `.codex`, runtime output, caches, and virtual environments.
It stores hashes, never task source.

## Completion, failure, and evidence semantics

Codex 0.147 emits `PostToolUse` only after its tool handler completes but its unified shell
post payload does not expose the command exit status. A completed test that exits nonzero
is still a real evidence-producing action: it may reveal the defect and change the next
decision. Treating every red test as a transport failure would make repeated verification
invisible and eliminate the mechanism being measured.

Therefore:

- a well-formed matching `PostToolUse` commits the action and records the post state and
  evidence hash, regardless of the command's application-level exit code;
- missing, malformed, duplicate, or identity-mismatched post events are integration
  failures, not successful actions;
- a denied pre action is settled as denied and never enters successful repetition history;
- runner termination with pending actions fails the ON run;
- complete hook coverage is exact: committed + denied + explicitly failed decisions must
  equal every hook-coverable Codex tool call, with one pre/post identity chain per executed
  action.

The frozen unproductive-repeat definition is: the same normalized invocation is proposed
after a completed execution, against unchanged observable workspace state, without new
evidence. The default detector discounts the second proposal and recommends stopping from
the third same-state proposal onward.

## Integrity, privacy, and fail-closed gates

Every public run must satisfy all of the following:

- exact instance ID, base commit, task-set hash, prompt hash, Codex version, model, effort,
  timeout, sandbox, image digest, overlay digest, source commit, and configuration hash;
- detached clean initial worktree and no run directory inside `/testbed`;
- strict Codex JSONL lifecycle and token accounting;
- exact ON hook coverage and no OFF MARGINAL footprint;
- no pending reservations or daemon errors at shutdown;
- a final patch extracted only from the task worktree;
- fail-closed secret scanning of raw public fields, patches, predictions, and generated
  reports before acceptance;
- no prompt, task source, raw tool output, credential, private ledger key, or user-home
  material in public artifacts.

Any mismatch produces an explicit infrastructure or integration failure. It is never
silently converted into an unresolved benchmark row.

## Benchmark stages and promotion gates

1. Unit and protocol suite with deterministic fake event streams.
2. Container integration fixture proving API auth, shell execution, hook coverage, denial,
   patch extraction, and secret scanning.
3. Frozen three-task paired smoke: six independent inference runs.
4. Official Modal verification and paired merge of the smoke.
5. Frozen twenty-task engineering canary: forty independent runs, only if the smoke has
   complete telemetry and the verifier pipeline is green.
6. Official Modal verification and paired merge of the canary.
7. README/site publication only from committed machine-readable verifier artifacts.

An integrity failure is fixed and the affected stage rerun from clean state. Policy
thresholds, task membership, prompt, timeout, and analysis rules are not tuned after lane
outcomes are observed.

## Outcomes and analysis

The official verifier alone owns `resolved`. Paired outcomes are `BOTH_SOLVE`,
`BASELINE_ONLY`, `MARGINAL_ONLY`, and `NEITHER`. Primary reporting always includes:

- resolved count/rate by lane and paired outcome counts;
- total/input/cached/output/reasoning tokens by lane and paired differences;
- wall time and governance overhead;
- tool calls, denials, reroutes, repeated proposals, and hook coverage;
- infrastructure/integration failures as a separate denominator;
- per-task rows sufficient to recompute every aggregate.

Token savings are reported as correctness-preserving only for `BOTH_SOLVE` pairs or as a
clearly labeled all-pairs engineering metric. If ON regresses correctness, the headline
must show the regression before any token reduction. Confidence intervals and statistical
tests are included when the sample supports them; a smoke or twenty-task canary remains
exploratory and is never described as publication-grade proof.

Intervention labels are `BENEFICIAL`, `NEUTRAL`, `HARMFUL`, or `INDETERMINATE`. Without
explicit counterfactual or reviewer evidence, a trajectory-level outcome does not assign
causal value to an individual denial.

## Publication contract

The root README and website may show benchmark data at the top only after the official
artifact has been validated against its schema and provenance. The headline links to the
machine-readable artifact, exact workflow run, methodology, task manifest, source commit,
and limitations. If the result is negative or neutral, it is published unchanged. If only
the smoke completes, it is labeled an integration smoke and not promoted as a performance
claim.

## Non-goals

- Tuning MARGINAL policy or estimator on benchmark outcomes.
- Claiming causal value for individual actions from final task success.
- Treating synthetic demonstrations, the smoke, or the canary as broad model evidence.
- Hiding regressions, failed runs, intervention overhead, or negative results.
- Generalizing beyond the pinned model, version, tasks, policy, and official environment.
