# MARGINAL Roadmap

MARGINAL's North Star is simple:

> **Install MARGINAL once, keep using your AI development agent normally, and reduce avoidable token consumption without sacrificing verified quality.**

MARGINAL is being developed as one universal, local compute-governance product for the main AI development agents. A single core, protocol, installer, policy system, and reporting experience will support Codex, Claude Code, GitHub Copilot, OpenCode, and future compatible runtimes through thin engine adapters.

This roadmap is milestone-driven rather than date-driven. It communicates product direction and measurable outcomes. GitHub Issues and pull requests should track implementation-level work.

## Product principles

1. **One product:** one core, one protocol, one installer, and one user experience.
2. **Thin adapters:** engine-specific behavior stays outside the decision core.
3. **Quality first:** token reduction is valuable only when verified quality is preserved.
4. **Measured claims:** public savings claims must use real runtime or provider telemetry.
5. **Local first:** prompts and source code are not uploaded or logged by default.
6. **Simple installation:** supported agents should require no manual code changes.
7. **Transparent capabilities:** observe-only and enforcement integrations must be clearly distinguished.
8. **Small core:** the provider-neutral core keeps zero mandatory runtime dependencies.

## Status legend

| Status | Meaning |
|---|---|
| **Planned** | Scope is defined, but implementation has not started. |
| **In progress** | Implementation is actively underway. |
| **Validation** | Implementation is complete, but benchmark or compatibility evidence is still pending. |
| **Complete** | All exit criteria have been met and supporting evidence is available. |

## Milestones at a glance

| Milestone | Status | Primary outcome |
|---|---|---|
| **v0.1 — Reference Allocator Foundation** | Complete | Provider-neutral allocation, accounting, tracing, demos, and first release |
| **v0.2 — Universal Agent Foundation** | In progress | Shared protocol and runtime for every supported development agent |
| **v0.3 — Codex Reference Integration** | Planned | Real Codex integration and measured paired benchmark |
| **v0.4 — Multi-Engine Developer Preview** | Planned | Codex, OpenCode, Claude Code, and GitHub Copilot compatibility |
| **v0.5 — One-Command Universal Installation** | Planned | Automatic detection, installation, diagnostics, and rollback |
| **v0.6 — Adaptive Allocation** | Planned | Context-aware value estimation and dynamic compute pricing |
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

## v0.2 — Universal Agent Foundation

**Status:** In progress

**Objective:** Create the shared architecture that lets every supported development agent use the same MARGINAL decision engine, telemetry model, and safety guarantees.

### Deliverables

- [ ] Publish MARGINAL Universal Agent Protocol v1
- [ ] Define versioned normalized event, decision, capability, and outcome schemas
- [ ] Add capability negotiation for observe, modify, deny, stop, and verification control
- [ ] Add token usage v2 with input, cached input, output, reasoning, and total token fields
- [ ] Add trace schema v2 with run, task, trajectory, action, policy, estimator, and model identity
- [ ] Add state-aware fingerprints and configurable deduplication scopes
- [ ] Add `shadow`, `recommend`, and `enforce` operating modes
- [ ] Add explicit settlement for failed, partial, unknown, and measured usage
- [ ] Add conservative built-in policy profiles: Quality First, Balanced, Token Saver, and Strict Budget
- [ ] Add a local session runtime and state store
- [ ] Define the shared adapter SDK and conformance test suite
- [ ] Preserve a dependency-free provider-neutral core

### Exit criteria

- The protocol and schemas are versioned and documented.
- A reference simulated adapter passes all conformance tests.
- Existing v0.1 behavior remains backward compatible or has an explicit migration path.
- Shadow mode can observe a complete agent session without changing its behavior.
- The core still has zero mandatory runtime dependencies.

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
- [ ] Reuse the same protocol, policy profiles, telemetry, and reports across all adapters
- [ ] Publish an engine capability matrix
- [ ] Add adapter-specific compatibility and end-to-end tests
- [ ] Clearly label each integration as Observe, Tool Enforcement, or Full Compute Enforcement
- [ ] Add unified cross-engine session reporting
- [ ] Validate clean failure and fail-open behavior for every adapter

### Exit criteria

- At least four development-agent environments, including Codex, pass protocol conformance tests.
- No adapter contains duplicated economic decision logic.
- Every supported engine has documented capabilities and limitations.
- The same policy profile produces comparable decision traces across engines.
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
- [ ] Enable Quality First and shadow mode by default
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

## v0.6 — Adaptive Allocation

**Status:** Planned

**Objective:** Replace static expected-gain assumptions with contextual, uncertainty-aware estimates learned from real agent trajectories.

### Deliverables

- [ ] Add contextual value estimation by task, phase, engine, model, evidence, and repository state
- [ ] Attach uncertainty, confidence, sample size, and provenance to value estimates
- [ ] Add a calibrated task belief state updated by tests, errors, reviews, and verifier evidence
- [ ] Estimate context-carry cost across future model turns
- [ ] Add dynamic token shadow pricing based on scarcity and projected remaining work
- [ ] Add controlled, budgeted exploration for counterfactual learning
- [ ] Prevent exploration for unsafe or irreversible actions
- [ ] Add estimator calibration and drift reports
- [ ] Compare adaptive policies against fixed reference policies
- [ ] Preserve deterministic policy modes for reproducibility and regulated use cases

### Exit criteria

- Predicted value and observed outcomes have published calibration evidence.
- Adaptive allocation improves token cost per verified task over the fixed reference policy on held-out runs.
- Quality remains within the predefined non-inferiority margin.
- Exploration behavior is bounded, reproducible, and separately accounted.

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
