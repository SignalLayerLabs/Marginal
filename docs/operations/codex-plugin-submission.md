# Codex Plugin Directory Submission

```text
status: not_submitted
status_date: 2026-08-13
plugin_version: 0.3.0
marketplace_selector: marginal@marginal
```

## Submission identity

- Developer: SignalLayer Labs
- Repository: `https://github.com/SignalLayerLabs/Marginal`
- Website: `https://signallayerlabs.github.io/Marginal/`
- Privacy: `https://signallayerlabs.github.io/Marginal/privacy.html`
- Terms: `https://signallayerlabs.github.io/Marginal/terms.html`
- Support: `https://signallayerlabs.github.io/Marginal/support.html`
- Category: Productivity
- Authentication: none; local plugin runtime only
- Network access: none
- Data region: local user device

## Review description

MARGINAL is a local-first compute-governance plugin for Codex. It observes tool lifecycle events,
detects repeated semantic work against unchanged repository and evidence state, accounts for its
own overhead, and starts globally in Shadow Mode. Repository-scoped Tool Enforcement requires a
versioned Earned Enforcement receipt plus explicit user promotion and demotes automatically if its
coverage or identity changes.

## Reviewer setup

1. Add this repository as a local marketplace.
2. Install `marginal@marginal`.
3. Review the exact commands through `/hooks`; do not bypass hook trust.
4. Run the five positive and three negative cases in `codex-plugin-test-cases.json`.
5. Confirm Shadow Mode emits no deny, evidence contains no raw marker, demotion fails open, and
   uninstall removes the plugin.

## Pre-submission gates

- [x] Official plugin validator passes.
- [x] Skill validator passes.
- [x] Isolated Codex 0.147.0 marketplace add/install/remove smoke passes.
- [x] Four-event direct lifecycle smoke passes with 100% exercised coverage.
- [x] Secret-marker scan returns zero persisted occurrences.
- [x] Reproducible smoke evidence is committed with runtime SHA-256 provenance.
- [x] Privacy, terms, support, and eight reviewer cases exist.
- [ ] Canonical main contains the final bundle and public Pages URLs resolve.
- [ ] SignalLayer Labs identity and Apps Management write permission are confirmed in Platform.
- [ ] Final archive is uploaded and external review is started.

The status above changes only after the external portal accepts the final submission. No external
identifier, credential, or reviewer correspondence belongs in this repository.

Acceptance evidence:
[`codex-plugin-smoke-2026-08-13.json`](evidence/codex-plugin-smoke-2026-08-13.json).
