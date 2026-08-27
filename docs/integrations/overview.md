# Integrations

## Generic callable integration

Use `budgeted_call` or `async_budgeted_call` around an existing Python or SDK callable. Use `funded_call` or `async_funded_call` after `Treasury.fund_best`.

The wrappers authorize before execution, reserve estimated resources, settle actual usage, and release reservations when no spend occurred.

## Usage extraction

`extract_common_llm_usage` returns total `Cost.tokens`. `extract_common_token_usage` returns normalized uncached input, cached input, non-reasoning output, reasoning, and total tokens.

Provider schemas differ in whether reasoning is included inside output. The extractor uses a declared total where available and recognizes reasoning reported through output-detail objects. Production adapters must test their exact SDK version.

## Failure accounting

A failed external call may still be billed. Provide `failure_usage_extractor`:

- return `Cost` when spend is measured or best-known;
- return `None` only when no external spend occurred;
- if extraction fails, MARGINAL settles the reserved estimate conservatively.

The original execution exception remains primary. Measured failure does not mark the action as a completed duplicate, so a valid retry remains possible and is charged independently.

## Universal engine adapters

Use `AgentAction`, `AgentCapabilities`, `AgentDecision`, `AgentDirective`, and `UniversalRuntime`. Do not embed economic policy in an adapter.

A thin adapter should:

1. declare capabilities;
2. normalize a native proposed action;
3. call `before_action`;
4. apply or surface the returned directive;
5. call `after_action` with actual cost, or `fail_action` after failure;
6. record verifier outcomes;
7. classify identifiers, free text, verifier details, and errors before persistence;
8. select a Decision Ledger privacy profile appropriate to the trust boundary.

Enforce Mode requires `block_actions=True`. `UniversalRuntime` rejects an observe-only adapter configured as enforced.

## Protocol directives

Protocol v1 supports allow, deny, modify, defer, reuse, stop, and force-verify. The reference v0.2 runtime currently emits allow and deny based on core decisions. An adapter may transport the broader directive contract, but documentation must not imply those actions are generated automatically until a policy implements them.


## Privacy for adapters

Adapter-native logs are outside the Decision Ledger privacy boundary. Do not assume that using
`SAFE_TELEMETRY` sanitizes vendor logs, shell history, IDE telemetry, or custom callbacks. Keep
action kinds generic, use opaque local IDs, avoid embedding source paths in error messages, and
route shareable evidence through `ledger-export`.

- use `LOCAL_FULL` only on a trusted local filesystem;
- use `SAFE_TELEMETRY` for structured event-level evidence with keyed pseudonyms;
- use `AGGREGATE_EXPORT` for grouped datasets intended to cross trust boundaries.

Pseudonymization is not anonymization. Organizations should add retention limits, minimum-group
rules, access controls, and legal review appropriate to their data.

## Integration labels

Documentation must distinguish:

- **Observe:** telemetry and non-blocking recommendations;
- **Tool Enforcement:** supported tool actions can be blocked or changed;
- **Full Compute Enforcement:** model turns, tools, retries, and stop behavior are controllable and measured.

A prompt instruction, skill, or advisory middleware is not equivalent to enforced interception.

See the [capability glossary](../reference/capability-glossary.md) for the contributor-facing
version of these definitions, including how to choose a label for a new adapter.

## Current status

The v0.3 candidate implements and validates the native Codex plugin against Codex CLI 0.147.0.
It provides lifecycle correlation, privacy-safe normalization, outcome classification, an
authenticated local service, Shadow Mode, Earned Enforcement receipts, and reversible native
installation. See [Codex plugin](codex.md).

The Claude Code plugin is labeled **Observe**. It records normalized evidence and repeated-work
recommendations in a local Decision Ledger, declares no control capability, and never blocks a tool
call. Its outcome evidence is engine-declared, because Claude Code reports success and failure as
separate hook events. See [Claude Code plugin](claude-code.md).

The OpenCode plugin is labeled **Observe**. It runs inside the engine process and speaks to one bridge
child process over pipes. Its outcome evidence is weaker than Claude Code's: the shell tool reports an
exit code, most other tools prove nothing, and those outcomes stay `unknown`. See
[OpenCode plugin](opencode.md).

PrivacyCode is an **Observe** install target for the same OpenCode adapter because its validated plugin
surface is currently compatible. It keeps a distinct engine label, configuration path, ledger root, and
evidence history. Target compatibility does not transfer Earned Enforcement authority: trust remains
engine-specific. If the plugin/event contract diverges, PrivacyCode becomes a separate adapter rather
than accumulating target-specific governance semantics.

Gemini CLI is research-only: no adapter is shipped. The native hooks cover interactive sessions and
can technically block or rewrite work, but they do not document the stable per-tool identity needed by
hookkit. Headless `stream-json` provides stronger tool correlation and outcome evidence for runs that
MARGINAL launches. The recommended first prototype is therefore **Observe** over headless JSONL. See
[Gemini CLI integration research](gemini-cli.md).

GitHub Copilot remains roadmap work. Codex is labeled Tool Enforcement,
not Full Compute Enforcement, because specialized and hosted tool paths can fall outside local
hook coverage.

Engine-independent parts of a hook integration live in `marginal.integrations.hookkit`: normalized
events, action normalization, structured outcome classification, workspace state evidence, and
session correlation. The Codex integration predates that module and still carries its own copies;
migrating it is separate work so a new adapter never destabilizes the validated Codex path.
