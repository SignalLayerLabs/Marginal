# Universal Agent Runtime

MARGINAL is one product with one decision core. Engine integrations are thin adapters over Universal Agent Protocol v1.

## Adapter responsibilities

1. declare engine capabilities;
2. translate a native proposed action into `AgentAction`;
3. call `UniversalRuntime.before_action`;
4. apply or surface `AgentDecision` according to mode and capability;
5. execute the native action when applied;
6. call `after_action` with actual cost, or `fail_action` with measured cost when available;
7. record verifier outcomes with the matching task ID;
8. classify identifiers and free text before persistence;
9. use `SAFE_TELEMETRY` or `AGGREGATE_EXPORT` before data leaves a trusted boundary.

The runtime adds engine, session, and task identity to the core action metadata. Action IDs remain pending until successful settlement, measured failure settlement, or abort.

The runtime does not itself sanitize adapter inputs. Privacy is enforced at the Decision Ledger
boundary. `SAFE_TELEMETRY` removes action names, model identity, metadata, verifier details, and
error text while pseudonymizing correlation identifiers. An adapter should still minimize
sensitive data before it reaches any log outside MARGINAL.

## Capability levels

- `observe`: telemetry but no action control;
- `control`: at least one blocking, modification, stop, or model-turn control surface;
- `full`: all currently modeled capabilities.

Capability level is derived from booleans and validated during dictionary parsing. Labels describe technical control, not benchmark quality.

Enforce Mode requires `block_actions=True`; construction fails otherwise. Shadow and Recommend modes support observe-only adapters.

## Directives

Protocol v1 defines:

```text
allow · deny · modify · defer · reuse · stop · force_verify
```

The reference runtime converts current core decisions to allow or deny. Replacement payloads and richer directives are stable protocol extension points, not automatic v0.2 policy behavior.

## Deduplication scopes

- `exact`: same semantic action payload;
- `once_per_state`: reruns are valid after workspace state changes;
- `once_per_phase`: one execution in a named task phase;
- `allow_retry`: retry number participates in identity.

Protocol fingerprint metadata must be JSON serializable. Non-blocking modes maintain separate internal reservations for concurrent semantic duplicates, preserving Shadow Mode behavior and complete accounting.

## Settlement safety

`after_action` and `fail_action` validate actual cost before removing the runtime action ID. Invalid settlement data therefore does not orphan a Treasury reservation.

Failed work with measured cost is settled but not marked as successfully completed, so a retry may be authorized and charged.

## Published schemas

- `schemas/agent-event-v1.json`;
- `schemas/agent-decision-v1.json`;
- `schemas/agent-capabilities-v1.json`;
- `schemas/token-usage-v2.json`;
- `schemas/outcome-v1.json`;
- `schemas/decision-ledger-v2.json`;
- `schemas/aggregate-export-v1.json`.

## Vendor adapters

Codex, OpenCode, Claude Code, and GitHub Copilot adapters are separate milestones. This release provides their shared contract and local runtime but does not claim those vendor integrations are complete.
