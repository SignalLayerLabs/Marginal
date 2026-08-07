# MARGINAL Roadmap

MARGINAL's North Star is:

> **Reduce avoidable compute per verified successful task while accounting for the cost and mistakes of the governor itself.**

The project is one universal, local compute-governance product for AI development agents. A shared core, protocol, policy system, evidence model and reporting layer support engine-specific adapters without duplicating economic logic.

This roadmap is milestone-driven rather than date-driven. GitHub Issues and pull requests should track implementation-level work.

## Product principles

1. **One product:** one core, protocol, evidence model and user experience.
2. **Thin adapters:** engine-specific interception stays outside the decision core.
3. **Quality first:** lower compute is valuable only when verified quality remains inside the preregistered constraint.
4. **Measured claims:** public savings claims require matched real-runtime telemetry.
5. **Learning without overclaiming:** observational associations are not causal proof.
6. **Local first:** prompts and source code are not uploaded or logged by default.
7. **Simple installation:** supported agents should require no manual project-code changes.
8. **Transparent capabilities:** observe-only and enforcement integrations are clearly distinguished.
9. **Small core:** the provider-neutral runtime keeps zero mandatory dependencies.
10. **Self-accounting:** governance tokens, USD and latency are first-class evidence, not hidden overhead.
11. **Graceful irrelevance:** if MARGINAL does not demonstrate positive net value for a workload, pass-through is a valid outcome.
12. **False-stop visibility:** harmful deny recommendations are explicitly reviewed and never inferred away by aggregate success.
13. **Community pressure testing:** criticism can change the roadmap when it creates a stronger falsification test; unsupported speculation does not become product doctrine.

## Status legend

| Status | Meaning |
|---|---|
| **Planned** | Scope is defined; implementation has not started. |
| **In progress** | Implementation is actively underway. |
| **Validation** | Implementation exists; final CI, release, integration or evidence is pending. |
| **Complete** | Exit criteria and supporting evidence are satisfied. |

## Milestones at a glance

| Milestone | Status | Primary outcome |
|---|---|---|
| **v0.1 — Reference Allocator Foundation** | Complete | Provider-neutral allocation, accounting, tracing and first release |
| **v0.2 — Learning Loop Foundation** | Validation | Universal protocol, non-blocking observation, versioned evidence, privacy and replay |
| **Community hardening** | In progress | Governance tax, false-stop accounting, diminishing-return control and clearer evidence UX |
| **v0.3 — Codex Reference Integration** | Planned | One-command target, real telemetry and first matched public benchmark |
| **v0.4 — Multi-Engine Developer Preview** | Planned | Shared core across materially different coding agents |
| **v0.5 — One-Command Universal Installation** | Planned | Detection, installation, diagnostics and rollback across engines |
| **v0.6 — Adaptive and Causal Allocation** | Planned | Calibrated learning, exploration and stronger identification strategies |
| **v0.7 — Ecosystem and Operational Scale** | Planned | Persistence, observability, team controls and more engines |

---

## v0.1 — Reference Allocator Foundation

**Status:** Complete

Delivered provider-neutral `Action`, `Cost`, `Decision` and `Allocation` primitives; hard token/USD/latency/risk budgets; reservations and settlement; hierarchical treasuries; verification reserves; marginal-value policy; duplicate protection; guarded-call adapters; common usage extraction; JSONL traces; synthetic benchmark; Killer Demo; public comparison utility; Python 3.10–3.13 CI and project documentation.

**Exit criteria:** released, CI green, synthetic claims separated from measured claims, zero mandatory runtime dependencies.

---

## v0.2 — Learning Loop Foundation

**Status:** Validation

The v0.2 release candidate adds:

- Universal Agent Protocol v1 and capability negotiation;
- normalized action, decision, outcome, token-usage and ledger schemas;
- additive uncached/cached/output/reasoning token accounting;
- `shadow`, `recommend` and `enforce` modes;
- Decision Ledger v2 with engine/model/task/trajectory identity;
- `LOCAL_FULL`, `SAFE_TELEMETRY` and `AGGREGATE_EXPORT` privacy boundaries;
- state-aware fingerprints and deduplication scopes;
- failed-action settlement and measured overruns;
- quality-first/balanced/token-saver/strict-budget profiles;
- versioned estimators, uncertainty, confidence and provenance;
- task outcomes separated from action-level realized gain;
- non-causal replay and ledger/reporting CLI support.

