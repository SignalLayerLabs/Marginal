# Evidence-Based Autonomy Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or
> superpowers:executing-plans task-by-task. Every behavior change uses red-green-refactor.

**Goal:** Turn MARGINAL's tested compute-governance foundation into an auditable, progressive,
contextual autonomy governor with hash-chained evidence, correctness-first utility,
counterfactual/regret evaluation, safe Codex Autopilot, and fail-closed benchmark provenance.

**Architecture:** Provider-neutral governance primitives live in focused core modules and are
consumed by Treasury, replay, diagnostics, and thin engine adapters. Codex owns only lifecycle
translation, ephemeral user-intent normalization, local service operation, and capability-limited
Tool Enforcement. Existing v2 APIs remain readable and compatible while new v3 attestations use a
single canonical serializer and hash chain.

**Tech Stack:** Python 3.10–3.13 standard library, pytest, Ruff 0.16.2, strict mypy, JSON Schema,
Codex 0.147 lifecycle hooks, deterministic zipapp plugin runtime.

## Global constraints

- Correctness dominates efficiency and unknown evidence cannot justify enforcement.
- No raw prompt, prompt hash, source, raw command, raw output, transcript, auth, or credential is
  persisted by governance code.
- Hook/runtime failures fail open for the agent action and fail closed for governance authority.
- Preserve current public constructors, CLI commands, v2 ledgers, frozen evidence, and Python
  3.10–3.13 compatibility.
- No mandatory runtime dependency.
- No commit, push, tag, release, package publication, marketplace submission, or external
  production mutation during this execution.
- Codex reports Tool Enforcement, never Full Compute Enforcement.

---

### Task 1: Canonical serialization and versioned reason codes

**Files:**
- Create: `src/marginal/canonical.py`
- Create: `src/marginal/reason_codes.py`
- Create: `tests/test_canonical.py`
- Create: `tests/test_reason_codes.py`
- Modify: `src/marginal/fingerprint.py`
- Modify: `src/marginal/policy.py`
- Modify: `src/marginal/controls/progress.py`

**Produces:**
- `canonical_bytes(value: Any) -> bytes`
- `canonical_hash(value: Any) -> str`
- `ReasonCode(str, Enum)` and `REASON_CODE_VERSION = "1.0"`

- [x] Write tests proving stable hashes across key order, rejection of NaN/non-JSON values, and
  exact documented values for the small reason-code registry.
- [x] Run the focused tests and confirm failure because the modules do not exist.
- [x] Implement canonical compact JSON with `sort_keys=True`, `ensure_ascii=False`,
  `allow_nan=False`, and UTF-8 SHA-256.
- [x] Add only used governance codes: approval, insufficient evidence/trust, repeated action,
  no progress, user-requested repeat, control-plane bypass, policy revoked, distribution shift,
  integrity failure, recovery, and outcome unknown.
- [x] Replace duplicated attestation hashing where compatibility permits; preserve historical hash
  formats where changing them would invalidate frozen artifacts.
- [x] Run focused tests, existing fingerprint/policy/progress tests, Ruff, and mypy.

### Task 2: Decision Receipts and structured governance signals

**Files:**
- Create: `src/marginal/receipts.py`
- Create: `src/marginal/utility.py`
- Create: `schemas/decision-receipt-v1.json`
- Create: `schemas/progress-evidence-v1.json`
- Mirror: `src/marginal/schemas/decision-receipt-v1.json`
- Mirror: `src/marginal/schemas/progress-evidence-v1.json`
- Create: `tests/test_receipts.py`
- Create: `tests/test_utility.py`
- Modify: `tests/test_packaged_schemas_v2.py`

**Interfaces:**

```python
class ProgressLevel(str, Enum):
    ACTIVITY = "activity"
    INFORMATION = "information"
    PROGRESS = "progress"
    VERIFIED_PROGRESS = "verified_progress"


@dataclass(frozen=True, slots=True)
class ProgressEvidence:
    schema_version: str
    level: ProgressLevel
    state_hash: str
    evidence_hash: str
    confidence: float
    verifier: str | None


@dataclass(frozen=True, slots=True)
class GovernanceCost:
    wall_clock_ms: float
    cpu_ms: float | None
    memory_peak_bytes: int | None
    storage_bytes: int
    tokens: int
    model_calls: int
    additional_tool_calls: int


@dataclass(frozen=True, slots=True)
class DecisionReceipt:
    schema_version: str
    decision_id: str
    timestamp: str
    context: Mapping[str, str]
    decision: str
    reason_code: str
    state_hash: str | None
    evidence_hash: str | None
    trajectory_hash: str | None
    policy_hash: str
    decision_hash: str
    confidence: float
    expected_utility: Mapping[str, Any] | None
    estimated_cost: Mapping[str, Any] | None
    enforcement_level: str
    trust_snapshot: Mapping[str, Any]
    governance_cost: GovernanceCost
```

