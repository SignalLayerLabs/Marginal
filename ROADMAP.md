# MARGINAL Roadmap

MARGINAL's North Star is simple:

> **Install MARGINAL once, keep using your AI development agent normally, and reduce avoidable token consumption without sacrificing verified quality.**

MARGINAL is being developed as one universal, local compute-governance product for the main AI development agents. A single core, protocol, installer, policy system, learning loop, and reporting experience will support Codex, Claude Code, GitHub Copilot, OpenCode, and future compatible runtimes through thin engine adapters.

This roadmap is milestone-driven rather than date-driven. It communicates product direction and measurable outcomes. GitHub Issues and pull requests should track implementation-level work.

## Product principles

1. **One product:** one core, one protocol, one installer, and one user experience.
2. **Thin adapters:** engine-specific behavior stays outside the decision core.
3. **Quality first:** token reduction is valuable only when verified quality is preserved.
4. **Measured claims:** public savings claims must use real runtime or provider telemetry.
5. **Learning without overclaiming:** observational associations are not described as causal value.
6. **Local first:** prompts and source code are not uploaded or logged by default.
7. **Simple installation:** supported agents should require no manual code changes.
8. **Transparent capabilities:** observe-only and enforcement integrations must be clearly distinguished.
9. **Small core:** the provider-neutral core keeps zero mandatory runtime dependencies.

## Status legend

| Status | Meaning |
|---|---|
| **Planned** | Scope is defined, but implementation has not started. |
| **In progress** | Implementation is actively underway. |
| **Validation** | Implementation exists, but final CI, release, integration, or benchmark evidence is pending. |
| **Complete** | All exit criteria have been met and supporting evidence is available. |

## Milestones at a glance

| Milestone | Status | Primary outcome |
|---|---|---|
| **v0.1 — Reference Allocator Foundation** | Complete | Provider-neutral allocation, accounting, tracing, demos, and first release |
| **v0.2 — Learning Loop Foundation** | Validation | Universal protocol, non-blocking observation, versioned evidence, outcomes, replay, and estimators |
| **v0.3 — Codex Reference Integration** | Planned | Real Codex integration and measured paired benchmark |
| **v0.4 — Multi-Engine Developer Preview** | Planned | Codex, OpenCode, Claude Code, and GitHub Copilot compatibility |
| **v0.5 — One-Command Universal Installation** | Planned | Automatic detection, installation, diagnostics, and rollback |
| **v0.6 — Adaptive and Causal Allocation** | Planned | Calibrated learning, context-carry economics, exploration, and regret measurement |
| **v0.7 — Ecosystem and Operational Scale** | Planned | Additional engines, persistent runtimes, observability, and team controls |

---

## v0.1 — Reference Allocator Foundation

**Status:** Complete

**Objective:** Establish a small, auditable, provider-neutral compute-allocation core.

### Delivered

- [x] Provider-neutral `Action`, `Cost`, `Decision`, and `Allocation` primitives
- [x] Hard token, USD, latency, and risk budgets
- [x] Atomic reservation, settlement, abort, and overrun accounting
- [x] Hierarchical treasuries and protected verification reserves
- [x] Deterministic marginal-value policy and candidate ranking
- [x] Exact duplicate and pending-action protection
- [x] Synchronous and asynchronous guarded-call adapters
- [x] Common LLM usage extraction
- [x] Append-only JSONL decision traces and CLI reporting
- [x] Synthetic benchmark and end-to-end Killer Demo
- [x] Public benchmark comparison utility
- [x] Python 3.10–3.13 CI, CodeQL, packaging, and project documentation

### Exit criteria

- [x] `v0.1.0` released
- [x] CI passes across supported Python versions
- [x] Synthetic claims are clearly separated from measured production claims
- [x] Core remains free of mandatory runtime dependencies

Evidence: [`CHANGELOG.md`](CHANGELOG.md), [`docs/architecture.md`](docs/architecture.md), and [`demos/killer-demo`](demos/killer-demo/RESULTS.md).

---

## v0.2 — Learning Loop Foundation

**Status:** Validation

**Objective:** Create the shared, versioned learning-loop foundation that lets every supported development agent use the same MARGINAL decisions, evidence model, accounting, and safety guarantees.

### Delivered in the release candidate

