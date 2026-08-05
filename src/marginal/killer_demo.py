"""Deterministic end-to-end demonstration of marginal compute allocation."""

from __future__ import annotations

import html
import json
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .adapters import funded_call
from .budget import BudgetLimits
from .models import Action, Cost
from .policy import MarginalPolicy, PolicyConfig
from .treasury import Treasury

Runner = Callable[[], str]


@dataclass(frozen=True, slots=True)
class _Candidate:
    action: Action
    run: Runner


class _MemoryTraceSink:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event: Mapping[str, Any]) -> None:
        self.events.append(dict(event))


def _seed_workspace(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pricing.py").write_text(
        '"""Small checkout pricing module used by the MARGINAL demo."""\n\n'
        "def apply_discount(total: float, rate: float) -> float:\n"
        "    return total - rate\n",
        encoding="utf-8",
    )
    (path / "test_pricing.py").write_text(
        "from pricing import apply_discount\n\n"
        "def test_twenty_percent_discount() -> None:\n"
        "    assert apply_discount(100.0, 0.20) == 80.0\n",
        encoding="utf-8",
    )
    (path / "README.md").write_text(
        "# Checkout service\n\nA deterministic micro-repository for the MARGINAL demo.\n",
        encoding="utf-8",
    )


def _load_discount(path: Path) -> Callable[[float, float], float]:
    namespace: dict[str, Any] = {}
    source = (path / "pricing.py").read_text(encoding="utf-8")
    exec(compile(source, str(path / "pricing.py"), "exec"), namespace)
    function = namespace["apply_discount"]
    if not callable(function):
        raise TypeError("apply_discount is not callable")
    return cast(Callable[[float, float], float], function)


def _verify_workspace(path: Path) -> bool:
    try:
        return _load_discount(path)(100.0, 0.20) == 80.0
    except Exception:
        return False


def _stages(path: Path) -> tuple[tuple[str, tuple[_Candidate, ...]], ...]:
    def inspect_assertion() -> str:
        test = (path / "test_pricing.py").read_text(encoding="utf-8")
        return "expected 80.0" if "80.0" in test else "assertion not found"

    def scan_repository() -> str:
        return ", ".join(sorted(item.name for item in path.iterdir()))

    def ask_parallel_reviewers() -> str:
        return "reviewer-a: inspect arithmetic; reviewer-b: inspect type contract"

    def apply_targeted_patch() -> str:
        module = path / "pricing.py"
        source = module.read_text(encoding="utf-8")
        module.write_text(
            source.replace("return total - rate", "return total * (1 - rate)"),
            encoding="utf-8",
        )
        return "replaced subtraction with percentage multiplication"

    def rewrite_module() -> str:
        (path / "pricing.py").write_text(
            '"""Small checkout pricing module used by the MARGINAL demo."""\n\n'
            "def apply_discount(total: float, rate: float) -> float:\n"
            "    return total * (1 - rate)\n",
            encoding="utf-8",
        )
        return "rewrote the complete pricing module"

    def ask_frontier_model() -> str:
        module = path / "pricing.py"
        source = module.read_text(encoding="utf-8")
        if "return total * (1 - rate)" not in source:
            source = source.replace("return total - rate", "return total * (1 - rate)")
            module.write_text(source, encoding="utf-8")
        return "alternative patch agreed with the targeted correction"

    def targeted_verifier() -> str:
        if not _verify_workspace(path):
            raise AssertionError("targeted verifier failed")
        return "targeted verifier passed"

    def full_suite() -> str:
        compile((path / "pricing.py").read_text(encoding="utf-8"), "pricing.py", "exec")
        compile(
            (path / "test_pricing.py").read_text(encoding="utf-8"),
            "test_pricing.py",
            "exec",
        )
        if not _verify_workspace(path):
            raise AssertionError("full suite failed")
        return "full suite passed"

    def premium_audit() -> str:
        source = (path / "pricing.py").read_text(encoding="utf-8")
        if "return total - rate" in source or not _verify_workspace(path):
            raise AssertionError("premium audit failed")
        return "premium audit found no remaining defect"

    return (
        (
            "Diagnose",
            (
                _Candidate(
                    Action(
                        name="inspect the failing assertion",
                        kind="research",
                        cost=Cost(tokens=1_200, usd=0.006, latency_ms=350),
                        expected_gain=0.22,
                        metadata={"stage": "diagnose"},
                    ),
                    inspect_assertion,
                ),
                _Candidate(
                    Action(
                        name="scan the entire repository",
                        kind="research",
                        cost=Cost(tokens=9_000, usd=0.045, latency_ms=2_200),
                        expected_gain=0.05,
                        metadata={"stage": "diagnose"},
                    ),
                    scan_repository,
                ),
                _Candidate(
                    Action(
                        name="ask two parallel reviewers",
                        kind="review",
                        cost=Cost(tokens=14_000, usd=0.12, latency_ms=4_500),
                        expected_gain=0.04,
                        metadata={"stage": "diagnose"},
                    ),
                    ask_parallel_reviewers,
                ),
            ),
        ),
        (
            "Fix",
            (
                _Candidate(
                    Action(
                        name="apply the targeted one-line patch",
                        kind="generation",
                        cost=Cost(tokens=2_400, usd=0.018, latency_ms=700),
                        expected_gain=0.50,
                        metadata={"stage": "fix"},
                    ),
                    apply_targeted_patch,
                ),
                _Candidate(
                    Action(
                        name="rewrite the complete pricing module",
                        kind="generation",
                        cost=Cost(tokens=12_000, usd=0.11, latency_ms=3_200),
                        expected_gain=0.20,
                        metadata={"stage": "fix"},
                    ),
                    rewrite_module,
                ),
                _Candidate(
                    Action(
                        name="ask a frontier model for an alternative patch",
                        kind="generation",
                        cost=Cost(tokens=18_000, usd=0.28, latency_ms=5_500),
                        expected_gain=0.15,
                        metadata={"stage": "fix"},
                    ),
                    ask_frontier_model,
                ),
            ),
        ),
        (
            "Verify",
            (
                _Candidate(
                    Action(
                        name="run the targeted verifier",
                        kind="verification",
                        cost=Cost(tokens=700, usd=0.002, latency_ms=180),
                        expected_gain=0.35,
                        is_verification=True,
                        metadata={"stage": "verify"},
                    ),
                    targeted_verifier,
                ),
                _Candidate(
                    Action(
                        name="run the full test suite",
                        kind="verification",
                        cost=Cost(tokens=4_500, usd=0.012, latency_ms=1_400),
                        expected_gain=0.08,
                        is_verification=True,
                        metadata={"stage": "verify"},
                    ),
                    full_suite,
                ),
                _Candidate(
                    Action(
                        name="request a premium model audit",
                        kind="verification",
                        cost=Cost(tokens=11_000, usd=0.17, latency_ms=4_000),
                        expected_gain=0.05,
                        is_verification=True,
                        metadata={"stage": "verify"},
                    ),
                    premium_audit,
                ),
            ),
        ),
    )


def _empty_metrics() -> dict[str, Any]:
    return {
        "tokens": 0,
        "usd": 0.0,
        "latency_ms": 0,
        "calls": 0,
        "verified_success": False,
    }


def _record(metrics: dict[str, Any], cost: Cost) -> None:
    metrics["tokens"] += cost.tokens
    metrics["usd"] += cost.usd
    metrics["latency_ms"] += cost.latency_ms
    metrics["calls"] += 1


