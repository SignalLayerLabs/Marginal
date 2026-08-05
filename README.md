<div align="center">

# MARGINAL

### Compute capital allocation for AI agents

**Fund only the next action worth taking.**

[![CI](https://github.com/BlumFinancialLab/Marginal/actions/workflows/ci.yml/badge.svg)](https://github.com/BlumFinancialLab/Marginal/actions/workflows/ci.yml)
[![CodeQL](https://github.com/BlumFinancialLab/Marginal/actions/workflows/codeql.yml/badge.svg)](https://github.com/BlumFinancialLab/Marginal/actions/workflows/codeql.yml)
[![Python 3.10–3.13](https://img.shields.io/badge/python-3.10--3.13-blue.svg)](https://www.python.org/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Zero runtime dependencies](https://img.shields.io/badge/runtime%20dependencies-0-brightgreen.svg)](pyproject.toml)

</div>

---

MARGINAL is an open-source decision and accounting layer for AI agents. It evaluates
proposed model calls, tool calls, searches, retries, reviewers, and sub-agents before they
run, then funds only actions whose expected marginal value justifies their direct cost,
token scarcity, latency, and risk.

> **Hard budgets ask “can we afford this?” MARGINAL also asks “is this worth funding?”**

MARGINAL does not compress prompts or replace an agent framework. It removes entire
low-value actions before they consume tokens.

## Why this exists

Agent runtimes commonly execute the next step because it appears in a workflow, because a
model requested it, or because a hard limit has not yet been reached. Those mechanisms do
not compare the expected improvement of the next action with its total economic cost.

MARGINAL adds that missing allocation layer:

- rank candidate actions by marginal value;
- reserve budget at authorization time;
- protect a verification reserve;
- prevent duplicate and concurrent double-spend;
- account for actual usage, including overruns;
- release reservations when execution fails;
- enforce parent and child budgets atomically;
- produce provider-neutral JSONL evidence;
- work with synchronous and asynchronous Python callables;
- keep zero mandatory runtime dependencies.

## Killer demo: same verified fix, 94.09% fewer declared tokens

The bundled end-to-end demo creates a real buggy Python micro-repository, executes the
same diagnose → fix → verify workflow twice, and checks the final result with a deterministic
verifier. The baseline runs every search, reviewer, rewrite, and audit. MARGINAL funds only
the highest-value action in each stage.

[![Killer demo: baseline versus MARGINAL](demos/killer-demo/comparison.svg)](demos/killer-demo/RESULTS.md)

| Metric | Run everything | MARGINAL | Savings |
|---|---:|---:|---:|
| Declared tokens | 72,800 | 4,300 | **94.09%** |
| Calls | 9 | 3 | **66.67%** |
| Estimated USD | $0.763 | $0.026 | **96.59%** |
| Estimated latency | 22,030 ms | 1,230 ms | **94.42%** |
| Verified outcome | PASS | PASS | preserved |

```bash
marginal killer-demo --output killer-demo-output
```

The command produces a standalone HTML report, GitHub-ready Markdown, SVG comparison,
structured JSON, and the complete provider-neutral decision trace. This is a deterministic
functional demonstration using declared action-cost estimates, **not a production benchmark,
provider measurement, or universal savings claim**.

[Open the full allocation report →](demos/killer-demo/RESULTS.md)

## Install

Install the tagged GitHub release:

```bash
pip install "marginal-ai @ git+https://github.com/BlumFinancialLab/Marginal.git@v0.1.0"
```

For development:

```bash
git clone https://github.com/BlumFinancialLab/Marginal.git
cd marginal
python -m pip install -e ".[dev]"
```

## Five-minute integration

```python
from marginal import (
    Action,
    ActionDenied,
    BudgetLimits,
    Cost,
    MarginalPolicy,
    PolicyConfig,
    Treasury,
    budgeted_call,
    funded_call,
)

policy = MarginalPolicy(
    PolicyConfig(
        outcome_value_usd=5.0,
        token_shadow_price_per_million_usd=10.0,
        minimum_roi=1.0,
    )
)

treasury = Treasury(
    BudgetLimits(
        max_tokens=100_000,
        max_usd=2.00,
        verification_reserve_tokens=10_000,
    ),
    policy=policy,
)

try:
    answer = budgeted_call(
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
except ActionDenied as exc:
    print(f"Skipped: {exc}")
```

The wrapped function is never called when authorization is denied. Approved estimates are
reserved immediately, preventing parallel actions from oversubscribing the same treasury.

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

`fund_best` evaluates every candidate against the same current state and reserves the
highest-scoring affordable action. `funded_call` executes that reservation and automatically
settles or releases it. Candidate rankings are recorded in the trace.

## Use actual provider usage

MARGINAL has no mandatory SDK dependency. Wrap the callable already used by your app and
extract actual token usage from its result:

```python
from marginal import budgeted_call, extract_common_llm_usage

response = budgeted_call(
    treasury,
    client.responses.create,
    action=Action(
        name="draft final answer",
        kind="llm",
        cost=Cost(tokens=5_000, usd=0.08),
        expected_gain=0.15,
    ),
    usage_extractor=extract_common_llm_usage,
    model="YOUR_MODEL",
    input="Draft the answer.",
)
```

The built-in extractor understands common OpenAI-, Anthropic-, and LiteLLM-like usage
objects. It replaces the token estimate and preserves direct USD, latency, and risk values
that provider responses do not expose consistently.

A custom extractor receives `(result, estimated_cost)` and returns a complete `Cost`.

## Async integration

```python
from marginal import async_budgeted_call

response = await async_budgeted_call(
    treasury,
    async_client_call,
    action=action,
    usage_extractor=extract_common_llm_usage,
)
```

Synchronous and asynchronous wrappers share the same reservation, settlement, duplicate,
and trace semantics.

## Decision model

The default policy converts all configured dimensions into a common USD-denominated value:

```text
expected value = capped expected success gain × outcome value
cost value     = direct USD + token shadow cost + latency shadow cost + risk shadow cost
marginal score = expected value − cost value
ROI            = expected value ÷ cost value
```

An action is approved only when:

1. child and parent hard budgets remain valid;
2. pending reservations leave enough budget;
3. the verification reserve remains protected;
4. the action is not a pending or completed duplicate;
5. the target success probability has not been reached;
6. expected gain and ROI clear configured thresholds.

`Cost.usd` is direct estimated or measured spend. Shadow prices are optional opportunity
costs used by the policy; they do not silently alter the hard USD ledger.

## Reliable settlement

Authorization and settlement are separate:

```text
propose → evaluate → reserve → execute → settle actual cost
                              ↘ abort and release on failure
```

If actual usage exceeds the reserved estimate, MARGINAL records the real spend first and
then raises `BudgetOverrun`. Accounting therefore remains truthful even when a provider or
tool costs more than predicted.

Authorization tracing is transactional: if the trace sink fails, the reservation and counters
are rolled back. During execution failure, the original callable exception remains primary even
if abort tracing also fails. A settlement trace failure cannot undo external spend, so committed
usage remains recorded and the trace error is surfaced.

## Duplicate protection

For `budgeted_call` and `async_budgeted_call`, the fingerprint includes:

- the declared action;
- the callable identity;
- positional arguments;
- keyword arguments.

Only the SHA-256 digest is stored in normal traces. Inputs must be composed of supported,
deterministically serializable values, or the caller can provide an explicit
`Action.fingerprint`.

## Synthetic benchmark

The repository ships a deterministic functional benchmark. It is intentionally synthetic
and is **not a production performance claim**.

| Metric | Baseline | MARGINAL | Savings |
|---|---:|---:|---:|
| Tokens | 97,500 | 42,500 | **56.41%** |
| Calls | 25 | 15 | **40.00%** |
| Simulated USD | $1.1500 | $0.4500 | **60.87%** |
| Simulated latency | 17,750 ms | 7,750 ms | **56.34%** |
| Verified success | 100% | 100% | preserved |

Run it locally:

```bash
marginal demo
```

See [benchmarks.md](benchmarks.md) and [docs/benchmarking.md](docs/benchmarking.md) for the
methodology and limitations.

## How MARGINAL differs

| Category | Primary question | MARGINAL relationship |
|---|---|---|
| Hard budget / circuit breaker | Can this session spend more? | Complementary; MARGINAL also prices expected value |
| Model router | Which model should answer? | A router can be one candidate action |
| Prompt compressor | Can the same call use fewer tokens? | Complementary; MARGINAL may eliminate the call |
| Workflow optimizer | Can a fixed workflow be simplified? | MARGINAL makes online decisions at runtime |
| Observability | What was spent? | MARGINAL decides before spending and records settlement |

## Core primitives

| Primitive | Responsibility |
|---|---|
| `Action` | Declares proposed work, estimated cost, expected gain, and metadata |
| `Cost` | Normalizes tokens, direct USD, latency, and risk |
| `BudgetLimits` | Defines hard limits and protected verification reserves |
| `MarginalPolicy` | Produces deterministic, explainable decisions |
| `Treasury` | Ranks, reserves, settles, aborts, traces, and creates child budgets |
| `fund_best` | Selects and reserves the highest-value candidate |
| `budgeted_call` | Authorizes, executes, and settles a synchronous callable |
| `funded_call` | Executes and settles the action reserved by `fund_best` |
| `async_budgeted_call` | Guards an asynchronous callable |
| `async_funded_call` | Executes an asynchronous funded allocation |
| `JsonlTraceSink` | Produces append-only provider-neutral evidence |

## Hierarchical agent budgets

```python
root = Treasury(BudgetLimits(max_tokens=200_000, max_usd=5.0))
research = root.child("research", BudgetLimits(max_tokens=40_000, max_usd=1.0))
verification = root.child(
    "verification",
    BudgetLimits(max_tokens=30_000, max_usd=0.75),
)
```

A child authorization reserves capacity from the child and every parent treasury under one
shared lock. A child settlement charges every level, preventing fan-out oversubscription.

## Trace and inspect decisions

```python
from marginal import JsonlTraceSink

trace = JsonlTraceSink("marginal-trace.jsonl")
treasury = Treasury(BudgetLimits(max_tokens=50_000), trace_sink=trace)
```

```bash
marginal validate marginal-trace.jsonl
marginal report marginal-trace.jsonl
marginal report marginal-trace.jsonl --json
```

Trace events include candidate rankings, authorization decisions, reservations, commits,
aborts, actual usage, and overrun reasons. Prompts and model outputs are not recorded unless
an application explicitly places them in action metadata.

## Architecture

```text
Agent / workflow / SDK call
            │
            ▼
      Candidate actions
            │
            ▼
┌────────────────────────────────┐
│ MARGINAL Treasury              │
│ ├─ hard child + parent budgets │
│ ├─ pending reservations        │
│ ├─ verification reserve        │
│ ├─ duplicate detection         │
│ ├─ marginal-value ranking      │
│ └─ target-success stopping     │
└────────────────────────────────┘
       │ funded      │ denied
       ▼             └── no execution
 Execute callable
       │ success / failure
       ▼
 Settle actual cost or release reservation
       │
       └──► append-only JSONL trace
```

See [docs/architecture.md](docs/architecture.md).

## Research lineage

MARGINAL is an independent open-source reference implementation inspired by the research
direction described in Siqi Zhu’s position paper,
[“Agentic AI Systems Should Be Designed as Marginal Token Allocators”](https://arxiv.org/abs/2605.01214).
The paper proposes the economic framing; this repository focuses on a small, immediately
usable runtime contract, accounting model, trace format, tests, and integrations.

Related systems such as [AgentBudget](https://agentbudget.dev/) focus on hard session cost
enforcement. MARGINAL is designed to complement them by deciding whether an affordable
next action has sufficient expected value.

See [docs/research.md](docs/research.md) and [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md).

## Project status

MARGINAL `v0.1.0` is a reference implementation of **agent compute capital allocation**.
It provides deterministic online ranking, authorization, reservation, settlement, and
accounting. It does not claim causal value estimates, automatic counterfactual replay, or
guaranteed savings on arbitrary workloads.

The next validation milestone is a public benchmark across real agent frameworks and task
sets, measuring cost per verified outcome rather than cost alone.

## Documentation

- [Quickstart](docs/quickstart.md)
- [Concepts](docs/concepts.md)
- [Architecture](docs/architecture.md)
- [API reference](docs/api.md)
- [Integrations](docs/integrations.md)
- [Killer demo](demos/killer-demo/RESULTS.md)
- [Benchmarking](docs/benchmarking.md)
- [Research and prior art](docs/research.md)
- [FAQ](docs/faq.md)
- [Governance](docs/governance.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## Contributing

MARGINAL is deliberately small at the core and open at the edges. Contributions are
welcome for adapters, estimators, benchmark scenarios, documentation, and independent
validation. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## Citation

Academic and technical work can cite the repository using [CITATION.cff](CITATION.cff).

## License

Apache License 2.0. See [LICENSE](LICENSE).

---

**Suggested GitHub topics:** `ai-agents`, `agentic-ai`, `llm`, `token-optimization`,
`cost-optimization`, `ai-infrastructure`, `openai`, `anthropic`, `langgraph`, `crewai`,
`litellm`, `mcp`, `budget`, `observability`, `finops`, `ai-finops`,
`agent-economics`, `compute-allocation`, `llm-cost-optimization`.


## Public benchmarks

See [the public benchmark protocol](docs/public-benchmarks.md).
