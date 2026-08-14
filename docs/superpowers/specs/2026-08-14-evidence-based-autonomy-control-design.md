# Evidence-Based Autonomy Control Design

**Status:** Approved execution direction
**Date:** 2026-08-14
**Scope:** Local implementation only; no commit, push, release, package publication, or marketplace submission

## 1. Product contract

MARGINAL is an evidence-based governor for AI agents. It observes trajectories, measures verified
progress relative to compute, records auditable decisions, evaluates its own interventions, and
earns only the authority supported by local evidence.

The governing sequence is:

```text
Observe → Measure → Prove → Earn Authority → Revalidate → Revoke on degradation
```

Correctness dominates savings. Unknown evidence fails toward observation. The Codex integration
can claim Tool Enforcement only; hosted and specialized tool paths remain outside its complete
control surface.

## 2. Verified baseline

Before this design, the isolated plugin worktree passed:

- 449 pytest tests;
- Ruff format and lint;
- strict mypy over 43 source files;
- deterministic Codex plugin runtime verification;
- Codex doctor for CLI 0.147.0 with hooks and plugins available.

The frozen three-task SWE-bench smoke remains an integration observation: both lanes resolved 0/3,
ON used 24.93% fewer measured tokens, no denial occurred, and the intervention status is
`pass_through`. It is not efficacy evidence.

## 3. Existing architecture to preserve

The implementation extends, rather than duplicates:

- `protocol.py` for provider-neutral agent lifecycle values;
- `models.py`, `policy.py`, and `treasury.py` for actions, cost, decisions, and allocation;
- `controls/` for repetition, progress, and governance overhead;
- `ledger.py` for the existing v2 decision ledger and privacy exports;
- `replay.py` and `public_eval.py` for explicitly non-causal replay and paired evaluation;
- `integrations/codex/` for the production Codex anti-corruption layer;
- `benchmark/` and `benchmarks/swebench_lite/` for frozen experiment orchestration and evidence.

Compatibility requirements:

- Python 3.10–3.13;
- no mandatory third-party runtime dependency;
- v0.1/v0.2 constructors and v2 ledger readers remain supported;
- raw prompts, source, commands, outputs, transcripts, auth, and credentials are never persisted;
- hook/runtime failures allow the agent action but revoke governance authority;
- evidence or provenance corruption fails closed for promotion and claims.

## 4. Target module boundaries

New provider-neutral modules:

- `canonical.py`: one deterministic JSON serializer and SHA-256 primitive;
- `reason_codes.py`: small, versioned reason-code registry;
- `authority.py`: L0–L4 semantics, transitions, and hysteresis policy;
- `trust.py`: contextual evidence, confidence components, eligibility, decay, and shift handling;
- `receipts.py`: immutable Decision Receipts and transition receipts;
- `governance_ledger.py`: append-only hash-chained v3 ledger and verification reports;
- `utility.py`: progress evidence, structured correctness-first utility, and EMU estimates;
- `counterfactual.py`: live/replay branch contracts, intervention evaluation, and regret;
- `policy_evaluation.py`: offline candidate comparison, promotion receipts, active state, rollback;
- `diagnostics.py`: shared status, doctor, explain, verify, and privacy inspection models.

Codex-specific additions stay under `integrations/codex/`:

- `intent.py`: ephemeral normalization of user control and repeat intent;
- `autopilot.py`: first-session quick eligibility, deferred opt-in, recovery, and revocation;
- existing event, service, evidence, promotion, and command modules adapt to core authority/receipt
  contracts without reimplementing them.

## 5. Universal event and receipt model

Existing `AgentEvent` remains valid. New stable entities complement it:

- `EvidenceSignal` identifies a derived evidence kind and hash;
- `ProgressEvidence` distinguishes activity, information, progress, and verified progress;
- `VerificationSignal` records an observable verifier result or explicit unavailable state;
- `GovernanceCost` records wall-clock, CPU, memory peak, storage delta, tokens, model calls, and
  added tool calls where measurable;
- `TrustContext` keys evidence by repository, agent, model, task class, and policy version, using
  explicit `unknown` values where unavailable;
