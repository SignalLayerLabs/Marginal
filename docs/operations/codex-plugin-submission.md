# Codex Plugin Directory Submission

```text
status: not_submitted
status_date: 2026-08-13
plugin_version: 0.3.2
marketplace_selector: marginal@marginal
portal_submission_type: skills_only_zip
portal_access: authentication_required
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
- Availability: every country or region offered by the submission portal

## Directory listing copy

**Short description:** Earned enforcement for agent compute.

**Long description:** MARGINAL measures repeated Codex tool work locally, starts in Shadow Mode,
and permits repository Tool Enforcement only after a versioned evidence gate proves coverage,
reviewed false stops, and governance overhead. It never reads prompts, source, raw commands, raw
outputs, transcripts, or Codex credentials for evidence.

**Release notes:** Adds a dependency-free native control plane, repository-scoped hook attestation,
local Shadow Mode, review workflow, Earned Enforcement gates, fail-open demotion, production logo,
eight reviewer cases, and a reproducible v0.3.2 archive.

Starter prompts are the three `interface.defaultPrompt` entries in
`plugins/marginal/.codex-plugin/plugin.json`. The production logo is
`plugins/marginal/assets/marginal-logo.png`.

## Review description

MARGINAL is a local-first compute-governance plugin for Codex. It observes tool lifecycle events,
detects repeated semantic work against unchanged repository and evidence state, accounts for its
own overhead, and starts globally in Shadow Mode. Repository-scoped Tool Enforcement requires a
versioned Earned Enforcement receipt plus explicit user promotion and demotes automatically if its
coverage or identity changes.

## Reviewer setup

1. Add the public repository marketplace with
   `codex plugin marketplace add SignalLayerLabs/Marginal --ref main`.
2. Install `marginal@marginal` with `codex plugin add marginal@marginal`.
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
- [ ] Canonical main contains v0.3.2 after merge and every public Pages URL resolves.
- [x] A deterministic single-root ZIP builder covers the manifest, skill, hooks, runtime, and logo.
- [ ] SignalLayer Labs identity and Apps Management write permission are confirmed in Platform.
- [ ] The v0.3.2 archive is uploaded in Platform and external review is started.

Build the exact upload artifact with:

```bash
python scripts/build_codex_plugin_submission.py --output-dir dist
```

The release workflow attaches that same ZIP to the matching GitHub release. The package contains no
MCP or app configuration, so the portal submission type is **Skills only**. The archive also carries
the native Codex hook runtime tested by the public marketplace path; OpenAI's ingestion and review
remain authoritative for the components exposed by the universal directory.

The status above changes only after the external portal accepts the final submission. Creating or
submitting a draft requires an authenticated Platform session, Apps Management write access, and a
verified SignalLayer Labs identity; none can be inferred from repository or GitHub credentials. No
external identifier, credential, or reviewer correspondence belongs in this repository.

Acceptance evidence:
[`codex-plugin-smoke-2026-08-13-v0.3.2.json`](evidence/codex-plugin-smoke-2026-08-13-v0.3.2.json).
