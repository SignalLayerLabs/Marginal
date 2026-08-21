# Signed Commons Trust Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Authenticate exact Commons pack bytes through an offline-root-certified release key before MARGINAL caches or uses model-specific priors.

**Architecture:** A stdlib-only strict Ed25519 verifier and closed trust parser sit before the existing pack parser. The client downloads a fixed pack/signature pair, the cache atomically persists one signed artifact with anti-rollback, and trusted release tooling builds from immutable Git objects and signs only after verifying the frozen public chain.

**Tech Stack:** Python 3.10+ stdlib at runtime; pytest, cryptography, jsonschema, Git, GitHub Actions, Cloudflare Wrangler 4.124.0 for tests/release tooling.

**Spec:** `docs/superpowers/specs/2026-08-21-signed-commons-trust-path-design.md`

## Global Constraints

- Keep `pyproject.toml` production `dependencies = []`.
- Never access, display, persist, or log a private signing key.
- Never import or execute Marginal-Commons code or trust its `dist/` directory.
- Keep Commons prior-only, exact-model-isolated, and fail-open at runtime.
- Do not commit, push, merge, switch branches, or modify Marginal-Commons.

---

### Task 1: Strict Ed25519 and signed-envelope verification

**Files:**
- Create: `src/marginal/commons/ed25519.py`
- Create: `src/marginal/commons/trust.py`
- Create: `src/marginal/commons/commons-root-key-v1.json`
- Test: `tests/commons/test_ed25519.py`
- Test: `tests/commons/test_trust.py`

**Interfaces:**
- Produces: `verify_ed25519(public_key: bytes, message: bytes, signature: bytes) -> bool`
- Produces: `verify_signed_pack(pack: bytes, signature: bytes) -> VerifiedCommonsPack`

- [ ] Write RFC 8032 and strict-rejection tests using literal vectors and independently generated cryptography fixtures.
- [ ] Run `pytest -q tests/commons/test_ed25519.py tests/commons/test_trust.py` and observe missing-interface failures.
- [ ] Implement strict base64url, point decoding/subgroup checks, certificate/envelope parsing, and chain verification.
- [ ] Run the targeted tests to green.

### Task 2: Signed atomic cache and fixed-path paired download

**Files:**
- Modify: `src/marginal/commons/cache.py`
- Modify: `src/marginal/commons/client.py`
- Modify: `src/marginal/commons/sync.py`
- Modify: `src/marginal/commons/__init__.py`
- Test: `tests/commons/test_cache.py`
- Test: `tests/commons/test_client.py`
- Test: `tests/commons/test_sync.py`
- Test: `tests/commons/test_local_e2e.py`

**Interfaces:**
- Consumes: `verify_signed_pack(...)`.
- Produces: `CommonsPackDownload(pack: bytes, signature: bytes)` and `CommonsCache.refresh(download)`.

- [ ] Update tests and doubles for paired downloads, legacy-cache rejection, anti-rollback, idempotence, equivocation, exact-model isolation, and fail-open submission.
- [ ] Run the targeted tests and observe API/behavior failures.
- [ ] Implement the paired client, one-object signed cache, source-commit format validation, and sync integration.
- [ ] Run the targeted tests to green.

### Task 3: Immutable-snapshot release builder

**Files:**
- Create: `scripts/build_commons_release.py`
- Test: `tests/commons/test_release_builder.py`

**Interfaces:**
- Produces: CLI accepting a Commons repository/revision and output directory; writes `commons-pack-v1.json` and `commons-pack-v1.sig.json`.

- [ ] Write behavior tests for untrusted-code non-execution, Git entry types, worktree mutation, poisoned JSON, contract drift, deterministic revision/content, docs-only commits, and key mismatch.
- [ ] Run builder tests and observe the missing-script failures.
- [ ] Implement bounded Git-object reads, frozen-contract parsing, deterministic pack generation, public-chain preflight, and environment-only signing.
- [ ] Run builder tests to green.

### Task 4: Workflow, packaging, and operations documentation

**Files:**
- Create: `.github/workflows/commons-release.yml`
- Create: `docs/commons-release-security.md`
- Modify: `pyproject.toml`
- Modify: `MANIFEST.in`
- Modify: `tests/test_packaged_schemas_v2.py`
- Create: `tests/commons/test_release_workflow.py`

**Interfaces:**
- Consumes: release builder CLI and verifier CLI mode.
- Produces: scheduled/dispatch-only fail-closed production publication and distributable public trust data.

- [ ] Write workflow and package-artifact behavior tests and observe failures.
- [ ] Add the workflow, public-trust package data, and concise operations/security documentation.
- [ ] Run packaging/workflow tests to green.

### Task 5: Complete verification and runtime rebuild

**Files:**
- Rebuild: `plugins/marginal/runtime/marginal_runtime.pyz`
- Rebuild: `plugins/marginal/runtime/provenance.json`

**Interfaces:**
- Consumes: all implementation and tests.
- Produces: verified source tree, sdist/wheel, and deterministic Codex zipapp.

- [ ] Run targeted Commons tests.
- [ ] Run `ruff format --check .`, `ruff check .`, `mypy src/marginal`, and `pytest -q` in `/tmp/marginal-signed-commons-venv`.
- [ ] Run `python scripts/build_codex_plugin.py` followed by `python scripts/build_codex_plugin.py --check`.
- [ ] Run `python -m build`, `python -m twine check dist/*`, and `git diff --check`.
- [ ] Inspect `git status`, `git diff --stat`, the complete diff, runtime SHA-256, and provenance without committing.