- [x] Publish MARGINAL Universal Agent Protocol v1
- [x] Define normalized event, decision, capability, outcome, token-usage, and ledger schemas
- [x] Add capability negotiation for observe, modify, deny, stop, and verification control
- [x] Add additive token usage v2 for uncached input, cached input, output, reasoning, and total tokens
- [x] Add Decision Ledger v2 with run, task, trajectory, action, policy, estimator, engine, and model identity
- [x] Classify evidence fields as safe-by-default, pseudonymous, or potentially sensitive
- [x] Add `LOCAL_FULL` and keyed `SAFE_TELEMETRY` operational ledger profiles
- [x] Add separate grouped `AGGREGATE_EXPORT` output with no identifiers or timestamps
- [x] Suppress aggregate groups smaller than five records by default with a configurable threshold
- [x] Publish recursively strict JSON Schemas for safe event-level telemetry and aggregate exports
- [x] Add local 256-bit key generation, restrictive permission checks, race-safe exports, and safe export CLI
- [x] Add strict ledger parsing, monotonic sequence validation, and task/outcome correlation checks
- [x] Add state-aware fingerprints and configurable deduplication scopes
- [x] Add `shadow`, `recommend`, and `enforce` operating modes
- [x] Preserve concurrent Shadow Mode observations with separate reservation identities
- [x] Add explicit failed-action settlement for measured, estimated, and unavailable usage
- [x] Keep failed actions retryable while accounting for consumed resources
- [x] Add conservative fallback settlement when failure usage extraction itself fails
- [x] Add Quality First, Balanced, Token Saver, and Strict Budget reference profiles
- [x] Add a provider-neutral local `UniversalRuntime`
- [x] Add explicit task outcomes and separate action-level realized-gain observations
- [x] Add versioned estimator identities, uncertainty, confidence, sample size, provenance, and registry
- [x] Add deterministic training-data fingerprints for online observations
- [x] Add non-causal policy replay and CLI ledger validation/reporting
- [x] Add protocol and schema conformance tests, executable examples, and aligned documentation
- [x] Preserve the dependency-free provider-neutral runtime core

### Exit criteria

- [x] Protocols and schemas are versioned and documented.
- [x] Privacy profiles, field classification, key handling, small-group suppression, export boundaries, and limitations are documented.
- [x] The provider-neutral reference runtime passes focused protocol and lifecycle tests.
- [x] Shadow Mode can observe complete action lifecycles without blocking caller behavior.
- [x] Existing v0.1 constructors and enforced execution paths remain covered by regression tests.
- [x] The package metadata and public documentation describe the implemented v0.2 behavior consistently.
- [x] The runtime core still has zero mandatory dependencies.
- [ ] Ruff, mypy strict, the full repository test suite, package build, and Twine validation pass in the canonical GitHub checkout and CI.
- [ ] `v0.2.0` is tagged and released from the canonical repository.

The release remains in **Validation** until the final two exit criteria are satisfied. Vendor-specific adapters and measured production savings are intentionally not part of v0.2.

---

## v0.3 — Codex Reference Integration

**Status:** Planned

**Objective:** Integrate MARGINAL into Codex and produce the first real paired benchmark with measured token telemetry.

### Deliverables

- [ ] Build the Codex adapter against the Universal Agent Protocol
- [ ] Support `marginal install codex`
- [ ] Capture measured input, cached input, output, reasoning, and total tokens
- [ ] Intercept supported tool, retry, verification, and continuation decisions
- [ ] Add Codex session, workspace-state, and patch correlation
- [ ] Build the paired baseline-versus-MARGINAL benchmark runner
- [ ] Run a 10-task canary with identical model, prompts, tools, limits, and verifier
- [ ] Run a preregistered 100-task public benchmark
- [ ] Report token savings, quality delta, regressions, recoveries, latency, and tool calls
- [ ] Report token cost per verified successful task
- [ ] Publish raw paired JSONL results and a reproducible report

### Exit criteria

- Codex baseline and Codex with MARGINAL can be executed under matched conditions.
- Token usage comes from Codex telemetry rather than declared estimates.
- The 10-task canary completes without integration failures.
- The 100-task report includes statistical uncertainty and a predefined quality non-inferiority margin.
- Public claims link directly to reproducible evidence.

---

## v0.4 — Multi-Engine Developer Preview

**Status:** Planned

**Objective:** Prove that one MARGINAL runtime can govern materially different AI development agents without duplicating policy logic.

### Deliverables

- [ ] Build an OpenCode adapter
- [ ] Build a Claude Code adapter
- [ ] Build a GitHub Copilot CLI or coding-agent adapter where official control surfaces permit it
- [ ] Reuse the same protocol, policy profiles, telemetry, ledger, and reports across all adapters
- [ ] Publish an engine capability matrix
- [ ] Add adapter-specific compatibility and end-to-end tests
- [ ] Clearly label each integration as Observe, Tool Enforcement, or Full Compute Enforcement
- [ ] Add unified cross-engine session reporting
- [ ] Validate clean failure and fail-open behavior for every adapter

### Exit criteria

- At least four development-agent environments, including Codex, pass protocol conformance tests.
- No adapter contains duplicated economic decision logic.
- Every supported engine has documented capabilities and limitations.
- The same policy profile produces comparable decision records across engines.
- At least two engines support real action enforcement.

---

## v0.5 — One-Command Universal Installation

**Status:** Planned

**Objective:** Make MARGINAL installable and removable by non-expert users without manual configuration edits.

### Deliverables

- [ ] Add `marginal install --detect`
- [ ] Automatically detect supported agents and their versions
- [ ] Install only the required adapters
- [ ] Create safe backups before changing agent configuration
- [ ] Enable Quality First and Shadow Mode by default
- [ ] Add `marginal status`
- [ ] Add `marginal doctor`
- [ ] Add `marginal profile`
- [ ] Add `marginal uninstall`
- [ ] Restore original configurations during rollback
- [ ] Keep telemetry local and prompt logging disabled by default
- [ ] Test installation on Windows, macOS, and Linux
- [ ] Provide clear handling for unsupported or partially supported versions