- [x] Write schema and round-trip tests, including explicit `None` for unavailable measurements,
  immutable mappings, invalid confidence, and tampered receipt hash.
- [x] Confirm RED.
- [x] Implement correctness-first `UtilityVector` comparison and `MarginalUtilityEstimate` that
  returns a structured scorecard when scalar EMU is scientifically unavailable.
- [x] Implement Decision Receipt canonical payload/hash/verification without arbitrary object
  string representations.
- [x] Verify root and packaged schemas are byte-identical and validate real examples.
- [x] Run focused tests, schema suite, Ruff, and mypy.

### Task 3: Hash-chained governance ledger and v2 migration

**Files:**
- Create: `src/marginal/governance_ledger.py`
- Create: `schemas/governance-ledger-v3.json`
- Mirror: `src/marginal/schemas/governance-ledger-v3.json`
- Create: `tests/test_governance_ledger.py`
- Create: `tests/test_ledger_migration_v3.py`
- Modify: `src/marginal/ledger.py`
- Modify: `src/marginal/cli.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class LedgerVerificationReport:
    valid: bool
    records: int
    root_hash: str | None
    first_invalid_sequence: int | None
    error_codes: tuple[str, ...]


class GovernanceLedger:
    def append(self, payload: Mapping[str, Any]) -> str: ...
    def verify(self, *, expected_root: str | None = None) -> LedgerVerificationReport: ...


def migrate_v2_to_v3(source: Path, destination: Path) -> LedgerVerificationReport: ...
def quarantine_invalid_records(source: Path, destination: Path) -> Path: ...
```

- [x] Write tests for contiguous append, previous-hash and record-hash linkage, fsync/owner-only
  permissions, symlink refusal, tampered payload, deleted middle record, incompatible schema,
  expected-root mismatch, non-destructive quarantine, and deterministic v2 migration.
- [x] Confirm RED for each corruption class.
- [x] Implement v3 as a separate ledger so v2 read/write compatibility remains intact.
- [x] Use an OS file lock where available, re-read the tail under lock, append one canonical line,
  flush, and fsync. Fail safely on platforms without the lock primitive rather than claiming
  multi-process safety.
- [x] Add `marginal verify LEDGER [--expected-root HASH] [--json]` and
  `marginal ledger-migrate SOURCE DESTINATION`.
- [x] Run focused tests, existing ledger/privacy tests, CLI tests, Ruff, and mypy.

### Task 4: Progressive authority and contextual Trust Engine

**Files:**
- Create: `src/marginal/authority.py`
- Create: `src/marginal/trust.py`
- Create: `schemas/trust-snapshot-v1.json`
- Mirror: `src/marginal/schemas/trust-snapshot-v1.json`
- Create: `tests/test_authority.py`
- Create: `tests/test_trust.py`

**Interfaces:**

```python
class AuthorityLevel(IntEnum):
    OBSERVE = 0
    ADVISE = 1
    SOFT_INTERVENE = 2
    TOOL_GATE = 3
    COMPUTE_GOVERN = 4


@dataclass(frozen=True, slots=True)
class TrustContext:
    repository: str
    agent: str
    model: str
    task_class: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class TrustEvidence:
    observed: int
    evaluable: int
    covered: int
    coverable: int
    beneficial: int
    neutral: int
    harmful: int
    indeterminate: int
    governance_tax_ratio: float | None
    mean_regret: float | None
    integrity_valid: bool
    last_observed_at: str | None


class TrustEngine:
    def evaluate(
        self,
        context: TrustContext,
        evidence: TrustEvidence,
        current: AuthorityLevel,
        *,
        capabilities: int,
        shift_reasons: tuple[str, ...] = (),
    ) -> TrustSnapshot: ...
```

- [x] Write transition-table tests for minimum samples, coverage, harm, regret, tax, explicit
  capability ceilings, promotion hysteresis, one-level soft decay, critical reset, model/policy
  shift, large repository shift, inactivity, and anti-flapping.
