# Gemini CLI integration research

Status: **research complete; no adapter shipped**. Recommended first capability label: **Observe**.

This note evaluates the public Gemini CLI surfaces requested in
[issue #44](https://github.com/SignalLayerLabs/Marginal/issues/44). It does not claim that MARGINAL
currently installs into, observes, or controls Gemini CLI.

## Tested revision and evidence labels

The source-level evaluation used Gemini CLI commit
[`3c311beac2e78336816dd4a123db39743f9fbf85`](https://github.com/google-gemini/gemini-cli/tree/3c311beac2e78336816dd4a123db39743f9fbf85),
whose CLI package reports version `0.59.0-nightly.20260825.g812f7a2bc`.

This document uses four evidence labels:

- **Official:** documented or typed in that immutable Gemini CLI revision.
- **Reproduced:** exercised in the pinned source checkout by the checks below.
- **Inferred:** an adapter design consequence, not a Gemini CLI guarantee.
- **Unavailable:** a signal required by MARGINAL that the evaluated surface does not expose.

## Two usable surfaces

### 1. Native hooks: interactive coverage, incomplete correlation

**Official.** Gemini CLI documents session, agent, model, tool-selection, tool, compression, and
notification hooks. `BeforeTool` can deny execution or merge rewritten arguments; `AfterTool` can
hide or replace a result, append context, or request a tail call. Agent and model hooks can stop,
retry, redact, or replace work. See the pinned
[hook overview](https://github.com/google-gemini/gemini-cli/blob/3c311beac2e78336816dd4a123db39743f9fbf85/docs/hooks/index.md)
and [hook schemas](https://github.com/google-gemini/gemini-cli/blob/3c311beac2e78336816dd4a123db39743f9fbf85/docs/hooks/reference.md).

The common hook payload contains `session_id`, `transcript_path`, `cwd`, event name, and timestamp.
Tool hooks add `tool_name`, input, response, and optional MCP context. They do **not** document a
per-call ID, turn ID, duration, or token usage. `SessionEnd` is best effort and the CLI does not wait
for it.

That omission matters because MARGINAL's `ToolCallStart` and `ToolCallEnd` require a stable
`call_id`. Matching only `(session, tool name, input hash)` is ambiguous when identical or parallel
calls overlap. An initial hook adapter must therefore report unmatched or ambiguous completions as
`unknown`; it must not invent identity, cost, or success.

### 2. `stream-json`: strong headless correlation, no passive interactive coverage

**Official.** Headless mode can emit JSONL `init`, `message`, `tool_use`, `tool_result`, `error`, and
`result` events. `tool_use` and `tool_result` share a `tool_id`; tool results declare `success` or
`error`; the final result can include duration, tool-call count, and token statistics. See the pinned
[headless reference](https://github.com/google-gemini/gemini-cli/blob/3c311beac2e78336816dd4a123db39743f9fbf85/docs/cli/headless.md)
and [event types](https://github.com/google-gemini/gemini-cli/blob/3c311beac2e78336816dd4a123db39743f9fbf85/packages/core/src/output/types.ts).

**Inferred.** This is the cleaner first implementation target when MARGINAL launches and owns a
non-interactive Gemini CLI run: `tool_id` can map directly to hookkit `call_id`, result status can map
to engine-declared success/failure, and final stats can provide run-level cost evidence.

**Unavailable.** `stream-json` is not a passive observation channel for an already-running
interactive terminal session. A wrapper cannot claim coverage of work it did not launch and consume.

## Mapping to hookkit and UAP

| Gemini CLI evidence | MARGINAL mapping | Initial treatment |
| --- | --- | --- |
| `SessionStart` / `SessionEnd` hooks | `SessionBoundary` | Start is usable; end remains best-effort. |
| `BeforeTool` hook | `ToolCallStart` | Observe only when a stable call ID can be established; otherwise record coverage loss. |
| `AfterTool` hook | `ToolCallEnd` | Use documented error evidence only; ambiguous pairing is `unknown`. |
| `stream-json.tool_use.tool_id` | `ToolCallStart.call_id` | Direct correlation for wrapped headless runs. |
| `stream-json.tool_result` | `ToolCallEnd` | `success` / `error` are engine-declared outcomes; hash evidence before persistence. |
| Final `stream-json.result.stats` | UAP run-level usage evidence | Run-level latency and token counts; do not misattribute them to individual tools. |
| Hook deny/rewrite fields and exit code 2 | Future `AgentDirective` transport | Technically block-capable, but not enabled before an earned enforcement gate. |
| Missing hook call ID, duration, and tokens | No trustworthy mapping | Leave unavailable; never synthesize. |

The native hook surface is technically capable of Tool Enforcement, but surface capability is not
earned authority. The first MARGINAL integration should remain **Observe** until correlation,
coverage, fail-open behavior, and false-denial rates are validated on representative sessions.

## Privacy and fail-open requirements

Gemini CLI hands hooks raw prompts, tool arguments, tool responses, transcript paths, and working
directories. Those values are outside the Decision Ledger privacy boundary unless the adapter
actively minimizes them.

A compliant adapter should:

1. hash tool identity and canonicalized inputs in memory and persist only safe normalized metadata;
2. never persist raw prompts, source, command output, credentials, transcript paths, or model text;
3. treat Gemini CLI's own transcripts, logs, shell history, and telemetry as external to MARGINAL's
   privacy guarantee;
4. exit successfully with no control output whenever MARGINAL is missing, malformed, slow, or
   unavailable;
5. keep every enforcement-capable hook response disabled in Shadow Mode.

Gemini CLI's [hook guidance](https://github.com/google-gemini/gemini-cli/blob/3c311beac2e78336816dd4a123db39743f9fbf85/docs/hooks/index.md#security-considerations)
warns that project-level hooks are risky and fingerprints changed commands as untrusted. An installer
must not silently activate untrusted project hooks.

## Reversible installation design

**Inferred; not implemented.** Prefer a user-scoped installer that:

- parses and merges the existing Gemini CLI settings instead of replacing them;
- adds only MARGINAL-owned hook entries with a stable ownership marker;
- preserves a pre-change backup and writes atomically;
- refuses conflicting, malformed, or untrusted project configuration;
- exposes `doctor` before installation;
- removes only marked MARGINAL entries on uninstall and restores no unrelated state.

The headless alternative needs no persistent hook install: invoke the exact Gemini CLI executable
with `--output-format stream-json`, consume stdout directly, and leave the user's settings untouched.

## Reproduction

From the pinned Gemini CLI checkout:

```console
npm ci --ignore-scripts
npm run generate
npx vitest run packages/core/src/hooks/hookRunner.test.ts packages/core/src/hooks/hookEventHandler.test.ts
npx vitest run packages/core/src/output/stream-json-formatter.test.ts packages/core/src/core/coreToolHookTriggers.test.ts packages/core/src/scheduler/scheduler_hooks.test.ts packages/core/src/hooks/runtimeHooks.test.ts
npx vitest run packages/core/src/hooks/hookSystem.test.ts
```

**Reproduced.** The two direct hook suites passed 42 tests. The formatter, tool-trigger, scheduler,
and runtime-hook suites passed 34 more tests. The integrated `hookSystem` suite passed 4 of 8 tests;
four cases still failed in this checkout after generation, and the run emitted listener warnings.
That mixed result is a limitation, not positive adapter evidence. `npm ci` also reported dependency
vulnerabilities; no automated audit fix was applied because dependency mutation was outside this
research scope.

## Recommendation

Implement a small **headless Observe prototype** before an interactive hook adapter. It has the
stronger identity and outcome contract and the smaller installation risk. Evaluate it on repeated,
parallel, failed, cancelled, and MCP tool calls. Proceed to native hooks only if interactive coverage
is required, and keep ambiguous calls `unknown`. Do not label either path Tool Enforcement until the
repository has tests proving complete interception, safe denial behavior, rollback, and earned
authority.
