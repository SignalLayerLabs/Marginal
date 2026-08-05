"""Measured comparison utilities for public agent benchmarks."""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RunRecord:
    instance_id: str
    resolved: bool
    tokens: int
    usd: float = 0.0
    latency_ms: int = 0
    tool_calls: int = 0

    def __post_init__(self) -> None:
        if not self.instance_id:
            raise ValueError("instance_id must not be empty")
        if self.tokens < 0 or self.usd < 0 or self.latency_ms < 0 or self.tool_calls < 0:
            raise ValueError("metrics must be non-negative")
        if not math.isfinite(self.usd):
            raise ValueError("usd must be finite")


def load_runs(path: Path) -> dict[str, RunRecord]:
    """Load one JSON object per benchmark instance."""
    records: dict[str, RunRecord] = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, start=1):
            if not raw.strip():
                continue
            try:
                item = json.loads(raw)
                record = RunRecord(
                    instance_id=str(item["instance_id"]),
                    resolved=bool(item["resolved"]),
                    tokens=int(item.get("tokens", 0)),
                    usd=float(item.get("usd", 0.0)),
                    latency_ms=int(item.get("latency_ms", 0)),
                    tool_calls=int(item.get("tool_calls", 0)),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid benchmark row on line {line_number}") from exc
            if record.instance_id in records:
                raise ValueError(f"duplicate instance_id: {record.instance_id}")
            records[record.instance_id] = record
    if not records:
        raise ValueError("benchmark run is empty")
    return records


def _aggregate(records: list[RunRecord]) -> dict[str, Any]:
    tasks = len(records)
    resolved = sum(record.resolved for record in records)
    return {
        "tasks": tasks,
        "resolved": resolved,
        "resolve_rate": resolved / tasks,
        "tokens": sum(record.tokens for record in records),
        "usd": round(sum(record.usd for record in records), 6),
        "latency_ms": sum(record.latency_ms for record in records),
        "tool_calls": sum(record.tool_calls for record in records),
    }


def _saving(original: float, optimized: float) -> float:
    return round((original - optimized) / original * 100.0, 2) if original else 0.0


def _bootstrap_token_savings(
    pairs: list[tuple[RunRecord, RunRecord]], samples: int, seed: int
) -> tuple[float, float]:
    if samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        draw = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        baseline = sum(left.tokens for left, _ in draw)
        marginal = sum(right.tokens for _, right in draw)
        estimates.append(_saving(float(baseline), float(marginal)))
    estimates.sort()
    lower = estimates[int(0.025 * (samples - 1))]
    upper = estimates[int(0.975 * (samples - 1))]
    return round(lower, 2), round(upper, 2)


def compare_runs(
    baseline: dict[str, RunRecord],
    marginal: dict[str, RunRecord],
    *,
    bootstrap_samples: int = 2_000,
    seed: int = 42,
) -> dict[str, Any]:
    """Compare matched public-benchmark executions without imputing missing tasks."""
    if set(baseline) != set(marginal):
        missing = sorted(set(baseline) ^ set(marginal))
        raise ValueError(f"baseline and MARGINAL instance IDs differ: {missing[:5]}")
    ids = sorted(baseline)
    baseline_rows = [baseline[item] for item in ids]
    marginal_rows = [marginal[item] for item in ids]
    baseline_total = _aggregate(baseline_rows)
    marginal_total = _aggregate(marginal_rows)
    delta_pp = round(
        (marginal_total["resolve_rate"] - baseline_total["resolve_rate"]) * 100.0,
        2,
    )
    token_ci = _bootstrap_token_savings(
        list(zip(baseline_rows, marginal_rows, strict=True)), bootstrap_samples, seed
    )
    return {
        "benchmark": "public-agent-benchmark-comparison-v1",
        "tasks": len(ids),
        "baseline": baseline_total,
        "marginal": marginal_total,
        "savings": {
            "tokens_percent": _saving(baseline_total["tokens"], marginal_total["tokens"]),
            "usd_percent": _saving(baseline_total["usd"], marginal_total["usd"]),
            "latency_percent": _saving(
                baseline_total["latency_ms"], marginal_total["latency_ms"]
            ),
            "tool_calls_percent": _saving(
                baseline_total["tool_calls"], marginal_total["tool_calls"]
            ),
            "tokens_95pct_ci": list(token_ci),
        },
        "quality": {
            "resolved_delta_pp": delta_pp,
            "preserved_within_one_pp": delta_pp >= -1.0,
            "regressions": sum(
                baseline[item].resolved and not marginal[item].resolved for item in ids
            ),
            "recoveries": sum(
                not baseline[item].resolved and marginal[item].resolved for item in ids
            ),
        },
    }


def render_public_report(result: dict[str, Any]) -> str:
    baseline = result["baseline"]
    marginal = result["marginal"]
    savings = result["savings"]
    quality = result["quality"]
    ci = savings["tokens_95pct_ci"]
    return "\n".join(
        [
            "# Measured public benchmark comparison",
            "",
            "This report compares matched executions. It does not estimate or impute missing runs.",
            "",
            "| Metric | Baseline | MARGINAL | Change |",
            "|---|---:|---:|---:|",
            f"| Resolved | {baseline['resolved']}/{baseline['tasks']} | {marginal['resolved']}/{marginal['tasks']} | {quality['resolved_delta_pp']:+.2f} pp |",
            f"| Tokens | {baseline['tokens']:,} | {marginal['tokens']:,} | {savings['tokens_percent']:.2f}% fewer |",
            f"| USD | ${baseline['usd']:.4f} | ${marginal['usd']:.4f} | {savings['usd_percent']:.2f}% lower |",
            f"| Latency | {baseline['latency_ms']:,} ms | {marginal['latency_ms']:,} ms | {savings['latency_percent']:.2f}% lower |",
            f"| Tool calls | {baseline['tool_calls']} | {marginal['tool_calls']} | {savings['tool_calls_percent']:.2f}% fewer |",
            "",
            f"Token savings 95% bootstrap interval: **{ci[0]:.2f}% to {ci[1]:.2f}%**.",
            f"Quality preserved within 1 pp: **{quality['preserved_within_one_pp']}**.",
            f"Regressions: **{quality['regressions']}**. Recoveries: **{quality['recoveries']}**.",
            "",
        ]
    )