- `TrustSnapshot` exposes components, sample sizes, confidence band, eligible/current authority,
  and blockers;
- `DecisionReceipt` binds decision, hashes, trust, cost, and enforcement level;
- `CounterfactualOutcome` and `InterventionEvaluation` bind governed and comparison outcomes.

Every hash uses canonical UTF-8 JSON with sorted keys, compact separators, no NaN, and explicit
schema versions. Arbitrary `repr` output is never attestation material.

## 6. Hash-chained governance ledger

The existing v2 ledger remains readable. A new v3 governance ledger stores receipts, outcomes,
authority transitions, policy transitions, counterfactual references, and governance cost.

Each line contains:

```text
schema_version
sequence
timestamp
previous_hash
payload
record_hash = SHA256(canonical(envelope without record_hash))
```

The verifier checks contiguous sequences, previous-hash linkage, record hashes, receipt hashes,
schema compatibility, context/provenance identity, and optional expected root. Invalid ledgers are
never silently truncated. A quarantine command copies invalid records plus a report into an
owner-only quarantine directory and preserves the source.

Promotion receipts bind to the verified evidence window root, first/last sequence, record count,
identity, trust snapshot, criteria, and allowed enforcement scope. Editing evidence invalidates the
receipt.

## 7. Progressive authority and contextual trust

Authority levels:

- L0 `OBSERVE`: record counterfactual decisions only;
- L1 `ADVISE`: surface structured advice without changing execution;
- L2 `SOFT_INTERVENE`: request reconsideration; agent retains control;
- L3 `TOOL_GATE`: deny explicitly eligible local tool classes;
- L4 `COMPUTE_GOVERN`: allocate/deny candidate compute through an adapter that proves the needed
  capabilities. Codex is not eligible for L4.

Trust is a scorecard, not an opaque scalar. It records observed/evaluable decisions, coverage,
verified outcomes, beneficial/harmful/neutral/indeterminate interventions, false stops, regret,
governance tax, calibration error, recency, and shift indicators.

Promotion and demotion use different thresholds. Promotion requires minimum samples, coverage,
bounded harm/regret/tax, integrity, and capability. Demotion occurs at lower evidence quality,
identity changes, integrity failure, harmful recovery, or prolonged inactivity. Critical integrity
or capability drift returns directly to L0; non-critical decay steps down one level.

## 8. Progress and verified utility per compute

`ProgressEvidence` never equates activity with progress. It reports separately:

- activity completed;
- new information acquired;
- task state advanced;
- verified requirement satisfied.

`UtilityVector` is ordered lexicographically:

1. verified correctness;
2. task completion;
3. safety/risk;
4. latency;
5. tokens and monetary cost;
6. governance overhead.

Unknown correctness cannot be traded for lower compute. `MarginalUtilityEstimate` carries expected
incremental verified utility, cost, uncertainty, confidence, and provenance. A scalar ratio is
reported only when its inputs are commensurable; otherwise a structured scorecard is returned.

Treasury keeps its current API and gains an auditable candidate-ranking path that consumes these
estimates. Existing scalar policy behavior remains backward compatible.

## 9. Counterfactual evaluation and regret

Two explicitly labelled modes are supported:

- `LIVE_PAIRED`: a provider supplies two independently continued branches from an attested common
  start. The core validates comparability but does not pretend Codex hooks can clone a session.
- `REPLAY_APPROXIMATION`: recorded proposals are re-evaluated. It is non-causal and cannot simulate
  missing state changes.

`InterventionEvaluation` compares governed and counterfactual utility correctness-first and emits
`BENEFICIAL`, `NEUTRAL`, `HARMFUL`, or `INDETERMINATE`. Regret preserves a structured delta and only
provides a scalar when justified. Aggregate reports include reviewed count, category rates,
mean/median scalar regret when available, and high-regret incidents.

## 10. Offline policy lifecycle

Production observations never mutate an enforced policy directly. Calibration produces an
immutable candidate artifact with source-ledger root, training fingerprint, configuration hash,
and evaluation results.

The lifecycle is:

```text
evidence → candidate → replay → benchmark/counterfactual gates → explicit or pre-authorized
promotion → active policy → rollback
```

