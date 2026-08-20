# Privacy-Preserving Model-Specific Shared Evidence Design

Status: approved by the attached 2026-08-20 implementation mandate.

## Goal

Add an optional MARGINAL Commons learning loop without turning shared evidence into telemetry,
identity, or enforcement authority. The default remains Local Only and Shadow Mode.

## Repositories

- `SignalLayerLabs/Marginal-Ingress`: a minimal Cloudflare Worker privacy boundary.
- `SignalLayerLabs/Marginal-Commons`: public schemas, aggregates, validation, and deterministic pack.
- `SignalLayerLabs/Marginal`: local compiler, cache, outbox, lifecycle integration, diagnostics, and
  configuration.

## Closed wire contract

The contribution envelope contains only:

```text
schema_version = 1.0
model_namespace = exact value from canonical-model-registry-v1
atoms[] = closed aggregate dimensions and bounded observation counts
```

A one-time random base64url retry token is carried only in the `Idempotency-Key` HTTP header. It is
hashed immediately and never enters an envelope, response, GitHub commit, or Commons pack.

Each atom contains the reviewed `AGGREGATE_EXPORT` dimensions with closed enums:
`record_type`, `action_kind`, `cost_bucket`, `gain_bucket`, `recommendation`,
`applied_decision`, the existing aggregate-export reason class, `outcome_class`, and `count`. There are no timestamps,
identifiers, hashes, metadata objects, free-text values, repository information, or extension
fields. Unknown fields are rejected recursively.

## Canonical model identity

Codex supplies an untrusted `model` string and no provider or deployment provenance. It is safe
only when an exact string appears in MARGINAL's reviewed, versioned public-model registry and the
adapter supplies the provider (`openai`). No case folding, prefix matching, alias expansion, or
user-defined entry is allowed. Unknown, custom, private, fine-tuned, conflicting, or ambiguous
model identities remain local and produce no contribution.

The initial registry includes only exact public identifiers verified in official OpenAI
documentation on 2026-08-20. Registry changes require code review and tests.

## Ingress

`POST /v1/evidence` enforces content type, byte limit, strict schema, and the model registry before
any sink call. `GET /healthz` returns static health metadata and no request-derived data. Responses
never echo evidence. Production Wrangler configuration sets `observability.enabled=false` and
disables invocation logs explicitly. Source contains no request-specific logging.

A single Durable Object serializes GitHub aggregate updates and stores only short-lived digests of
one-time idempotency keys plus a pending write descriptor. The pending descriptor contains the
target aggregate path and expected Git blob digest, not raw envelopes. After an uncertain retry,
the coordinator reconciles the expected blob against GitHub before applying another increment.
GitHub writes use the current blob SHA and bounded 409 retry. The service credential is a
least-privilege secret with Commons Contents write access; contributor credentials are never used.

## Commons

Commons persists aggregate knowledge, never envelopes. New observations create or update
`candidate` aggregates. Counts cannot advance lifecycle. `supported`, `validated`, and `promoted`
require checked-in validation artifacts and deterministic validation rules. Every lifecycle state
remains a prior and cannot grant local authority.

The deterministic JSON pack sorts all namespaces and aggregates, contains schema compatibility,
Commons revision, source commit, and a SHA-256 digest over the canonical payload excluding the
digest field. Consumers reject malformed/incompatible packs and retain the previous valid cache.

## MARGINAL client

Persistent user configuration has three explicit modes:

- `local_only`: zero Commons network calls; default for new and existing installations.
- `read_only`: bounded pack download only.
- `contributor`: bounded download plus automatic safe contribution.

At `SessionStart`, enabled modes retry a valid outbox and refresh the pack cache. At `SessionEnd`,
all modes atomically finalize local memory. Contributor mode then compiles only verified,
model-attributable local records into closed atoms, writes an owner-only durable outbox envelope,
and attempts bounded synchronization. Empty or unsafe compilation performs no request.

Network, schema, filesystem, DNS, TLS, GitHub, and Cloudflare failures never block Codex and never
change enforcement state. Malformed queued files are quarantined. ACK removes the exact queued
file; retryable failures retain it.

## Authority boundary

Commons priors are loaded through a separate read-only path and are not passed into coverage,
trust, promotion, Autopilot counters, Decision Ledger hashes, or enforcement eligibility. Local
observations override Commons priors. Candidate through promoted Commons evidence independently
has zero enforcement authority.

## Acceptance

Synthetic tests must prove SessionEnd → outbox → Ingress → Commons → next SessionStart, model
isolation, no privacy canary in serialized or persisted data, retry idempotency, offline recovery,
and zero enforcement effect. Production deployment is reported only if Wrangler authentication and
the dedicated GitHub service credential are both verified.