### Exit criteria

- A new user can install MARGINAL with one command and no manual file edits.
- Supported-agent detection and diagnostics complete in under two minutes on a typical development machine.
- Uninstall restores the original agent configuration.
- A failed installer does not leave a supported agent unusable.
- The user sees one consistent status and configuration experience across engines.

---

## v0.6 — Adaptive and Causal Allocation

**Status:** Planned

**Objective:** Learn calibrated action value from real trajectories while distinguishing prediction, association, and causal evidence.

### Deliverables

- [ ] Train and validate contextual estimators on real engine trajectories
- [ ] Add a calibrated task belief state updated by deterministic evidence
- [ ] Estimate context-carry cost across future model turns
- [ ] Add dynamic token shadow pricing based on scarcity and projected remaining work
- [ ] Add controlled, budgeted exploration with propensity logging
- [ ] Prevent exploration for unsafe or irreversible actions
- [ ] Add off-policy evaluation appropriate to logged propensities
- [ ] Add estimator calibration, drift, and regret reports
- [ ] Compare adaptive policies against fixed reference policies on held-out runs
- [ ] Define explicit evidence standards before making causal marginal-value claims
- [ ] Preserve deterministic policy modes for reproducibility and regulated use cases

### Exit criteria

- Predicted action value and observed outcomes have published calibration evidence.
- Adaptive allocation improves token cost per verified task over the fixed reference policy on held-out runs.
- Quality remains within the predefined non-inferiority margin.
- Exploration behavior is bounded, reproducible, and separately accounted.
- Any causal claim includes a documented identification strategy and assumptions.

---

## v0.7 — Ecosystem and Operational Scale

**Status:** Planned

**Objective:** Expand compatibility and operational robustness after the universal runtime has been validated.

### Deliverables

- [ ] Evaluate Gemini CLI, Aider, Cline, Roo Code, Continue, and other compatible runtimes
- [ ] Add persistent local treasury and session recovery
- [ ] Add optional SQLite, Redis, or PostgreSQL backends without burdening the core
- [ ] Add reservation leases, expiry, replay, snapshots, and crash recovery
- [ ] Add OpenTelemetry spans and metrics
- [ ] Add team policy configuration and policy version pinning
- [ ] Add signed adapter and policy manifests
- [ ] Add optional shared dashboards without requiring MARGINAL Cloud
- [ ] Add portfolio allocation for parallel and multi-agent workloads
- [ ] Add action dependency, conflict, alternative, and prerequisite modeling
- [ ] Publish long-running and multi-agent reliability benchmarks

### Exit criteria

- Persistent sessions recover without losing committed usage.
- Distributed reservations prevent double-spend under supported backends.
- Additional adapters pass the same protocol conformance suite.
- Team features remain optional and the local open-source runtime remains fully usable without an account.

---

## Initial engine scope

The first product scope is AI development agents with observable or controllable agent loops.

| Engine | Planned role |
|---|---|
| **Codex** | Reference integration and primary measured benchmark |
| **OpenCode** | Open-source research and adapter-development environment |
| **Claude Code** | Rich hook-based commercial integration |
| **GitHub Copilot CLI / coding agent** | Broad developer adoption where official APIs permit enforcement |
| **Gemini CLI, Aider, Cline, Roo Code, Continue** | Later compatibility candidates |

Autocomplete-only surfaces and traditional IDE chat are not considered equivalent to a fully controllable agent runtime. They will not be labeled as full MARGINAL integrations unless an official control surface supports real interception and measured usage.

## Success metrics

MARGINAL will be evaluated on the combined outcome, not token savings alone:

- verified task resolution rate;
- input, cached input, output, reasoning, and total tokens;
- token cost per verified successful task;
- regressions and recoveries;
- tool and sub-agent calls;
- latency and direct cost;
- estimator calibration and decision regret;
- variance across repeated runs;
- installation success and rollback reliability;
- capability coverage by engine.

The primary optimization target is:

> **Minimize token consumption per verified successful task, subject to a predefined quality non-inferiority constraint.**

MARGINAL does not promise that every individual request will use fewer tokens. Some tasks may require additional verification. The product goal is to remove avoidable compute across real sessions while protecting outcome quality.

## Maintaining this roadmap

- Update milestone status only when its definition changes.
- Check off a deliverable only after implementation and validation are merged.
- Link relevant issues, pull requests, releases, benchmarks, or evidence where useful.
- Use GitHub Issues and Projects for task ownership and day-to-day execution.
- Keep implementation details out of this file unless they change product scope.
- Keep the README limited to the active milestone and a link to this roadmap.
- Update `CHANGELOG.md` when behavior is released, not when work is merely planned.
- Mark a milestone **Complete** only when every exit criterion has been satisfied.

Roadmap changes are welcome through focused issues and pull requests. Proposed changes should explain the user outcome, compatibility implications, validation method, and relationship to the North Star.