Policy promotion writes a hash-chained receipt. Rollback restores the previous validated policy.
Newer versions receive no automatic authority.

## 11. Codex Autopilot and user intent

Codex remains the reference adapter and uses official lifecycle hooks only.

The plugin adds `UserPromptSubmit`. User text is normalized in memory using Unicode NFKC,
case-folding, whitespace collapse, and a bounded Italian/English control vocabulary. Only ephemeral
turn flags are retained:

- `repeat_requested`;
- `force_run`;
- `pause_marginal`;
- `resume_marginal`;
- `status_requested`.

Neither prompt nor prompt hash is persisted. Ambiguity fails open.

Autopilot lifecycle:

1. user grants hook trust and one-time deferred promotion consent;
2. repository starts at L0 and observes a short clean window;
3. the quick profile may reach L3 only for exact successful no-progress repetitions, with 100%
   observed coverage inside that eligible family, observable outcomes, bounded latency, no
   failures, and an integrity-valid receipt;
4. the third equivalent action may be denied only when input, state, completion evidence, and user
   intent all support it;
5. polling, waiting, monitoring, unknown/failure outcomes, changed state/evidence, verification
   requested by the user, and uncovered tools always pass;
6. an immediate identical retry after denial is allowed once as recovery and demotes authority;
7. integration failure, false stop, recovery, integrity drift, identity drift, or coverage loss
   demotes and fails open.

MARGINAL control-plane commands are recognized in memory from the trusted installed script path
and bypass workload governance so promotion cannot block itself. They are not candidates or
pending workload actions.

Normal users do not run review/promote commands. Advanced manual Earned Enforcement remains
available. Status reports actual avoided actions and recoveries, never invented token savings.

## 12. Diagnostics and CLI

The coherent CLI surface is:

```text
marginal status
marginal doctor
marginal explain <decision-id>
marginal verify <ledger>
marginal replay <ledger> [--profile ...] [--compare-profile ...]
marginal policy evaluate|compare|promote|rollback
marginal privacy inspect
```

Existing commands remain aliases/compatible. Human and JSON output share typed report objects.
Doctor checks runtime, plugin artifact/provenance, hooks, permissions, schemas, ledger integrity,
policy identity, authority/trust, and benchmark readiness.

## 13. Benchmark and provenance

The frozen smoke is immutable. New validation verifies the full evidence DAG: run records,
provenance, verifier reports, merged verified rows, predictions, metrics, public JSON/Markdown,
patch hashes, configuration hashes, pair identity, and execution-order evidence.

Public evaluation adds token breakdown, paired outcome classes, intervention categories, regret,
candidate counts, and provenance hashes. At 0/3 vs 0/3 it reports insufficient correctness evidence,
not an easily misread quality-preserved boolean.

Governor performance benchmarks measure decision/event p50/p95, CPU, memory peak, storage/ledger
growth, and throughput. Thresholds guard regressions but are not generalized product claims.

## 14. Security, privacy, and configuration

- Repositories are untrusted input; governance never executes repository code by itself.
- Paths reject symlinks and traversal; ledgers are owner-only and durably fsynced.
- Global user policy caps repository policy authority. Repository configuration can reduce, never
  increase, authority.
- Hook commands remain reviewable and never bypass Codex trust.
- Local evidence uses derived enums, counts, and hashes with documented dictionary-attack limits;
  secret-bearing raw values are excluded.
- Release workflows require an explicit dispatch/tag and approval; no push to `main` creates a
  release automatically.

## 15. Testing and completion evidence

Behavior-critical work follows red-green-refactor. Required suites cover canonicalization,
schemas, chain corruption/missing records/migration, authority transitions/hysteresis/decay,
context shifts, structured utility, counterfactual/regret, offline policy promotion/rollback,
productive repetition, user-intent bypass, Autopilot recovery, control-plane bypass, partial event
streams, concurrency, privacy, provenance, and performance.

Final local gates are pytest, Ruff, strict mypy, plugin runtime reproducibility, build, Twine check,
CLI smoke, governor benchmark, and dirty-worktree review. External inference, marketplace review,
push, tag, release, and publication remain explicit blockers rather than simulated completion.
