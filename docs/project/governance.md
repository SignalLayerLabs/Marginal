# Governance

MARGINAL begins as a SignalLayer Labs-led open-source project.

## Decision process

- routine fixes and documentation changes use normal pull-request review;
- public API changes require rationale, compatibility notes, and tests;
- policy, ledger, protocol, schema, or privacy-profile changes require a design discussion before implementation;
- benchmark claims require reproducible evidence and independent review when practical;
- security-sensitive fixes may be developed privately before coordinated disclosure;
- shareable telemetry changes require an explicit field-classification and quasi-identifier review.

## Compatibility

Semantic Versioning applies to the Python public API. Trace records include explicit event
names and are designed for additive evolution. Breaking trace or API changes require a
major release after `1.0.0`.

## Maintainer responsibilities

Maintainers protect technical integrity, transparent claims, contributor safety, and a
small dependency-free core. Project influence follows sustained, reviewed contribution
rather than employer or commercial status.

## Privacy governance

The operational Decision Ledger and shareable telemetry are separate products with separate contracts. `LOCAL_FULL` may retain caller-controlled local evidence; `SAFE_TELEMETRY` is a strict allowlist with keyed pseudonyms; `AGGREGATE_EXPORT` contains generalized grouped rows only. Unknown fields are treated as potentially sensitive.

A change may not weaken a privacy profile silently. Any newly retained field requires tests, documentation, schema updates where applicable, and a migration or compatibility note. Pseudonymized data must never be described as anonymous.
