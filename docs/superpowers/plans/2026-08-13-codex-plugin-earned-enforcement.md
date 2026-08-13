# Codex Plugin and Earned Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a native, reversible MARGINAL Codex plugin that starts globally in Shadow Mode and permits repository-scoped Tool Enforcement only after a versioned local evidence gate passes.

**Architecture:** Official Codex lifecycle hooks call a generated Python runtime built from the installed source tree. A per-session authenticated loopback service owns one provider-neutral `Treasury`; the Codex anti-corruption layer converts strict hook events into core actions and writes hash-only evidence. A plugin marketplace and management CLI use Codex's plugin commands rather than editing its configuration.

**Tech Stack:** Python 3.10–3.13 standard library, pytest, strict mypy, Ruff, setuptools, Python zipapp, Codex CLI 0.147+ stable hooks/plugins, JSON/JSONL, loopback TCP.

## Global Constraints

- The provider-neutral runtime keeps zero mandatory dependencies.
- Production code never imports from `benchmark`.
- Global installation is Shadow Mode; enforcement scope is one repository.
- Product capability is `tool_enforcement`, never `full_compute_enforcement`.
- Only proven successful actions advance `DiminishingReturnDetector` history.
- Raw prompts, source, commands, tool responses, transcripts, and credentials are not persisted.
- Hook trust is never bypassed.
- Integration failures fail open, record a gap, and demote enforcement.
- Generated plugin runtime files are built from source and never edited manually.
- Public-directory availability is claimed only after OpenAI approval and publication.

---

## File map

- `src/marginal/controls/progress.py`: outcome and no-progress control.
- `src/marginal/integrations/codex/`: events, normalization, state, outcomes, evidence, promotion, runtime, transport, service, installer, and commands.
- `plugins/marginal/`: manifest, hooks, skill, launcher, assets, and generated runtime.
- `.agents/plugins/marketplace.json`: Git marketplace catalog.
- `scripts/build_codex_plugin.py`: reproducible plugin generator.
- `tests/integrations/codex/` and `tests/plugin/`: contracts and distribution tests.
- `docs/integrations/codex.md`, public policy pages, README, roadmap, changelog, and site: launch and submission surfaces.

---

### Task 1: Provider-neutral completion and no-progress control

**Files:**
- Create: `src/marginal/controls/progress.py`
- Modify: `src/marginal/controls/__init__.py`
- Test: `tests/controls/test_progress.py`

**Interfaces:**
- Consumes: semantic, state, evidence hashes and a normalized outcome.
- Produces: `ActionOutcomeStatus`, `NoProgressConfig`, `NoProgressSignal`, and `NoProgressDetector`.

- [ ] **Step 1: Write the failing tests**

```python
def test_unknown_completion_is_not_enforcement_eligible() -> None:
    detector = NoProgressDetector(NoProgressConfig(max_same_evidence_completions=2))
    detector.observe("semantic", "state", "evidence", ActionOutcomeStatus.UNKNOWN)
    detector.observe("semantic", "state", "evidence", ActionOutcomeStatus.UNKNOWN)
    signal = detector.evaluate("semantic", "state", "evidence")
    assert signal.should_recommend_stop is True
    assert signal.enforcement_eligible is False


def test_same_successful_evidence_can_be_enforcement_eligible() -> None:
    detector = NoProgressDetector(NoProgressConfig(max_same_evidence_completions=2))
    detector.observe("semantic", "state", "evidence", ActionOutcomeStatus.SUCCESS)
    detector.observe("semantic", "state", "evidence", ActionOutcomeStatus.SUCCESS)
    assert detector.evaluate("semantic", "state", "evidence").enforcement_eligible is True
```

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest tests/controls/test_progress.py -q`  
Expected: collection fails because `marginal.controls.progress` does not exist.

- [ ] **Step 3: Add the minimal immutable model**

```python
class ActionOutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class NoProgressDetector:
    def __init__(self, config: NoProgressConfig | None = None) -> None:
        self.config = config or NoProgressConfig()
        self._observations: dict[str, tuple[str, str, ActionOutcomeStatus, int]] = {}

    def evaluate(self, semantic_key: str, state_hash: str, evidence_hash: str) -> NoProgressSignal:
        previous = self._observations.get(semantic_key)
        matches = previous is not None and previous[:2] == (state_hash, evidence_hash)
        count = previous[3] if matches else 0
        outcome = previous[2] if matches else ActionOutcomeStatus.UNKNOWN
        return NoProgressSignal(
            semantic_key=semantic_key,
            same_evidence_completions=count,
            should_recommend_stop=count >= self.config.max_same_evidence_completions,
            enforcement_eligible=(
                count >= self.config.max_same_evidence_completions
                and outcome is ActionOutcomeStatus.SUCCESS
            ),
        )

    def observe(
        self, semantic_key: str, state_hash: str, evidence_hash: str, outcome: ActionOutcomeStatus
    ) -> None:
        previous = self._observations.get(semantic_key)
        count = (
            previous[3] + 1
            if previous is not None and previous[:2] == (state_hash, evidence_hash)
            else 1
        )
        self._observations[semantic_key] = (state_hash, evidence_hash, outcome, count)
