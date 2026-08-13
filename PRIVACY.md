# MARGINAL Privacy Notice

**Effective date:** 2026-08-13

MARGINAL is local-first open-source software. The Codex plugin makes no network request and does
not operate a SignalLayer Labs telemetry service.

## Data processed locally

Codex supplies lifecycle identifiers, tool names, tool inputs, tool responses, workspace paths,
and session metadata to local hooks. MARGINAL uses that input in memory to make a decision and to
derive hashes. By default it does not persist prompts, source code, raw commands, raw tool output,
transcripts, authentication files, or credential environment values.

The plugin may store redacted decisions, opaque hashes, aggregate coverage counts, outcome status,
reason codes, latency, review labels, promotion receipts, and user-private connection files under
Codex `PLUGIN_DATA`. Connection credentials are removed at session end. Local evidence remains
until the user deletes it or runs an explicit purge.

## Sharing and remote processing

MARGINAL does not transmit plugin evidence to SignalLayer Labs. GitHub, Codex, package registries,
and any model provider remain governed by their own policies. Exporting a ledger or attaching files
to an issue is an explicit user action; inspect exports before sharing them.

## User controls

- `marginal codex status` shows the local mode.
- `marginal codex demote` returns enforcement to Shadow Mode.
- `marginal uninstall codex` removes the plugin and preserves evidence.
- `marginal uninstall codex --purge-data --yes` removes plugin data explicitly.

Security issues must follow [SECURITY.md](SECURITY.md). Privacy questions can be filed through the
private contact route described in [SUPPORT.md](SUPPORT.md).

