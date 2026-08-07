<div align="center">

<img src="assets/marginal-readme-hero.png" alt="MARGINAL — compute governance for AI agents" width="100%">

# MARGINAL

### Compute governance that has to justify its own cost

**MARGINAL evaluates whether the next model call, tool call, retry, verification, review, or sub-agent is likely to add enough value to justify its compute — and now measures whether MARGINAL's own intervention was worth it.**

Open source · Local first · Provider neutral · Zero mandatory runtime dependencies

[Website](https://signallayerlabs.github.io/Marginal/) ·
[Quickstart](docs/getting-started/quickstart.md) ·
[Architecture](docs/product/architecture.md) ·
[Evidence standard](docs/evaluation/governance-evidence.md) ·
[Roadmap](ROADMAP.md) ·
[Contributing](CONTRIBUTING.md)

[![CI](https://github.com/SignalLayerLabs/Marginal/actions/workflows/ci.yml/badge.svg)](https://github.com/SignalLayerLabs/Marginal/actions/workflows/ci.yml)
[![CodeQL](https://github.com/SignalLayerLabs/Marginal/actions/workflows/codeql.yml/badge.svg)](https://github.com/SignalLayerLabs/Marginal/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/SignalLayerLabs/Marginal?style=flat-square)](https://github.com/SignalLayerLabs/Marginal/releases)
[![Python 3.10–3.13](https://img.shields.io/badge/python-3.10--3.13-blue.svg?style=flat-square)](https://www.python.org/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg?style=flat-square)](LICENSE)

</div>

---

## The problem in one trace

Coding agents can spend compute on actions whose incremental value is unclear or diminishing. The useful failure mode is not "GPT-5.6 is wasteful"; it is **repeated work against unchanged state that produces no new evidence**.

```text
Illustrative trace — not a benchmark

Agent proposes: read README.md
  → state changes: knowledge acquired

Agent proposes: verify README.md
  → evidence acquired

Agent proposes: verify README.md again
  → same semantic action
  → same workspace state
  → no new evidence

Agent proposes: verify README.md again
  → expected marginal gain is now lower
  → MARGINAL can recommend stopping the repetition
```

The mechanism is model independent. A future model may repeat less often, a different provider may repeat more often, and some tasks genuinely need multiple verification passes. MARGINAL should respond to the evidence rather than assume every repeat is waste. Shadow Mode remains the safe default for unvalidated integrations, while the Decision Ledger preserves versioned evidence for audit and replay.

## What changed after community review

Two early community criticisms exposed useful product tests:

1. **"Will the next model make this redundant?"** — valid as a design challenge. MARGINAL must remain useful across model generations, but it must also be able to conclude that an already-efficient agent does not need intervention.
2. **"Show the benchmark with and without it."** — valid. Performance claims require matched OFF/ON runs, not a synthetic demo or a persuasive website.
3. **"The website is too abstract."** — partially accepted. The concepts are real, but the explanation should start with an observable failure mode and proof standard before theory.
4. **"Providers may intentionally waste tokens."** — rejected as unsupported speculation. MARGINAL does not need that claim to justify independent compute governance.

The full decision log is in [Community feedback](docs/project/community-feedback.md).

## MARGINAL must earn its own compute

A governor that saves 20% of agent tokens while adding 25% overhead is not an optimization.

MARGINAL therefore separates:

- **agent workload cost** — model/tool tokens, USD, latency and calls;
- **governance tax** — tokens, USD and latency introduced by MARGINAL itself;
- **gross savings** — agent-only reduction;
- **net savings** — reduction after governance tax;
- **quality** — verified task outcomes, regressions and recoveries;
- **false stops** — reviewed cases where a deny recommendation would have prevented a helpful action.

The public evaluator treats net metrics as the evidence surface. A positive-looking gross number cannot hide governance overhead.

### Graceful Irrelevance

If a stronger model, better agent runtime, or simple task already behaves efficiently, MARGINAL should be able to produce:

```text
intervention.status = pass_through
```

That is not a failed product demo. It means the governor did not demonstrate enough net value to justify inserting itself into that workload.

## State-aware diminishing returns

The new `DiminishingReturnDetector` is intentionally opt-in while evidence is collected. It does not special-case GPT, Markdown files, Codex, or any provider.

```python
from marginal import (
    DiminishingReturnConfig,
    DiminishingReturnDetector,
    MarginalPolicy,
)

policy = MarginalPolicy(
    diminishing_detector=DiminishingReturnDetector(
        DiminishingReturnConfig(
            gain_decay=0.5,
            max_same_state_repeats=2,
        )
    )
)
```

The detector discounts expected gain only when the same semantic action has already executed against the same observable state without new evidence. A changed state or changed evidence resets the pressure. Missing state fails open instead of inventing certainty. Privacy guidance remains explicit through SAFE_TELEMETRY and AGGREGATE_EXPORT conventions.

This is designed to complement, not replace, the Universal Agent Protocol's existing exact and state-aware deduplication scopes.

## Governance accounting and false-stop review

`Treasury` records local decision latency and exposes explicit external overhead accounting for adapter-side work:

```python
treasury.record_governance_overhead(
    tokens=120,
    usd=0.002,
    latency_ms=40,
)
```

A false stop is never inferred from "the task eventually succeeded." It requires an explicit review or counterfactual label:

```python
treasury.record_stop_review(
    denied_action,
    would_have_helped=True,
)
```

This distinction matters. Correlation between an action and final task success is not causal proof, and an optimizer should not mark itself correct simply because the final answer happened to pass.

## Proof standard

A MARGINAL benchmark should compare the **same agent, model, prompt, tools, limits, task order and verifier** with MARGINAL OFF and ON.

| Evidence | Why it matters |
|---|---|
| Verified resolve rate | Prevents cheaper-but-worse optimization |
| Effective tokens / resolved task | Primary efficiency metric after governance tax |
| Gross vs net token savings | Shows whether MARGINAL pays for itself |
| USD and latency | Token savings can shift cost elsewhere |
| Tool and repeated calls | Shows what behavior actually changed |
| Regressions and recoveries | Makes quality movement inspectable |
| Reviewed false stops | Measures harmful deny recommendations |
| Bootstrap uncertainty / repeated runs | Separates signal from run variance |
| Intervention status | `supported`, `pass_through`, `quality_regression`, or `false_stop_risk` |

A 10-task canary is an **integration check**, not public performance evidence. Larger matched evaluation should be preregistered before headline claims are made.

SWE-bench Pro can be one requested evaluation surface, but no single benchmark is treated as ground truth. Dataset version, exclusions, verifier behavior and known task-quality limitations must be recorded alongside results.

Read the [benchmark protocol](docs/evaluation/public-benchmarks.md) and [governance evidence standard](docs/evaluation/governance-evidence.md).

## Install

Current v0.2 install target:

```bash
pip install "marginal-ai @ git+https://github.com/SignalLayerLabs/Marginal.git@v0.2.0"
```

Development checkout:

```bash
git clone https://github.com/SignalLayerLabs/Marginal.git
cd Marginal
python -m pip install -e ".[dev]"
```

The upcoming Codex reference integration remains a roadmap milestone. It is not presented here as already available.

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
    mode="shadow",
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

Start with `shadow` for a new integration. Promote controls only after representative evidence shows they preserve quality.

## Architecture

```text
AI development agents
Codex · Claude Code · Copilot · OpenCode · others
                         │
                  thin engine adapters
                         │
                Universal Agent Protocol
                         │
      ┌──────────────────┼──────────────────┐
      │                  │                  │
Value Estimator       Treasury        Decision Ledger
      │                  │                  │
Diminishing Return   Governance Tax    Outcomes / Replay
      └──────────────────┼──────────────────┘
                         │
             observe · recommend · enforce
```

The engine-specific adapter owns native interception and telemetry. The core owns economic policy, accounting and evidence semantics. That separation is what lets MARGINAL survive changes in model/provider behavior without accumulating vendor-specific patches.

## Project status

`v0.2.0` provides the Learning Loop Foundation, privacy profiles, Universal Agent Protocol, versioned evidence and replay. The community-hardening work prepares the core evidence model for **v0.3 — Codex Reference Integration**.

The next milestone must answer a falsifiable question:

> Does MARGINAL reduce effective compute per verified successful Codex task after its own overhead, without exceeding the preregistered quality and false-stop constraints?

If the answer is no, the result should be published as no demonstrated benefit for that configuration.

[View the roadmap →](ROADMAP.md)

## Documentation

| Area | Start here |
|---|---|
| Getting started | [Quickstart](docs/getting-started/quickstart.md) |
| Product model | [Concepts](docs/product/concepts.md) · [Architecture](docs/product/architecture.md) |
| Integrations | [Integration overview](docs/integrations/overview.md) · [Codex benchmark readiness](docs/integrations/codex-benchmark-readiness.md) |
| Evaluation | [Benchmarking](docs/evaluation/benchmarking.md) · [Public benchmarks](docs/evaluation/public-benchmarks.md) · [Governance evidence](docs/evaluation/governance-evidence.md) |
| Reference | [API](docs/reference/api.md) |
| Operations | [Privacy](docs/operations/privacy.md) · [Website](docs/operations/website.md) |
| Project | [Governance](docs/project/governance.md) · [Community feedback](docs/project/community-feedback.md) |

GitHub is the source of truth for code, evidence, releases and technical documentation.

## Contributing

Contributions are welcome, including criticism. A proposed performance improvement should include the evidence that could prove it wrong.

```bash
ruff format --check .
ruff check .
mypy src/marginal
pytest -q
python -m build
python -m twine check dist/*
```

Read [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
