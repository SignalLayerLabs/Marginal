# Privacy profiles

MARGINAL is local-first and has no mandatory network service, but locality alone does not
make telemetry safe to share. Identifiers, action names, model names, repository labels,
error text, verifier details, and caller metadata can reveal sensitive information even when
prompts and model outputs are absent.

MARGINAL therefore classifies evidence fields and provides three explicit privacy profiles.

## Field classes

### Safe by default

These fields are structured and retained by `safe_telemetry`:

- generic event and action kind;
- estimated and actual cost;
- token breakdown and latency;
- applied and recommended decisions;
- stable reason codes;
- structured task reward and resolved status;
- policy and estimator versions;
- confidence, uncertainty, score, and schema version.

Arbitrary strings are normalized or replaced with a generic value. Numeric sub-objects use
an allowlist, so custom metric names are not copied accidentally.

### Pseudonymous

These fields are transformed with field-separated HMAC-SHA-256 under a local key:

- event, run, task, trajectory, and action identifiers;
- action fingerprints and state hashes;
- other explicit engine-instance identifiers when adapters expose them.

Exact timestamps are generalized to UTC day boundaries. Pseudonyms are stable only for the
same key and field name. Different keys produce unlinkable identifiers.

When external correlation is unnecessary, prefer opaque random IDs from
`generate_local_identifier("run")`, `generate_local_identifier("task")`, or another simple
namespace. Random local IDs avoid embedding customer or project names before sanitization.

### Potentially sensitive

The strict profile excludes:

- free-form action names;
- complete model identity;
- metadata, tags, tool arguments, and replacement payloads;
- error, exception, abort, and failure text;
- human-readable policy reasons;
- verifier identity, evidence, and custom outcome metrics;
- treasury names and estimator training-data fingerprints.

## Profiles

### `LOCAL_FULL`

`local_full` is the backward-compatible default. It preserves the complete operational
Decision Ledger record. Use it only where the ledger path and filesystem access are trusted.
Caller-provided metadata remains caller responsibility.

```python
ledger = JsonlDecisionLedger(
    "ledger.jsonl",
    context=DecisionLedgerContext(run_id="local-run"),
    privacy_profile="local_full",
)
```

### `SAFE_TELEMETRY`

`safe_telemetry` removes free text and metadata, pseudonymizes identifiers, generalizes exact
timestamps, and keeps only allowlisted structured fields. Every strict record is validated when read through `read_decision_ledger(...)` and can also be
checked explicitly with `validate_safe_telemetry_record(...)`. The packaged
`safe-telemetry-v1.json` schema rejects unknown fields recursively.

```python
ledger = JsonlDecisionLedger(
    "safe-ledger.jsonl",
    context=DecisionLedgerContext(
        run_id="customer-acme-contract-2026",
        task_id="customer-acme-contract-2026",
        engine="codex",
        model="internal-legal-model",
    ),
    privacy_profile="safe_telemetry",
    privacy_key_path=".marginal/privacy.key",
)
```

New ledger and export files are created with owner-only permissions on POSIX systems. Existing
ledger append targets must be regular files, must not be symbolic links, and must not be accessible
by group or other users. When no key or key path is supplied, the ledger creates an owner-only
hidden key beside the ledger.
Generated keys contain 256 random bits and are never written into ledger records.
Keep the key outside version control and backups intended for sharing.

An existing key file must be a regular file and, on POSIX systems, must not be readable by
group or other users. Symbolic-link key paths are rejected.

### `AGGREGATE_EXPORT`

`aggregate_export` is deliberately separate from operational ledger persistence. It groups
generalized decision and outcome rows, removes all identifiers and timestamps, and suppresses
any group containing fewer than five source records by default. The threshold is configurable
and is recorded in every emitted row.

```bash
marginal ledger-export ledger.jsonl aggregate.jsonl \
  --privacy-profile aggregate_export --minimum-group-size 5
```

A grouped decision row contains only fields such as:

```json
{
  "schema_version": "1.0",
  "privacy_profile": "aggregate_export",
  "record_type": "decision",
  "action_kind": "verification",
  "cost_bucket": "low",
  "gain_bucket": "medium",
  "recommendation": "deny",
  "applied_decision": "allow",
  "reason_code": "SHADOW_OVERRIDE",
  "outcome_class": "not_applicable",
  "count": 12,
  "minimum_group_size": 5
}
```

Small groups are omitted entirely. Raising `--minimum-group-size` reduces disclosure risk but
can remove more data. Lowering it below five is intended only for controlled local analysis and
should not be treated as anonymous sharing. Default buckets are deterministic:

- cost: `low` up to 2,000 tokens, USD 0.02, and 1 second; `medium` up to 10,000
tokens, USD 0.20, and 10 seconds; otherwise `high`;
- expected gain: `low` below 0.10, `medium` below 0.30, otherwise `high`.

## Exporting an existing ledger

Create a new unlinkable safe export by using a dedicated export key:

```bash
marginal ledger-export ledger.jsonl safe-export.jsonl \
  --privacy-profile safe_telemetry \
  --privacy-key-file .marginal/export.key
```

The API equivalent is:

```python
from marginal import export_decision_ledger

export_decision_ledger(
    "ledger.jsonl",
    "safe-export.jsonl",
    privacy_profile="safe_telemetry",
    privacy_key_path=".marginal/export.key",
)
```

Exports create the destination with an exclusive filesystem operation and never overwrite an
existing path, including when another process creates the destination after the initial check. This
prevents accidental replacement of an authoritative ledger or a previously reviewed dataset.

## Threat model and limitations

Pseudonymization is not anonymization. Stable pseudonyms can still be linkable within one
export, rare action patterns can identify a workload, and small aggregate groups may permit
inference. The profiles do not provide differential privacy, k-anonymity, encryption at rest,
cryptographic tamper evidence, multi-process locking, or compliance certification.

Before sharing data:

1. prefer `aggregate_export` over event-level telemetry;
2. inspect the generated file;
3. use a new export key rather than an operational key;
4. raise the default minimum group size when the dataset or population is small;
5. avoid combining exports with external datasets that restore identity;
6. treat source ledgers and pseudonymization keys as sensitive assets.

The public classification map is available as `FIELD_CLASSIFICATION`. `classify_field(...)`
inherits reviewed classifications for nested fields such as `action.cost.tokens`, while unknown
paths default to potentially sensitive. Applications may use the map for UI explanations or
additional validation, but custom event fields are excluded by the strict profile unless MARGINAL
explicitly allowlists them.

Use `load_schema("safe-telemetry-v1.json")` and
`load_schema("aggregate-export-v1.json")` to validate shareable outputs from an installed wheel.
