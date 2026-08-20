# Architecture

```text
AI development agent
        │ native hook/event
        ▼
thin engine adapter
        │ AgentAction / AgentEvent
        ▼
UniversalRuntime
        │ Action
        ▼
Treasury ──► MarginalPolicy ──► ValueEstimator
   │              │                    │
   │ applied      │ recommendation     │ versioned estimate + state fingerprint
   ▼              ▼                    ▼
reserve → execute → settle / abort / failure settlement
   │
   └──► JsonlDecisionLedger ──► privacy profile ──► outcome / replay / export
```

## Module boundaries

- `models.py`: immutable provider-neutral values;
- `modes.py`: Shadow, Recommend, and Enforce semantics;
- `budget.py`: hard limits, reservations, settlement, and accounting;
- `estimator.py`: transparent versioned value estimates and learned-state identity;
- `registry.py`: estimator name/version resolution;
- `policy.py`: deterministic economic scoring and reason codes;
- `profiles.py`: transparent reference policy configurations;
- `fingerprint.py`: deterministic core action and call identity;
- `treasury.py`: mode-aware lifecycle, hierarchy, atomic coordination, and evidence;
- `adapters.py`: guarded sync/async execution and failure usage settlement;
- `outcomes.py`: verified task outcome contract;
- `ledger.py`: strict schema-versioned evidence and privacy-aware export orchestration;
- `privacy.py`: field classification, keyed pseudonymization, strict sanitization, and aggregate grouping;
- `protocol.py`: universal adapter contract, directives, and capability negotiation;
- `runtime.py`: normalized local engine-session lifecycle;
- `replay.py`: non-causal off-policy decision replay;
- `trace.py`: legacy trace sinks and deterministic fan-out;
- `cli.py`: trace, ledger, privacy export, replay, benchmark, and demo commands.

## Shadow authorization

Shadow Mode still creates reservations, including unchecked reservations for would-deny actions. This lets later recommendations observe pending demand while the external agent continues unchanged.

Concurrent semantic duplicates receive unique internal reservation identities. The semantic fingerprint remains in evidence and duplicate recommendations, while each actual execution is separately reserved and settled.

Settlement records actual usage and violations without raising a caller-visible overrun.

## Enforced authorization

Enforce Mode preserves v0.1 behavior: affordability and policy denial prevent execution; reservations are transactional; actual overruns are recorded before `BudgetOverrun` is raised.

## Failure boundary

No observed spend releases a reservation. Measured failed spend is committed without marking the action as successfully completed. If failure usage extraction fails, the reserved estimate is settled conservatively and the original execution exception remains primary.

## Evidence boundary

`record_outcome` records task evidence. `observe_value` records explicit action-level realized gain. The separation prevents causal credit from being assigned merely because an action appeared in a successful trajectory.

Decision Ledger writes are strict JSON and sequence-safe within one process. Composite sink fan-out and multiple processes are not an atomic distributed transaction; deployments needing that property must provide an external transactional sink.

## Privacy boundary

`JsonlDecisionLedger` constructs the complete event, validates task/outcome consistency, then
applies the configured profile before serialization. `local_full` preserves the event.
`safe_telemetry` uses a strict allowlist, field-separated HMAC pseudonyms, and UTC-day timestamp
generalization. Unknown custom fields are dropped. `aggregate_export` is not accepted by the
operational sink; it reads a completed ledger, suppresses groups below a configurable threshold
of five by default, and writes grouped generalized rows through a separate file with overwrite
protection.

Keys remain local and are not part of a trace transaction. Losing a key prevents future stable
correlation but does not make existing pseudonyms anonymous.

## Commons boundary

The optional Commons loop is separate from the authority path:

```text
verified local finalization → closed aggregate compiler → owner-only outbox
    → Ingress-compatible boundary → aggregate-only Commons pack → same-model prior
```

`local_only` is the default and performs no Commons network calls. `read_only` downloads a bounded,
digest-verified pack. `contributor` additionally submits only closed atoms for an exact reviewed
public-model namespace. It carries a one-time retry token in an HTTP header and no persistent
client identity. Cloudflare remains an external network processor; the application cannot promise
anonymity at that layer.

Downloaded priors enter a separate read-only diagnostic path. They are not inputs to coverage,
trust, promotion, Autopilot, Decision Ledger hashes, or enforcement eligibility, and local evidence
takes precedence. Shared failures fail open without changing the local mode.
