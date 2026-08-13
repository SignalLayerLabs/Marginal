---
name: marginal
description: Use when inspecting, reviewing, promoting, demoting, or explaining MARGINAL governance in Codex, especially for repeated tool work, token-saving claims, and Earned Enforcement readiness.
---

# MARGINAL

Treat compute as scarce and claims as evidence-bound. The plugin starts globally in Shadow Mode;
it may exercise repository-scoped Tool Enforcement only after a valid Earned Enforcement receipt
and explicit promotion.

## Workflow

1. Run `marginal codex status` before describing the active mode.
2. Run `marginal codex doctor` when hooks, coverage, or compatibility are uncertain.
3. Use `marginal codex review` to direct the user to the required `/hooks` trust review.
4. Review local redacted candidates and false-stop labels before promotion.
5. Run `marginal codex promote` only when the evidence receipt is ready.
6. Run `marginal codex demote` whenever identity, coverage, outcome observability, or policy drifts.

## Claims contract

- Say **Tool Enforcement**, never Full Compute Enforcement.
- Describe recommendations as counterfactual until an enforced run measures them.
- Never claim token savings without a matched benchmark that reports quality and governance tax.
- Treat `PostToolUse` as completion, not success; prose-only outcomes remain unknown.
- Never read Codex auth files, prompts, source, raw commands, raw outputs, or transcripts for evidence.

## Quick reference

| Need | Command |
| --- | --- |
| Current mode | `marginal codex status` |
| Capability diagnosis | `marginal codex doctor` |
| Hook trust instructions | `marginal codex review` |
| Evidence-gated enforcement | `marginal codex promote` |
| Immediate fail-open reset | `marginal codex demote` |

If evidence is incomplete or contradictory, keep Shadow Mode and report the exact blocking reason.