```

Missing hashes fail open. Failure and unknown outcomes may recommend in Shadow Mode but never become enforcement-eligible. This detector remains separate from successful-action diminishing returns.

- [ ] **Step 4: Verify GREEN and commit**

```bash
.venv/bin/python -m pytest tests/controls/test_progress.py tests/controls/test_diminishing.py -q
git add src/marginal/controls tests/controls/test_progress.py
git commit -m "feat: add provider-neutral no-progress evidence control"
```

### Task 2: Strict Codex events, normalization, and state hashing

**Files:**
- Create: `src/marginal/integrations/__init__.py`
- Create: `src/marginal/integrations/codex/__init__.py`
- Create: `src/marginal/integrations/codex/events.py`
- Create: `src/marginal/integrations/codex/normalization.py`
- Create: `src/marginal/integrations/codex/state.py`
- Test: `tests/integrations/codex/test_events.py`
- Test: `tests/integrations/codex/test_normalization.py`
- Test: `tests/integrations/codex/test_state.py`

**Interfaces:**
- Consumes: official hook JSON.
- Produces: typed hook events, official output builders, redacted `AgentAction`, and `workspace_state_hash`.

- [ ] **Step 1: Write failing event tests**

```python
def test_pre_tool_event_requires_tool_identity() -> None:
    with pytest.raises(ValueError, match="tool_use_id"):
        parse_hook_event({"hook_event_name": "PreToolUse", "session_id": "s"})


def test_denial_uses_official_shape() -> None:
    assert (
        build_pre_tool_output(False, "No progress", "NO_PROGRESS")["hookSpecificOutput"][
            "permissionDecision"
        ]
        == "deny"
    )
```

- [ ] **Step 2: Verify RED, implement events, verify GREEN**

Run before code: `.venv/bin/python -m pytest tests/integrations/codex/test_events.py -q`  
Expected: missing integration package. Use frozen dataclasses, exact event names, non-empty identifiers, and no transcript parsing.

- [ ] **Step 3: Write failing normalization/state tests**

```python
def test_normalization_never_persists_raw_command() -> None:
    action = normalize_pre_tool_use(pre_event(command="echo secret"), state_hash="state")
    assert "echo secret" not in json.dumps(action.to_dict())
    assert action.metadata["semantic_key"]


def test_state_hash_ignores_runtime_data(tmp_path: Path) -> None:
    before = workspace_state_hash(tmp_path)
    (tmp_path / ".marginal").mkdir()
    (tmp_path / ".marginal" / "runtime.json").write_text("changed")
    assert workspace_state_hash(tmp_path) == before