### Remaining exit criteria

- [ ] Ruff, mypy strict, full tests, package build and Twine validation pass in canonical CI.
- [ ] `v0.2.0` is tagged/released from the canonical repository.

Vendor-specific adapters and measured production savings are intentionally outside v0.2.

---

## Community hardening — Net-value evidence layer

**Status:** In progress

**Objective:** turn early community criticism into falsifiable product requirements without introducing model-specific patches or unsupported narratives.

### Deliverables

- [x] Add opt-in provider-neutral `DiminishingReturnDetector` for semantic same-state repetition.
- [x] Fail open when state is unavailable and reset pressure when state/evidence changes.
- [x] Integrate successful-execution observation without counting denied proposals as executed work.
- [x] Add `GovernanceTracker` for local decision latency and externally supplied governance tokens/USD/latency.
- [x] Add explicit reviewed false-stop accounting; never infer false stops from task outcome alone.
- [x] Extend public evaluation with repeated calls, gross versus net savings and governance overhead.
- [x] Add intervention statuses: `supported`, `pass_through`, `quality_regression`, `false_stop_risk`.
- [x] Define Graceful Irrelevance as a first-class product behavior.
- [x] Rewrite the website around a concrete trace and proof standard before theory.
- [x] Publish a Community Feedback Log with accepted, partial and rejected decisions.
- [x] Reorganize documentation by getting-started/product/integrations/evaluation/reference/operations/project responsibility.
- [ ] Validate the overlay against the canonical full repository and merge through normal CI/review.

### Exit criteria

- Existing v0.2 public benchmark rows remain parseable.
- Existing public-eval keys remain usable; new rows count governance overhead in net metrics.
- State-aware repetition control is opt-in until engine evidence supports enforcement.
- A no-benefit configuration can report `pass_through` without being mislabeled as a successful optimization.
- Website examples contain no fabricated performance numbers.
- Community feedback documentation distinguishes evidence-backed design requirements from speculation.

---

## v0.3 — Codex Reference Integration

**Status:** Planned

**Objective:** integrate MARGINAL into Codex and produce the first real matched benchmark with measured telemetry and net-value accounting.

### Integration deliverables

- [ ] Build a thin Codex adapter against the Universal Agent Protocol.
- [ ] Target `marginal install codex` with safe backup, Shadow Mode default and clean uninstall.
- [ ] Detect Codex version/capability level and refuse unsupported enforcement claims.
- [ ] Capture measured input, cached input, output, reasoning and total tokens.
- [ ] Correlate model/tool/retry/verification actions with session, task and workspace state.
- [ ] Record evidence hashes where deterministic evidence boundaries exist.
- [ ] Capture governance tokens, USD and latency separately from workload usage.
- [ ] Define and record repeated-call metrics consistently in OFF and ON arms.
- [ ] Export raw paired JSONL sufficient to reproduce the public report.

### Canary: engineering validation only

- [ ] Run a 10-task matched canary with identical model, prompt, tools, limits and verifier.
- [ ] Confirm event/session/state correlation and no orphaned reservations.
- [ ] Confirm telemetry is measured rather than declared.
- [ ] Confirm governance overhead is separately accounted.
- [ ] Review deny recommendations for false-stop candidates.
- [ ] Preserve pass-through and negative results instead of filtering them out.

**The 10-task canary is not public performance evidence.** Its purpose is to prove the measurement/integration pipeline is trustworthy enough for a larger run.

### Public benchmark

Before execution, preregister:

- [ ] agent/model/version and environment;
- [ ] benchmark dataset/version and exclusions;
- [ ] matched task count and repeat count;
- [ ] quality non-inferiority margin;
- [ ] maximum acceptable false-stop rate;
- [ ] minimum net token-savings threshold;
- [ ] verifier and failure policy;
- [ ] bootstrap/repeated-run statistical method.

Run at least:

