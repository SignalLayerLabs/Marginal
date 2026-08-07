# Security Policy

## Supported versions

Security fixes are provided for the latest released minor version. Users should upgrade to the newest `0.x` release because the public API may still evolve before `1.0.0`.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub Security Advisories for `SignalLayerLabs/Marginal`. Do not open a public issue for credential exposure, arbitrary code execution, path traversal, ledger tampering, unsafe installer behavior, or sensitive-data disclosure.

Include the affected version, platform, minimal reproduction, impact, and suggested mitigation. Do not include real credentials, private prompts, proprietary source code, or personal data.

## Data handling and privacy profiles

MARGINAL is local-first, has no mandatory cloud account, and the core does not transmit data.
Callers control trace paths, ledger paths, identifiers, metadata, and retention. Local storage is
still a security boundary: access controls, backups, synchronization tools, and developer
workstations can expose a ledger.

The primary privacy risk is not limited to prompts. Quasi-identifiers and free text can reveal a
customer, repository, task, model, or incident even when prompt and output fields are absent.
Prefer opaque values from `generate_local_identifier(...)` when external identity is not needed.
Examples include task IDs, action names, model identity, repository metadata, verifier names,
tool arguments, exception text, and exact timestamps.

MARGINAL provides three profiles:

- `LOCAL_FULL` preserves the complete operational record and is the backward-compatible default;
- `SAFE_TELEMETRY` removes free text and metadata, pseudonymizes identifiers using a local
  HMAC-SHA-256 key, generalizes exact timestamps, and retains only allowlisted structured fields;
- `AGGREGATE_EXPORT` groups generalized decision and outcome rows, contains no identifiers or
  timestamps, and suppresses groups smaller than five records by default. It is an export format,
  not an operational ledger mode.

Pseudonymization is not anonymization. Stable pseudonyms can be linked within one key domain,
rare patterns can still identify a workload. Aggregate export applies a configurable minimum
group size of five by default, but this threshold is not a proof of anonymity or formal
k-anonymity. The profiles do not provide differential privacy, encryption at rest, compliance
certification, or protection against a party that has both the source values and local key.

Generated privacy keys contain 256 random bits, are created with owner-only permissions on POSIX
systems, and are never written into ledger records. Symbolic-link key paths and overly permissive
existing key files are rejected. Keep keys out of source control and do not distribute an
operational key with an exported dataset. The default ignore rules exclude `*.privacy.key` and
`.marginal/`.

Applications can still write sensitive data to `JsonlTraceSink`, `LOCAL_FULL` ledgers, custom
files, logs outside MARGINAL, or downstream systems. `SAFE_TELEMETRY` is a strict allowlist at the
Decision Ledger boundary; it does not sanitize arbitrary external logs. Review
[`docs/operations/privacy.md`](docs/operations/privacy.md) before sharing evidence.

Protocol metadata used for automatic fingerprints must be deterministically JSON serializable.
This rejects ambiguous custom-object representations, but it does not make the source metadata
safe. Fingerprints are identifiers, not secrets; the strict profile re-pseudonymizes them with a
keyed construction because low-entropy hashes can be guessed.

## Adapter trust boundary

Engine adapters can observe or control agent actions. Install adapters only from trusted sources, review configuration changes, and use least privilege. An adapter must disclose whether it can block actions, modify actions, stop the agent, observe model usage, or access source code.

Capability negotiation prevents an adapter from claiming unsupported controls accidentally, but it is not a sandbox or an authorization system. The host application remains responsible for validating and applying adapter decisions safely.

## Ledger integrity and concurrency

`JsonlDecisionLedger` is append-only at the application level and uses a process-local lock. It is not a cryptographic audit log and does not provide multi-process or distributed atomicity. Filesystem users can modify it, and two independent processes must not append to the same ledger without an external coordinator.

`CompositeTraceSink` invokes sinks sequentially. It does not provide a distributed transaction across sinks. A later sink can fail after an earlier sink has accepted an event.

Environments requiring tamper evidence, cross-process coordination, or compliance-grade retention should add immutable storage, external locking, signing, or hash chaining before treating the ledger as authoritative evidence.

## Failure behavior

Shadow and Recommend modes are intentionally non-blocking. Enforce Mode can deny actions. Integrations must document what happens if the runtime, ledger, or trace sink is unavailable.

Failed provider or tool calls may still consume resources. A failure usage extractor should return measured or best-known usage when available. If extraction itself fails, the built-in wrappers conservatively settle the reserved estimate, preserve the original execution exception as primary, and chain the extraction failure for diagnosis. Failed actions are accounted but are not marked as successfully completed duplicates, so a legitimate retry remains possible.

## Replay and scientific claims

Policy replay evaluates recorded actions under another policy. It does not execute the omitted counterfactual trajectory, establish causality, or prove quality preservation. Security, compliance, or safety decisions must not treat replay output as causal evidence.