def _finalize(metrics: dict[str, Any]) -> dict[str, Any]:
    result = dict(metrics)
    result["usd"] = round(float(result["usd"]), 6)
    return result


def _savings(baseline: dict[str, Any], marginal: dict[str, Any], key: str) -> float:
    original = float(baseline[key])
    optimized = float(marginal[key])
    return round((original - optimized) / original * 100.0, 2) if original else 0.0


def _candidate_rows(event: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in event["candidates"]:
        action = item["action"]
        decision = item["decision"]
        rows.append(
            {
                "name": action["name"],
                "kind": action["kind"],
                "tokens": action["cost"]["tokens"],
                "usd": action["cost"]["usd"],
                "expected_gain": decision["expected_gain"],
                "score": round(float(decision["score"]), 6),
                "allowed": decision["allowed"],
                "reason": decision["reason"],
            }
        )
    return rows


def run_killer_demo(output_dir: str | Path | None = None) -> dict[str, Any]:
    """Run the baseline and MARGINAL against the same deterministic coding defect."""

    with tempfile.TemporaryDirectory(prefix="marginal-killer-demo-") as temporary:
        root = Path(temporary)
        baseline_workspace = root / "baseline"
        marginal_workspace = root / "marginal"
        _seed_workspace(baseline_workspace)
        _seed_workspace(marginal_workspace)
        initial_verified_success = _verify_workspace(baseline_workspace)
        if initial_verified_success or _verify_workspace(marginal_workspace):
            raise RuntimeError("killer demo fixture must begin in a failing state")

        baseline = _empty_metrics()
        baseline_actions: list[dict[str, Any]] = []
        for stage_name, candidates in _stages(baseline_workspace):
            for candidate in candidates:
                output = candidate.run()
                _record(baseline, candidate.action.cost)
                baseline_actions.append(
                    {
                        "stage": stage_name,
                        "name": candidate.action.name,
                        "tokens": candidate.action.cost.tokens,
                        "output": output,
                    }
                )
        baseline["verified_success"] = _verify_workspace(baseline_workspace)

        trace = _MemoryTraceSink()
        policy = MarginalPolicy(
            PolicyConfig(
                outcome_value_usd=1.0,
                token_shadow_price_per_million_usd=20.0,
                latency_shadow_price_per_second_usd=0.002,
                risk_shadow_price_usd=1.0,
                minimum_roi=1.0,
                minimum_expected_gain=0.001,
                target_success_probability=1.0,
            )
        )
        treasury = Treasury(
            BudgetLimits(
                max_tokens=40_000,
                max_usd=1.0,
                verification_reserve_tokens=700,
            ),
            policy=policy,
            trace_sink=trace,
            name="killer-demo",
        )

        stage_results: list[dict[str, Any]] = []
        marginal_outputs: list[dict[str, Any]] = []
        for stage_name, candidates in _stages(marginal_workspace):
            before = len(trace.events)
            allocation = treasury.fund_best(candidate.action for candidate in candidates)
            ranking = next(
                event
                for event in trace.events[before:]
                if event.get("event") == "candidate_ranking"
            )
            if allocation is None:
                raise RuntimeError(f"no action funded for stage {stage_name}")
            runner = next(
                candidate.run
                for candidate in candidates
                if candidate.action.name == allocation.action.name
            )
            output = funded_call(treasury, allocation, runner)
            stage_results.append(
                {
                    "stage": stage_name,
                    "selected": allocation.action.name,
                    "decision": allocation.decision.reason,
                    "candidates": _candidate_rows(ranking),
                }
            )
            marginal_outputs.append(
                {
                    "stage": stage_name,
                    "name": allocation.action.name,
                    "output": output,
                }
            )

        marginal: dict[str, Any] = {
            "tokens": treasury.usage.tokens,
            "usd": treasury.usage.usd,
            "latency_ms": treasury.usage.latency_ms,
            "calls": len(marginal_outputs),
            "verified_success": _verify_workspace(marginal_workspace),
        }

    baseline_result = _finalize(baseline)
    marginal_result = _finalize(marginal)
    result: dict[str, Any] = {
        "demo": "marginal-killer-demo-v1",
        "initial_verified_success": initial_verified_success,
        "scenario": "Fix a percentage-discount bug in a deterministic Python repository",
        "defect": {
            "before": "return total - rate",
            "after": "return total * (1 - rate)",
            "verifier": "apply_discount(100.0, 0.20) == 80.0",
        },
        "disclaimer": (
            "Deterministic functional demonstration using declared action-cost estimates; "
            "not provider telemetry, not a production benchmark, and not a claim about "
            "every agent workload."
        ),
        "baseline": baseline_result,
        "marginal": marginal_result,
        "savings": {
            "tokens_percent": _savings(baseline_result, marginal_result, "tokens"),
            "usd_percent": _savings(baseline_result, marginal_result, "usd"),
            "latency_percent": _savings(baseline_result, marginal_result, "latency_ms"),
            "calls_percent": _savings(baseline_result, marginal_result, "calls"),
        },
        "baseline_actions": baseline_actions,
        "marginal_actions": marginal_outputs,
        "stages": stage_results,
    }

    if output_dir is not None:
        _write_artifacts(Path(output_dir), result, trace.events)
    return result


def render_killer_demo_markdown(result: dict[str, Any]) -> str:
    baseline = result["baseline"]
    marginal = result["marginal"]
    savings = result["savings"]
    lines = [
        "# MARGINAL Killer Demo",
        "",
        "**Fund only the next action worth taking.**",
        "",
        f"> {result['disclaimer']}",
        "",
        f"Scenario: **{result['scenario']}**",
        "",
        "![Baseline versus MARGINAL](comparison.svg)",
        "",
        "## The defect",
        "",
        "```diff",
        f"- {result['defect']['before']}",
        f"+ {result['defect']['after']}",
        "```",
        "",
        f"Verifier: `{result['defect']['verifier']}`",
        "",
        "Initial verifier: **FAIL**",
        "",
        "| Metric | Baseline: run everything | MARGINAL | Savings |",
        "|---|---:|---:|---:|",
        (
            f"| Declared tokens | {baseline['tokens']:,} | {marginal['tokens']:,} | "
            f"**{savings['tokens_percent']:.2f}%** |"
        ),
        (
            f"| Calls | {baseline['calls']} | {marginal['calls']} | "
            f"**{savings['calls_percent']:.2f}%** |"
        ),
        (
            f"| Estimated USD | ${baseline['usd']:.3f} | ${marginal['usd']:.3f} | "
            f"**{savings['usd_percent']:.2f}%** |"
        ),
        (
            f"| Estimated latency | {baseline['latency_ms']:,} ms | "
            f"{marginal['latency_ms']:,} ms | **{savings['latency_percent']:.2f}%** |"
        ),
        "| Verified outcome | PASS | PASS | preserved |",
        "",
        "## Allocation decisions",
        "",
    ]
    for stage in result["stages"]:
        lines.extend(
            [
                f"### {stage['stage']}",
                "",
                f"Funded: **{stage['selected']}** — {stage['decision']}",
                "",
                "| Candidate | Declared tokens | Expected gain | Score | Decision |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for candidate in stage["candidates"]:
            status = "FUNDED" if candidate["name"] == stage["selected"] else "SKIPPED"
            lines.append(
                f"| {candidate['name']} | {candidate['tokens']:,} | "
                f"{candidate['expected_gain']:.3f} | {candidate['score']:.3f} | "
                f"{status}: {candidate['reason']} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Reproduce",
            "",
            "```bash",
            "marginal killer-demo --output killer-demo-output",
            "```",
            "",
            "The command writes this report, a standalone HTML report, an SVG comparison, "
            "the JSON result, and the provider-neutral decision trace.",
            "",
        ]
    )
    return "\n".join(lines)


def render_killer_demo_svg(result: dict[str, Any]) -> str:
    baseline_tokens = int(result["baseline"]["tokens"])
    marginal_tokens = int(result["marginal"]["tokens"])
    chart_width = 520
    marginal_bar = max(4, round(chart_width * marginal_tokens / baseline_tokens))
    savings = float(result["savings"]["tokens_percent"])
    return "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="230"',
            ' viewBox="0 0 720 230" role="img"',
            ' aria-label="Baseline versus MARGINAL token use">',
            '  <rect width="720" height="230" rx="20" fill="#0b1020"/>',
            '  <text x="40" y="42" fill="#ffffff"',
            ' font-family="Arial, sans-serif" font-size="24" font-weight="700">',
            "Declared token cost for the same verified fix</text>",
            '  <text x="40" y="88" fill="#cbd5e1"',
            ' font-family="Arial, sans-serif" font-size="16">Baseline</text>',
            f'  <rect x="150" y="68" width="{chart_width}" height="30"',
            ' rx="8" fill="#ef4444"/>',
            '  <text x="680" y="89" text-anchor="end" fill="#ffffff"',
            ' font-family="Arial, sans-serif" font-size="16">',
            f"{baseline_tokens:,}</text>",
            '  <text x="40" y="148" fill="#cbd5e1"',
            ' font-family="Arial, sans-serif" font-size="16">MARGINAL</text>',
            f'  <rect x="150" y="128" width="{marginal_bar}" height="30"',
            ' rx="8" fill="#22c55e"/>',
            f'  <text x="{160 + marginal_bar}" y="149" fill="#ffffff"',
            ' font-family="Arial, sans-serif" font-size="16">',
            f"{marginal_tokens:,}</text>",
            '  <text x="40" y="202" fill="#86efac"',
            ' font-family="Arial, sans-serif" font-size="20" font-weight="700">',
            f"{savings:.2f}% fewer declared tokens · outcome preserved</text>",
            "</svg>",
            "",
        ]
    )


