# Claude Code Plugin

Capability label: **Observe**.

The plugin records normalized tool-call evidence and repeated-work recommendations in a local
Decision Ledger. It never blocks a tool call, never rewrites tool arguments, and never returns
output to Claude Code. Shadow Mode is the only mode this integration supports today.

Validated against Claude Code 2.1.233 on Linux.

## Install

```bash
claude plugin marketplace add SignalLayerLabs/Marginal
claude plugin install marginal-claude-code@marginal
```

`marginal install claude-code` runs the same two commands through the Claude Code CLI.

The plugin needs the `marginal-ai` package importable by the `python3` on your `PATH`:

```bash
python3 -m pip install --user marginal-ai
```

If `marginal` cannot be imported, every hook exits 0 without output and Claude Code behaves exactly
as if the plugin were absent. The plugin never installs anything on your behalf.

Point `MARGINAL_RUNTIME` at a directory or zipapp to load MARGINAL from somewhere else.

## Remove

```bash
claude plugin uninstall marginal-claude-code@marginal
```

Removal leaves the ledger in place. Delete the plugin data directory to discard the evidence.

## What it observes

| Hook | What MARGINAL records |
|---|---|
| `SessionStart` | starts one authenticated loopback service for the session |
| `PreToolUse` | a normalized action, its semantic key, workspace state hash, and the repetition signal |
| `PostToolUse` | a **proven success** with engine-measured `duration_ms` |
| `PostToolUseFailure` | a **proven failure**, or `unknown` when the call was interrupted |
| `SessionEnd` | a session summary, then closes the service |

Claude Code separates success from failure at the event level, so outcome is an engine-declared fact
rather than something inferred from response text. That is a stronger evidence surface than a single
completion hook provides. Two limits still apply:

- per-tool token usage is not exposed, so token cost is reported as unavailable rather than as zero;
- a hook that Claude Code does not deliver leaves a proposal unmatched, and the session records it as
  `unknown` instead of assuming success.

## Repeated work

A repeat is only interesting when the same semantic action runs against the same workspace state and
produces the same completion evidence. The ledger escalates through
`NO_PROGRESS_OBSERVED` to `NO_PROGRESS_ENFORCEMENT_ELIGIBLE`, and Shadow Mode still allows the
action, recording `SHADOW_OVERRIDE`. Nothing is blocked.

Read the recommendations back with the standard tooling:

```bash
marginal ledger-report "$CLAUDE_PLUGIN_DATA/ledger"/*/*.jsonl
```

## Enforcement

This integration does not enforce. The adapter declares no control capability, so the core refuses to
run it in a blocking mode. The documented deny transport is implemented and tested
(`marginal.integrations.claude_code.decisions`) but nothing calls it.

Turning it on requires an evidence gate equivalent to the Codex Earned Enforcement window: proven hook
coverage, reviewed stop candidates, zero false stops, and bounded governance latency. Until that
evidence exists for Claude Code, a stop recommendation stays a recommendation.

## Privacy and limits

The ledger is written under the plugin's own data directory with owner-only permissions.

- tool arguments, command text, tool output, prompts, and transcripts are never persisted; only
  digests of them are;
- error text from a failed tool contributes to an evidence digest and is not written to the ledger;
- `LOCAL_FULL` is the default profile because the ledger stays on the user's machine. It retains
  session identifiers and tool names;
- set `MARGINAL_PRIVACY_PROFILE=safe_telemetry` to write keyed pseudonyms instead. Pseudonymization is
  not anonymization;
- Claude Code's own transcripts, shell history, and telemetry are outside this boundary.

## Workspace state

State evidence comes from Git. A session directory inside a work tree is observable, including a
repository with no commits yet. Outside a repository the state hash is empty, which makes every
repetition control fail open rather than invent certainty.
