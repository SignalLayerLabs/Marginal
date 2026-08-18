# Interactive Killer Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an artifact-backed, synchronized browser race that shows the same deterministic coding task with and without MARGINAL in real time.

**Architecture:** Keep Python as the deterministic data and artifact generator, but split the browser presentation into generated `index.html`, `demo.css`, and `demo.js`. The JavaScript state machine replays one candidate per synchronized tick and never calls a backend or model.

**Tech Stack:** Python 3.10+, static HTML/CSS/vanilla JavaScript, pytest, Ruff, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-08-18-interactive-killer-demo-design.md`

## Global Constraints

- No API keys, backend, external runtime dependency, or paid model calls.
- Playback data must come from `run_killer_demo()` output.
- Browser timing must be labeled accelerated deterministic replay, not provider telemetry.
- Preserve existing publication-contract strings for legacy tests.
- Python source physical lines must fit the repository 100-character Ruff line-length rule.
- Regenerate Codex runtime and provenance after any `src/marginal` change.

---

### Task 1: Playback data contract

**Files:**
- Modify: `src/marginal/killer_demo.py`
- Test: `tests/test_killer_demo_interactive.py`

**Interfaces:**
- Produces: `build_killer_demo_playback(result: dict[str, Any]) -> dict[str, Any]`
- Playback contains one tick per deterministic candidate and cumulative lane metrics.

- [ ] Write failing tests for nine synchronized ticks, three funded decisions, and final PASS/PASS totals.
- [ ] Run the focused tests and confirm RED.
- [ ] Add candidate latency to result rows and implement `build_killer_demo_playback`.
- [ ] Run focused tests and confirm GREEN.

### Task 2: Interactive race artifact

**Files:**
- Modify: `src/marginal/killer_demo.py`
- Test: `tests/test_killer_demo_interactive.py`

**Interfaces:**
- Produces: `render_killer_demo_css() -> str`
- Produces: `render_killer_demo_js() -> str`
- Produces: `render_killer_demo_html(result: dict[str, Any]) -> str`

- [ ] Add failing tests for split-screen lane markers, controls, embedded playback JSON, CSS/JS references, and final comparison copy.
- [ ] Run tests and confirm RED.
- [ ] Implement semantic race HTML, responsive CSS, and deterministic playback state machine.
- [ ] Validate generated JavaScript with `node --check`.
- [ ] Run focused tests and confirm GREEN.

### Task 3: Reproducible generated assets and Pages gate

**Files:**
- Modify: `src/marginal/killer_demo.py`
- Modify: `.github/workflows/pages.yml`
- Test: `tests/test_killer_demo_interactive.py`

**Interfaces:**
- `_write_artifacts` writes `demo.css` and `demo.js` next to the existing five artifacts.

- [ ] Add failing test that generated CSS/JS match committed artifacts.
- [ ] Update `_write_artifacts` and Pages verification checks.
- [ ] Regenerate `demos/killer-demo/`.
- [ ] Confirm artifact test GREEN.

### Task 4: Repository compatibility and release verification

**Files:**
- Modify: `plugins/marginal/runtime/marginal_runtime.pyz`
- Modify: `plugins/marginal/runtime/provenance.json`

- [ ] Run `ruff format` on changed Python/test files.
- [ ] Run `ruff format --check .` and `ruff check .`.
- [ ] Run `python scripts/build_codex_plugin.py` and `--check`.
- [ ] Run Killer Demo and Codex plugin targeted tests.
- [ ] Run full pytest.
- [ ] Run `git diff --check`.
- [ ] Preview `/demo/` through a local static server before push.
