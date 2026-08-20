# Capability glossary

MARGINAL labels every integration with exactly one capability level. The label
is a claim about what the integration can *do*, not about how much evidence it
collects, and it is the first thing a reviewer checks on an adapter pull
request.

The normative definitions live in the
[integration overview](../integrations/overview.md#integration-labels). This
page restates them for contributors and adds the reasoning a reviewer applies,
so an adapter PR can link to one place.

## The three levels

### Observe

Telemetry and non-blocking recommendations.

An Observe integration records normalized evidence and may surface advice, but
it declares no control capability and never blocks or alters an action. If the
integration were removed, the engine would behave identically.

### Tool Enforcement

Supported tool actions can be blocked or changed.

The integration intercepts tool calls through an official engine control point
and a deny or modify directive actually takes effect. The qualifier
**supported** carries weight: a level is Tool Enforcement, not Full Compute
Enforcement, when some tool paths fall outside that coverage.

### Full Compute Enforcement

Model turns, tools, retries, and stop behavior are controllable and measured.

This is the whole compute loop, not just the tool surface.
[`CONTRIBUTING.md`](../../CONTRIBUTING.md#adapter-contributions) states the bar
directly: an adapter must not advertise Full Compute Enforcement unless the
underlying engine exposes official controls for the relevant model turns, tool
calls, retry loops, and stopping behavior.

## What is not enforcement

A prompt instruction, skill, or advisory middleware **is not** equivalent to
enforced interception.

Asking a model not to do something is not the same as being able to stop it.
Only an official engine control point that MARGINAL can refuse through counts
toward an enforcement label. Text that the model is free to ignore does not,
however reliably it happens to be obeyed in practice.

Two related boundaries a reviewer will also check:

- **Transporting a directive is not implementing it.** Protocol v1 defines
  allow, deny, modify, defer, reuse, stop, and force-verify, but the reference
  v0.2 runtime emits only allow and deny. An adapter may carry the broader
  contract; documentation must not imply the rest are generated automatically
  until a policy implements them.
- **Enforce Mode requires `block_actions=True`.** `UniversalRuntime` rejects an
  observe-only adapter configured as enforced, so the label and the
  configuration cannot silently disagree.

## Current MARGINAL examples

### Codex — Tool Enforcement

The native Codex plugin is validated against Codex CLI 0.147.0 and provides
lifecycle correlation, an authenticated local service, Shadow Mode, and Earned
Enforcement receipts.

It is labeled Tool Enforcement rather than Full Compute Enforcement because
specialized and hosted tool paths can fall outside local hook coverage. The
gap is in coverage, not in the mechanism — which is exactly the distinction the
two labels exist to record. See [Codex plugin](../integrations/codex.md).

### Claude Code — Observe

The Claude Code plugin records normalized evidence and repeated-work
recommendations in a local Decision Ledger, declares no control capability, and
never blocks a tool call.

Its outcome evidence is engine-declared, because Claude Code reports success
and failure as separate hook events. Note that this is a statement about
evidence quality, not capability: richer evidence does not move an integration
up a level. See [Claude Code plugin](../integrations/claude-code.md).

## Choosing a label

1. Can the integration refuse or alter an action through an official engine
   control point, such that the engine honors it? If no, the label is
   **Observe**.
2. Does that control cover every tool path, or only the supported ones? Partial
   coverage is **Tool Enforcement**.
3. Does it additionally control model turns, retries, and stopping, with those
   measured? Only then is it **Full Compute Enforcement**.

When a step is uncertain, claim the lower label. An integration that
under-claims is merely conservative; one that over-claims invites a user to
rely on a control that will fail open.
