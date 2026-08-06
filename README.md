<div align="center">

<img src="assets/marginal-readme-hero.png" alt="MARGINAL — compute governance and token optimization for AI agents" width="100%">

# MARGINAL

### Compute governance and token optimization for AI agents

**MARGINAL helps AI agents decide whether the next model call, tool call, search, retry, review, or sub-agent is worth its compute cost.**

Open source · Local first · Provider neutral · Zero mandatory runtime dependencies

[Website](https://signallayerlabs.github.io/Marginal/) ·
[Quickstart](docs/quickstart.md) ·
[Architecture](docs/architecture.md) ·
[Roadmap](ROADMAP.md) ·
[Contributing](CONTRIBUTING.md)

[![CI](https://github.com/SignalLayerLabs/Marginal/actions/workflows/ci.yml/badge.svg)](https://github.com/SignalLayerLabs/Marginal/actions/workflows/ci.yml)
[![CodeQL](https://github.com/SignalLayerLabs/Marginal/actions/workflows/codeql.yml/badge.svg)](https://github.com/SignalLayerLabs/Marginal/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/SignalLayerLabs/Marginal?style=flat-square)](https://github.com/SignalLayerLabs/Marginal/releases)
[![Python 3.10–3.13](https://img.shields.io/badge/python-3.10--3.13-blue.svg?style=flat-square)](https://www.python.org/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg?style=flat-square)](LICENSE)
[![Runtime dependencies: 0](https://img.shields.io/badge/runtime%20dependencies-0-brightgreen.svg?style=flat-square)](pyproject.toml)

</div>

---

## Why MARGINAL

Most agent runtimes ask:

> **Can this action run?**

MARGINAL adds the economic question:

> **Is this action worth funding now?**

It evaluates expected improvement against tokens, direct cost, latency, risk, remaining budget, verification reserves, and prior evidence. It then records what actually happened so future policies can be evaluated against real outcomes.

```text
observe decisions
      ↓
measure actual cost and outcomes
      ↓
estimate marginal value
      ↓
allocate compute
      ↓
measure calibration and regret
      ↓
improve the policy
```

The goal is not to make an agent merely cheaper. It is to make autonomous work **economically disciplined, measurable, and auditable**.

MARGINAL also supports Shadow Mode, where recommendations can be observed without blocking execution, letting teams collect evidence before enforcement.

## How it works

```text
Agent proposes an action
          ↓
MARGINAL estimates value and total cost
          ↓
ALLOW · DENY · RECOMMEND · SHADOW
          ↓
Budget is reserved before execution
          ↓
Actual usage and verified outcome are settled
          ↓
Versioned evidence is written to the Decision Ledger
```

MARGINAL can sit around model calls, tool calls, searches, tests, reviewers, retries, and sub-agents. The core remains engine-neutral; thin adapters translate native events from coding agents into one universal protocol.

## What makes it different

| Capability | What it adds |
|---|---|
| **Transactional accounting** | Atomic reserve, settle, abort, overrun, hierarchy, and verification reserves—not a token counter wrapper. |
| **Shadow-to-enforce lifecycle** | Observe recommendations safely before allowing the policy to block work. |
| **Learning Loop Foundation** | Versioned estimators, outcomes, replay, and evidence for progressively better allocation. |
| **Privacy by design** | Local ledgers, pseudonymous telemetry, aggregate exports, and no prompt/output logging by default. |
| **Universal agent protocol** | One core for Codex, Claude Code, GitHub Copilot, OpenCode, and future compatible runtimes. |
| **Scientific honesty** | Synthetic demonstrations are labeled as demonstrations; public claims require measured telemetry and preserved quality. |

## Install

Install the tagged release:

```bash
pip install "marginal-ai @ git+https://github.com/SignalLayerLabs/Marginal.git@v0.2.0"
```

For development:

```bash
git clone https://github.com/SignalLayerLabs/Marginal.git
cd Marginal
python -m pip install -e ".[dev]"
```

## Quickstart

```python
from marginal import Action, BudgetLimits, Cost, Treasury, budgeted_call, build_policy

treasury = Treasury(
    BudgetLimits(
        max_tokens=100_000,
        max_usd=2.00,
        verification_reserve_tokens=10_000,
    ),
    policy=build_policy("balanced"),
    mode="enforce",
)

result = budgeted_call(
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

When enforcement denies the action, the wrapped function is not called. Approved estimates are reserved immediately, preventing concurrent actions from oversubscribing the same treasury.

Start with [`shadow` mode](docs/quickstart.md) when collecting evidence for a new workflow.

## Execution modes

| Mode | Applied behavior | Best for |
|---|---|---|
| `shadow` | Executes every proposed action and records the recommendation | Safe observation and calibration |
| `recommend` | Executes while surfacing the policy recommendation | Human or agent advisory workflows |
| `enforce` | Applies allow/deny and hard-budget decisions | Validated production control |

`fund_best(...)` remains an active selection API in every mode because the caller is explicitly asking MARGINAL to choose among alternatives.

## The Learning Loop Foundation

MARGINAL v0.2 moves beyond manually supplied expected gain without pretending causal inference is already solved.

The current foundation provides:

- versioned `ValueEstimator` identities and configurations;
- contextual observations by engine, phase, task type, language, and model;
- uncertainty, confidence, sample size, and provenance;
- task-level verified outcomes;
- separately supplied action-level realized gain;
- policy replay over recorded actions;
- deterministic Decision Ledger records for audit and comparison.

A successful task does **not** prove that every action in its trajectory caused success. MARGINAL keeps task outcomes and action attribution separate so correlation is not mislabeled as causal value.

Read [Learning and replay](docs/concepts.md) and [Benchmarking](docs/benchmarking.md).

## Universal Agent Runtime

The universal runtime gives engine adapters one shared contract:

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
```

The protocol defines consistent events, capabilities, usage fields, decisions, settlement, and outcome contracts. Vendor-specific adapters are developed as thin integrations; they do not duplicate the economic policy.

### Integration status

| Environment | Current status | Intended capability |
|---|---|---|
| Core Python runtime | Available | Full allocation, accounting, ledger, replay |
| Universal Agent Protocol | Available | Adapter contract and capability negotiation |
| Codex | Roadmap | Reference integration and measured benchmark |
| OpenCode | Roadmap | Open-source adapter and research environment |
| Claude Code | Roadmap | Hook-based integration |
| GitHub Copilot CLI / coding agent | Roadmap | Integration where official control surfaces permit |

See the [full roadmap](ROADMAP.md). Planned adapters are not presented as completed integrations.

## Privacy by design

Not recording prompts is not enough: identifiers, action names, model names, metadata, verifier details, and exception text can still expose sensitive information.

MARGINAL therefore separates operational evidence from shareable telemetry:

| Profile | Purpose |
|---|---|
| `LOCAL_FULL` | Full operational ledger on a trusted local filesystem |
| `SAFE_TELEMETRY` | Removes free text and pseudonymizes identifiers with a local key |
| `AGGREGATE_EXPORT` | Produces generalized grouped rows with no identifiers or timestamps |

Aggregate exports suppress groups smaller than five records by default to reduce re-identification risk. Pseudonymization is not anonymization; exports must still be reviewed before sharing.

Read the [privacy model](docs/privacy.md) and [security policy](SECURITY.md).

## Evidence, not hype

MARGINAL includes a deterministic Killer Demo that fixes the same code defect with a baseline workflow and a MARGINAL-funded workflow.

```bash
marginal killer-demo --output-dir demo-output
```

The demo uses declared action-cost estimates. It is useful for understanding allocation behavior, but it is **not provider telemetry and not a production savings claim**.

Public evaluation compares matched runs with the same agent, model, prompt, tools, limits, task order, and verifier:

```bash
marginal public-eval baseline.jsonl marginal.jsonl
```

The report covers:

- resolve-rate delta and quality non-inferiority;
- total and per-resolved-task token cost;
- USD, latency, and tool calls;
- regressions and recoveries;
- bootstrap uncertainty.

A token reduction without preserved verified outcomes is not considered a successful result.

See [Public benchmark protocol](docs/public-benchmarks.md) and [Killer Demo results](demos/killer-demo/RESULTS.md).

## Architecture

```text
AI development agents
Codex · Claude Code · Copilot · OpenCode · others
                         │
                  thin engine adapters
                         │
                Universal Agent Protocol
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   Value Estimator   Treasury       Decision Ledger
        │                │                │
        └────────── Decision Policy ──────┘
                         │
          observe · recommend · enforce
```

MARGINAL is deliberately modular:

- the **core** evaluates and accounts;
- the **runtime** coordinates sessions and adapters;
- the **ledger** preserves evidence;
- privacy exports transform data for controlled sharing;
- external frameworks retain ownership of execution.

Read the [architecture](docs/architecture.md) and [API reference](docs/api.md).

## Project status

`v0.2.0` provides the Learning Loop Foundation, privacy profiles, Universal Agent Protocol, versioned evidence, policy replay, and a dependency-free core.

The active milestone is **v0.3 — Codex Reference Integration**: measured token telemetry, matched baseline runs, a 10-task canary, and a preregistered public evaluation before broader enforcement claims.

[View the roadmap →](ROADMAP.md)

## Documentation

| Start here | Deep dives |
|---|---|
| [Quickstart](docs/quickstart.md) | [Architecture](docs/architecture.md) |
| [Core concepts](docs/concepts.md) | [API reference](docs/api.md) |
| [Integration guide](docs/integrations.md) | [Privacy profiles](docs/privacy.md) |
| [Benchmarking](docs/benchmarking.md) | [Public benchmark protocol](docs/public-benchmarks.md) |
| [Roadmap](ROADMAP.md) | [Security](SECURITY.md) |
| [Changelog](CHANGELOG.md) | [Governance](docs/governance.md) |

The [project website](https://signallayerlabs.github.io/Marginal/) provides the product-level overview; GitHub remains the source of truth for code, evidence, releases, and technical documentation.

## Contributing

Contributions are welcome across the core, protocol, adapters, privacy, benchmarks, and documentation.

Before opening a pull request:

```bash
ruff format --check .
ruff check .
mypy src/marginal
pytest -q
python -m build
python -m twine check dist/*
```

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) and the [governance model](docs/governance.md).

## Citation

```bibtex
@software{marginal2026,
  title   = {MARGINAL: Compute Governance for AI Agents},
  author  = {SignalLayer Labs and contributors},
  year    = {2026},
  url     = {https://github.com/SignalLayerLabs/Marginal},
  license = {Apache-2.0}
}
```

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
