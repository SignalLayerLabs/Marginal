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
inactive or Shadow-only.

An installed Python package can perform the same native transaction:

```bash
marginal install codex
```

## Remove

```bash
codex plugin remove marginal@marginal
```

Or:

```bash
marginal uninstall codex
```

Removal preserves local evidence. Purge it only through the explicit destructive form:

```bash
marginal uninstall codex --purge-data --yes
```

## Earned Enforcement

Global installation never turns blocking on. A repository can enter Tool Enforcement only after:

- 100 covered actions across at least five sessions;
- at least 99% coverage of hook-coverable local actions;
- five reviewed stop candidates and zero false stops;
- zero integration failures, pending actions, or unknown enforceable outcomes;
- p95 decision latency no greater than 75 ms;
- an unchanged repository, Codex, plugin, adapter, policy, and hook identity;
- an observable outcome contract for every enforced action family;
- explicit `marginal codex promote` intent.

Any identity drift, lifecycle failure, coverage loss, false stop, or unknown enforced outcome
invalidates the receipt and demotes to Shadow Mode. Integration failure fails open because MARGINAL
is an efficiency governor, not a security boundary.

## Commands

| Command | Purpose |
| --- | --- |
| `marginal codex status` | Show mode and capability label |
| `marginal codex doctor` | Inspect Codex version, stable hooks, and plugins |
| `marginal codex review` | Show hook-trust guidance |
| `marginal codex promote` | Require a ready, hash-valid local receipt |
| `marginal codex demote` | Immediately return to Shadow Mode |

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

