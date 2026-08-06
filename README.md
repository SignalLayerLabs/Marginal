<div align="center">

<img src="assets/marginal-readme-hero.png" alt="MARGINAL — Compute capital allocation for AI agents" width="100%">

<br>

[![CI](https://github.com/SignalLayerLabs/Marginal/actions/workflows/ci.yml/badge.svg)](https://github.com/SignalLayerLabs/Marginal/actions/workflows/ci.yml)
[![CodeQL](https://github.com/SignalLayerLabs/Marginal/actions/workflows/codeql.yml/badge.svg)](https://github.com/SignalLayerLabs/Marginal/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/SignalLayerLabs/Marginal?style=flat-square)](https://github.com/SignalLayerLabs/Marginal/releases)
[![Python 3.10–3.13](https://img.shields.io/badge/python-3.10--3.13-blue.svg?style=flat-square)](https://www.python.org/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg?style=flat-square)](LICENSE)
[![Zero runtime dependencies](https://img.shields.io/badge/runtime%20dependencies-0-brightgreen.svg?style=flat-square)](pyproject.toml)

</div>

---

MARGINAL is an open-source decision, accounting, and evidence layer for AI agents. It evaluates proposed model calls, tool calls, searches, retries, reviewers, and sub-agents before they run, then accounts for what actually happened.

> **Hard budgets ask “can we afford this?” MARGINAL also asks “is this worth funding?”**

Version `0.2.0` adds the **Learning Loop Foundation**: Shadow Mode, a versioned Decision Ledger, explicit privacy profiles, measured outcome contracts, versioned value estimators, policy replay, and a universal engine-neutral runtime for future Codex, Claude Code, GitHub Copilot, OpenCode, and other adapters.

MARGINAL does not compress prompts or replace an agent framework. It can eliminate entire low-value actions before they consume tokens, or observe them without interference while evidence is collected.

## Why this exists

Agent runtimes commonly execute the next step because it appears in a workflow, a model requested it, or a hard limit has not yet been reached. Those mechanisms answer whether work is permitted; they do not compare the expected improvement of the next action with its total economic cost.

MARGINAL adds that allocation layer while keeping execution and evidence explicit:

- rank candidate actions by marginal value;
- reserve budget before execution and settle actual usage afterward;
- protect verification capacity;
- prevent concurrent double-spend and state-insensitive duplicates;
- observe recommendations without blocking through Shadow Mode;
- record versioned policy, estimator, cost, failure, and outcome evidence;
- protect quasi-identifiers and free text through explicit privacy profiles;
- support provider-neutral synchronous, asynchronous, and engine-adapter integrations;
- keep the runtime core free of mandatory dependencies.

## What changed in v0.2

### Shadow Mode

Shadow Mode evaluates every proposed action but never blocks it:

```text
agent proposes action
        ↓
MARGINAL recommends allow or deny
        ↓
action still executes
        ↓
actual cost and verified outcome are recorded
```

This is the safe default for collecting evidence before enforcement.

### Decision Ledger

`JsonlDecisionLedger` records schema-versioned, append-only evidence with:

- run, task, trajectory, engine, and model identity;
- policy and estimator versions;
- recommended versus applied decisions;
- estimated and actual costs;
- failures, overruns, observations, and outcomes;
- deterministic sequence numbers for replay and audit.

Prompts and model outputs are not recorded by default. That alone is not sufficient for safe
sharing: task IDs, action names, model identity, repository metadata, verifier details, and
error text can still reveal sensitive information.

### Privacy profiles

Every Decision Ledger field is treated as safe-by-default, pseudonymous, or potentially
sensitive. MARGINAL provides three explicit profiles:

- `LOCAL_FULL` preserves the complete operational ledger on a trusted local filesystem;
- `SAFE_TELEMETRY` removes free text and metadata, pseudonymizes identifiers with a local
  HMAC-SHA-256 key, and generalizes exact timestamps;
- `generate_local_identifier(...)` creates opaque random local IDs when correlation with
  external names is unnecessary;
- `AGGREGATE_EXPORT` creates grouped generalized rows with no identifiers or timestamps and
  suppresses groups smaller than five records by default.

`aggregate_export` is a separate export path, not an operational ledger mode. Its default
minimum group size is five and can be raised for more conservative sharing. Pseudonymization
is not anonymization; inspect data before sharing it. See [Privacy profiles](docs/privacy.md).

### Versioned Value Estimator

`ValueEstimator` now returns `ValueEstimate` objects with expected gain, uncertainty, confidence, sample size, provenance, and a stable estimator identity. Explicit caller estimates remain supported, and historical observations can be contextualized by engine, phase, task type, language, and model.

MARGINAL does **not** infer that every action caused a successful task. Action-level realized gain must be supplied explicitly through `Treasury.observe_value(...)`.

### Universal Agent Protocol

`AgentAction`, `AgentEvent`, `AgentDecision`, `AgentCapabilities`, and `UniversalRuntime` provide the shared contract for thin engine adapters. Engine-specific code translates native events; the economic policy remains in one core.

The versioned JSON contracts ship inside the installed package as well as in the repository:

```python
from marginal import available_schemas, load_schema

print(available_schemas())
event_schema = load_schema("agent-event-v1.json")
```

## Install

Install the tagged GitHub release:

```bash
pip install "marginal-ai @ git+https://github.com/SignalLayerLabs/Marginal.git@v0.2.0"
```

For development:

```bash
git clone https://github.com/SignalLayerLabs/Marginal.git
cd Marginal
python -m pip install -e ".[dev]"
```

## Five-minute enforced integration

```python
from marginal import Action, BudgetLimits, Cost, Treasury, budgeted_call, build_policy

policy = build_policy("balanced")
treasury = Treasury(
    BudgetLimits(
        max_tokens=100_000,
        max_usd=2.00,
        verification_reserve_tokens=10_000,
    ),
    policy=policy,
    mode="enforce",
)

response = budgeted_call(
    treasury,
    your_expensive_function,
    "input",
    action=Action(
        name="research missing evidence",
        kind="research",
        cost=Cost(tokens=4_000, usd=0.04, latency_ms=1_500),
        expected_gain=0.12,
    ),
)
```

The wrapped function is never called when enforcement denies the action. Approved estimates are reserved immediately, preventing parallel actions from oversubscribing the same treasury.

## Fund the best next action

```python
allocation = treasury.fund_best(
    [
        Action(
            name="search the web",
            kind="research",
            cost=Cost(tokens=6_000, usd=0.06),
            expected_gain=0.05,
        ),
        Action(
            name="run the targeted test",
            kind="verification",
            cost=Cost(tokens=800, usd=0.002),
            expected_gain=0.18,
            is_verification=True,
        ),
    ]
)

if allocation is not None:
    result = funded_call(treasury, allocation, execute, allocation.action)
```

`fund_best` evaluates candidates against one locked state, records the full ranking, and reserves only the highest-value affordable candidate. It remains an active selection API in every execution mode.

## Use measured provider usage

```python
response = budgeted_call(
    treasury,
    client.responses.create,
    action=action,
    usage_extractor=extract_common_llm_usage,
    model="YOUR_MODEL",
    input="Draft the answer.",
)
```

The total-token extractor preserves direct USD, latency, and risk values that a provider response does not expose consistently. `extract_common_token_usage` provides the additive input, cached-input, non-reasoning output, reasoning, and total breakdown.

Async callables use the same lifecycle:

```python
response = await async_budgeted_call(
    treasury,
    client.responses.create,
    action=action,
    usage_extractor=extract_common_llm_usage,
    **request,
)
```

## Start safely with Shadow Mode

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
)

ledger = JsonlDecisionLedger(
    "marginal-ledger.jsonl",
    context=DecisionLedgerContext(
        run_id="run-001",
        task_id="task-042",
        trajectory_id="baseline-a",
        engine="codex",
        model="your-model",
    ),
    privacy_profile="safe_telemetry",
    privacy_key_path=".marginal/privacy.key",
)

treasury = Treasury(
    BudgetLimits(max_tokens=50_000, verification_reserve_tokens=5_000),
    policy=build_policy("quality-first"),
    trace_sink=ledger,
    mode="shadow",
)

result = budgeted_call(
    treasury,
    your_expensive_function,
    action=Action(
        name="ask another reviewer",
        kind="review",
        cost=Cost(tokens=5_000),
        expected_gain=0.01,
    ),
)
```

Even when the policy recommendation is deny, Shadow Mode executes the callable, records the non-blocking override, and accounts for actual usage.

## Record verified outcomes and action-level learning

```python
from marginal import Action, Outcome

# Task outcome: evidence about the trajectory as a whole.
treasury.record_outcome(
    Outcome(
        task_id="task-042",
        reward=1.0,
        resolved=True,
        verifier="pytest",
        evidence={"suite": "tests/test_payment.py"},
    )
)

# Action-level realized gain: supplied only when the application can justify it.
treasury.observe_value(
    Action(name="run targeted test", kind="verification"),
    realized_gain=0.18,
)
```

Task outcomes and action-level realized gain are deliberately separate. A passing task alone does not establish the causal value of every action in its trajectory.

## Universal runtime for engine adapters

```python
from marginal import AgentAction, AgentCapabilities, Cost, UniversalRuntime

runtime = UniversalRuntime(
    treasury,
    engine="opencode",
    session_id="session-1",
    task_id="task-42",
    capabilities=AgentCapabilities(
        observe_model_usage=True,
        block_actions=True,
        record_outcomes=True,
    ),
)

decision = runtime.before_action(
    AgentAction(
        action_id="read-1",
        name="read complete repository",
        kind="file_read",
        estimated_cost=Cost(tokens=8_000),
        expected_gain=0.03,
        state_hash="workspace-sha",
        phase="diagnose",
        deduplication_scope="once_per_state",
    )
)

# The adapter applies the decision, executes when allowed, then settles actual usage.
runtime.after_action("read-1", actual_cost=Cost(tokens=6_400))
```

`UniversalRuntime` in `enforce` mode requires an adapter that declares `block_actions=True`; MARGINAL refuses to advertise enforcement through an observe-only integration.

Protocol v1 defines `allow`, `deny`, `modify`, `defer`, `reuse`, `stop`, and `force_verify` directives so adapters can negotiate future control surfaces consistently. The v0.2 reference runtime currently derives `allow` and `deny` from the core decision; richer directives remain adapter and policy extension points and are not claimed as automatic behavior.

## Measured token breakdown

```python
from marginal import extract_common_token_usage

usage = extract_common_token_usage(response)
print(usage.input_tokens)
print(usage.cached_input_tokens)
print(usage.output_tokens)
print(usage.reasoning_tokens)
print(usage.total_tokens)
```

The normalized fields are additive: `input_tokens` means uncached input, while cached input is reported separately.

## Failed calls that still consumed resources

Some provider calls fail after compute was consumed. Supply a failure usage extractor to keep accounting truthful while preserving the original exception:

```python
result = budgeted_call(
    treasury,
    client.responses.create,
    action=action,
    failure_usage_extractor=lambda error, estimate: measured_or_best_known_cost(error),
    **request,
)
```

Returning `None` means no external spend was observed and releases the reservation. Returning `Cost` settles the failed action.

## Policy replay

```bash
marginal ledger-validate marginal-ledger.jsonl
marginal ledger-report marginal-ledger.jsonl
marginal replay marginal-ledger.jsonl --profile balanced
marginal ledger-export marginal-ledger.jsonl safe-export.jsonl \
  --privacy-profile safe_telemetry --privacy-key-file .marginal/export.key
marginal ledger-export marginal-ledger.jsonl aggregate.jsonl \
  --privacy-profile aggregate_export --minimum-group-size 5
```

Replay re-evaluates recorded proposed actions under another policy. It is an off-policy diagnostic based on recorded actions and costs. It is **not causal proof**, does not simulate missing trajectories, and does not establish preserved task quality.

## Execution modes

| Mode | Applied behavior | Intended use |
|---|---|---|
| `shadow` | Execute every proposed action; record recommendation | Safe data collection and calibration |
| `recommend` | Execute every proposed action; surface recommendation | Human/agent advisory integrations |
| `enforce` | Apply allow/deny and hard-budget decisions | Validated production control |

`fund_best` remains an active selection API in every mode because MARGINAL is explicitly being asked to choose among candidates.

## Reference policy profiles

```python
from marginal import build_policy

quality_first = build_policy("quality-first")
balanced = build_policy("balanced")
token_saver = build_policy("token-saver")
strict_budget = build_policy("strict-budget")
```

These are transparent reference defaults, not universally calibrated guarantees. Production policies should be validated against representative tasks and verifiers.

## Decision model

The reference policy converts configured dimensions into a common USD-denominated value:

```text
expected value = capped expected success gain × outcome value
cost value     = direct USD + token shadow cost + latency shadow cost + risk shadow cost
marginal score = expected value − cost value
ROI            = expected value ÷ cost value
```

A recommended action must remain affordable, preserve verification reserves, avoid an exact duplicate under the chosen fingerprint scope, remain below the success target, and clear expected-gain and ROI thresholds.

## Reliable accounting

```text
propose → evaluate → reserve → execute → settle actual cost
                              ↘ abort when no spend occurred
                              ↘ settle failure when spend occurred
```

If actual usage exceeds the reservation, MARGINAL records the real spend first. Enforce mode then raises `BudgetOverrun`. Shadow and recommend modes record the observed overrun without changing caller behavior.

If a failure usage extractor itself fails, MARGINAL conservatively settles the reserved estimate, releases the reservation, and keeps the original execution exception primary. A measured failed action is not marked as a completed duplicate, so a legitimate retry remains possible.

## Duplicate protection and state-aware retries

Guarded call fingerprints include the action, callable identity, arguments, and keyword arguments. Universal-agent actions additionally support:

- `exact`;
- `once_per_state`;
- `once_per_phase`;
- `allow_retry`.

This lets an adapter distinguish an accidental repeated read from a legitimate test rerun after the workspace changes. Shadow Mode can observe concurrent semantic duplicates without blocking them while still reserving and settling each execution separately.

## Hierarchical agent budgets

```python
root = Treasury(BudgetLimits(max_tokens=200_000, max_usd=5.0), mode="shadow")
research = root.child("research", BudgetLimits(max_tokens=40_000, max_usd=1.0))
verification = root.child(
    "verification",
    BudgetLimits(max_tokens=30_000, max_usd=0.75),
)
```

A child authorization reserves capacity from every ancestor under one shared lock. Settlement charges every level, preventing parallel sub-agents from oversubscribing a parent budget.

## Trace and inspect decisions

`JsonlTraceSink` preserves the v0.1 trace format. `JsonlDecisionLedger` is the strict v0.2 evidence format with schema, identity, sequencing, and correlation fields.

```bash
marginal validate marginal-trace.jsonl
marginal report marginal-trace.jsonl
marginal ledger-validate marginal-ledger.jsonl
marginal ledger-report marginal-ledger.jsonl
marginal ledger-export marginal-ledger.jsonl aggregate.jsonl \
  --privacy-profile aggregate_export --minimum-group-size 5
```

`LOCAL_FULL` is the backward-compatible ledger default. Use `SAFE_TELEMETRY` for strict
local telemetry and `AGGREGATE_EXPORT` for grouped sharing. Aggregate groups smaller than five
records are suppressed by default, and export destinations are never overwritten automatically.

A `CompositeTraceSink` can fan events to multiple sinks in order, but writes across different sinks are not an atomic distributed transaction. Use one authoritative ledger when atomic evidence is required.

## Killer Demo

The bundled deterministic demo still demonstrates the allocation mechanism:

```bash
marginal killer-demo --output killer-demo-output
```

It uses declared action-cost estimates and a deterministic verifier. It is not provider telemetry, a production benchmark, or a universal savings claim.

[Open the committed demo report →](demos/killer-demo/RESULTS.md)

## Synthetic benchmark

The bundled deterministic benchmark exercises policy, reservation, accounting, and reproducibility:

```bash
marginal demo
```

Its declared token, USD, and latency values are synthetic. The result tests mechanics and must not be presented as provider-measured savings.

## Public benchmarking

Real evaluations should compare the same model, task, tools, limits, and verifier with and without MARGINAL. The comparator accepts an explicit confidence level and preregistered quality margin:

```bash
marginal public-eval baseline.jsonl marginal.jsonl \
  --confidence-level 0.95 --quality-margin-pp 1.0
```

Report:

- resolved rate and confidence intervals;
- input, cached input, output, reasoning, and total tokens where available;
- direct cost, latency, tool calls, and sub-agent calls;
- cost per verified successful task;
- regressions and recoveries;
- policy and estimator identities;
- raw paired evidence without dropped failures.

Savings without preserved quality are not optimization.

See [`docs/public-benchmarks.md`](docs/public-benchmarks.md) and [`docs/benchmarking.md`](docs/benchmarking.md).

## How MARGINAL differs

| Category | Primary question | MARGINAL relationship |
|---|---|---|
| Hard budget / circuit breaker | Can this session spend more? | Complementary; MARGINAL also evaluates expected value |
| Model router | Which model should answer? | A model choice can be represented as a candidate action |
| Prompt compressor | Can this call use fewer tokens? | Complementary; MARGINAL may avoid the entire action |
| Workflow optimizer | Can a fixed flow be simplified? | MARGINAL makes state-aware online decisions |
| Observability | What was spent? | MARGINAL decides before spending and settles afterward |
| Decision Ledger | Why did policy behavior change? | Records versioned recommendation, application, cost, and outcome evidence |

## Core primitives

| Primitive | Responsibility |
|---|---|
| `Action`, `Cost`, `TokenUsage` | Describe proposed work and estimated or measured resources |
| `Decision`, `Allocation` | Expose applied behavior, recommendation, reason, score, and funded candidate |
| `BudgetLimits`, `BudgetLedger` | Enforce hard limits, reservations, and verification reserves |
| `MarginalPolicy`, `ValueEstimator` | Score expected marginal value with versioned identities |
| `Treasury` | Coordinate ranking, authorization, settlement, hierarchy, evidence, and outcomes |
| `JsonlDecisionLedger` | Persist strict, append-only learning-loop evidence with an explicit privacy profile |
| `PrivacyProfile`, `export_decision_ledger` | Pseudonymize safe telemetry or create grouped aggregate exports |
| `AgentAction`, `AgentDecision`, `AgentEvent` | Normalize engine-adapter communication |
| `UniversalRuntime` | Correlate one engine session with transactional core operations |
| `replay_ledger` | Compare policy recommendations over recorded actions without causal claims |

## Architecture

```text
AI development agent
        │ native hook/event
        ▼
thin engine adapter
        │ universal protocol
        ▼
UniversalRuntime → Treasury → policy → versioned estimator
        │              │
        │              ├─ reserve / settle / abort / failure settlement
        │              └─ Decision Ledger → privacy profile → outcome / replay / export
        ▼
allow / deny today; richer negotiated directives through protocol extensions
```

See [`docs/architecture.md`](docs/architecture.md).

## Project status

MARGINAL `v0.2.0` is the **Learning Loop Foundation**. It provides a universal protocol, local runtime, non-blocking shadow evaluation, schema-versioned evidence, explicit privacy profiles, outcome recording, contextual historical estimates, failure settlement, and off-policy replay.

It does not yet claim complete vendor-specific adapters, causal marginal-value estimation, automatic regret minimization, or guaranteed savings on arbitrary workloads. The next validation milestone is a real paired Codex integration using measured telemetry and a predefined quality non-inferiority criterion.

## Roadmap

The project remains one product and one repository. Future Codex, OpenCode, Claude Code, GitHub Copilot, and other integrations will be thin adapters over the same protocol and core.

[View the full product roadmap →](ROADMAP.md)

## Documentation

- [Quickstart](docs/quickstart.md)
- [Concepts](docs/concepts.md)
- [Architecture](docs/architecture.md)
- [API reference](docs/api.md)
- [Learning loop](docs/learning-loop.md)
- [Universal runtime](docs/universal-runtime.md)
- [Privacy profiles](docs/privacy.md)
- [Integrations](docs/integrations.md)
- [Benchmarking](docs/benchmarking.md)
- [Public benchmark protocol](docs/public-benchmarks.md)
- [Research and prior art](docs/research.md)
- [FAQ](docs/faq.md)
- [Governance](docs/governance.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## Research lineage

MARGINAL is an independent open-source reference implementation inspired by the research direction described in Siqi Zhu’s position paper, “Agentic AI Systems Should Be Designed as Marginal Token Allocators.” The paper proposes an economic framing; this repository focuses on a usable runtime contract, accounting, evidence, tests, integrations, and honest validation.

## Contributing

Contributions are welcome for adapters, estimator implementations, benchmark scenarios, schemas, documentation, and independent validation. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request.

## Citation

Research and technical work can cite the repository using [`CITATION.cff`](CITATION.cff).

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