- [x] Confirm RED.
- [x] Implement transparent component calculations and blocker lists; do not hide sample size in a
  single score.
- [x] Implement transition receipts bound to the evidence-ledger root.
- [x] Run focused tests, Ruff, and mypy.

### Task 5: Progress proof, governance tax, and Treasury EMU allocation

**Files:**
- Modify: `src/marginal/controls/progress.py`
- Modify: `src/marginal/controls/governance.py`
- Modify: `src/marginal/models.py`
- Modify: `src/marginal/treasury.py`
- Create: `tests/controls/test_progress_evidence.py`
- Modify: `tests/controls/test_treasury_governance.py`
- Create: `tests/test_treasury_utility.py`

**Produces:**
- conversion from no-progress observations to `ProgressEvidence`;
- governance p50/p95, CPU, memory, storage, model/tool call accounting;
- `Treasury.rank_candidates(actions, estimates) -> tuple[AllocationScore, ...]` with structured
  utility and uncertainty.

- [ ] Write tests proving activity/new information/progress/verified progress remain distinct,
  failure/unknown never create verified progress, and changed evidence resets repetition.
- [ ] Write tests for governance-tax distributions and net scorecards without dividing by zero or
  inventing unavailable fields.
- [ ] Write ranking tests where correctness/verification beats cheaper low-value work, uncertainty
  lowers confidence, and existing `fund_best` behavior remains unchanged.
- [ ] Confirm RED, implement minimal behavior, and refactor shared validation only after GREEN.
- [ ] Run Treasury, controls, policy, benchmark, Ruff, and mypy suites.

### Task 6: Counterfactual engine and Intervention Regret

**Files:**
- Create: `src/marginal/counterfactual.py`
- Create: `schemas/intervention-evaluation-v1.json`
- Mirror: `src/marginal/schemas/intervention-evaluation-v1.json`
- Create: `tests/test_counterfactual.py`
- Create: `tests/test_intervention_regret.py`
- Modify: `src/marginal/outcomes.py`

**Interfaces:**

```python
class CounterfactualMode(str, Enum):
    LIVE_PAIRED = "live_paired"
    REPLAY_APPROXIMATION = "replay_approximation"


class InterventionCategory(str, Enum):
    BENEFICIAL = "beneficial"
    NEUTRAL = "neutral"
    HARMFUL = "harmful"
    INDETERMINATE = "indeterminate"


class PairedBranchRunner(Protocol):
    def run_pair(self, spec: PairedBranchSpec) -> PairedBranchResult: ...


def evaluate_intervention(
    governed: CounterfactualOutcome, comparison: CounterfactualOutcome
) -> InterventionEvaluation: ...
def summarize_regret(items: Sequence[InterventionEvaluation]) -> RegretSummary: ...
```

- [ ] Write tests for all four categories, correctness dominance, unavailable outcomes,
  structured regret, scalar regret only for comparable measurements, median/mean/high-regret
  summaries, and live-pair attestation mismatch rejection.
- [ ] Confirm RED.
- [ ] Implement the provider-neutral live runner contract plus deterministic reference runner for
  tests; document that Codex cannot supply live session cloning.
- [ ] Persist evaluations as v3 ledger payloads and validate schemas.
- [ ] Run focused tests, outcome/ledger tests, Ruff, and mypy.

### Task 7: Replay Lab and offline policy lifecycle

**Files:**
- Modify: `src/marginal/replay.py`
- Create: `src/marginal/policy_evaluation.py`
- Create: `tests/test_replay_lab.py`
- Create: `tests/test_policy_evaluation.py`
- Modify: `src/marginal/cli.py`

**Produces:**
- event timeline and candidate/actual intervention report;
- `compare_policies(...) -> PolicyComparison`;
- immutable candidate artifacts and hash-verified promotion/rollback state.

- [ ] Write replay tests for progress/evidence timeline, earliest/highest-confidence candidates,
  later invalidating evidence, explicit replay approximation labels, and two-policy comparison.
- [ ] Write policy tests proving no promotion on missing quality, unknown policy, harmful-rate or
  integrity failure; valid candidate promotion writes a receipt; rollback restores the prior hash.
- [ ] Confirm RED.
- [ ] Implement `marginal policy evaluate|compare|promote|rollback` without direct online mutation
  of an enforced estimator.
