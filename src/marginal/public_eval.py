"""Measured comparison utilities for public agent benchmarks."""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Measured result for one benchmark instance.

    ``tokens/usd/latency_ms`` describe the agent workload. Governance overhead is stored
    separately so reports can show both gross savings and net savings after MARGINAL's own
    cost. Existing v0.2 JSONL rows remain valid because all new fields default to zero.
    """

    instance_id: str
    resolved: bool
    tokens: int
    usd: float = 0.0
    latency_ms: int = 0
    tool_calls: int = 0
    repeated_calls: int = 0
    governance_tokens: int = 0
    governance_usd: float = 0.0
    usd_measured: bool = True
    governance_latency_ms: int = 0
    reviewed_stops: int = 0
    false_stops: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, str) or not self.instance_id:
            raise ValueError("instance_id must not be empty")
        if not isinstance(self.resolved, bool):
            raise TypeError("resolved must be a boolean")
        for name in (
            "tokens",
            "latency_ms",
            "tool_calls",
            "repeated_calls",
            "governance_tokens",
            "governance_latency_ms",
            "reviewed_stops",
            "false_stops",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError("metrics must be non-negative")
        for name in ("usd", "governance_usd"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(float(value)) or value < 0:
                raise ValueError("metrics must be finite and non-negative")
            object.__setattr__(self, name, float(value))
        if not isinstance(self.usd_measured, bool):
            raise TypeError("usd_measured must be a boolean")
        if self.false_stops > self.reviewed_stops:
            raise ValueError("false_stops cannot exceed reviewed_stops")

    @property
    def effective_tokens(self) -> int:
        return self.tokens + self.governance_tokens

    @property
    def effective_usd(self) -> float:
        return self.usd + self.governance_usd

    @property
    def effective_latency_ms(self) -> int:
        return self.latency_ms + self.governance_latency_ms


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
                    repeated_calls=item.get("repeated_calls", 0),
                    governance_tokens=item.get("governance_tokens", 0),
                    governance_usd=item.get("governance_usd", 0.0),
                    usd_measured=item.get("usd_measured", True),
                    governance_latency_ms=item.get("governance_latency_ms", 0),
                    reviewed_stops=item.get("reviewed_stops", 0),
                    false_stops=item.get("false_stops", 0),
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
    governance_tokens = sum(record.governance_tokens for record in records)
    governance_usd = sum(record.governance_usd for record in records)
    governance_latency_ms = sum(record.governance_latency_ms for record in records)
    tokens = sum(record.tokens for record in records)
    usd = sum(record.usd for record in records)
    usd_measured = all(record.usd_measured for record in records)
    latency_ms = sum(record.latency_ms for record in records)
    reviewed_stops = sum(record.reviewed_stops for record in records)
    false_stops = sum(record.false_stops for record in records)
    return {
        "tasks": tasks,
        "resolved": resolved,
        "resolve_rate": resolved / tasks,
        "tokens": tokens,
        "usd": round(usd, 6) if usd_measured else None,
        "latency_ms": latency_ms,
        "tool_calls": sum(record.tool_calls for record in records),
        "repeated_calls": sum(record.repeated_calls for record in records),
        "governance_tokens": governance_tokens,
        "governance_usd": round(governance_usd, 6) if usd_measured else None,
        "governance_latency_ms": governance_latency_ms,
        "effective_tokens": tokens + governance_tokens,
        "effective_usd": round(usd + governance_usd, 6) if usd_measured else None,
        "effective_latency_ms": latency_ms + governance_latency_ms,
        "reviewed_stops": reviewed_stops,
        "false_stops": false_stops,
        "false_stop_rate": false_stops / reviewed_stops if reviewed_stops else None,
    }


def _saving(original: float, optimized: float) -> float:
    return round((original - optimized) / original * 100.0, 2) if original else 0.0


def _optional_saving(original: Any, optimized: Any) -> float | None:
    if original is None or optimized is None:
        return None
    return _saving(float(original), float(optimized))


def _bootstrap_token_savings(
    pairs: list[tuple[RunRecord, RunRecord]],
    samples: int,
    seed: int,
    confidence_level: float,
    *,
    include_governance: bool,
) -> tuple[float, float]:
    if samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        draw = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        if include_governance:
            baseline = sum(left.effective_tokens for left, _ in draw)
            marginal = sum(right.effective_tokens for _, right in draw)
        else:
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
    minimum_net_token_savings_percent: float = 0.0,
    max_false_stop_rate: float = 0.0,
) -> dict[str, Any]:
    """Compare matched executions without imputing missing tasks.

    The intervention earns a ``supported`` status only when quality is preserved, reviewed
    false stops stay within the configured threshold, and net token savings after governance
    overhead exceed the configured minimum. Otherwise MARGINAL should be treated as unsafe or
    pass through rather than manufacturing a savings claim.
    """

    for name, value in (
        ("quality_margin_pp", quality_margin_pp),
        ("minimum_net_token_savings_percent", minimum_net_token_savings_percent),
        ("max_false_stop_rate", max_false_stop_rate),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a number")
        if not math.isfinite(float(value)):
            raise ValueError(f"{name} must be finite")
    if quality_margin_pp < 0:
        raise ValueError("quality_margin_pp must be non-negative")
    if minimum_net_token_savings_percent < 0:
        raise ValueError("minimum_net_token_savings_percent must be non-negative")
    if not 0.0 <= max_false_stop_rate <= 1.0:
        raise ValueError("max_false_stop_rate must be between 0 and 1")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    quality_margin_pp = float(quality_margin_pp)
    minimum_net_token_savings_percent = float(minimum_net_token_savings_percent)
    max_false_stop_rate = float(max_false_stop_rate)

    if set(baseline) != set(marginal):
        missing = sorted(set(baseline) ^ set(marginal))
        raise ValueError(f"baseline and MARGINAL instance IDs differ: {missing[:5]}")
    ids = sorted(baseline)
    baseline_rows = [baseline[item] for item in ids]
    marginal_rows = [marginal[item] for item in ids]
    baseline_total = _aggregate(baseline_rows)
    marginal_total = _aggregate(marginal_rows)
    quality_evaluable = int(baseline_total["resolved"]) > 0 and int(marginal_total["resolved"]) > 0
    delta_pp = round(
        (marginal_total["resolve_rate"] - baseline_total["resolve_rate"]) * 100.0,
        2,
    )
    pairs = list(zip(baseline_rows, marginal_rows, strict=True))
    net_token_ci = _bootstrap_token_savings(
        pairs,
        bootstrap_samples,
        seed,
        confidence_level,
        include_governance=True,
    )
    gross_token_ci = _bootstrap_token_savings(
        pairs,
        bootstrap_samples,
        seed,
        confidence_level,
        include_governance=False,
    )

    def efficiency(total: dict[str, Any], *, include_governance: bool) -> dict[str, float | None]:
        resolved = int(total["resolved"])
        if resolved == 0:
            return {"tokens_per_resolved": None, "usd_per_resolved": None}
        token_key = "effective_tokens" if include_governance else "tokens"
        usd_key = "effective_usd" if include_governance else "usd"
        return {
            "tokens_per_resolved": round(float(total[token_key]) / resolved, 6),
            "usd_per_resolved": (
                round(float(total[usd_key]) / resolved, 6) if total[usd_key] is not None else None
            ),
        }

    gross_savings = {
        "tokens_percent": _saving(float(baseline_total["tokens"]), float(marginal_total["tokens"])),
        "usd_percent": _optional_saving(baseline_total["usd"], marginal_total["usd"]),
        "latency_percent": _saving(
            float(baseline_total["latency_ms"]),
            float(marginal_total["latency_ms"]),
        ),
        "tool_calls_percent": _saving(
            float(baseline_total["tool_calls"]),
            float(marginal_total["tool_calls"]),
        ),
        "repeated_calls_percent": _saving(
            float(baseline_total["repeated_calls"]),
            float(marginal_total["repeated_calls"]),
        ),
        "confidence_level": confidence_level,
        "tokens_confidence_interval": list(gross_token_ci) if quality_evaluable else None,
    }
    net_savings = {
        "tokens_percent": _saving(
            float(baseline_total["effective_tokens"]),
            float(marginal_total["effective_tokens"]),
        ),
        "usd_percent": _optional_saving(
            baseline_total["effective_usd"], marginal_total["effective_usd"]
        ),
        "latency_percent": _saving(
            float(baseline_total["effective_latency_ms"]),
            float(marginal_total["effective_latency_ms"]),
        ),
        "tool_calls_percent": gross_savings["tool_calls_percent"],
        "repeated_calls_percent": gross_savings["repeated_calls_percent"],
        "confidence_level": confidence_level,
        "tokens_confidence_interval": list(net_token_ci) if quality_evaluable else None,
        "tokens_95pct_ci": list(net_token_ci) if quality_evaluable else None,
    }

    quality_margin_value = float(quality_margin_pp)
    quality_preserved = delta_pp >= -quality_margin_value if quality_evaluable else None
    has_verified_success = int(marginal_total["resolved"]) > 0
    false_stop_rate = marginal_total["false_stop_rate"]
    false_stops_acceptable = false_stop_rate is None or float(false_stop_rate) <= float(
        max_false_stop_rate
    )
    if not quality_evaluable:
        intervention_status = "pass_through"
    elif not quality_preserved:
        intervention_status = "quality_regression"
    elif not false_stops_acceptable:
        intervention_status = "false_stop_risk"
    elif not has_verified_success or float(cast(float, net_savings["tokens_percent"])) <= float(
        minimum_net_token_savings_percent
    ):
        intervention_status = "pass_through"
    else:
        intervention_status = "supported"

    return {
        "benchmark": "public-agent-benchmark-comparison-v3",
        "tasks": len(ids),
        "baseline": baseline_total,
        "marginal": marginal_total,
        "efficiency": {
            "baseline": efficiency(baseline_total, include_governance=True),
            "marginal": efficiency(marginal_total, include_governance=True),
        },
        "agent_only_efficiency": {
            "baseline": efficiency(baseline_total, include_governance=False),
            "marginal": efficiency(marginal_total, include_governance=False),
        },
        "gross_savings": gross_savings,
        "net_savings": net_savings,
        # Backward-compatible key. For rows without governance overhead it is numerically
        # identical to v0.2. For new evidence it deliberately points to the net result.
        "savings": net_savings,
        "governance": {
            "tokens": marginal_total["governance_tokens"],
            "usd": marginal_total["governance_usd"],
            "latency_ms": marginal_total["governance_latency_ms"],
        },
        "quality": {
            "resolved_delta_pp": delta_pp,
            "non_inferiority_margin_pp": quality_margin_pp,
            "preserved_within_margin": quality_preserved,
            "preserved_within_one_pp": delta_pp >= -1.0 if quality_evaluable else None,
            "evaluable": quality_evaluable,
            "regressions": sum(
                baseline[item].resolved and not marginal[item].resolved for item in ids
            ),
            "recoveries": sum(
                not baseline[item].resolved and marginal[item].resolved for item in ids
            ),
            "reviewed_stops": marginal_total["reviewed_stops"],
            "false_stops": marginal_total["false_stops"],
            "false_stop_rate": false_stop_rate,
            "max_false_stop_rate": max_false_stop_rate,
            "false_stops_acceptable": false_stops_acceptable,
            "has_verified_success": has_verified_success,
        },
        "intervention": {
            "status": intervention_status,
            "minimum_net_token_savings_percent": minimum_net_token_savings_percent,
            "net_positive": float(cast(float, net_savings["tokens_percent"])) > 0.0,
            "graceful_irrelevance": intervention_status == "pass_through",
            "eligible_for_support": (
                quality_preserved is True and false_stops_acceptable and has_verified_success
            ),
        },
    }


def _format_optional_number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.2f}"


def _format_optional_usd(value: float | None) -> str:
    return "n/a" if value is None else f"${value:.6f}"


def _format_optional_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100.0:.2f}%"


def render_public_report(result: dict[str, Any]) -> str:
    baseline = result["baseline"]
    marginal = result["marginal"]
    savings = result["savings"]
    gross = result.get("gross_savings", savings)
    quality = result["quality"]
    efficiency = result["efficiency"]
    baseline_efficiency = efficiency["baseline"]
    marginal_efficiency = efficiency["marginal"]
    ci = savings["tokens_confidence_interval"]
    confidence_percent = float(savings["confidence_level"]) * 100.0
    margin = float(quality["non_inferiority_margin_pp"])
    intervention = result.get("intervention", {"status": "unclassified"})
    governance = result.get("governance", {"tokens": 0, "usd": 0.0, "latency_ms": 0})
    usd_change = "n/a" if savings["usd_percent"] is None else f"{savings['usd_percent']:.2f}% lower"
    quality_result = (
        quality["preserved_within_margin"] if quality.get("evaluable", True) else "not evaluable"
    )
    return "\n".join(
        [
            "# Measured public benchmark comparison",
            "",
            "This report compares matched executions. It does not estimate or impute missing runs.",
            "MARGINAL overhead is counted in net efficiency and net savings.",
            "",
            "| Metric | Baseline | MARGINAL | Change |",
            "|---|---:|---:|---:|",
            (
                f"| Resolved | {baseline['resolved']}/{baseline['tasks']} | "
                f"{marginal['resolved']}/{marginal['tasks']} | "
                f"{quality['resolved_delta_pp']:+.2f} pp |"
            ),
            (
                f"| Agent tokens | {baseline['tokens']:,} | "
                f"{marginal['tokens']:,} | {gross['tokens_percent']:.2f}% fewer |"
            ),
            (
                f"| Effective tokens (incl. governance) | {baseline['effective_tokens']:,} | "
                f"{marginal['effective_tokens']:,} | {savings['tokens_percent']:.2f}% fewer |"
            ),
            (
                "| Effective USD | "
                f"{_format_optional_usd(baseline['effective_usd'])} | "
                f"{_format_optional_usd(marginal['effective_usd'])} | "
                f"{usd_change} |"
            ),
            (
                f"| Effective latency | {baseline['effective_latency_ms']:,} ms | "
                f"{marginal['effective_latency_ms']:,} ms | "
                f"{savings['latency_percent']:.2f}% lower |"
            ),
            (
                f"| Tool calls | {baseline['tool_calls']} | "
                f"{marginal['tool_calls']} | {savings['tool_calls_percent']:.2f}% fewer |"
            ),
            (
                f"| Repeated calls | {baseline['repeated_calls']} | "
                f"{marginal['repeated_calls']} | "
                f"{savings['repeated_calls_percent']:.2f}% fewer |"
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
            "## Governance tax",
            "",
            (
                f"MARGINAL overhead: **{governance['tokens']:,} tokens**, "
                f"**{_format_optional_usd(governance['usd'])}**, "
                f"**{governance['latency_ms']:,} ms**."
            ),
            (
                f"Gross agent-token savings: **{gross['tokens_percent']:.2f}%**. "
                f"Net token savings after governance: **{savings['tokens_percent']:.2f}%**."
            ),
            "",
            "## Quality and intervention decision",
            "",
            (
                f"Net token savings {confidence_percent:.1f}% bootstrap interval: "
                f"**{ci[0]:.2f}% to {ci[1]:.2f}%**."
                if quality.get("evaluable", True)
                else "Token uncertainty: **not evaluable** without a successful task in both arms."
            ),
            (
                f"Quality preserved within the {margin:.2f} pp non-inferiority margin: "
                f"**{quality_result}**."
            ),
            f"Regressions: **{quality['regressions']}**. Recoveries: **{quality['recoveries']}**.",
            (
                f"Reviewed deny recommendations: **{quality.get('reviewed_stops', 0)}**. "
                f"False stops: **{quality.get('false_stops', 0)}** "
                f"({_format_optional_rate(quality.get('false_stop_rate'))})."
            ),
            f"Intervention status: **{intervention['status']}**.",
            (
                "No verified successful task was observed, so token efficiency per resolved "
                "task is undefined and the intervention cannot be classified as supported."
                if not quality.get("has_verified_success", True)
                else ""
            ),
            "",
            (
                "`pass_through` is a valid result: it means MARGINAL did not demonstrate "
                "enough net value to justify intervention under the preregistered threshold."
            ),
            "",
        ]
    )
