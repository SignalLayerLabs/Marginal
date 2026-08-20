# Privacy-Preserving Model-Specific Shared Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the optional, privacy-safe, model-specific Commons learning loop across Ingress,
Commons, and MARGINAL while preserving local-only Shadow Mode and local enforcement authority.

**Architecture:** A closed-schema Worker validates and serializes aggregate GitHub updates; a
public Commons repository deterministically compiles aggregate knowledge; the zero-dependency
MARGINAL client finalizes local evidence, compiles bounded atoms, retries a durable outbox, and
loads verified model-specific priors.

**Tech Stack:** Python 3.10+ stdlib and pytest/Ruff/mypy; TypeScript, Vitest, Wrangler 4, Cloudflare
Durable Objects; GitHub Contents API; JSON Schema 2020-12.

**Spec:** `docs/superpowers/specs/2026-08-20-privacy-preserving-model-specific-shared-evidence-design.md`

## Global Constraints

- Default is `local_only`; existing installations are never opted into network behavior.
- Unknown fields and arbitrary strings are rejected recursively at the Commons boundary.
- No raw context, local pseudonym, persistent client ID, contributor identity, or exact timestamp.
- Commons never contributes to local promotion, trust, coverage, or enforcement counters.
- Network and shared-state failures fail open and cannot block Codex.
- MARGINAL core keeps zero mandatory runtime dependencies.
- Historical benchmark artifacts and claims remain unchanged.
- No production deployment claim without verified credentials and endpoint probe.

---

### Task 1: Freeze the cross-repository contract

**Files:**
- Create in all repositories: `schemas/commons-evidence-envelope-v1.json`
- Create in Commons and MARGINAL: `schemas/commons-pack-v1.json`
- Create in Commons and MARGINAL: `models/canonical-model-registry-v1.json`
- Test: schema/privacy tests in each repository

**Interfaces:**
- Produces: exact `schema_version="1.0"`, registry-issued `model_namespace`, and `atoms` with
  closed aggregate dimensions; retry identity is a separate base64url `Idempotency-Key` header.
- Consumes: reviewed aggregate-export action/reason/outcome enums.

- [ ] Write schema tests that reject direct/nested unknown fields, canaries, URLs, paths, hashes,
  arbitrary model strings, invalid enums, invalid retry headers, oversized counts, and empty atoms.
- [ ] Run those tests and record RED because the schemas/registry do not exist.
- [ ] Add recursively closed schemas and exact registry entries documented by official sources.
- [ ] Mirror schema bytes where repositories consume the same contract and test equality.
- [ ] Run focused tests and commit the contract separately in each repository.

### Task 2: Implement Marginal-Ingress