def _candidate_lookup(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        candidate["name"]: candidate
        for stage in result["stages"]
        for candidate in stage["candidates"]
    }


def _render_flow_steps(
    actions: list[dict[str, Any]],
    candidates: dict[str, dict[str, Any]],
    selected_names: set[str],
    *,
    marginal: bool,
) -> str:
    rows: list[str] = []
    for position, action in enumerate(actions, start=1):
        candidate = candidates[action["name"]]
        justified = action["name"] in selected_names
        if marginal:
            state_class = "funded"
            state_label = "Funded"
            state_icon = "✓"
        elif justified:
            state_class = "justified"
            state_label = "Justified"
            state_icon = "✓"
        else:
            state_class = "excess"
            state_label = "Executed"
            state_icon = "×"
        rows.append(
            "".join(
                [
                    f'<li class="flow-step {state_class}">',
                    f'<span class="step-index">{position}</span>',
                    '<span class="step-copy">',
                    f"<strong>{html.escape(action['name'])}</strong>",
                    f"<small>{html.escape(action['stage'])} · "
                    f"{candidate['tokens']:,} tokens</small>",
                    "</span>",
                    '<span class="step-cost">',
                    f"<strong>${candidate['usd']:.3f}</strong>",
                    f"<small>{state_label}</small>",
                    "</span>",
                    f'<span class="step-state" aria-label="{state_label}">{state_icon}</span>',
                    "</li>",
                ]
            )
        )
    return "".join(rows)


def _render_allocation_rows(result: dict[str, Any]) -> str:
    rows: list[str] = []
    for stage in result["stages"]:
        for candidate in stage["candidates"]:
            funded = candidate["name"] == stage["selected"]
            state_class = "funded-pill" if funded else "rejected-pill"
            state_label = "FUNDED" if funded else "REJECTED"
            rows.append(
                "".join(
                    [
                        "<tr>",
                        "<td>",
                        f"<strong>{html.escape(candidate['name'])}</strong>",
                        f"<small>{html.escape(stage['stage'])}</small>",
                        "</td>",
                        "<td>",
                        f"<strong>${candidate['usd']:.3f}</strong>",
                        f"<small>{candidate['tokens']:,} tokens</small>",
                        "</td>",
                        "<td>",
                        f"<strong>{candidate['expected_gain']:.3f}</strong>",
                        f"<small>score {candidate['score']:.3f}</small>",
                        "</td>",
                        "<td>",
                        f'<span class="decision-pill {state_class}">{state_label}</span>',
                        f"<small>{html.escape(candidate['reason'])}</small>",
                        "</td>",
                        "</tr>",
                    ]
                )
            )
    return "".join(rows)


