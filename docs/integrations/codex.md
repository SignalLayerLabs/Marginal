# Codex Plugin

MARGINAL 0.3 packages its provider-neutral compute governor as a native Codex plugin. It starts in
Shadow Mode, processes tool lifecycle events locally, and identifies its supported control surface
as **Tool Enforcement**.

## Install

```bash
codex plugin marketplace add SignalLayerLabs/Marginal --ref main && codex plugin add marginal@marginal
```

Open `/hooks` in Codex and inspect the four MARGINAL lifecycle commands before granting trust. The
plugin never uses the bypass-trust flag. Until trust and runtime coverage are observed, MARGINAL is
unobserved or Shadow-only; lack of evidence alone does not prove that hooks are disabled.

An installed Python package can perform the same native transaction:

```bash
marginal install codex
```

## Remove

```bash
codex plugin remove marginal@marginal
```

Removal preserves local evidence. The optional Python package also exposes
`marginal uninstall codex --purge-data --yes` for an explicit data purge.

## Earned Enforcement

Global installation never turns blocking on. A repository can enter Tool Enforcement only after:

- 100 covered actions across at least five sessions;
- at least 99% coverage of hook-coverable local actions;
- five reviewed stop candidates and zero false stops;
- zero integration failures, pending actions, or unknown enforceable outcomes;
- p95 decision latency no greater than 75 ms;
- an unchanged repository, Codex, plugin, adapter, policy, and hook identity;
- an observable outcome contract for every enforced action family;
- explicit native `promote` intent.

Any identity drift, lifecycle failure, coverage loss, false stop, or unknown enforced outcome
invalidates the receipt and demotes to Shadow Mode. Integration failure fails open because MARGINAL
is an efficiency governor, not a security boundary. Failures and false stops remain in the local
audit history, then open a fresh evidence window; enforcement can be earned again only with a new
100-action, five-session clean window.

## Native commands

The plugin bundle does not modify `PATH`. Run `codex plugin list --json`, select the exact
`marginal@marginal` entry, and use its `source.path` as `<plugin-root>`. Then invoke:

| Command | Purpose |
| --- | --- |
| `python3 <plugin-root>/scripts/marginal_control.py status --workspace <repo> --json` | Show live hook service, prior evidence, mode, and coverage |
| `python3 <plugin-root>/scripts/marginal_control.py doctor --json` | Inspect Codex version, stable hooks, and plugins |
| `python3 <plugin-root>/scripts/marginal_control.py review --workspace <repo> --json` | List redacted, unreviewed stop candidates |
| `python3 <plugin-root>/scripts/marginal_control.py promote --workspace <repo> --json` | Require a ready, hash-valid local receipt |
| `python3 <plugin-root>/scripts/marginal_control.py demote --workspace <repo> --json` | Immediately return to Shadow Mode |

Label a candidate by hash; no raw command or output is displayed or persisted:

```bash
python3 <plugin-root>/scripts/marginal_control.py review --workspace <repo> --candidate ACTION_HASH --verdict waste
python3 <plugin-root>/scripts/marginal_control.py review --workspace <repo> --candidate ACTION_HASH --verdict helpful
```

On Windows, replace `python3` with `py -3` and use Windows path separators. From a Codex chat,
`$marginal` performs plugin discovery and these commands automatically.

`hooks_active` attests at least one live authenticated MARGINAL service for the selected repository;
`hooks_observed` reports persisted lifecycle evidence. Neither field is the enforcement mode, and
the privacy-preserving control plane does not expose a raw Codex chat identifier.

`waste` means the repeated action added no useful evidence. `helpful` marks the recommendation as a
false stop and immediately demotes any active receipt.

## Privacy and limits

The plugin does not persist prompts, source, raw tool inputs, raw outputs, transcripts, Codex auth
files, or credential environment values. It stores hashes, decisions, reason codes, latency,
coverage, review labels, and receipts under user-private `PLUGIN_DATA`.

Codex specialized and hosted tool paths may not traverse local hooks. The plugin therefore does
not claim Full Compute Enforcement. A `PostToolUse` event proves completion, not success; only
allowlisted structured fields can prove success or failure, and prose remains `unknown`.

## Directory availability

The repository contains a validation-ready marketplace plugin and the external submission packet.
The Git marketplace command works immediately. Appearance in the universal directory requires a
separate OpenAI review and release step, so it is not represented as available there yet.

The reproducible isolated acceptance result is preserved in
[`codex-plugin-smoke-2026-08-13.json`](../operations/evidence/codex-plugin-smoke-2026-08-13.json).
