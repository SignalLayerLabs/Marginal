# Privacy Profiles Design

## Objective

Protect MARGINAL Decision Ledger evidence from quasi-identifier and free-text disclosure
without weakening the local operational record or adding a mandatory runtime dependency.

The privacy boundary is the Decision Ledger serializer and export path. It does not claim to
sanitize arbitrary application logs, provider SDK traces, or caller-owned files.

## Threat model

A record can disclose sensitive context without containing prompts or model outputs. Examples
include customer-derived task IDs, repository names, action descriptions, model identities,
verifier details, tool arguments, exception text, and exact timestamps.

The design assumes:

- the host process and local filesystem account are trusted;
- pseudonymization keys remain local and separate from exported datasets;
- exported files may be shared with parties that must not receive the source identifiers;
- unknown fields are sensitive until reviewed explicitly;
- pseudonymization reduces direct disclosure but does not provide anonymity.

## Field classification

Every supported field belongs to one of three classes:

- **Safe by default:** structured economic, decision, outcome, and version fields;
- **Pseudonymous:** correlation identifiers transformed with a local keyed construction;
- **Potentially sensitive:** free text, arbitrary metadata, complete model identity, verifier
  details, tool arguments, error text, and other caller-defined content.

`FIELD_CLASSIFICATION` is immutable. `classify_field(...)` inherits classifications from
reviewed parent paths and treats every unknown path as potentially sensitive.

## Privacy profiles

### LOCAL_FULL

Preserves the complete operational record. It is the backward-compatible default and may
contain sensitive caller data. New files use owner-only permissions on POSIX systems.

### SAFE_TELEMETRY

Uses an explicit allowlist. It:

- removes free-form and arbitrary metadata fields;
- pseudonymizes event, run, task, trajectory, action, fingerprint, state, and engine-instance
  identifiers with field-separated HMAC-SHA-256;
- generalizes timestamps to UTC day boundaries;
- normalizes engine, event, action-kind, mode, directive, and reason-code labels;
- retains only allowlisted finite numeric fields and validates their ranges;
- retains only version-like policy and estimator identities;
- validates every record on read against the same canonical transformation;
- publishes a recursively strict JSON Schema with no unknown fields.

Pseudonyms use 128 bits of the HMAC digest and are stable only for the same key and field
name. Different keys produce unlinkable export domains.

### AGGREGATE_EXPORT

Is not an operational ledger mode. It groups decisions and outcomes into generalized
categories and emits no identifiers, timestamps, free text, metadata, model identity, or
verifier details. The output remains vulnerable to inference from rare groups, so consumers
must apply organizational minimum-group and retention rules before publication.

## Key and filesystem handling

Generated keys contain 256 random bits. On supported POSIX filesystems they are created with
mode `0600`. Existing key files must be regular, non-symlink files and must not be accessible
by group or other users. Existing keys are read from a validated descriptor to prevent path
replacement between validation and read.

Decision Ledger append targets reject symbolic links, non-regular files, and permissive POSIX
modes. Export destinations are created exclusively and are never overwritten, including if a
competing process creates the destination after an earlier existence check.

## Data flow

```text
Treasury event
    │
    ▼
Decision Ledger envelope
    │
    ├─ LOCAL_FULL ───────► complete local JSONL
    │
    └─ SAFE_TELEMETRY ───► allowlist → pseudonymize → generalize → validate → JSONL

Existing operational ledger
    │
    └─ export_decision_ledger
           ├─ SAFE_TELEMETRY ─► unlinkable event-level export
           └─ AGGREGATE_EXPORT ► grouped shareable rows
```

## Public contracts

- `PrivacyProfile`
- `PrivacyClass`
- `PrivacyConfig`
- `LocalPseudonymizer`
- `FIELD_CLASSIFICATION`
- `classify_field(...)`
- `generate_local_identifier(...)`
- `load_or_create_privacy_key(...)`
- `sanitize_ledger_record(...)`
- `validate_safe_telemetry_record(...)`
- `aggregate_ledger_records(...)`
- `export_decision_ledger(...)`
- `safe-telemetry-v1.json`
- `aggregate-export-v1.json`

## Non-goals

The profiles do not provide encryption at rest, differential privacy, k-anonymity,
cryptographic tamper evidence, distributed locking, regulatory certification, or protection
against a party that possesses both the source values and pseudonymization key.

## Acceptance criteria

- Sensitive fixture strings never appear in strict or aggregate exports.
- Pseudonyms are deterministic per field/key and unlinkable across keys.
- Unknown fields are removed from strict telemetry and rejected on read.
- Strict records conform to the packaged schema.
- Aggregate rows conform to their packaged schema and contain no identifiers.
- Key, ledger, and export filesystem hardening has regression tests.
- Public API, CLI, README, security guide, privacy guide, roadmap, and changelog describe the
  same implemented behavior.
