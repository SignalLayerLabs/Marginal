# Privacy Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add explicit privacy profiles that protect quasi-identifiers and free-text fields in Decision Ledger telemetry, while providing a separate aggregate-only export suitable for sharing.

**Architecture:** Introduce a provider-neutral privacy module with field classifications, keyed local pseudonymization, strict safe-telemetry sanitization, and aggregate record generation. Integrate profiles at the Decision Ledger boundary so all Treasury events are protected consistently. Keep operational local ledgers and aggregate exports separate, expose both through the public API and CLI, and package versioned JSON schemas.

**Tech Stack:** Python 3.10+, standard library only (`enum`, `dataclasses`, `hashlib`, `hmac`, `secrets`, `json`, `pathlib`), pytest, existing JSON Schema test suite.

## Global Constraints

- Preserve zero mandatory runtime dependencies.
- Default behavior remains backward-compatible `local_full`.
- `safe_telemetry` must remove free text and metadata, pseudonymize identifiers with HMAC-SHA-256, and generalize exact timestamps.
- Pseudonymization keys are local, never written into ledger records, and created with restrictive permissions when generated automatically.
- `aggregate_export` must not be usable as an operational Decision Ledger profile; it is a separate export path with grouped generalized rows, no identifiers or timestamps, and default suppression for groups smaller than five records.
- Public schemas, CLI help, API docs, security documentation, roadmap, changelog, examples, and README must agree with runtime behavior.
- No claim that pseudonymization is anonymization.

---

## Execution status

Tasks 1–5 have been implemented with test-first coverage. Task 6 is complete for all checks available in the isolated build environment; Ruff, mypy, and Twine remain mandatory pre-commit/CI gates because their executables could not be installed without network access.

### Task 1: Define privacy contracts and sanitization

**Files:**
- Create: `src/marginal/privacy.py`
- Create: `tests/test_privacy.py`

**Interfaces:**
- Produces: `PrivacyProfile`, `PrivacyClass`, `PrivacyConfig`, `LocalPseudonymizer`, `sanitize_ledger_record`, `aggregate_ledger_records`, `load_or_create_privacy_key`.

- [x] Write failing tests for profile parsing, deterministic keyed pseudonymization, key separation, strict sensitive-field removal, timestamp generalization, and aggregate grouping.
- [x] Run `python -m pytest tests/test_privacy.py -q` and verify failures are caused by the missing module/API.
- [x] Implement the minimal privacy module.
- [x] Run the privacy tests and refactor while green.

### Task 2: Integrate privacy at the Decision Ledger boundary

**Files:**
- Modify: `src/marginal/ledger.py`
- Modify: `tests/test_decision_ledger.py`

**Interfaces:**
- `JsonlDecisionLedger(..., privacy_profile=..., privacy_key=..., privacy_key_path=...)`
- Every record includes `privacy_profile`.
- `safe_telemetry` applies before JSON serialization.

- [x] Write failing ledger tests for local-full preservation, safe telemetry sanitization, consistent context/outcome pseudonyms, key-file creation, reserved-field protection, and aggregate-profile rejection.
- [x] Run focused tests and verify RED.
- [x] Implement profile integration and reader validation.
- [x] Run focused tests and full regression tests.

### Task 3: Add aggregate export API and CLI

**Files:**
- Modify: `src/marginal/ledger.py`
- Modify: `src/marginal/cli.py`
- Modify: `src/marginal/__init__.py`
- Create or modify: `tests/test_cli_v2.py`, `tests/test_public_api_v2.py`

**Interfaces:**
- `export_decision_ledger(source, destination, *, privacy_profile, privacy_key=None, privacy_key_path=None)`
- CLI: `marginal ledger-export SOURCE DESTINATION --privacy-profile safe_telemetry|aggregate_export [--privacy-key-file PATH] [--minimum-group-size N]`

- [x] Write failing API and CLI tests.
- [x] Verify RED.
- [x] Implement export and CLI behavior with overwrite protection.
- [x] Verify GREEN and regression compatibility.

### Task 4: Publish schemas and package resources

**Files:**
- Modify: `schemas/decision-ledger-v2.json`
- Modify: `src/marginal/schemas/decision-ledger-v2.json`
- Create: `schemas/aggregate-export-v1.json`
- Create: `src/marginal/schemas/aggregate-export-v1.json`
- Modify: schema tests.

**Interfaces:**
- Decision ledger schema documents `privacy_profile`.
- Aggregate export schema validates grouped generalized records.

- [x] Write failing packaged-schema and conformance tests.
- [x] Verify RED.
- [x] Add synchronized schemas.
- [x] Verify package API and JSON Schema validation.

### Task 5: Align the full project ecosystem

**Files:**
- Modify: `README.md`, `SECURITY.md`, `CHANGELOG.md`, `ROADMAP.md`
- Modify: `docs/api.md`, `docs/concepts.md`, `docs/learning-loop.md`, `docs/universal-runtime.md`, `docs/architecture.md`, `docs/quickstart.md`, `docs/faq.md`, `docs/index.md`
- Create: `docs/privacy.md`
- Create: `examples/privacy_profiles.py`
- Modify: repository consistency tests.

**Interfaces:**
- One consistent description of field classes and three profiles.
- Clear statement that pseudonymization does not equal anonymization.
- Operational ledger and aggregate export are explicitly separate.

- [x] Add failing consistency assertions for privacy documentation, public API references, and schema presence.
- [x] Verify RED.
- [x] Update all documentation and examples.
- [x] Verify GREEN and scan for contradictory privacy claims.

### Task 6: Final verification and delivery

**Files:**
- Verify entire repository.
- Create clean ZIP, SHA-256 file, verification report, and Visual Studio commit/push prompt.

- [x] Run pytest, compileall, lint/type/build tools when available, wheel/sdist build, clean-venv install, packaged schema checks, examples, CLI smoke tests, link checks, secret scans, and archive integrity checks.

  Local note: pytest, compileall, build, clean-wheel install, schema, example, CLI, link, secret, and archive checks passed. Ruff, mypy, and Twine are still required in Visual Studio/CI because those executables were unavailable in the offline container.
- [x] Remove caches, build products, temporary ledgers, and local key files from the deliverable.
- [x] Generate `VERIFICATION_REPORT.md` with exact commands and results.
- [x] Generate `VISUAL_STUDIO_COMMIT_PROMPT.md` with review, test, commit, and push instructions.
- [x] Create a single clean ZIP and SHA-256 checksum.
