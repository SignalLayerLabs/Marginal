# OpenCode Plugin

Capability label: **Observe**.

The plugin records normalized tool-call evidence and repeated-work recommendations in a local
Decision Ledger. It never blocks a tool call, never rewrites tool arguments, and never throws out of a
hook. Shadow Mode is the only mode this integration supports today.

Validated against OpenCode 1.18.18 on Linux.

Also validated against PrivacyCode 1.18.10, an OpenCode-compatible fork. See
[Compatible forks](#compatible-forks).

## Install

```bash
marginal install opencode
```

That copies one file to `~/.config/opencode/plugins/marginal.js`. Remove it with:

```bash
marginal uninstall opencode
```

Uninstall only deletes a file carrying MARGINAL's own marker, so a hand-written plugin with the same
name is never destroyed. For the same reason, install refuses to overwrite one.

The plugin needs the `marginal-ai` package importable by the `python3` on your `PATH`:

```bash
python3 -m pip install --user marginal-ai
```

| Variable | Effect |
|---|---|
| `MARGINAL_PYTHON` | interpreter used to run the bridge |
| `MARGINAL_RUNTIME` | directory or zipapp prepended to the bridge's `PYTHONPATH` |
| `MARGINAL_DATA_ROOT` | where the Decision Ledger is written |
| `MARGINAL_PRIVACY_PROFILE` | `safe_telemetry` or `aggregate_export` instead of local-only |
| `MARGINAL_TIMEOUT_MS` | per-request bridge timeout, default 5000 |

If the bridge cannot start, the plugin registers no hooks at all and OpenCode behaves exactly as if it
were not installed.

## Architecture

OpenCode loads plugins into its own long-running process, so the plugin owns one bridge child process
and speaks newline-delimited JSON to it over pipes. There is no socket, no port, and no token, because
the only possible caller is the process that spawned it. One bridge governs every session in that
OpenCode process; tool calls from different sessions interleave and stay separate.

| Plugin hook | Bridge operation |
|---|---|
| `event` → `session.created` | `session_start` |
| `tool.execute.before` | `tool_start` |
| `tool.execute.after` | `tool_end` |
| `event` → `session.deleted`, `dispose` | `session_end` |

OpenCode has no guaranteed session-start hook in every mode, so the first observed tool call opens the
session.

## What it can prove

OpenCode's shell tool reports an exit code in result metadata, which is a provable success or failure
signal. Most other tools report nothing that separates success from a completed failure, and those
outcomes are recorded as `unknown` rather than assumed successful.

Two further limits:

- a tool that throws produces no `tool.execute.after` call, so its proposal is settled as unobservable
  when the session closes;
- per-tool token usage is not exposed, so token cost is reported as unavailable rather than as zero.

This is a weaker evidence surface than an engine that reports success and failure as separate events.
It is enough to detect repeated work and to measure governance overhead; it is not enough to justify
enforcement, and none is attempted.

## Privacy

Tool output never leaves the OpenCode process. The plugin sends a SHA-256 digest of the result plus an
allowlist of outcome signals (`exit`, `exit_code`, `exitCode`, `success`, `status`), so file content and
command output never reach MARGINAL, not even in memory.

Tool arguments do reach the bridge, because semantic identity and verification detection depend on
them. They are hashed into a semantic key and never persisted. The ledger holds digests, generic action
kinds, and tool names.

`LOCAL_FULL` is the default profile because the ledger stays on the user's machine. Set
`MARGINAL_PRIVACY_PROFILE=safe_telemetry` for keyed pseudonyms. Pseudonymization is not anonymization.
OpenCode's own logs, database, and telemetry are outside this boundary.

## Reading the evidence

```bash
marginal ledger-report ~/.local/share/marginal/opencode/ledger/*/*.jsonl
```

## Compatible forks

OpenCode's plugin loader is reused unchanged by compatible forks, so the same plugin and the same bridge
protocol govern them. A target records only what differs: the executable name, the global configuration
directory, and the ledger location.

| Target | Executable | Plugin path | Ledger root |
|---|---|---|---|
| `opencode` | `opencode` | `~/.config/opencode/plugins/marginal.js` | `~/.local/share/marginal/opencode` |
| `privacycode` | `privacycode` | `~/.config/privacycode/plugins/marginal.js` | `~/.local/share/marginal/privacycode` |

```bash
marginal install privacycode
marginal uninstall privacycode
```

Each target keeps a distinct engine label, so one ledger never conflates two engines and a later
measurement can compare them instead of pooling them. Installing binds the copied plugin to its engine,
so both can be installed at once without interfering. `MARGINAL_PRIVACYCODE_DATA` overrides the ledger
location for that target alone.

Adding another compatible fork means one `OpenCodeTarget` entry. Nothing about the governance contract
is per-target, so a fork that has diverged in its plugin API is not a target — it is a new adapter.