def render_killer_demo_html(result: dict[str, Any]) -> str:
    baseline = result["baseline"]
    marginal = result["marginal"]
    savings = result["savings"]
    candidates = _candidate_lookup(result)
    selected_names = {stage["selected"] for stage in result["stages"]}
    baseline_steps = _render_flow_steps(
        result["baseline_actions"],
        candidates,
        selected_names,
        marginal=False,
    )
    marginal_steps = _render_flow_steps(
        result["marginal_actions"],
        candidates,
        selected_names,
        marginal=True,
    )
    allocation_rows = _render_allocation_rows(result)
    page = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#050814">
  <meta name="color-scheme" content="dark">
  <title>MARGINAL Killer Demo</title>
  <meta name="description"
    content="A deterministic comparison between a baseline workflow and MARGINAL-funded execution.">
  <meta property="og:title" content="MARGINAL Killer Demo">
  <meta property="og:description"
    content="Same verified outcome. Far fewer tokens, lower cost, lower latency.">
  <meta property="og:type" content="website">
  <style>
    :root {
      --canvas: #02040a;
      --bg: #050814;
      --bg-elevated: rgba(10, 16, 31, 0.82);
      --panel: rgba(11, 19, 36, 0.82);
      --panel-strong: rgba(13, 22, 42, 0.95);
      --line: rgba(148, 163, 184, 0.16);
      --line-strong: rgba(148, 163, 184, 0.26);
      --text: #f8fafc;
      --text-soft: #d8e1ef;
      --muted: #8fa1b9;
      --blue: #2f6df6;
      --cyan: #22d3ee;
      --purple: #7c3aed;
      --green: #34d399;
      --green-soft: rgba(52, 211, 153, 0.12);
      --red: #fb7185;
      --red-soft: rgba(251, 113, 133, 0.11);
      --amber: #fbbf24;
      --radius-xl: 28px;
      --radius-lg: 22px;
      --radius-md: 16px;
      --shadow: 0 32px 100px rgba(0, 0, 0, 0.48);
      --font: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",
        "Inter", "Segoe UI", sans-serif;
      --mono: "SFMono-Regular", "Cascadia Code", "Roboto Mono", Consolas, monospace;
    }

    * {
      box-sizing: border-box;
    }

    html {
      scroll-behavior: smooth;
      background: var(--canvas);
    }

    body {
      margin: 0;
      min-width: 320px;
      color: var(--text);
      background:
        radial-gradient(circle at 82% 8%, rgba(124, 58, 237, 0.23), transparent 28rem),
        radial-gradient(circle at 12% 70%, rgba(47, 109, 246, 0.14), transparent 30rem),
        linear-gradient(180deg, #010207 0%, #050814 52%, #071226 100%);
      font-family: var(--font);
      font-size: 16px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
    }

    a {
      color: inherit;
      text-decoration: none;
    }

    button,
    a {
      -webkit-tap-highlight-color: transparent;
    }

    button {
      font: inherit;
    }

    .skip-link {
      position: fixed;
      top: 12px;
      left: 12px;
      z-index: 100;
      padding: 10px 14px;
      border-radius: 10px;
      color: #020617;
      background: #f8fafc;
      transform: translateY(-160%);
    }

    .skip-link:focus {
      transform: translateY(0);
    }

    .page-wrap {
      width: min(1520px, calc(100% - 28px));
      margin: 14px auto;
      padding-bottom: 14px;
    }

    .browser-shell {
      position: relative;
      overflow: hidden;
      border: 1px solid rgba(148, 163, 184, 0.28);
      border-radius: 24px;
      background: rgba(4, 8, 18, 0.93);
      box-shadow: var(--shadow);
      isolation: isolate;
    }

    .browser-shell::before {
      position: absolute;
      inset: 0;
      z-index: -2;
      content: "";
      background:
        linear-gradient(rgba(148, 163, 184, 0.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(148, 163, 184, 0.025) 1px, transparent 1px);
      background-size: 42px 42px;
      mask-image: linear-gradient(to bottom, black, transparent 78%);
    }

    .browser-chrome {
      display: grid;
      grid-template-columns: 110px minmax(220px, 620px) 110px;
      align-items: center;
      justify-content: space-between;
      min-height: 50px;
      padding: 8px 18px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.12);
      background: linear-gradient(180deg, rgba(35, 35, 35, 0.96), rgba(20, 20, 21, 0.94));
    }

    .traffic-lights {
      display: flex;
      gap: 8px;
    }

    .traffic-lights span {
      width: 12px;
      height: 12px;
      border-radius: 999px;
      box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.2);
    }

    .traffic-lights span:nth-child(1) { background: #ff5f57; }
    .traffic-lights span:nth-child(2) { background: #febc2e; }
    .traffic-lights span:nth-child(3) { background: #28c840; }

    .address-bar {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 9px;
      min-height: 34px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 9px;
      color: rgba(248, 250, 252, 0.8);
      background: rgba(255, 255, 255, 0.06);
      font-size: 13px;
      letter-spacing: 0.01em;
    }

    .address-bar svg,
    .chrome-actions svg {
      width: 16px;
      height: 16px;
    }

    .chrome-actions {
      display: flex;
      justify-content: flex-end;
      gap: 13px;
      color: rgba(248, 250, 252, 0.62);
    }

    .site-header {
      position: sticky;
      top: 0;
      z-index: 30;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 28px;
      min-height: 76px;
      padding: 12px clamp(22px, 4vw, 52px);
      border-bottom: 1px solid rgba(148, 163, 184, 0.12);
      background: rgba(4, 9, 22, 0.78);
      backdrop-filter: blur(24px) saturate(145%);
    }

    .brand {
      display: inline-flex;
      align-items: center;
      gap: 14px;
      min-width: max-content;
    }

    .brand-mark {
      display: grid;
      width: 42px;
      height: 42px;
      place-items: center;
      border: 1px solid rgba(96, 165, 250, 0.28);
      border-radius: 13px;
      background:
        linear-gradient(145deg, rgba(47, 109, 246, 0.28), rgba(124, 58, 237, 0.14)),
        rgba(15, 23, 42, 0.9);
      box-shadow: 0 10px 32px rgba(47, 109, 246, 0.16);
      font-size: 25px;
      font-weight: 850;
      letter-spacing: -0.08em;
    }

    .brand-copy {
      display: flex;
      align-items: center;
      gap: 14px;
    }

    .wordmark {
      font-size: 17px;
      font-weight: 780;
      letter-spacing: 0.05em;
    }

    .brand-divider {
      width: 1px;
      height: 30px;
      background: var(--line-strong);
    }

    .brand-tagline {
      max-width: 150px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.25;
    }

    .nav {
      display: flex;
      align-items: center;
      gap: clamp(12px, 2.2vw, 30px);
      color: #b9c5d6;
      font-size: 14px;
    }

    .nav a {
      position: relative;
      padding: 12px 0;
      transition: color 180ms ease;
    }

    .nav a:hover,
    .nav a:focus-visible,
    .nav a.active {
      color: #f8fafc;
    }

    .nav a.active::after {
      position: absolute;
      right: 0;
      bottom: 4px;
      left: 0;
      height: 2px;
      border-radius: 999px;
      content: "";
      background: linear-gradient(90deg, var(--cyan), var(--purple));
    }

    .content {
      padding: 0 clamp(20px, 4vw, 52px) 28px;
    }

    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(360px, 0.9fr);
      align-items: center;
      gap: clamp(36px, 6vw, 92px);
      min-height: 430px;
      padding: clamp(54px, 7vw, 92px) 0 44px;
    }

    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 9px;
      margin-bottom: 20px;
      color: #a8c7ff;
      font-size: 12px;
      font-weight: 760;
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }

    .eyebrow::before {
      width: 26px;
      height: 1px;
      content: "";
      background: linear-gradient(90deg, var(--cyan), var(--purple));
    }

    h1,
    h2,
    h3,
    p {
      margin-top: 0;
    }

    h1 {
      max-width: 800px;
      margin-bottom: 20px;
      font-size: clamp(54px, 7.2vw, 96px);
      font-weight: 750;
      letter-spacing: -0.055em;
      line-height: 0.94;
    }

    .hero-copy {
      max-width: 760px;
      margin-bottom: 28px;
      color: var(--text-soft);
      font-size: clamp(18px, 2vw, 24px);
      line-height: 1.45;
    }

    .hero-copy strong {
      display: block;
      color: #f8fafc;
      font-weight: 620;
    }

    .hero-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 20px;
    }

    .button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      min-height: 48px;
      padding: 0 20px;
      border: 1px solid transparent;
      border-radius: 13px;
      font-size: 14px;
      font-weight: 680;
      transition:
        transform 180ms ease,
        border-color 180ms ease,
        background 180ms ease,
        box-shadow 180ms ease;
    }

    .button:hover {
      transform: translateY(-1px);
    }

    .button:focus-visible,
    .nav a:focus-visible,
    .copy-button:focus-visible {
      outline: 3px solid rgba(56, 189, 248, 0.45);
      outline-offset: 3px;
    }

    .button-primary {
      color: white;
      background: linear-gradient(120deg, #1d8cff, #7c3aed 72%);
      box-shadow: 0 12px 34px rgba(91, 76, 255, 0.32);
    }

    .button-primary:hover {
      box-shadow: 0 16px 42px rgba(91, 76, 255, 0.42);
    }

    .button-secondary {
      border-color: var(--line-strong);
      color: #e8eef8;
      background: rgba(8, 15, 29, 0.65);
    }

    .button-secondary:hover {
      border-color: rgba(125, 211, 252, 0.36);
      background: rgba(15, 23, 42, 0.92);
    }

    .disclaimer-line {
      display: flex;
      align-items: flex-start;
      gap: 9px;
      max-width: 680px;
      color: var(--muted);
      font-size: 12px;
    }

    .disclaimer-line svg {
      flex: 0 0 auto;
      width: 15px;
      height: 15px;
      margin-top: 2px;
      color: var(--amber);
    }

    .hero-visual {
      position: relative;
      min-height: 390px;
    }

    .hero-visual::before,
    .hero-visual::after {
      position: absolute;
      border-radius: 999px;
      content: "";
      filter: blur(60px);
      pointer-events: none;
    }

    .hero-visual::before {
      top: 12%;
      right: 4%;
      width: 240px;
      height: 240px;
      background: rgba(124, 58, 237, 0.3);
    }

    .hero-visual::after {
      right: 28%;
      bottom: 4%;
      width: 180px;
      height: 180px;
      background: rgba(34, 211, 238, 0.16);
    }

    .mascot-card {
      position: relative;
      z-index: 1;
      overflow: hidden;
      max-width: 480px;
      margin-left: auto;
      border: 1px solid rgba(148, 163, 184, 0.22);
      border-radius: 34px;
      background:
        linear-gradient(145deg, rgba(47, 109, 246, 0.1), rgba(124, 58, 237, 0.16)),
        rgba(7, 12, 26, 0.82);
      box-shadow:
        0 36px 80px rgba(0, 0, 0, 0.44),
        inset 0 1px 0 rgba(255, 255, 255, 0.05);
      transform: perspective(900px) rotateY(-3deg) rotateX(1deg);
    }

    .mascot-card img {
      display: block;
      width: 100%;
      height: auto;
    }

    .verified-chip {
      position: absolute;
      right: 18px;
      bottom: 18px;
      z-index: 2;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 12px;
      border: 1px solid rgba(52, 211, 153, 0.28);
      border-radius: 999px;
      color: #b7f7dc;
      background: rgba(3, 20, 18, 0.78);
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.32);
      backdrop-filter: blur(12px);
      font-size: 12px;
      font-weight: 760;
      letter-spacing: 0.04em;
    }

    .verified-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--green);
      box-shadow: 0 0 14px rgba(52, 211, 153, 0.9);
    }

    .metric-grid {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
      margin: 0 0 18px;
    }

    .metric-card {
      position: relative;
      overflow: hidden;
      min-height: 142px;
      padding: 18px 18px 14px;
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      background:
        linear-gradient(150deg, rgba(255, 255, 255, 0.025), transparent 42%),
        var(--panel);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
    }

    .metric-card::after {
      position: absolute;
      top: -55px;
      right: -48px;
      width: 110px;
      height: 110px;
      border-radius: 999px;
      content: "";
      background: rgba(47, 109, 246, 0.1);
      filter: blur(24px);
    }

    .metric-label {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;
      color: var(--muted);
      font-size: 12px;
    }

    .metric-label svg {
      width: 17px;
      height: 17px;
      color: #4ba7ff;
    }

    .metric-value {
      position: relative;
      z-index: 1;
      display: block;
      color: #f8fafc;
      font-size: clamp(22px, 2vw, 30px);
      font-weight: 560;
      letter-spacing: -0.035em;
      line-height: 1.1;
      white-space: nowrap;
    }

    .metric-value.success {
      color: #67e8c1;
    }

    .metric-context {
      position: relative;
      z-index: 1;
      display: block;
      margin-top: 6px;
      color: #71839b;
      font-size: 9px;
    }

    .sparkline {
      position: absolute;
      right: 14px;
      bottom: 10px;
      left: 14px;
      width: calc(100% - 28px);
      height: 28px;
      opacity: 0.82;
    }

    .section {
      padding: 22px 0 0;
      scroll-margin-top: 100px;
    }

    .section-heading {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 18px;
    }

    .section-heading h2 {
      margin-bottom: 4px;
      font-size: clamp(26px, 3vw, 38px);
      font-weight: 660;
      letter-spacing: -0.035em;
    }

    .section-heading p {
      max-width: 680px;
      margin-bottom: 0;
      color: var(--muted);
      font-size: 14px;
    }

    .results-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.75fr) minmax(420px, 1fr);
      gap: 14px;
      align-items: start;
    }

    .glass-card {
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      background:
        linear-gradient(150deg, rgba(255, 255, 255, 0.02), transparent 34%),
        var(--panel);
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.035),
        0 20px 60px rgba(0, 0, 0, 0.2);
      backdrop-filter: blur(18px);
    }

    .comparison-card {
      padding: 14px;
    }

    .comparison-columns {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }

    .flow-panel {
      min-width: 0;
      padding: 16px;
      border: 1px solid rgba(148, 163, 184, 0.13);
      border-radius: 18px;
      background: rgba(4, 10, 22, 0.62);
    }

    .flow-panel.marginal-panel {
      background:
        radial-gradient(circle at 70% 100%, rgba(52, 211, 153, 0.08), transparent 48%),
        rgba(4, 10, 22, 0.7);
    }

    .panel-heading {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
    }

    .panel-heading h3 {
      margin-bottom: 0;
      font-size: 17px;
      letter-spacing: -0.015em;
    }

    .count-badge {
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }

    .count-badge.baseline {
      color: #fda4af;
      background: rgba(190, 24, 93, 0.15);
    }

    .count-badge.marginal {
      color: #6ee7b7;
      background: rgba(5, 150, 105, 0.15);
    }

    .flow-list {
      display: flex;
      flex-direction: column;
      gap: 7px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .flow-step {
      position: relative;
      display: grid;
      grid-template-columns: 27px minmax(0, 1fr) auto 22px;
      align-items: center;
      gap: 9px;
      min-height: 52px;
      padding: 7px 8px;
      border: 1px solid rgba(148, 163, 184, 0.1);
      border-radius: 12px;
      background: rgba(15, 23, 42, 0.42);
    }

    .flow-step.excess {
      border-color: rgba(251, 113, 133, 0.12);
    }

    .flow-step.funded,
    .flow-step.justified {
      border-color: rgba(52, 211, 153, 0.18);
      background: linear-gradient(90deg, rgba(52, 211, 153, 0.08), rgba(15, 23, 42, 0.38));
    }

    .step-index {
      display: grid;
      width: 24px;
      height: 24px;
      place-items: center;
      border: 1px solid rgba(148, 163, 184, 0.2);
      border-radius: 999px;
      color: #dbeafe;
      background: rgba(51, 65, 85, 0.72);
      font-size: 10px;
      font-weight: 750;
    }

    .step-copy,
    .step-cost {
      display: flex;
      min-width: 0;
      flex-direction: column;
    }

    .step-copy strong,
    .step-cost strong {
      overflow: hidden;
      color: #e7edf7;
      font-size: 11px;
      font-weight: 620;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .step-copy small,
    .step-cost small {
      color: #71839b;
      font-size: 9px;
      white-space: nowrap;
    }

    .step-cost {
      text-align: right;
    }

    .flow-step.excess .step-cost strong,
    .flow-step.excess .step-state {
      color: var(--red);
    }

    .flow-step.funded .step-cost strong,
    .flow-step.funded .step-state,
    .flow-step.justified .step-state {
      color: var(--green);
    }

    .step-state {
      font-size: 15px;
      font-weight: 800;
      text-align: center;
    }

    .panel-total {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 11px;
    }

    .panel-total strong {
      color: #f8fafc;
      font-size: 14px;
    }

    .panel-total strong.negative { color: var(--red); }
    .panel-total strong.positive { color: var(--green); }

    .comparison-caption {
      margin: 12px 8px 2px;
      color: var(--muted);
      font-size: 11px;
      text-align: center;
    }

    .allocation-card {
      overflow: hidden;
    }

    .allocation-header {
      padding: 18px 18px 14px;
      border-bottom: 1px solid var(--line);
    }

    .allocation-header h3 {
      margin-bottom: 4px;
      font-size: 17px;
    }

    .allocation-header p {
      margin-bottom: 0;
      color: var(--muted);
      font-size: 11px;
    }

    .table-scroll {
      max-height: 610px;
      overflow: auto;
      scrollbar-width: thin;
      scrollbar-color: rgba(96, 165, 250, 0.35) transparent;
    }

    .allocation-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 11px;
    }

    .allocation-table th,
    .allocation-table td {
      padding: 11px 12px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.1);
      text-align: left;
      vertical-align: top;
    }

    .allocation-table th {
      position: sticky;
      top: 0;
      z-index: 2;
      color: #91a3bb;
      background: rgba(7, 13, 27, 0.97);
      font-size: 9px;
      font-weight: 720;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }

    .allocation-table td strong,
    .allocation-table td small {
      display: block;
    }

    .allocation-table td strong {
      color: #dfe7f3;
      font-size: 10px;
      font-weight: 620;
    }

    .allocation-table td small {
      max-width: 190px;
      margin-top: 3px;
      color: #71839b;
      font-size: 8px;
      line-height: 1.35;
    }

    .decision-pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 62px;
      padding: 4px 7px;
      border: 1px solid transparent;
      border-radius: 999px;
      font-size: 8px;
      font-weight: 820;
      letter-spacing: 0.06em;
    }

    .funded-pill {
      border-color: rgba(52, 211, 153, 0.25);
      color: #6ee7b7;
      background: rgba(5, 150, 105, 0.14);
    }

    .rejected-pill {
      border-color: rgba(251, 113, 133, 0.22);
      color: #fda4af;
      background: rgba(190, 24, 93, 0.12);
    }

    .method-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(380px, 0.95fr);
      gap: 14px;
      margin-top: 14px;
    }

    .proof-card,
    .defect-card {
      padding: 22px;
    }

    .proof-card {
      display: grid;
      grid-template-columns: 58px 1fr;
      gap: 18px;
      border-color: rgba(124, 58, 237, 0.34);
      background:
        linear-gradient(120deg, rgba(47, 109, 246, 0.07), rgba(124, 58, 237, 0.11)),
        var(--panel);
    }

    .proof-icon,
    .cta-icon {
      display: grid;
      place-items: center;
      border: 1px solid rgba(129, 140, 248, 0.34);
      border-radius: 18px;
      color: #b9a8ff;
      background: rgba(76, 29, 149, 0.16);
    }

    .proof-icon {
      width: 58px;
      height: 58px;
    }

    .proof-icon svg,
    .cta-icon svg {
      width: 30px;
      height: 30px;
    }

    .proof-card h3,
    .defect-card h3 {
      margin-bottom: 12px;
      font-size: 18px;
    }

    .proof-list {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px 24px;
      margin: 0;
      padding: 0;
      color: #b7c4d5;
      list-style: none;
      font-size: 12px;
    }

    .proof-list li {
      position: relative;
      padding-left: 14px;
    }

    .proof-list li::before {
      position: absolute;
      top: 0.6em;
      left: 0;
      width: 4px;
      height: 4px;
      border-radius: 999px;
      content: "";
      background: #8b5cf6;
    }

    .defect-card p {
      color: var(--muted);
      font-size: 12px;
    }

    .code-diff {
      overflow: hidden;
      margin: 14px 0;
      border: 1px solid rgba(148, 163, 184, 0.14);
      border-radius: 14px;
      background: rgba(2, 6, 23, 0.74);
      font-family: var(--mono);
      font-size: 11px;
    }

    .code-line {
      display: block;
      padding: 9px 12px;
    }

    .code-line.removed {
      color: #fecdd3;
      background: rgba(190, 24, 93, 0.1);
    }

    .code-line.added {
      color: #a7f3d0;
      background: rgba(5, 150, 105, 0.1);
    }

    .verifier {
      display: flex;
      align-items: center;
      gap: 8px;
      color: #a8b7ca;
      font-size: 11px;
    }

    .verifier code {
      overflow-wrap: anywhere;
      color: #dbeafe;
      font-family: var(--mono);
    }

    .cta-card {
      display: grid;
      grid-template-columns: 74px minmax(0, 1fr) auto;
      align-items: center;
      gap: 22px;
      margin-top: 14px;
      padding: 22px;
      border-color: rgba(124, 58, 237, 0.44);
      background:
        linear-gradient(100deg, rgba(47, 109, 246, 0.08), rgba(124, 58, 237, 0.13)),
        var(--panel);
    }

    .cta-icon {
      width: 74px;
      height: 74px;
    }

    .cta-copy h3 {
      margin-bottom: 5px;
      font-size: clamp(18px, 2vw, 25px);
      letter-spacing: -0.025em;
    }

    .cta-copy p {
      margin-bottom: 0;
      color: var(--muted);
      font-size: 13px;
    }

    .cta-actions {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 10px;
    }

    .reproduce-card {
      margin-top: 14px;
      padding: 18px 20px;
    }

    .reproduce-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 12px;
    }

    .reproduce-header h3 {
      margin-bottom: 0;
      font-size: 15px;
    }

    .copy-button {
      border: 0;
      border-radius: 9px;
      padding: 7px 10px;
      color: #bfdbfe;
      background: rgba(37, 99, 235, 0.14);
      cursor: pointer;
      font-size: 11px;
      font-weight: 700;
    }

    .command {
      display: block;
      overflow-x: auto;
      padding: 13px 14px;
      border: 1px solid rgba(148, 163, 184, 0.14);
      border-radius: 12px;
      color: #dbeafe;
      background: rgba(2, 6, 23, 0.72);
      font-family: var(--mono);
      font-size: 12px;
      white-space: nowrap;
    }

    .site-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding: 22px 2px 4px;
      color: #71839b;
      font-size: 11px;
    }

    .footer-links {
      display: flex;
      gap: 18px;
    }

    @media (max-width: 1180px) {
      .metric-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }

      .results-grid,
      .method-grid {
        grid-template-columns: 1fr;
      }

      .allocation-card {
        max-height: none;
      }

      .table-scroll {
        max-height: 520px;
      }
    }

    @media (max-width: 920px) {
      .browser-chrome {
        grid-template-columns: 80px minmax(180px, 1fr) 80px;
      }

      .brand-divider,
      .brand-tagline {
        display: none;
      }

      .site-header {
        align-items: flex-start;
        flex-direction: column;
        gap: 4px;
      }

      .nav {
        width: 100%;
        overflow-x: auto;
      }

      .hero {
        grid-template-columns: 1fr;
      }

      .hero-visual {
        min-height: auto;
      }

      .mascot-card {
        max-width: 560px;
        margin: 0 auto;
        transform: none;
      }

      .cta-card {
        grid-template-columns: 64px 1fr;
      }

      .cta-icon {
        width: 64px;
        height: 64px;
      }

      .cta-actions {
        grid-column: 1 / -1;
        justify-content: flex-start;
      }
    }

    @media (max-width: 720px) {
      .page-wrap {
        width: 100%;
        margin: 0;
      }

      .browser-shell {
        border-right: 0;
        border-left: 0;
        border-radius: 0;
      }

      .browser-chrome {
        display: none;
      }

      .site-header {
        padding: 12px 18px;
      }

      .content {
        padding-right: 16px;
        padding-left: 16px;
      }

      h1 {
        font-size: clamp(48px, 17vw, 72px);
      }

      .metric-grid {
        grid-template-columns: 1fr 1fr;
      }

      .metric-card:last-child {
        grid-column: 1 / -1;
      }

      .comparison-columns {
        grid-template-columns: 1fr;
      }

      .proof-card {
        grid-template-columns: 1fr;
      }

      .proof-list {
        grid-template-columns: 1fr;
      }

      .cta-card {
        grid-template-columns: 1fr;
      }

      .cta-actions,
      .cta-actions .button {
        width: 100%;
      }

      .site-footer {
        align-items: flex-start;
        flex-direction: column;
      }
    }

    @media (max-width: 480px) {
      .metric-grid {
        grid-template-columns: 1fr;
      }

      .metric-card:last-child {
        grid-column: auto;
      }

      .hero-actions,
      .hero-actions .button {
        width: 100%;
      }

      .flow-step {
        grid-template-columns: 26px minmax(0, 1fr) 20px;
      }

      .step-cost {
        display: none;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      html {
        scroll-behavior: auto;
      }

      *,
      *::before,
      *::after {
        scroll-behavior: auto !important;
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
      }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to content</a>
  <div class="page-wrap">
    <div class="browser-shell">
      <div class="browser-chrome" aria-hidden="true">
        <div class="traffic-lights"><span></span><span></span><span></span></div>
        <div class="address-bar">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <rect x="5" y="10" width="14" height="10" rx="2"></rect>
            <path d="M8 10V7a4 4 0 0 1 8 0v3"></path>
          </svg>
          marginal.compute
        </div>
        <div class="chrome-actions">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M12 3v12"></path><path d="m7 8 5-5 5 5"></path>
            <path d="M5 13v7h14v-7"></path>
          </svg>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M12 5v14M5 12h14"></path>
          </svg>
        </div>
      </div>

      <header class="site-header">
        <a class="brand" href="#overview" aria-label="MARGINAL home">
          <span class="brand-mark">M</span>
          <span class="brand-copy">
            <span class="wordmark">MARGINAL</span>
            <span class="brand-divider"></span>
            <span class="brand-tagline">Compute capital allocation for AI agents</span>
          </span>
        </a>
        <nav class="nav" aria-label="Killer Demo navigation">
          <a href="#overview">Overview</a>
          <a href="#method">Method</a>
          <a class="active" href="#results">Results</a>
          <a href="trace.jsonl">Trace</a>
          <a
            href="https://github.com/SignalLayerLabs/Marginal/blob/main/docs/public-benchmarks.md"
          >Benchmark</a>
        </nav>
      </header>

      <main id="main-content" class="content">
        <section id="overview" class="hero">
          <div>
            <div class="eyebrow">Deterministic evaluation</div>
            <h1>Killer Demo</h1>
            <p class="hero-copy">
              <strong>Fund only the next action worth taking.</strong>
              Same verified outcome. Far fewer tokens, lower cost, lower latency.
            </p>
            <div class="hero-actions">
              <a class="button button-primary" href="trace.jsonl">
                View full trace
                <span aria-hidden="true">→</span>
              </a>
              <a class="button button-secondary" href="#method">
                Read methodology
                <span aria-hidden="true">⌘</span>
              </a>
            </div>
            <div class="disclaimer-line">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <circle cx="12" cy="12" r="9"></circle>
                <path d="M12 8v5M12 16.5h.01"></path>
              </svg>
              <span>{{DISCLAIMER}}</span>
            </div>
          </div>

          <div class="hero-visual" aria-label="MARGINAL allocation visual">
            <div class="mascot-card">
              <img
                src="{{MASCOT_URL}}"
                alt="Dante, the SignalLayer Labs mascot, representing MARGINAL compute allocation"
              >
              <div class="verified-chip">
                <span class="verified-dot"></span>
                VERIFIED · PASS
              </div>
            </div>
          </div>
        </section>

        <section aria-label="Key performance indicators">
          <div class="metric-grid">
            <article class="metric-card">
              <div class="metric-label">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                  <circle cx="12" cy="12" r="8"></circle>
                  <path d="M8 12h8M12 8v8"></path>
                </svg>
                Token reduction
              </div>
              <strong class="metric-value">{{TOKEN_SAVINGS}}%</strong>
              <small class="metric-context">
                {{BASELINE_TOKENS}} → {{MARGINAL_TOKENS}} declared tokens
              </small>
              <svg
                class="sparkline"
                viewBox="0 0 180 28"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <path
                  d="M0 22 22 20 45 18 65 16 87 18 106 11 127 20 149 19 166 23 180 16"
                  fill="none"
                  stroke="#2997ff"
                  stroke-width="1.6"
                ></path>
              </svg>
            </article>

            <article class="metric-card">
              <div class="metric-label">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                  <path d="m13 2-8 12h6l-1 8 8-12h-6l1-8Z"></path>
                </svg>
                Actions executed
              </div>
              <strong class="metric-value">{{BASELINE_CALLS}} → {{MARGINAL_CALLS}}</strong>
              <svg
                class="sparkline"
                viewBox="0 0 180 28"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <path
                  d="M0 22 20 21 44 19 65 19 88 20 109 17 130 22 151 15 168 21 180 18"
                  fill="none"
                  stroke="#2997ff"
                  stroke-width="1.6"
                ></path>
              </svg>
            </article>

            <article class="metric-card">
              <div class="metric-label">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                  <path
                    d="M12 3v18M16 7.5c0-1.4-1.8-2.5-4-2.5S8 6.1 8 7.5s1.8 2.5 4 2.5
                      4 1.1 4 2.5S14.2 15 12 15s-4-1.1-4-2.5"
                  ></path>
                </svg>
                Estimated cost
              </div>
              <strong class="metric-value">${{BASELINE_USD}} → ${{MARGINAL_USD}}</strong>
              <svg
                class="sparkline"
                viewBox="0 0 180 28"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <path
                  d="M0 21 18 19 38 20 58 14 78 18 96 12 118 21 138 17 159 20 180 14"
                  fill="none"
                  stroke="#2997ff"
                  stroke-width="1.6"
                ></path>
              </svg>
            </article>

            <article class="metric-card">
              <div class="metric-label">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                  <circle cx="12" cy="12" r="9"></circle>
                  <path d="M12 7v5l3 2"></path>
                </svg>
                Estimated latency
              </div>
              <strong class="metric-value">{{BASELINE_LATENCY}}s → {{MARGINAL_LATENCY}}s</strong>
              <svg
                class="sparkline"
                viewBox="0 0 180 28"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <path
                  d="M0 23 20 20 40 17 60 19 80 13 100 18 120 15 140 21 160 17 180 19"
                  fill="none"
                  stroke="#2997ff"
                  stroke-width="1.6"
                ></path>
              </svg>
            </article>

            <article class="metric-card">
              <div class="metric-label">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                  <path d="M12 3 5 6v5c0 4.7 2.8 8 7 10 4.2-2 7-5.3 7-10V6l-7-3Z"></path>
                  <path d="m9 12 2 2 4-5"></path>
                </svg>
                Verified result
              </div>
              <strong class="metric-value success">PASS → PASS</strong>
              <svg
                class="sparkline"
                viewBox="0 0 180 28"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <path
                  d="M0 18 18 18 36 15 55 18 74 17 93 13 112 17 132 16 151 20 166 16 180 17"
                  fill="none"
                  stroke="#34d399"
                  stroke-width="1.6"
                ></path>
              </svg>
            </article>
          </div>
        </section>

        <section id="results" class="section">
          <div class="section-heading">
            <div>
              <h2>Same fix. Different capital discipline.</h2>
              <p>
                A like-for-like execution of diagnose, fix, and verification against the
                same deterministic defect.
              </p>
            </div>
          </div>

          <div class="results-grid">
            <article class="glass-card comparison-card">
              <div class="comparison-columns">
                <section class="flow-panel" aria-labelledby="baseline-title">
                  <div class="panel-heading">
                    <h3 id="baseline-title">Baseline</h3>
                    <span class="count-badge baseline">{{BASELINE_CALLS}} actions</span>
                  </div>
                  <ol class="flow-list">{{BASELINE_STEPS}}</ol>
                  <div class="panel-total">
                    <span>Total estimated cost</span>
                    <strong class="negative">${{BASELINE_USD}}</strong>
                  </div>
                </section>

                <section class="flow-panel marginal-panel" aria-labelledby="marginal-title">
                  <div class="panel-heading">
                    <h3 id="marginal-title">MARGINAL</h3>
                    <span class="count-badge marginal">{{MARGINAL_CALLS}} actions</span>
                  </div>
                  <ol class="flow-list">{{MARGINAL_STEPS}}</ol>
                  <div class="panel-total">
                    <span>Total estimated cost</span>
                    <strong class="positive">${{MARGINAL_USD}}</strong>
                  </div>
                </section>
              </div>
              <p class="comparison-caption">
                The baseline executes every available action. MARGINAL finances only the
                economically justified sequence.
              </p>
            </article>

            <article class="glass-card allocation-card">
              <div class="allocation-header">
                <h3>Allocation decisions</h3>
                <p>Every candidate is priced against expected marginal gain before execution.</p>
              </div>
              <div class="table-scroll">
                <table class="allocation-table">
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th>Cost</th>
                      <th>Expected gain</th>
                      <th>Decision</th>
                    </tr>
                  </thead>
                  <tbody>{{ALLOCATION_ROWS}}</tbody>
                </table>
              </div>
            </article>
          </div>
        </section>

        <section id="method" class="section">
          <div class="method-grid">
            <article class="glass-card proof-card">
              <div class="proof-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                  <path d="M12 3 5 6v5c0 4.7 2.8 8 7 10 4.2-2 7-5.3 7-10V6l-7-3Z"></path>
                  <path d="m9 12 2 2 4-5"></path>
                </svg>
              </div>
              <div>
                <h3>What this demo proves</h3>
                <ul class="proof-list">
                  <li>The task starts in FAIL.</li>
                  <li>Both workflows finish in PASS.</li>
                  <li>Costs are declared action budgets used by the allocator.</li>
                  <li>This is a deterministic demonstration of economic action selection.</li>
                </ul>
              </div>
            </article>

            <article class="glass-card defect-card">
              <h3>The deterministic defect</h3>
              <p>{{SCENARIO}}</p>
              <div class="code-diff" aria-label="Patch applied by the funded action">
                <span class="code-line removed">− {{DEFECT_BEFORE}}</span>
                <span class="code-line added">+ {{DEFECT_AFTER}}</span>
              </div>
              <div class="verifier">
                <span>Verifier</span>
                <code>{{VERIFIER}}</code>
              </div>
            </article>
          </div>
        </section>

        <section class="glass-card cta-card" aria-labelledby="cta-title">
          <div class="cta-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
              <path d="m8 9-4 3 4 3M16 9l4 3-4 3M14 5l-4 14"></path>
            </svg>
          </div>
          <div class="cta-copy">
            <h3 id="cta-title">Build agents that spend compute deliberately.</h3>
            <p>
              Explore the open-source project and run the same deterministic evaluation
              locally.
            </p>
          </div>
          <div class="cta-actions">
            <a
              class="button button-primary"
              href="https://github.com/SignalLayerLabs/Marginal"
            >Open repository</a>
            <a class="button button-secondary" href="#reproduce">Run the demo locally</a>
          </div>
        </section>

        <section id="reproduce" class="glass-card reproduce-card">
          <div class="reproduce-header">
            <h3>Reproduce the result</h3>
            <button
              class="copy-button"
              type="button"
              data-copy="marginal killer-demo --output killer-demo-output"
            >Copy command</button>
          </div>
          <code class="command">marginal killer-demo --output killer-demo-output</code>
        </section>

        <footer class="site-footer">
          <span>© 2026 SignalLayer Labs</span>
          <span class="footer-links">
            <a href="https://github.com/SignalLayerLabs/Marginal/blob/main/LICENSE">Apache-2.0</a>
            <a href="result.json">Structured result</a>
            <a href="trace.jsonl">Decision trace</a>
          </span>
        </footer>
      </main>
    </div>
  </div>

  <script>
    const copyButton = document.querySelector("[data-copy]");
    if (copyButton) {
      copyButton.addEventListener("click", async () => {
        const command = copyButton.getAttribute("data-copy") || "";
        try {
          await navigator.clipboard.writeText(command);
          const original = copyButton.textContent;
          copyButton.textContent = "Copied";
          window.setTimeout(() => { copyButton.textContent = original; }, 1400);
        } catch (_error) {
          window.prompt("Copy command", command);
        }
      });
    }
  </script>
</body>
</html>
"""
    replacements = {
        "{{MASCOT_URL}}": (
            "https://raw.githubusercontent.com/SignalLayerLabs/Marginal/main/assets/"
            "marginal-project-mark.png"
        ),
        "{{DISCLAIMER}}": html.escape(result["disclaimer"]),
        "{{TOKEN_SAVINGS}}": f"{savings['tokens_percent']:.2f}",
        "{{BASELINE_TOKENS}}": f"{baseline['tokens']:,}",
        "{{MARGINAL_TOKENS}}": f"{marginal['tokens']:,}",
        "{{BASELINE_CALLS}}": str(baseline["calls"]),
        "{{MARGINAL_CALLS}}": str(marginal["calls"]),
        "{{BASELINE_USD}}": f"{baseline['usd']:.3f}",
        "{{MARGINAL_USD}}": f"{marginal['usd']:.3f}",
        "{{BASELINE_LATENCY}}": f"{baseline['latency_ms'] / 1000:.2f}",
        "{{MARGINAL_LATENCY}}": f"{marginal['latency_ms'] / 1000:.2f}",
        "{{BASELINE_STEPS}}": baseline_steps,
        "{{MARGINAL_STEPS}}": marginal_steps,
        "{{ALLOCATION_ROWS}}": allocation_rows,
        "{{SCENARIO}}": html.escape(result["scenario"]),
        "{{DEFECT_BEFORE}}": html.escape(result["defect"]["before"]),
        "{{DEFECT_AFTER}}": html.escape(result["defect"]["after"]),
        "{{VERIFIER}}": html.escape(result["defect"]["verifier"]),
    }
    for placeholder, value in replacements.items():
        page = page.replace(placeholder, value)
    return page


def _write_artifacts(
    output_dir: Path,
    result: dict[str, Any],
    events: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "RESULTS.md").write_text(
        render_killer_demo_markdown(result),
        encoding="utf-8",
    )
    (output_dir / "index.html").write_text(
        render_killer_demo_html(result),
        encoding="utf-8",
    )
    (output_dir / "comparison.svg").write_text(
        render_killer_demo_svg(result),
        encoding="utf-8",
    )
    (output_dir / "trace.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
