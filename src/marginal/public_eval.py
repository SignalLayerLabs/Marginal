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
    """Measured result for one benchmark instance."""

    instance_id: str
    resolved: bool
    tokens: int
    usd: float = 0.0
    latency_ms: int = 0
    tool_calls: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, str) or not self.instance_id:
            raise ValueError("instance_id must not be empty")
        if not isinstance(self.resolved, bool):
            raise TypeError("resolved must be a boolean")
        for name in ("tokens", "latency_ms", "tool_calls"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError("metrics must be non-negative")
        if isinstance(self.usd, bool) or not isinstance(self.usd, (int, float)):
            raise TypeError("usd must be a number")
        if not math.isfinite(float(self.usd)):
            raise ValueError("usd must be finite")
        if self.usd < 0:
            raise ValueError("metrics must be non-negative")
        object.__setattr__(self, "usd", float(self.usd))


def load_runs(path: Path) -> dict[str, RunRecord]:
    """Load one strict JSON object per benchmark instance."""

    records: dict[str, RunRecord] = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, start=1):
            if not raw.strip():
                continue
            try:
                item = json.loads(raw)
                if not isinstance(item, dict):
                    raise TypeError("benchmark row must be an object")
                record = RunRecord(
                    instance_id=item["instance_id"],
                    resolved=item["resolved"],
                    tokens=item.get("tokens", 0),
                    usd=item.get("usd", 0.0),
                    latency_ms=item.get("latency_ms", 0),
                    tool_calls=item.get("tool_calls", 0),
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
    pairs: list[tuple[RunRecord, RunRecord]],
    samples: int,
    seed: int,
    confidence_level: float,
) -> tuple[float, float]:
    if samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        draw = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        baseline = sum(left.tokens for left, _ in draw)
        marginal = sum(right.tokens for _, right in draw)
        estimates.append(_saving(float(baseline), float(marginal)))
    estimates.sort()
    tail = (1.0 - confidence_level) / 2.0
    lower = estimates[int(tail * (samples - 1))]
    upper = estimates[int((1.0 - tail) * (samples - 1))]
    return round(lower, 2), round(upper, 2)


def compare_runs(
    baseline: dict[str, RunRecord],
    marginal: dict[str, RunRecord],
    *,
    bootstrap_samples: int = 2_000,
    seed: int = 42,
    confidence_level: float = 0.95,
    quality_margin_pp: float = 1.0,
) -> dict[str, Any]:
    """Compare matched executions without imputing missing tasks."""

    if isinstance(quality_margin_pp, bool) or not isinstance(quality_margin_pp, (int, float)):
        raise TypeError("quality_margin_pp must be a number")
    if not math.isfinite(float(quality_margin_pp)) or quality_margin_pp < 0:
        raise ValueError("quality_margin_pp must be finite and non-negative")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    quality_margin_pp = float(quality_margin_pp)

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
        list(zip(baseline_rows, marginal_rows, strict=True)),
        bootstrap_samples,
        seed,
        confidence_level,
    )

    def efficiency(total: dict[str, Any]) -> dict[str, float | None]:
        resolved = int(total["resolved"])
        if resolved == 0:
            return {"tokens_per_resolved": None, "usd_per_resolved": None}
        return {
            "tokens_per_resolved": round(float(total["tokens"]) / resolved, 6),
            "usd_per_resolved": round(float(total["usd"]) / resolved, 6),
        }

    return {
        "benchmark": "public-agent-benchmark-comparison-v2",
        "tasks": len(ids),
        "baseline": baseline_total,
        "marginal": marginal_total,
        "efficiency": {
            "baseline": efficiency(baseline_total),
            "marginal": efficiency(marginal_total),
        },
        "savings": {
            "tokens_percent": _saving(baseline_total["tokens"], marginal_total["tokens"]),
            "usd_percent": _saving(baseline_total["usd"], marginal_total["usd"]),
            "latency_percent": _saving(baseline_total["latency_ms"], marginal_total["latency_ms"]),
            "tool_calls_percent": _saving(
                baseline_total["tool_calls"], marginal_total["tool_calls"]
            ),
            "confidence_level": confidence_level,
            "tokens_confidence_interval": list(token_ci),
            "tokens_95pct_ci": list(token_ci),
        },
        "quality": {
            "resolved_delta_pp": delta_pp,
            "non_inferiority_margin_pp": quality_margin_pp,
            "preserved_within_margin": delta_pp >= -quality_margin_pp,
            "preserved_within_one_pp": delta_pp >= -1.0,
            "regressions": sum(
                baseline[item].resolved and not marginal[item].resolved for item in ids
            ),
            "recoveries": sum(
                not baseline[item].resolved and marginal[item].resolved for item in ids
            ),
        },
    }


def _format_optional_number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.2f}"


def _format_optional_usd(value: float | None) -> str:
    return "n/a" if value is None else f"${value:.6f}"


def render_public_report(result: dict[str, Any]) -> str:
    baseline = result["baseline"]
    marginal = result["marginal"]
    savings = result["savings"]
    quality = result["quality"]
    efficiency = result["efficiency"]
    baseline_efficiency = efficiency["baseline"]
    marginal_efficiency = efficiency["marginal"]
    ci = savings["tokens_confidence_interval"]
    confidence_percent = float(savings["confidence_level"]) * 100.0
    margin = float(quality["non_inferiority_margin_pp"])
    return "\n".join(
        [
            "# Measured public benchmark comparison",
            "",
            "This report compares matched executions. It does not estimate or impute missing runs.",
            "",
            "| Metric | Baseline | MARGINAL | Change |",
            "|---|---:|---:|---:|",
            (
                f"| Resolved | {baseline['resolved']}/{baseline['tasks']} | "
                f"{marginal['resolved']}/{marginal['tasks']} | "
                f"{quality['resolved_delta_pp']:+.2f} pp |"
            ),
            (
                f"| Tokens | {baseline['tokens']:,} | "
                f"{marginal['tokens']:,} | {savings['tokens_percent']:.2f}% fewer |"
            ),
            (
                f"| USD | ${baseline['usd']:.4f} | "
                f"${marginal['usd']:.4f} | {savings['usd_percent']:.2f}% lower |"
            ),
            (
                f"| Latency | {baseline['latency_ms']:,} ms | "
                f"{marginal['latency_ms']:,} ms | "
                f"{savings['latency_percent']:.2f}% lower |"
            ),
            (
                f"| Tool calls | {baseline['tool_calls']} | "
                f"{marginal['tool_calls']} | "
                f"{savings['tool_calls_percent']:.2f}% fewer |"
            ),
            (
                "| Tokens per resolved task | "
                f"{_format_optional_number(baseline_efficiency['tokens_per_resolved'])} | "
                f"{_format_optional_number(marginal_efficiency['tokens_per_resolved'])} | — |"
            ),
            (
                "| USD per resolved task | "
                f"{_format_optional_usd(baseline_efficiency['usd_per_resolved'])} | "
                f"{_format_optional_usd(marginal_efficiency['usd_per_resolved'])} | — |"
            ),
            "",
            (
                f"Token savings {confidence_percent:.1f}% bootstrap interval: "
                f"**{ci[0]:.2f}% to {ci[1]:.2f}%**."
            ),
            (
                f"Quality preserved within the {margin:.2f} pp non-inferiority margin: "
                f"**{quality['preserved_within_margin']}**."
            ),
            f"Regressions: **{quality['regressions']}**. Recoveries: **{quality['recoveries']}**.",
            "",
        ]
    )
