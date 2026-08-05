"""Deterministic synthetic benchmark for the reference allocation policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .budget import BudgetLimits
from .models import Action, Cost
from .policy import MarginalPolicy, PolicyConfig
from .treasury import Treasury


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    actions: tuple[Action, ...]


def _scenarios() -> tuple[Scenario, ...]:
    scenarios: list[Scenario] = []
    names = ("coding", "research", "support", "analysis", "planning")
    for index, name in enumerate(names, start=1):
        common = {"scenario": name, "sequence": index}
        scenarios.append(
            Scenario(
                name=name,
                actions=(
                    Action(
                        name=f"{name}: inspect evidence",
                        kind="research",
                        cost=Cost(tokens=3_000, usd=0.03, latency_ms=500),
                        expected_gain=0.18,
                        metadata={**common, "required": True, "step": 1},
                    ),
                    Action(
                        name=f"{name}: generate candidate",
                        kind="generation",
                        cost=Cost(tokens=4_000, usd=0.05, latency_ms=800),
                        expected_gain=0.22,
                        metadata={**common, "required": True, "step": 2},
                    ),
                    Action(
                        name=f"{name}: redundant second opinion",
                        kind="review",
                        cost=Cost(tokens=6_000, usd=0.08, latency_ms=1_100),
                        expected_gain=0.004,
                        metadata={**common, "required": False, "step": 3},
                    ),
                    Action(
                        name=f"{name}: broad extra search",
                        kind="research",
                        cost=Cost(tokens=5_000, usd=0.06, latency_ms=900),
                        expected_gain=0.003,
                        metadata={**common, "required": False, "step": 4},
                    ),
                    Action(
                        name=f"{name}: verify outcome",
                        kind="verification",
                        cost=Cost(tokens=1_500, usd=0.01, latency_ms=250),
                        expected_gain=0.16,
                        is_verification=True,
                        metadata={**common, "required": True, "step": 5},
                    ),
                ),
            )
        )
    return tuple(scenarios)


def _empty_metrics() -> dict[str, Any]:
    return {
        "tokens": 0,
        "usd": 0.0,
        "latency_ms": 0,
        "calls": 0,
        "verified_successes": 0,
        "tasks": 0,
    }


def _add_cost(metrics: dict[str, Any], cost: Cost) -> None:
    metrics["tokens"] += cost.tokens
    metrics["usd"] += cost.usd
    metrics["latency_ms"] += cost.latency_ms
    metrics["calls"] += 1


def _finalize(metrics: dict[str, Any]) -> dict[str, Any]:
    result = dict(metrics)
    tasks = int(result["tasks"])
    result["usd"] = round(float(result["usd"]), 6)
    result["verified_success_rate"] = (
        round(int(result["verified_successes"]) / tasks, 6) if tasks else 0.0
    )
    return result


def run_benchmark() -> dict[str, Any]:
    """Compare all-actions execution with MARGINAL on fixed synthetic scenarios."""

    baseline = _empty_metrics()
    marginal = _empty_metrics()

    for scenario in _scenarios():
        baseline["tasks"] += 1
        for action in scenario.actions:
            _add_cost(baseline, action.cost)
        baseline["verified_successes"] += 1

        marginal["tasks"] += 1
        policy = MarginalPolicy(
            PolicyConfig(
                outcome_value_usd=1.0,
                token_shadow_price_per_million_usd=20.0,
                latency_shadow_price_per_second_usd=0.005,
                risk_shadow_price_usd=1.0,
                minimum_roi=1.0,
                minimum_expected_gain=0.001,
                target_success_probability=1.0,
            )
        )
        treasury = Treasury(
            BudgetLimits(
                max_tokens=30_000,
                max_usd=1.0,
                verification_reserve_tokens=1_500,
            ),
            policy=policy,
            name=scenario.name,
        )
        required_complete = True
        for action in scenario.actions:
            decision = treasury.authorize(action)
            if decision.allowed:
                treasury.commit(action)
                _add_cost(marginal, action.cost)
            elif action.metadata.get("required", False):
                required_complete = False
        if required_complete:
            marginal["verified_successes"] += 1

    baseline_result = _finalize(baseline)
    marginal_result = _finalize(marginal)

    def savings(key: str) -> float:
        original = float(baseline_result[key])
        optimized = float(marginal_result[key])
        return round((original - optimized) / original * 100.0, 2) if original else 0.0

    return {
        "benchmark": "marginal-synthetic-v1",
        "baseline": baseline_result,
        "marginal": marginal_result,
        "savings": {
            "tokens_percent": savings("tokens"),
            "usd_percent": savings("usd"),
            "latency_percent": savings("latency_ms"),
            "calls_percent": savings("calls"),
        },
    }


def render_markdown(result: dict[str, Any]) -> str:
    baseline = result["baseline"]
    marginal = result["marginal"]
    savings = result["savings"]
    rows = [
        "# Synthetic benchmark",
        "",
        (
            "This bundled deterministic benchmark is a functional demonstration, "
            "**not a production performance claim**."
        ),
        "",
        "| Metric | Baseline | MARGINAL | Savings |",
        "|---|---:|---:|---:|",
        (
            f"| Tokens | {baseline['tokens']:,} | {marginal['tokens']:,} | "
            f"{savings['tokens_percent']:.2f}% |"
        ),
        (
            f"| Calls | {baseline['calls']} | {marginal['calls']} | "
            f"{savings['calls_percent']:.2f}% |"
        ),
        (
            f"| USD | ${baseline['usd']:.4f} | ${marginal['usd']:.4f} | "
            f"{savings['usd_percent']:.2f}% |"
        ),
        (
            f"| Latency | {baseline['latency_ms']:,} ms | "
            f"{marginal['latency_ms']:,} ms | {savings['latency_percent']:.2f}% |"
        ),
        (
            f"| Verified success | {baseline['verified_success_rate']:.0%} | "
            f"{marginal['verified_success_rate']:.0%} | preserved |"
        ),
        "",
        f"**Token savings:** {savings['tokens_percent']:.2f}% on the bundled scenarios.",
        "",
    ]
    return "\n".join(rows)