```

- [ ] **Step 4: Verify RED, implement, verify GREEN, and commit**

```bash
.venv/bin/python -m pytest tests/integrations/codex/test_normalization.py tests/integrations/codex/test_state.py -q
# Add minimal canonical SHA-256 normalization and explicit workspace exclusions.
.venv/bin/python -m pytest tests/integrations/codex/test_events.py tests/integrations/codex/test_normalization.py tests/integrations/codex/test_state.py -q
git add src/marginal/integrations tests/integrations/codex
git commit -m "feat: add strict redacted Codex hook contracts"
```

### Task 3: Conservative outcome classification and runtime settlement

**Files:**
- Create: `src/marginal/integrations/codex/outcomes.py`
- Create: `src/marginal/integrations/codex/runtime.py`
- Test: `tests/integrations/codex/test_outcomes.py`
- Test: `tests/integrations/codex/test_runtime.py`

**Interfaces:**
- Produces: `classify_tool_outcome(event) -> ActionOutcomeStatus` and `CodexSessionRuntime.pre_tool_use`, `.post_tool_use`, `.close`.

- [ ] **Step 1: Write failing classifier tests**

```python
def test_model_facing_shell_prose_remains_unknown() -> None:
    assert (
        classify_tool_outcome(post_event(response="Process exited with code 0"))
        is ActionOutcomeStatus.UNKNOWN
    )


def test_structured_exit_status_is_classified() -> None:
    assert (
        classify_tool_outcome(post_event(response={"exit_code": 0})) is ActionOutcomeStatus.SUCCESS
    )
    assert (
        classify_tool_outcome(post_event(response={"exit_code": 7})) is ActionOutcomeStatus.FAILURE
    )
```

- [ ] **Step 2: Verify RED, implement the allowlisted classifier, verify GREEN**

Run: `.venv/bin/python -m pytest tests/integrations/codex/test_outcomes.py -q`  
Expected before code: missing module. Undocumented prose must remain unknown.

- [ ] **Step 3: Write failing lifecycle tests**

```python
def test_unknown_post_does_not_advance_success_history(tmp_path: Path) -> None:
    runtime = runtime_for(tmp_path)
    runtime.pre_tool_use(pre_event("call-1"))
    runtime.post_tool_use(post_event("call-1", response="red test"))
    assert runtime.summary()["successful_observations"] == 0


def test_identity_mismatch_keeps_original_pending(tmp_path: Path) -> None:
    runtime = runtime_for(tmp_path)
    runtime.pre_tool_use(pre_event("call-1"))
    with pytest.raises(CodexIntegrationError, match="identity"):
        runtime.post_tool_use(post_event("call-2", response={"exit_code": 0}))
    assert runtime.pending_action_ids() == ("call-1",)
```

- [ ] **Step 4: Verify RED, implement lifecycle, verify GREEN, and commit**

Unknown aborts without successful observation and records a separate no-progress completion. Failure uses `fail_action`; success uses `after_action`.

```bash
.venv/bin/python -m pytest tests/integrations/codex/test_runtime.py -q
git add src/marginal/integrations/codex tests/integrations/codex
git commit -m "feat: settle Codex outcomes without guessing success"
```

### Task 4: Hash-only evidence and Earned Enforcement receipts

**Files:**
- Create: `src/marginal/integrations/codex/evidence.py`
- Create: `src/marginal/integrations/codex/promotion.py`
- Test: `tests/integrations/codex/test_evidence.py`
- Test: `tests/integrations/codex/test_promotion.py`

**Interfaces:**
- Produces: `EvidenceStore`, `CoverageSummary`, `PromotionCriteria`, `PromotionReceipt`, and `evaluate_promotion`.

- [ ] **Step 1: Write failing evidence tests**

```python
def test_store_rejects_raw_payload_fields(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="forbidden evidence field"):
        EvidenceStore(tmp_path).append({"event": "decision", "tool_input": {"command": "secret"}})