- [ ] Keep `Treasury.observe_value` backward compatible but mark its estimator state as a candidate
  training fingerprint unless an explicitly active policy consumes it.
- [ ] Run replay/policy/CLI tests, Ruff, and mypy.

### Task 8: Codex user-intent normalization and control-plane bypass

**Files:**
- Create: `src/marginal/integrations/codex/intent.py`
- Modify: `src/marginal/integrations/codex/events.py`
- Modify: `src/marginal/integrations/codex/normalization.py`
- Modify: `plugins/marginal/hooks/hooks.json`
- Create: `tests/integrations/codex/test_intent.py`
- Modify: `tests/integrations/codex/test_events.py`
- Modify: `tests/integrations/codex/test_normalization.py`
- Modify: `tests/integrations/codex/test_marketplace_smoke.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class UserIntent:
    repeat_requested: bool = False
    force_run: bool = False
    pause_marginal: bool = False
    resume_marginal: bool = False
    status_requested: bool = False


def normalize_user_prompt(prompt: str) -> UserIntent: ...
def is_control_plane_action(event: PreToolUseEvent, plugin_root: Path) -> bool: ...
```

- [x] Write Italian/English NFKC/case/whitespace/synonym tests, ambiguous language fail-open tests,
  and assertions that prompt text/hash never enters evidence serialization.
- [x] Write control-plane tests accepting only the resolved trusted plugin script path and
  rejecting lookalike repository paths, traversal, symlinks, and shell injection.
- [x] Confirm RED.
- [x] Parse official `UserPromptSubmit` events, retain intent only in the authenticated in-memory
  session, and add the hook to the deterministic plugin bundle.
- [x] Mark trusted control-plane actions as non-coverable bypass decisions with a stable reason and
  no pending workload reservation.
- [x] Run Codex event/normalization/privacy/marketplace tests, rebuild the zipapp, and run check.

### Task 9: Codex Autopilot, receipt-bound evidence, and recovery

**Files:**
- Create: `src/marginal/integrations/codex/autopilot.py`
- Modify: `src/marginal/integrations/codex/evidence.py`
- Modify: `src/marginal/integrations/codex/promotion.py`
- Modify: `src/marginal/integrations/codex/runtime.py`
- Modify: `src/marginal/integrations/codex/service.py`
- Modify: `src/marginal/integrations/codex/commands.py`
- Create: `tests/integrations/codex/test_autopilot.py`
- Modify: `tests/integrations/codex/test_evidence.py`
- Modify: `tests/integrations/codex/test_promotion.py`
- Modify: `tests/integrations/codex/test_runtime.py`
- Modify: `tests/integrations/codex/test_service.py`

**Behavior:**
- deferred one-time Autopilot consent;
- first-session quick receipt bound to a verified evidence root;
- L3 only for exact proven-success no-progress local actions;
- user-requested repeat, polling/waiting, failure/unknown, changed state/evidence, and uncovered
  families pass;
- one immediate retry is allowed as recovery and demotes;
- errors, recovery, integrity/capability/identity drift demote and fail open.

- [x] Write end-to-end state-machine tests for consent, warmup, auto-eligibility, receipt creation,
  third-repeat deny, user-intent bypass, recovery, auto-demotion, concurrent pending actions, and
  restart persistence.
- [x] Confirm RED.
- [x] Make Codex evidence use or anchor to the v3 chain; promotion verifies root/range before
  activation.
- [x] Separate active workload pending counts from unrelated concurrent actions so concurrency does
  not spuriously demote while unresolved eligible-family outcomes still fail closed.
- [x] Add actual `avoided_actions` and `recoveries` counters; do not estimate tokens.
- [x] Run the full Codex integration suite, plugin build/check, Ruff, and mypy.

### Task 10: Unified diagnostics, explainability, and privacy inspection

**Files:**
- Create: `src/marginal/diagnostics.py`
- Modify: `src/marginal/cli.py`
- Modify: `src/marginal/integrations/codex/commands.py`
- Modify: `src/marginal/integrations/codex/installer.py`
- Create: `tests/test_diagnostics.py`
- Modify: `tests/test_cli_v2.py`
- Modify: `tests/integrations/codex/test_commands.py`
- Modify: `tests/integrations/codex/test_installer.py`

**Commands:**
- `marginal status [--json]`
- `marginal doctor [--json]`
- `marginal explain DECISION_ID [--json]`
- `marginal privacy inspect [--json]`

