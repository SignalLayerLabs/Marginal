# Quickstart

## Native agent integrations

MARGINAL starts conservatively. Codex installs in Shadow Mode before any earned tool enforcement;
Claude Code, OpenCode, and PrivacyCode are **Observe-only** and cannot block.

```bash
# Codex native plugin
codex plugin marketplace add SignalLayerLabs/Marginal --ref main
codex plugin add marginal@marginal

# With the MARGINAL Python CLI installed
marginal install claude-code
marginal install opencode
marginal install privacycode
```

Remove an integration with its matching uninstall command. See the
[integration overview](../integrations/overview.md) for capability and evidence limits.

## Python library / development install

```bash
python -m pip install -e ".[dev]"
```

For the native Codex plugin, Commons remains Local Only unless you explicitly choose otherwise:

```bash
marginal install codex                              # local_only; no Commons network calls
marginal install codex --commons-mode read_only    # verified pack download only
marginal install codex --commons-mode contributor  # download plus closed aggregate submission
```

Contributor mode sends no prompt, source, command, output, repository data, local hash, timestamp,
free text, or persistent identity. Its Cloudflare transport is not an anonymity boundary, and
Commons priors never affect local Tool Enforcement. Production contribution remains unavailable
until both Wrangler authentication and a dedicated least-privilege GitHub service credential are
verified.

## Shadow first

```python
from marginal import (
    Action,
    BudgetLimits,
    Cost,
    DecisionLedgerContext,
    JsonlDecisionLedger,
    Treasury,
    budgeted_call,
    build_policy,
    generate_local_identifier,
)

ledger = JsonlDecisionLedger(
    "ledger.jsonl",
    context=DecisionLedgerContext(
        run_id=generate_local_identifier("run"),
        task_id=generate_local_identifier("task"),
        engine="generic",
    ),
    privacy_profile="safe_telemetry",
    privacy_key_path=".marginal/privacy.key",
)

treasury = Treasury(
    BudgetLimits(max_tokens=20_000, verification_reserve_tokens=2_000),
    policy=build_policy("quality-first"),
    trace_sink=ledger,
    mode="shadow",
)

result = budgeted_call(
    treasury,
    lambda: "done",
    action=Action(
        name="draft answer",
        kind="generation",
        cost=Cost(tokens=2_000),
        expected_gain=0.10,
    ),
)
```

Inspect the evidence:

```bash
marginal ledger-validate ledger.jsonl
marginal ledger-report ledger.jsonl
marginal replay ledger.jsonl --profile balanced
marginal ledger-export ledger.jsonl aggregate.jsonl --privacy-profile aggregate_export \
  --minimum-group-size 5
```

`safe_telemetry` excludes free text and pseudonymizes identifiers. Use `local_full` only for a
trusted operational ledger. Use `aggregate_export` when preparing grouped data for sharing; groups
smaller than five records are suppressed by default.
Pseudonymization is not anonymization; read [`privacy.md`](../operations/privacy.md) before export.

Move to `recommend` when recommendations are surfaced to a user or agent. Move to `enforce` only after representative validation shows acceptable quality.

## Engine adapters

Use `UniversalRuntime` when integrating a development agent. Enforce Mode requires an adapter that declares real action-blocking capability. The reference runtime currently maps core decisions to allow or deny; other protocol directives are extension points.

See [`universal-runtime.md`](../product/architecture.md) and the executable examples in [`examples`](../../examples).