- [ ] the community-requested SWE-bench Pro surface, with version/exclusion/quality notes;
- [ ] a targeted MARGINAL repetition suite that exposes same-state retry/verification behavior.

Report:

- [ ] verified resolve-rate delta;
- [ ] gross agent tokens and net effective tokens;
- [ ] effective tokens per verified successful task;
- [ ] governance tokens/USD/latency;
- [ ] tool calls and repeated calls;
- [ ] regressions and recoveries;
- [ ] reviewed false stops and false-stop rate;
- [ ] uncertainty across matched/repeated runs;
- [ ] final intervention status.

### v0.3 exit criteria

- Codex baseline and Codex + MARGINAL run under matched conditions.
- Telemetry comes from the runtime/provider integration rather than declared demo estimates.
- The canary completes without integration failures.
- Public results are reproducible from raw paired artifacts.
- Headline claims use **net** metrics after governance tax.
- If the preregistered gate is not met, the published conclusion says so.

See [Codex benchmark readiness](docs/integrations/codex-benchmark-readiness.md).

---

## v0.4 — Multi-Engine Developer Preview

**Status:** Planned

Build OpenCode, Claude Code and GitHub Copilot integrations where official control surfaces permit them. Reuse the same protocol, policy, governance accounting, privacy boundaries and reports. Publish a capability matrix and label each engine as Observe, Tool Enforcement or Full Compute Enforcement.

**Exit criteria:** at least four environments pass protocol conformance; economic logic remains centralized; at least two integrations support real enforcement; each engine documents limitations and fail-open behavior.

---

## v0.5 — One-Command Universal Installation

**Status:** Planned

Add `marginal install --detect`, safe backups, supported-agent detection, Shadow Mode defaults, `status`, `doctor`, profile management and clean uninstall/rollback on Windows, macOS and Linux.

**Exit criteria:** non-expert installation requires no project-code edits; failed installation leaves agents usable; uninstall restores prior configuration; users receive one consistent diagnostic experience.

---

## v0.6 — Adaptive and Causal Allocation

**Status:** Planned

Train contextual estimators on real trajectories; add calibrated belief state, context-carry economics, dynamic shadow pricing, bounded exploration with propensity logging, off-policy evaluation, calibration/drift/regret reporting and explicit identification strategies before causal claims.

**Exit criteria:** held-out evidence shows better effective compute per verified task than fixed policy while preserving quality; exploration remains bounded; any causal claim documents assumptions and identification strategy.

---

## v0.7 — Ecosystem and Operational Scale

**Status:** Planned

Evaluate additional engines; add persistent sessions, optional storage backends, reservation leases/recovery, OpenTelemetry, team policy pinning, signed manifests, optional shared dashboards and portfolio allocation for multi-agent workloads.

**Exit criteria:** persistent sessions recover without lost committed usage; distributed reservations prevent supported double-spend; optional team/cloud features do not make the local open-source runtime dependent on an account.

---

## Success metrics

MARGINAL is evaluated on the combined outcome, not token savings alone:

- verified task resolution rate;
- input, cached input, output, reasoning and total workload tokens;
- governance tokens, USD and latency;
- effective tokens and USD per verified successful task;
- gross versus net savings;
- regressions and recoveries;
- tool calls and repeated calls;
- reviewed stops, false stops and false-stop rate;
- estimator calibration and decision regret;
- variance across repeated runs;
- installation success and rollback reliability;
- capability coverage by engine.

The primary optimization target is:

> **Minimize effective compute per verified successful task, subject to predefined quality and false-stop constraints.**

MARGINAL does not promise that every request will use fewer tokens. Some tasks should spend more on verification. Some efficient model/runtime combinations should result in pass-through.

## Maintaining this roadmap

- Check off deliverables only after implementation and validation are merged.
- Link issues, pull requests, releases and benchmark evidence where useful.
- Keep README claims aligned with the active released milestone.
- Update `CHANGELOG.md` when behavior is released, not merely planned.
- Mark a milestone Complete only after every exit criterion is satisfied.
- Treat negative benchmark results as valid project evidence.
- Require proposed performance changes to state how they could be falsified.