- [x] Write output-contract tests for authority/current eligibility, trust components, exact next
  promotion blockers, ledger integrity, plugin/runtime provenance, permissions, benchmark
  readiness, deterministic decision explanation, and persisted data categories.
- [x] Confirm RED.
- [x] Implement typed report objects shared by human/JSON renderers.
- [x] Keep `marginal codex status|doctor` as compatible aliases.
- [x] Add install-time Autopilot consent configuration without allowing repository configuration to
  raise user-level authority.
- [x] Run CLI/installer/privacy/integration tests, Ruff, and mypy.

### Task 11: Benchmark provenance and correctness-first public metrics

**Files:**
- Modify: `benchmark/codex_adapter/evidence.py`
- Modify: `benchmark/codex_adapter/runner.py`
- Modify: `benchmark/codex_adapter/container_runner.py`
- Modify: `benchmarks/swebench_lite/protocol.py`
- Modify: `benchmarks/swebench_lite/merge_results.py`
- Modify: `src/marginal/public_eval.py`
- Create: `benchmark/schemas/evidence-bundle-v2.json`
- Modify: `tests/evaluation/test_swebench_lite_protocol.py`
- Modify: `tests/evaluation/test_swebench_lite_merge.py`
- Modify: `tests/test_public_eval_v2.py`

- [ ] Write fail-closed tests for run records, provenance, verifier digests, merged rows, public
  artifacts, patch/configuration hashes, pair mismatch, starting SHA, task mismatch, execution
  order, and missing files.
- [ ] Confirm RED without altering frozen evidence.
- [ ] Add a versioned evidence-DAG manifest for future runs and a compatibility validator for the
  existing frozen v1 smoke.
- [ ] Add input/cached/output/reasoning metrics, paired classes, intervention categories, regret,
  candidate counts, and provenance hashes to public evaluation.
- [ ] Report `insufficient_correctness_evidence` for zero-resolved paired samples and preserve
  `pass_through`.
- [ ] Generate public summaries programmatically and verify the frozen JSON remains traceable.
- [ ] Run benchmark/evaluation tests, Ruff, and mypy.

### Task 12: Security, performance, documentation, and release readiness

**Files:**
- Create: `tests/performance/test_governor_performance.py`
- Create: `tests/adversarial/test_productive_repetition.py`
- Create: `tests/adversarial/test_partial_streams.py`
- Modify: `.github/workflows/release.yml`
- Modify: `README.md`, `CHANGELOG.md`, `SECURITY.md`, `ROADMAP.md`
- Create: `docs/adr/0001-earned-authority.md`
- Create: `docs/adr/0002-decision-receipt-ledger.md`
- Create: `docs/adr/0003-contextual-trust.md`
- Create: `docs/adr/0004-counterfactual-and-regret.md`
- Create: `docs/adr/0005-plugin-core-boundary.md`
- Create: `docs/product/decision-receipts.md`
- Create: `docs/product/trust-and-authority.md`
- Create: `docs/evaluation/counterfactual-and-regret.md`
- Create: `docs/evaluation/replay-and-policy-lab.md`
- Create: `docs/reference/reason-codes.md`
- Modify: `docs/integrations/codex.md`
- Modify: `docs/integrations/codex-benchmark-readiness.md`
- Modify: `benchmark/analysis/summary.md`

- [ ] Add adversarial tests for productive repetition, long debugging, slow eventual progress,
  changed-state verification, oscillating exploration, new repository, policy/model shift,
  corrupted ledger, clock anomaly, and partial streams.
- [ ] Add a deterministic governor microbenchmark measuring throughput, p50/p95 event and decision
  latency, CPU, memory peak, storage, and ledger growth with conservative local regression limits.
- [ ] Change release creation to explicit manual/tag-gated approval; do not create a release.
- [ ] Update product positioning to Evidence-Based Agent Governance and document every implemented
  CLI, schema, authority rule, privacy category, security boundary, migration, and external blocker.
- [ ] Reconcile 10-versus-20 canary wording and stale zero-run analysis while preserving historical
  provenance.
- [ ] Regenerate plugin runtime and submission archive locally without uploading it.
- [ ] Run the full final gate: Ruff format/check, strict mypy, full pytest, plugin build check,
  package build, Twine check, CLI smoke, governor benchmark, secret/path scan, and git diff review.
