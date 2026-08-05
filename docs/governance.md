# Governance

MARGINAL begins as a SignalLayer Labs-led open-source project.

## Decision process

- routine fixes and documentation changes use normal pull-request review;
- public API changes require rationale, compatibility notes, and tests;
- policy or trace format changes require a design discussion before implementation;
- benchmark claims require reproducible evidence and independent review when practical;
- security-sensitive fixes may be developed privately before coordinated disclosure.

## Compatibility

Semantic Versioning applies to the Python public API. Trace records include explicit event
names and are designed for additive evolution. Breaking trace or API changes require a
major release after `1.0.0`.

## Maintainer responsibilities

Maintainers protect technical integrity, transparent claims, contributor safety, and a
small dependency-free core. Project influence follows sustained, reviewed contribution
rather than employer or commercial status.