def test_store_round_trip_is_canonical(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    store.append(redacted_decision())
    assert store.read_all() == [redacted_decision()]
```

- [ ] **Step 2: Verify RED, implement strict storage, verify GREEN**

Use an allowlist, canonical JSONL, bounded records, atomic JSON checkpoints, and private modes.

- [ ] **Step 3: Write failing promotion tests**

```python
def test_default_gate_requires_minimum_actions() -> None:
    receipt = evaluate_promotion(summary(covered=99, coverable=100), PromotionCriteria())
    assert receipt.is_ready is False
    assert "MINIMUM_ACTIONS" in receipt.blocking_reasons


def test_policy_change_invalidates_ready_receipt() -> None:
    assert ready_receipt(policy_hash="old").valid_for(identity(policy_hash="new")) is False
```

- [ ] **Step 4: Verify RED, implement exact thresholds, verify GREEN, and commit**

Thresholds: 100 actions, five sessions, 99% coverage, five reviewed candidates, zero false stops, zero failures/pending, p95 at most 75 ms, unchanged identity, observable enforceable outcomes.

```bash
.venv/bin/python -m pytest tests/integrations/codex/test_evidence.py tests/integrations/codex/test_promotion.py -q
git add src/marginal/integrations/codex tests/integrations/codex
git commit -m "feat: add evidence-gated Codex promotion receipts"
```

### Task 5: Authenticated per-session service

**Files:**
- Create: `src/marginal/integrations/codex/transport.py`
- Create: `src/marginal/integrations/codex/service.py`
- Test: `tests/integrations/codex/test_transport.py`
- Test: `tests/integrations/codex/test_service.py`

**Interfaces:**
- Produces: `ConnectionInfo`, `start_session_service`, `request_session`, `stop_session_service`, and `run_hook`.

- [ ] **Step 1: Write failing transport tests**

```python
def test_wrong_token_is_rejected(tmp_path: Path) -> None:
    with running_server(tmp_path, token="expected") as server:
        response = send(server, token="wrong", operation="status", payload={})
    assert response["error_code"] == "AUTH_FAILED"


def test_oversized_request_is_rejected(tmp_path: Path) -> None:
    with running_server(tmp_path) as server:
        response = send_bytes(server, b"x" * (MAX_MESSAGE_BYTES + 1))
    assert response["error_code"] == "MESSAGE_TOO_LARGE"
```

- [ ] **Step 2: Verify RED, implement bounded loopback transport, verify GREEN**

Bind literal `127.0.0.1`, select an ephemeral port, compare a 256-bit token with `hmac.compare_digest`, accept one bounded JSON line, and never echo payloads in errors.

- [ ] **Step 3: Write failing service tests**

```python
def test_start_is_idempotent_and_end_removes_credentials(tmp_path: Path) -> None:
    first = start_session_service(session_event(), data_root=tmp_path)
    assert start_session_service(session_event(), data_root=tmp_path) == first
    stop_session_service("session-1", data_root=tmp_path)
    assert not first.connection_file.exists()


def test_missing_service_fails_open_and_demotes(tmp_path: Path) -> None:
    configure_enforcement(tmp_path)
    result = run_hook_without_service(pre_event(), data_root=tmp_path)
    assert result.exit_code == 0
    assert read_mode(tmp_path) == "shadow"
```

- [ ] **Step 4: Verify RED, implement service lifecycle, verify GREEN, and commit**

```bash
.venv/bin/python -m pytest tests/integrations/codex/test_transport.py tests/integrations/codex/test_service.py -q
git add src/marginal/integrations/codex tests/integrations/codex
git commit -m "feat: run Codex governance in an authenticated local service"
```

### Task 6: Installer and management CLI

**Files:**
- Create: `src/marginal/integrations/codex/installer.py`
- Create: `src/marginal/integrations/codex/commands.py`
- Modify: `src/marginal/cli.py`
- Test: `tests/integrations/codex/test_installer.py`
- Test: `tests/integrations/codex/test_commands.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `CodexInstallation`, `CodexDoctorReport`, `inspect_codex`, `plan_install`, `install`, `uninstall`, and CLI exit codes 0/1/2.

- [ ] **Step 1: Write failing discovery tests**

```python
def test_discovery_never_reads_auth() -> None:
    runner = RecordingRunner(version="codex-cli 0.147.0", hooks=True, plugins=True)
    report = inspect_codex(runner=runner)
    assert report.capability_level == "tool_enforcement"
    assert all("auth.json" not in " ".join(call) for call in runner.calls)


def test_missing_hooks_refuses_enforcement_claim() -> None:
    assert inspect_codex(runner=RecordingRunner(hooks=False)).capability_level == "observe"
```

- [ ] **Step 2: Verify RED, implement read-only discovery, verify GREEN**

Subprocesses use argument arrays, an environment allowlist, bounded output, timeout, and no shell.

- [ ] **Step 3: Write failing mutation/CLI tests**

```python
def test_install_uses_codex_plugin_commands() -> None:
    runner = RecordingRunner()
    install(runner=runner, repository="SignalLayerLabs/Marginal", ref="main")
    assert ["codex", "plugin", "add", "marginal@marginal", "--json"] in runner.calls


def test_unready_promotion_returns_two() -> None:
    assert main(["codex", "promote", "--data-dir", str(fixture_data)]) == 2
```

- [ ] **Step 4: Verify RED, add exact CLI grammar, verify GREEN, and commit**

Grammar: `marginal install codex`, `marginal uninstall codex`, and `marginal codex status|doctor|review|promote|demote`. Normal uninstall preserves data; purge requires explicit `--purge-data --yes`.

```bash
.venv/bin/python -m pytest tests/integrations/codex/test_installer.py tests/integrations/codex/test_commands.py tests/test_cli.py -q
git add src/marginal/cli.py src/marginal/integrations/codex tests/integrations/codex tests/test_cli.py
git commit -m "feat: add reversible Codex integration commands"
```

### Task 7: Scaffold and build the native plugin marketplace

**Files:**
- Create via scaffold: `.agents/plugins/marketplace.json`
- Create via scaffold: `plugins/marginal/.codex-plugin/plugin.json`
- Create via scaffold: `plugins/marginal/hooks/hooks.json`
- Create via scaffold: `plugins/marginal/skills/marginal/SKILL.md`
- Create: `plugins/marginal/scripts/marginal_hook.py`
- Create generated: `plugins/marginal/runtime/marginal_runtime.pyz`
- Create generated: `plugins/marginal/runtime/provenance.json`
- Create: `scripts/build_codex_plugin.py`
- Test: `tests/plugin/test_codex_plugin.py`

**Interfaces:**
- Produces: a plugin accepted by the Codex validator and marketplace selector `marginal@marginal`.

- [ ] **Step 1: Run the official scaffold**

```bash
python3 /Users/renatovinai/.codex/skills/.system/plugin-creator/scripts/create_basic_plugin.py marginal \
  --path . \
  --marketplace-path .agents/plugins/marketplace.json \
  --with-skills --with-hooks --with-scripts --with-assets --with-marketplace
```

Use a recoverable move to place the generated directory under `plugins/marginal`; regenerate the repo marketplace so its source is exactly `./plugins/marginal`.

- [ ] **Step 2: Write failing bundle tests**

```python
def test_marketplace_points_to_valid_plugin() -> None:
    marketplace = json.loads((REPO / ".agents/plugins/marketplace.json").read_text())
    assert marketplace["name"] == "marginal"
    assert marketplace["plugins"][0]["source"]["path"] == "./plugins/marginal"


def test_generated_runtime_matches_provenance(tmp_path: Path) -> None:
    rebuilt = build_plugin_runtime(REPO, output_dir=tmp_path)
    assert sha256(rebuilt.zipapp) == committed_provenance()["sha256"]
```

- [ ] **Step 3: Verify RED, implement deterministic builder, verify GREEN**

Run before builder: `.venv/bin/python -m pytest tests/plugin/test_codex_plugin.py -q`.  
Expected: missing build module/runtime. The zipapp entry point calls `marginal.integrations.codex.service:hook_main`; sorted archive paths, normalized timestamps, canonical provenance, and source hashes make the output reproducible.

- [ ] **Step 4: Configure official hooks**

`hooks/hooks.json` covers `SessionStart`, `PreToolUse`, `PostToolUse`, and `SessionEnd`. Commands use `$PLUGIN_ROOT`, `$PLUGIN_DATA`, `commandWindows`, synchronous execution, and bounded timeouts. The manifest contains no unsupported fields; default hook discovery finds the hook file.

- [ ] **Step 5: Validate and commit**

```bash
.venv/bin/python scripts/build_codex_plugin.py --check
python3 /Users/renatovinai/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/marginal
.venv/bin/python -m pytest tests/plugin/test_codex_plugin.py -q
git add .agents plugins scripts/build_codex_plugin.py tests/plugin
git commit -m "feat: package MARGINAL as a native Codex plugin"
```

### Task 8: Isolated marketplace install and removal smoke

**Files:**
- Create: `tests/integrations/codex/test_marketplace_smoke.py`
- Create: `scripts/smoke_codex_plugin.py`
- Modify: the canonical workflow under `.github/workflows/`

**Interfaces:**
- Consumes: a real Codex CLI and temporary `HOME`/`CODEX_HOME`.
- Produces: redacted install, lifecycle, coverage, and removal evidence.

- [ ] **Step 1: Write the failing smoke test**

```python
def test_marketplace_install_and_remove(tmp_path: Path) -> None:
    result = smoke_plugin(codex=find_codex(), codex_home=tmp_path, marketplace=REPO)
    assert result.installed is True
    assert result.shadow_block_count == 0
    assert result.hook_coverage == 1.0
    assert result.raw_secret_occurrences == 0
    assert result.removed is True
```

- [ ] **Step 2: Verify RED, implement isolated smoke, verify GREEN**

Run: `.venv/bin/python -m pytest tests/integrations/codex/test_marketplace_smoke.py -q`.  
The helper adds the local marketplace, installs the plugin, invokes captured official hook fixtures directly, removes the plugin, and never reads the real Codex home. Trust remains a separate manual live step.

- [ ] **Step 3: Add the non-secret CI gate and commit**

CI validates the plugin, checks generated runtime, installs/removes against temporary homes, and exercises direct hook lifecycle without model credentials.

```bash
git add tests/integrations/codex/test_marketplace_smoke.py scripts/smoke_codex_plugin.py .github/workflows
git commit -m "test: verify Codex plugin install lifecycle"
```

### Task 9: Documentation, legal pages, and submission packet

**Files:**
- Create: `docs/integrations/codex.md`
- Create: `docs/operations/codex-plugin-submission.md`
- Create: `docs/operations/codex-plugin-test-cases.json`
- Create: `PRIVACY.md`
- Create: `TERMS.md`
- Modify: `SUPPORT.md`, `README.md`, `ROADMAP.md`, `CHANGELOG.md`, `docs/index.md`, `docs/integrations/overview.md`
- Modify: `site/index.html`, `site/styles.css`, `site/sitemap.xml`
- Test: `tests/plugin/test_publication_packet.py`
- Modify: `tests/evaluation/test_public_benchmark_surface.py`

**Interfaces:**
- Produces: public install/remove UX, truthful capability language, and five positive plus three negative reviewer cases.

- [ ] **Step 1: Write failing public-surface tests**

```python
def test_readme_and_site_publish_install_remove() -> None:
    for path in (REPO / "README.md", REPO / "site/index.html"):
        text = path.read_text()
        assert "codex plugin marketplace add SignalLayerLabs/Marginal" in text
        assert "codex plugin remove marginal@marginal" in text
        assert "Tool Enforcement" in text


def test_submission_packet_has_required_cases() -> None:
    packet = json.loads(TEST_CASES.read_text())
    assert len(packet["positive"]) >= 5
    assert len(packet["negative"]) >= 3
```

- [ ] **Step 2: Verify RED, write exact content, verify GREEN**

Run: `.venv/bin/python -m pytest tests/plugin/test_publication_packet.py tests/evaluation/test_public_benchmark_surface.py -q`.  
README/site lead with install and Earned Enforcement while retaining the benchmark pass-through limitation. Submission status is one of `not_submitted`, `submitted`, `in_review`, `approved`, or `published` with ISO date.

- [ ] **Step 3: Validate and commit**

```bash
.venv/bin/python scripts/validate_readme_pages.py
git add README.md ROADMAP.md CHANGELOG.md PRIVACY.md TERMS.md SUPPORT.md docs site tests
git commit -m "docs: launch the Codex plugin and earned enforcement"
```

### Task 10: Full quality, security, package, and live gates

**Files:**
- Create: `docs/operations/evidence/codex-plugin-smoke-2026-08-13.json`
- Modify only code whose failure is reproduced by a new failing test.

**Interfaces:**
- Produces: a release-ready tree and redacted live evidence.

- [ ] **Step 1: Run all automated gates**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src/marginal
.venv/bin/python -m build
.venv/bin/twine check dist/*
.venv/bin/python scripts/build_codex_plugin.py --check
python3 /Users/renatovinai/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/marginal
git diff --check
```

Expected: every command exits 0 with no MARGINAL warnings.

- [ ] **Step 2: Run security/privacy assertions**

Search plugin, evidence, docs, and diff for credential patterns and a smoke secret marker. Assert that persisted evidence contains none, runtime networking targets literal loopback only, and no auth-file access exists.

- [ ] **Step 3: Run live Codex acceptance**

Install in an isolated Codex home, review hooks through supported Codex UI, run harmless shell/edit/local-function calls, verify zero Shadow denials and exact coverage, exercise one synthetic ready receipt and controlled denial, invalidate the policy hash, verify demotion, and remove the plugin. Persist hashes and redacted counters only.

- [ ] **Step 4: Re-run gates and commit evidence**

```bash
git add docs/operations/evidence tests src plugins scripts README.md ROADMAP.md CHANGELOG.md site
git commit -m "test: record verified Codex plugin acceptance"
```

### Task 11: Independent review, GitHub publication, and OpenAI submission

**Files:**
- Update: `docs/operations/codex-plugin-submission.md`
- Modify other files only after a reproduced review failure.

**Interfaces:**
- Produces: reviewed GitHub state and exact portal submission status.

- [ ] **Step 1: Review the complete diff**

Every actionable finding names file/line, consequence, and reproducing test. Fix via RED/GREEN and rerun Task 10.

- [ ] **Step 2: Push and open a ready pull request**

Include install/remove commands, capability limits, test evidence, and the external-review caveat. Merge only after green CI.

- [ ] **Step 3: Verify canonical main and Pages after merge**

Confirm main contains `.agents/plugins/marketplace.json` and `plugins/marginal`, and the public site renders install, uninstall, privacy, terms, and evidence links.

- [ ] **Step 4: Submit through OpenAI Platform**

Use the verified SignalLayer Labs organization with Apps Management write access, upload the final bundle, public URLs, prompts, eight test cases, supported regions, and policy attestations, then submit for review.

- [ ] **Step 5: Record exact external status**

After portal acceptance record `submitted` or `in_review` with timestamp and non-secret identifier. Record `published` only after OpenAI approval and publisher release.

---

## Plan self-review

- Spec coverage: all design sections map to Tasks 1–11; external approval is separate from implementation completion.
- Placeholder scan: every task names exact files, interfaces, RED/GREEN commands, and commit boundaries.
- Type consistency: outcome, progress, event, runtime, evidence, receipt, transport, installer, and CLI names are introduced once and reused.
- Dependency direction: benchmark may consume stable production contracts; production never imports benchmark code.
