---
name: marginal
description: Use when inspecting, reviewing, promoting, demoting, or explaining MARGINAL governance in Codex, especially for repeated tool work, token-saving claims, and Earned Enforcement readiness.
---

# MARGINAL

Treat compute as scarce and claims as evidence-bound. The plugin starts globally in Shadow Mode;
it may exercise repository-scoped Tool Enforcement only after a valid Earned Enforcement receipt
and explicit promotion.

## Native control

Do not require a global `marginal` executable or a pip installation. Resolve the native plugin:

1. Run `codex plugin list --json`.
2. Select the exact `pluginId` `marginal@marginal` and read its `source.path` as the plugin root.
3. On macOS/Linux, run `python3 <plugin-root>/scripts/marginal_control.py COMMAND`; on Windows,
   run `py -3 <plugin-root>\scripts\marginal_control.py COMMAND`.

Pass `--workspace <repository>` and `--json` when inspecting repository-scoped state. The launcher
uses Codex's native plugin data directory, so hook evidence and control commands share one state.
It automatically replaces an older `python3` with an available Python 3.10–3.13 interpreter. If
none is installed, report that exact runtime requirement and do not claim hooks are operational.

## Workflow

1. Run the native `status` command before describing the active mode.
2. Read live operation, prior evidence, and enforcement as separate facts:
   - `hooks_active: true` attests a live authenticated MARGINAL lifecycle service for this
     repository. It is the strongest available operational signal, but does not expose or prove a
     raw chat session identity.
   - `hooks_observed: true` proves lifecycle evidence exists for this repository, even when no
     session is currently live.
   - `hooks_observed: false` means not yet observed, not that hooks are disabled. Use `/hooks` to
     review and trust the exact definitions, perform a tool action, then run `status` again.
   - `mode` reports `shadow` or repository-scoped `enforce`; installation alone never implies
     enforcement.
3. Run `doctor` when hooks, coverage, or compatibility remain uncertain.
4. Run `review`, then label each local redacted candidate with
   `--candidate HASH --verdict waste|helpful` before promotion.
5. Run `promote` only when the evidence receipt is ready.
6. Run `demote` whenever identity, coverage, outcome observability, or policy drifts.

## Claims contract

- Say **Tool Enforcement**, never Full Compute Enforcement.
- Describe recommendations as counterfactual until an enforced run measures them.
- Never claim token savings without a matched benchmark that reports quality and governance tax.
- Treat `PostToolUse` as completion, not success; prose-only outcomes remain unknown.
- Never read Codex auth files, prompts, source, raw commands, raw outputs, or transcripts for evidence.

## Quick reference

| Need | Command |
| --- | --- |
| Current mode and hook evidence | `python3 <plugin-root>/scripts/marginal_control.py status --workspace <repo> --json` |
| Capability diagnosis | `python3 <plugin-root>/scripts/marginal_control.py doctor --json` |
| Unreviewed evidence | `python3 <plugin-root>/scripts/marginal_control.py review --workspace <repo> --json` |
| Evidence-gated enforcement | `python3 <plugin-root>/scripts/marginal_control.py promote --workspace <repo> --json` |
| Immediate fail-open reset | `python3 <plugin-root>/scripts/marginal_control.py demote --workspace <repo> --json` |

If evidence is incomplete or contradictory, keep Shadow Mode and report the exact blocking reason.