**Files:**
- Create: `src/index.ts`, `src/schema.ts`, `src/github-sink.ts`, `src/coordinator.ts`
- Create: `wrangler.jsonc`, `package.json`, `package-lock.json`, `tsconfig.json`
- Create: `test/*.test.ts`, `.github/workflows/ci.yml`
- Create: `README.md`, `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `docs/*.md`

**Interfaces:**
- Consumes: `CommonsEvidenceEnvelopeV1` from Task 1.
- Produces: `{accepted:true, duplicate:boolean}` ACK without evidence echo; GitHub aggregate update.

- [ ] Write Vitest RED cases for health, content type, malformed/oversized JSON, recursive unknown
  fields, unsafe models/free text, no echo/logging, sink failure, and duplicate retry.
- [ ] Implement a dependency-minimal strict parser whose output type contains only allowed fields.
- [ ] Implement `GET /healthz` and `POST /v1/evidence`; never inspect `request.cf`, headers beyond
  Content-Type/length, or request-specific logging.
- [ ] Implement one Durable Object coordinator with strong serialized state. Store only SHA-256
  idempotency digests with expiry and a pending target/blob descriptor; reconcile uncertain writes.
- [ ] Implement GitHub Contents reads/writes using blob SHA, bounded 409 retry, fixed repository,
  fixed committer, no contributor data, and no envelope persistence.
- [ ] Set `observability.enabled=false` and `observability.logs.invocation_logs=false`; add a static
  test that fails on any production logging enablement or request-specific console call.
- [ ] Add Apache-2.0 docs, threat/privacy model, synthetic request/rejection, lockfile, and least-
  privilege service credential instructions.
- [ ] Run `npm ci`, format, lint, typecheck, Vitest, and `wrangler deploy --dry-run`; commit.

### Task 3: Implement Marginal-Commons

**Files:**
- Create: `models/registry-v1.json`, `models/<namespace>/aggregates.json`
- Create: `validation/schema.py`, `validation/lifecycle.py`
- Create: `tooling/build_pack.py`, `tooling/validate_commons.py`
- Create: `dist/commons-pack-v1.json`, `tests/*`, `.github/workflows/ci.yml`
- Create: `README.md`, `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `docs/*.md`, `pyproject.toml`

**Interfaces:**
- Consumes: aggregate files written by Ingress.
- Produces: canonical `dist/commons-pack-v1.json` with compatibility, revision, source commit,
  models, and digest.

- [ ] Write RED tests for schema closure, registry isolation, first registered namespace,
  aggregate invariants, lifecycle gates, poisoning volume, deterministic bytes, and digest checks.
- [ ] Implement strict stdlib validators and canonical JSON serialization.
- [ ] Implement `candidate → supported → validated → promoted` advancement only from checked-in
  validation artifacts; counts never advance status.
- [ ] Implement deterministic pack compilation and rebuild/diff validation.
- [ ] Add docs stating observations are not users and every Commons state is only a prior.
- [ ] Run format, Ruff, mypy, pytest, validation, and deterministic rebuild; commit.

### Task 4: Add MARGINAL Commons configuration, identity, and compiler

**Files:**
- Create: `src/marginal/commons/{__init__,config,identity,evidence}.py`
- Create/mirror: `src/marginal/schemas/commons-*.json`, root `schemas/commons-*.json`
- Modify: `src/marginal/integrations/codex/installer.py`, `src/marginal/cli.py`
- Test: `tests/commons/test_config.py`, `test_identity.py`, `test_evidence.py`

**Interfaces:**
- Produces: `CommonsMode`, `CommonsConfig`, `CanonicalModelIdentity | None`, immutable
  `CommonsEvidenceAtom` and `compile_verified_evidence(...)`.
- Consumes: only exact registry model strings and verified local evidence records.

- [ ] Write RED tests for Local Only default, explicit persistent choice, owner-only atomic config,
  exact public registry match, unknown/private/fine-tune rejection, version isolation, conflicting
  model attribution, and canary-free serialized atoms.
- [ ] Implement configuration in the existing owner-only `user-config.json` contract without
  changing existing Autopilot consent.
- [ ] Implement exact, case-sensitive, registry-backed model resolution; never normalize arbitrary
  model strings.
- [ ] Extend safe local action evidence with bounded `action_kind`, applied recommendation, outcome,
  and resolved safe model namespace; keep all local hashes out of compiler output.
- [ ] Implement closed compiler construction from typed fields, not arbitrary caller mappings.
- [ ] Run focused tests, schema mirror tests, Ruff, and mypy; commit.

### Task 5: Add cache, outbox, and bounded client

**Files:**
- Create: `src/marginal/commons/{cache,outbox,client,sync}.py`
- Test: `tests/commons/test_cache.py`, `test_outbox.py`, `test_client.py`, `test_sync.py`

**Interfaces:**
- Produces: `CommonsCache.refresh/load_prior`, `CommonsOutbox.enqueue/ack/quarantine`,
  `CommonsClient.download/submit`, and fail-open lifecycle results.
- Consumes: Task 1 pack/envelope schemas and Task 4 config/atoms.

- [ ] Write RED tests for malformed/incompatible/digest-invalid packs, previous-cache fallback,
  symlink/path rejection, 0600 atomic queue files, restart retry, 2xx ACK deletion, 4xx quarantine,
  5xx/timeout retention, and zero calls for local/read-only/no-evidence modes.
- [ ] Implement no-follow owner-only safe file operations following GovernanceLedger conventions.
- [ ] Implement a stdlib HTTP client with fixed endpoint paths, no tracking parameters, bounded
  connect/read timeout, bounded response size, and no request-body logging.
- [ ] Implement exact outbox ACK/quarantine/retry state transitions.
- [ ] Run focused tests, Ruff, and mypy; commit.

### Task 6: Integrate SessionStart/SessionEnd without authority escalation

**Files:**
- Modify: `src/marginal/integrations/codex/service.py`, `events.py`, `evidence.py`, `runtime.py`
- Modify: `src/marginal/diagnostics.py`, plugin control surface as required
- Test: `tests/integrations/codex/test_service.py`, `tests/commons/test_enforcement.py`,
  `tests/test_diagnostics.py`

**Interfaces:**
- SessionStart: retry valid outbox, refresh/cache pack, load same-model prior, continue locally.
- SessionEnd: close runtime, append authoritative end, atomically finalize memory, compile, enqueue,
  bounded sync, shutdown; all shared failures return success/fail-open.

- [ ] Write RED lifecycle tests for finalization in all modes, offline queue/retry, ambiguous model
  no-upload, same-model prior visibility, model isolation, and network failure fail-open.
- [ ] Implement idempotent finalization checkpoint bound to verified local ledger root/record count.
- [ ] Add Commons orchestration after local finalization and outside promotion/Autopilot inputs.
- [ ] Prove candidate/supported/validated/promoted packs independently leave enforcement disabled
  and local evidence overrides conflicting Commons priors.
- [ ] Extend privacy inspection with mode, endpoint, safe namespace, queue count, last sync, cache
  revision, and schema version; never expose a remote identity.
- [ ] Run lifecycle, diagnostics, authority, promotion, and privacy suites; commit.

### Task 7: Documentation, plugin runtime, and local dogfood installation

**Files:**
- Modify: `README.md`, `PRIVACY.md`, `CHANGELOG.md`, `docs/operations/privacy.md`,
  `docs/product/architecture.md`, `docs/integrations/codex.md`,
  `docs/getting-started/quickstart.md`, plugin skill/manifest docs as needed
- Regenerate: `plugins/marginal/runtime/marginal_runtime.pyz`, `provenance.json`

- [ ] Document Local Only default, Read-Only downloads, Contributor closed-schema upload, Cloudflare
  infrastructure limitation, no persistent identity, and no enforcement authority.
- [ ] Remove only statements made inaccurate by optional Contributor mode; make no compliance,
  anonymity, performance, or deployment claims.
- [ ] Rebuild runtime and verify provenance determinism.
- [ ] Reinstall/update the local plugin through the real Codex flow, preserve evidence, and verify
  status/doctor/privacy plus effective Shadow Mode.
- [ ] Run documentation/publication/plugin tests and commit.

### Task 8: End-to-end security verification and publication

**Files:**
- Create synthetic E2E fixtures/tests in the appropriate repositories.
- Update this plan's SDD ledger and final reports.

- [ ] Run synthetic SessionStart → SessionEnd → outbox → local Ingress → Commons aggregate → pack
  → fresh SessionStart and assert same-model prior visibility.
- [ ] Assert another model sees nothing, no canary reaches envelope/Ingress/Commons, and Commons
  never enables enforcement.
- [ ] Perform hostile review of all fifteen mandate questions and fix violations.
- [ ] Run all MARGINAL contributor gates, Ingress gates/dry-run, Commons gates/build, plugin
  provenance, privacy/model/retry/poisoning tests, and E2E from clean trees.
- [ ] Create/publicize absent GitHub repositories, push focused commits, open non-draft PRs where
  appropriate, wait for green CI, and merge only green changes already authorized by the mandate.
- [ ] Attempt production Worker deployment only with verified Wrangler auth and a dedicated
  least-privilege Commons service credential; otherwise report that exact external blocker.
