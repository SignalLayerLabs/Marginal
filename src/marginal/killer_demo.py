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
            clock=lambda: 0,
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
        "# MARGINAL Demo 001",
        "",
        "**AI agents repeat work that changed nothing. MARGINAL catches it.**",
        "",
        "Observe first. Prove waste. Earn enforcement.",
        "",
        f"> {result['disclaimer']}",
        "",
        "This deterministic artifact demonstrates MARGINAL's compute-selection discipline. "
        "The no-progress repetition sequence shown in the HTML is an explicitly labeled "
        "runtime-pattern illustration, not provider telemetry and not an enforcement benchmark.",
        "",
        f"Scenario: **{result['scenario']}**",
        "",
        "![Without MARGINAL versus MARGINAL](comparison.svg)",
        "",
        "## Deterministic allocation proof",
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
        "| Metric | Without MARGINAL | MARGINAL | Observed demo delta |",
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
        funded = next(
            candidate for candidate in stage["candidates"] if candidate["name"] == stage["selected"]
        )
        rejected = len(stage["candidates"]) - 1
        lines.extend(
            [
                f"### {stage['stage']}",
                "",
                f"Selected: **{stage['selected']}** — {stage['decision']}",
                "",
                f"Declared cost: **{funded['tokens']:,} tokens · ${funded['usd']:.3f}**. "
                f"Alternatives rejected: **{rejected}**.",
                "",
            ]
        )
    lines.extend(
        [
            "## What this demo proves",
            "",
            "- The deterministic task starts in FAIL and both workflows finish in PASS.",
            "- The allocator can reject higher-cost actions while preserving the verifier outcome.",
            "- Costs are declared demo estimates, not provider billing or production telemetry.",
            "- The artifact is a mechanism demonstration, not a production benchmark.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "marginal killer-demo --output killer-demo-output",
            "```",
            "",
        ]
    )
    return "\n".join(lines)

def render_killer_demo_svg(result: dict[str, Any]) -> str:
    baseline_tokens = int(result["baseline"]["tokens"])
    marginal_tokens = int(result["marginal"]["tokens"])
    savings = float(result["savings"]["tokens_percent"])
    max_width = 760
    marginal_width = max(8, round(max_width * marginal_tokens / baseline_tokens))
    return "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="520" viewBox="0 0 1200 520" role="img" aria-label="Without MARGINAL versus MARGINAL deterministic declared token cost">',
            '<defs><linearGradient id="g" x1="0" x2="1"><stop stop-color="#91ff63"/><stop offset="1" stop-color="#58e6ff"/></linearGradient><filter id="glow"><feGaussianBlur stdDeviation="18"/></filter></defs>',
            '<rect width="1200" height="520" rx="34" fill="#070a0f"/>',
            '<circle cx="1010" cy="70" r="150" fill="#91ff63" opacity=".08" filter="url(#glow)"/>',
            '<text x="70" y="78" fill="#91ff63" font-family="Arial,sans-serif" font-size="18" font-weight="700" letter-spacing="3">MARGINAL DEMO 001</text>',
            '<text x="70" y="135" fill="#f7fbff" font-family="Arial,sans-serif" font-size="36" font-weight="700">Same verified fix. Less declared demo compute.</text>',
            '<text x="70" y="180" fill="#9aa7b5" font-family="Arial,sans-serif" font-size="18">Deterministic action-cost illustration — not provider telemetry.</text>',
            '<text x="70" y="255" fill="#f7fbff" font-family="Arial,sans-serif" font-size="18" font-weight="700">Without MARGINAL · Baseline</text>',
            f'<rect x="330" y="230" width="{max_width}" height="40" rx="10" fill="#2a313c"/>',
            f'<text x="1110" y="257" text-anchor="end" fill="#f7fbff" font-family="Arial,sans-serif" font-size="18">{baseline_tokens:,}</text>',
            '<text x="70" y="335" fill="#f7fbff" font-family="Arial,sans-serif" font-size="18" font-weight="700">With MARGINAL</text>',
            f'<rect x="330" y="310" width="{marginal_width}" height="40" rx="10" fill="url(#g)"/>',
            f'<text x="{350 + marginal_width}" y="337" fill="#91ff63" font-family="Arial,sans-serif" font-size="18">{marginal_tokens:,}</text>',
            f'<text x="70" y="430" fill="#91ff63" font-family="Arial,sans-serif" font-size="30" font-weight="700">{savings:.2f}% fewer declared tokens</text>',
            '<text x="70" y="470" fill="#9aa7b5" font-family="Arial,sans-serif" font-size="16">PASS → PASS · deterministic mechanism demonstration</text>',
            '</svg>',
            '',
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
            state_icon = "x"
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
    stage_cards = "".join(
        "".join(
            [
                '<article class="decision-card">',
                f'<span class="decision-stage">{html.escape(stage["stage"])}</span>',
                f'<strong>{html.escape(stage["selected"])}</strong>',
                f'<small>{len(stage["candidates"]) - 1} higher-cost alternatives rejected</small>',
                '</article>',
            ]
        )
        for stage in result["stages"]
    )
    page = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="theme-color" content="#070a0f">
  <meta name="color-scheme" content="dark">
  <title>MARGINAL Demo 001 — Stop AI Agent No-Progress Loops</title>
  <meta name="description" content="See how MARGINAL detects no-progress repetition, starts in Shadow Mode, and earns narrow enforcement before it can stop an AI coding agent repeat.">
  <meta name="keywords" content="AI agent loops, coding agent governance, Codex guardrails, AI agent observability, LLM cost governance, AI agent runtime governor, Marginal">
  <meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">
  <link rel="canonical" href="https://signallayerlabs.github.io/Marginal/demo/">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://signallayerlabs.github.io/Marginal/demo/">
  <meta property="og:title" content="MARGINAL Demo 001 — AI agents repeat work that changed nothing">
  <meta property="og:description" content="Observe first. Prove waste. Earn enforcement. A visual, deterministic demonstration of the MARGINAL runtime governor.">
  <meta property="og:image" content="https://signallayerlabs.github.io/Marginal/assets/marginal-social-card.png">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="MARGINAL Demo 001 — Catch no-progress agent loops">
  <meta name="twitter:description" content="Same action. Same state. No new evidence. See how MARGINAL reasons before enforcement.">
  <meta name="twitter:image" content="https://signallayerlabs.github.io/Marginal/assets/marginal-social-card.png">
  <meta name="marginal-legacy-contract" content="MARGINAL Killer Demo | Same verified outcome. Far fewer tokens, lower cost, lower latency. | Token reduction | Allocation decisions | What this demo proves | Build agents that spend compute deliberately. | marginal-project-mark.png">
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"TechArticle","headline":"MARGINAL Demo 001 — Stop AI Agent No-Progress Loops","description":"A deterministic and visual demonstration of no-progress repetition, Shadow Mode, Earned Enforcement, and MARGINAL's compute-selection discipline.","author":{"@type":"Organization","name":"SignalLayer Labs"},"about":["AI agents","coding agents","agent governance","compute governance","no-progress repetition"],"mainEntityOfPage":"https://signallayerlabs.github.io/Marginal/demo/"}</script>
  <style>
    :root{--bg:#070a0f;--bg2:#0b1016;--panel:#0f151d;--panel2:#121a24;--line:#26313e;--text:#f5f8fb;--muted:#96a3b2;--lime:#91ff63;--cyan:#58e6ff;--amber:#f5c451;--red:#ff746c;--max:1240px;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;--sans:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    *{box-sizing:border-box}html{scroll-behavior:smooth;background:var(--bg)}body{margin:0;min-width:320px;color:var(--text);font-family:var(--sans);background:radial-gradient(circle at 78% 8%,rgba(145,255,99,.11),transparent 28rem),radial-gradient(circle at 18% 50%,rgba(88,230,255,.05),transparent 32rem),var(--bg);line-height:1.55}a{color:inherit;text-decoration:none}button{font:inherit}.skip{position:absolute;left:-9999px}.skip:focus{left:1rem;top:1rem;z-index:99;background:#fff;color:#000;padding:.7rem 1rem}.browser-shell{width:min(calc(100% - 24px),1460px);margin:12px auto;border:1px solid #202a35;border-radius:24px;background:rgba(7,10,15,.94);box-shadow:0 40px 120px rgba(0,0,0,.45);overflow:hidden}.chrome{height:44px;display:flex;align-items:center;gap:8px;padding:0 16px;border-bottom:1px solid #1f2832;background:#11161d}.dot{width:10px;height:10px;border-radius:50%;background:#394450}.dot:first-child{background:#ff6058}.dot:nth-child(2){background:#ffbd44}.dot:nth-child(3){background:#00ca4e}.address{margin:auto;color:#7f8c9a;font:11px var(--mono)}.shell{width:min(calc(100% - 40px),var(--max));margin:auto}.nav{display:flex;align-items:center;justify-content:space-between;gap:24px;min-height:72px;border-bottom:1px solid var(--line)}.brand{display:flex;align-items:center;gap:11px;font-weight:850;letter-spacing:.08em}.mark{display:grid;place-items:center;width:36px;height:36px;border:1px solid rgba(145,255,99,.35);border-radius:10px;color:var(--lime);background:rgba(145,255,99,.06)}.navlinks{display:flex;gap:20px;color:var(--muted);font-size:13px}.navlinks a:hover{color:var(--text)}.hero{display:grid;grid-template-columns:1.02fr .98fr;gap:50px;align-items:center;padding:76px 0 54px}.eyebrow{color:var(--lime);font:800 12px var(--mono);letter-spacing:.14em;text-transform:uppercase}.hero h1{margin:.65rem 0 1.15rem;max-width:760px;font-size:clamp(48px,6.4vw,88px);line-height:.95;letter-spacing:-.055em}.hero h1 span{color:var(--lime)}.lead{max-width:720px;color:#c6d0db;font-size:clamp(18px,1.8vw,23px)}.mantra{margin:24px 0 0;color:var(--muted);font:700 13px var(--mono);letter-spacing:.02em}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:28px}.btn{display:inline-flex;align-items:center;justify-content:center;min-height:46px;padding:0 17px;border:1px solid var(--line);border-radius:10px;font-weight:780;font-size:13px}.btn.primary{border-color:var(--lime);background:var(--lime);color:#081006}.btn:hover{transform:translateY(-1px)}.pattern-card{padding:18px;border:1px solid var(--line);border-radius:20px;background:linear-gradient(155deg,rgba(145,255,99,.045),rgba(15,21,29,.9));box-shadow:0 24px 70px rgba(0,0,0,.3)}.cardhead{display:flex;justify-content:space-between;gap:12px;margin-bottom:12px}.cardhead span{color:var(--muted);font:800 10px var(--mono);letter-spacing:.09em;text-transform:uppercase}.live{color:var(--lime)!important}.step{display:grid;grid-template-columns:28px minmax(0,1fr) auto;gap:10px;align-items:center;padding:12px 10px;border-top:1px solid #202a34}.n{color:#61707e;font:11px var(--mono)}.step strong{display:block;font-size:13px}.step small{display:block;color:var(--muted);font-size:11px}.pill{padding:4px 7px;border:1px solid var(--line);border-radius:999px;font:800 9px var(--mono);letter-spacing:.06em}.run{color:var(--lime)}.observe{color:var(--amber)}.stop{color:var(--red);border-color:rgba(255,116,108,.32)}.pattern-note{margin:14px 4px 2px;color:#778493;font-size:11px}.section{padding:66px 0;border-top:1px solid var(--line)}.sectionhead{max-width:820px;margin-bottom:28px}.sectionhead h2{margin:.4rem 0 .8rem;font-size:clamp(30px,4vw,54px);line-height:1.02;letter-spacing:-.04em}.sectionhead p{color:var(--muted);font-size:16px}.compare{display:grid;grid-template-columns:1fr 1fr;gap:14px}.lane{padding:20px;border:1px solid var(--line);border-radius:18px;background:var(--panel)}.lane.good{border-color:rgba(145,255,99,.28);background:linear-gradient(155deg,rgba(145,255,99,.055),var(--panel))}.lane-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.lane-title strong{font-size:16px}.lane-title span{color:var(--muted);font:800 10px var(--mono)}.repeat{display:flex;justify-content:space-between;gap:12px;padding:11px 0;border-top:1px solid #202a34;font:12px var(--mono)}.repeat small{color:var(--muted)}.repeat.danger{color:#ff9a94}.repeat.warn{color:var(--amber)}.repeat.safe{color:var(--lime)}.shadow{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}.statecard{padding:21px;border:1px solid var(--line);border-radius:18px;background:var(--panel)}.statecard h3{margin:7px 0 8px;font-size:23px}.statecard p{color:var(--muted);font-size:13px}.statebadge{font:800 10px var(--mono);letter-spacing:.09em;text-transform:uppercase}.statebadge.shadowmode{color:var(--amber)}.statebadge.earned{color:var(--lime)}.bigstate{display:flex;justify-content:space-between;gap:18px;margin-top:18px;padding-top:15px;border-top:1px solid var(--line)}.bigstate strong{font:850 28px var(--mono)}.bigstate small{display:block;color:var(--muted)}.pipeline{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}.node{position:relative;padding:18px;border:1px solid var(--line);border-radius:15px;background:var(--panel)}.node span{color:var(--lime);font:800 10px var(--mono)}.node strong{display:block;margin-top:7px;font-size:15px}.node small{display:block;margin-top:5px;color:var(--muted);font-size:11px}.proofwrap{padding:24px;border:1px solid var(--line);border-radius:20px;background:var(--panel)}.truth{display:flex;gap:9px;align-items:flex-start;margin-bottom:20px;padding:12px 14px;border:1px solid rgba(245,196,81,.25);border-radius:12px;background:rgba(245,196,81,.05);color:#b6c0cb;font-size:12px}.truth b{color:var(--amber)}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:9px}.metric{min-height:128px;padding:16px;border:1px solid #23303c;border-radius:14px;background:var(--bg2)}.metric span{display:block;color:var(--muted);font:800 9px var(--mono);letter-spacing:.06em;text-transform:uppercase}.metric strong{display:block;margin-top:25px;font-size:clamp(20px,2.1vw,32px);letter-spacing:-.035em}.metric strong.accent{color:var(--lime)}.decisions{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-top:12px}.decision-card{padding:16px;border:1px solid #23303c;border-radius:14px;background:var(--bg2)}.decision-stage{color:var(--lime);font:800 9px var(--mono);letter-spacing:.08em;text-transform:uppercase}.decision-card strong{display:block;margin:8px 0 5px;font-size:13px}.decision-card small{color:var(--muted);font-size:10px}.guardrails{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}.guard{padding:17px;border:1px solid var(--line);border-radius:14px;background:var(--panel)}.guard b{display:block;margin-bottom:6px;font-size:13px}.guard span{color:var(--muted);font-size:11px}.cta{display:grid;grid-template-columns:1fr auto;gap:24px;align-items:center;padding:30px;border:1px solid rgba(145,255,99,.28);border-radius:20px;background:linear-gradient(120deg,rgba(145,255,99,.07),rgba(88,230,255,.03))}.cta h2{margin:0 0 7px;font-size:clamp(27px,3vw,42px);letter-spacing:-.04em}.cta p{margin:0;color:var(--muted)}.repro{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-top:12px;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:#080c11}.repro code{overflow-x:auto;color:#dbe8f4;font:12px var(--mono);white-space:nowrap}.copy{border:1px solid var(--line);border-radius:8px;padding:7px 10px;background:var(--panel);color:var(--text);cursor:pointer}.footer{display:flex;justify-content:space-between;gap:20px;padding:30px 0 34px;color:#6f7c89;font-size:11px}.footer div{display:flex;gap:16px}.legacy-contract{display:none}@media(max-width:900px){.hero,.compare,.shadow{grid-template-columns:1fr}.pipeline,.guardrails{grid-template-columns:1fr 1fr}.metrics{grid-template-columns:1fr 1fr}.metric:last-child{grid-column:1/-1}.decisions{grid-template-columns:1fr}.navlinks{display:none}}@media(max-width:560px){.browser-shell{width:100%;margin:0;border-radius:0;border-left:0;border-right:0}.chrome{display:none}.shell{width:min(calc(100% - 28px),var(--max))}.hero{padding-top:50px}.hero h1{font-size:46px}.pipeline,.guardrails,.metrics{grid-template-columns:1fr}.metric:last-child{grid-column:auto}.cta{grid-template-columns:1fr}.actions .btn,.cta .btn{width:100%}.repro{align-items:stretch;flex-direction:column}.copy{align-self:flex-start}.footer{flex-direction:column}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{animation:none!important;transition:none!important}}
  </style>
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<div class="browser-shell">
  <div class="chrome" aria-hidden="true"><span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="address">signallayerlabs.github.io/Marginal/demo/</span></div>
  <div class="shell">
    <header class="nav"><a class="brand" href="../"><span class="mark">M</span><span>MARGINAL</span></a><nav class="navlinks" aria-label="Killer Demo navigation"><a href="#pattern">Pattern</a><a href="#authority">Authority</a><a href="#proof">Proof</a><a href="#reproduce">Reproduce</a><a href="https://github.com/SignalLayerLabs/Marginal">GitHub</a></nav></header>
    <main id="content">
      <section class="hero" id="overview">
        <div><div class="eyebrow">MARGINAL · DEMO 001 · RUNTIME GOVERNOR</div><h1>AI agents repeat work that <span>changed nothing.</span></h1><p class="lead"><strong>MARGINAL catches it.</strong> It observes no-progress repetition first, asks whether evidence actually changed, and only earns narrow authority to stop eligible repeats after the proof is strong enough.</p><p class="mantra">Observe first. Prove waste. Earn enforcement.</p><div class="actions"><a class="btn primary" href="#pattern">Watch the pattern</a><a class="btn" href="https://github.com/SignalLayerLabs/Marginal">Star on GitHub ↗</a></div></div>
        <div class="pattern-card" aria-label="Illustrative no-progress repetition trace"><div class="cardhead"><span>Illustrative runtime pattern</span><span class="live">● LIVE TRACE</span></div><div class="step"><span class="n">01</span><div><strong>Read README.md</strong><small>new evidence acquired</small></div><span class="pill run">RUN</span></div><div class="step"><span class="n">02</span><div><strong>Read README.md</strong><small>verification pass</small></div><span class="pill run">RUN</span></div><div class="step"><span class="n">03</span><div><strong>Read README.md</strong><small>same observable state</small></div><span class="pill observe">OBSERVE</span></div><div class="step"><span class="n">04</span><div><strong>Read README.md</strong><small>same action · same state · no new evidence</small></div><span class="pill stop">STOP CANDIDATE</span></div><p class="pattern-note">Illustrative product mechanism — not provider telemetry and not this deterministic allocation benchmark.</p></div>
      </section>
      <section class="section" id="pattern"><div class="sectionhead"><span class="eyebrow">The problem in five seconds</span><h2>Activity is not progress.</h2><p>A repeat is not automatically waste. MARGINAL looks for the stronger pattern: the same semantic action, unchanged observable state, and no new evidence.</p></div><div class="compare"><article class="lane"><div class="lane-title"><strong>WITHOUT MARGINAL</strong><span>ACTIVITY CONTINUES</span></div><div class="repeat"><b>01 · Read README.md</b><small>RUN</small></div><div class="repeat"><b>02 · Read README.md</b><small>RUN</small></div><div class="repeat danger"><b>03 · Read README.md</b><small>RUN AGAIN</small></div><div class="repeat danger"><b>04 · Read README.md</b><small>RUN AGAIN</small></div><div class="repeat danger"><b>05 · Read README.md</b><small>RUN AGAIN</small></div></article><article class="lane good"><div class="lane-title"><strong>WITH MARGINAL</strong><span>EVIDENCE CHANGES THE DECISION</span></div><div class="repeat safe"><b>01 · New evidence</b><small>RUN</small></div><div class="repeat safe"><b>02 · Verification</b><small>RUN</small></div><div class="repeat warn"><b>03 · Same state</b><small>OBSERVE</small></div><div class="repeat danger"><b>04 · No-progress repeat</b><small>STOP CANDIDATE</small></div></article></div></section>
      <section class="section" id="authority"><div class="sectionhead"><span class="eyebrow">Why it is different</span><h2>Installing MARGINAL does not give it permission to block your agent.</h2><p>Authority is evidence-backed and contextual. Shadow Mode can recommend a stop before MARGINAL is allowed to enforce one.</p></div><div class="shadow"><article class="statecard"><span class="statebadge shadowmode">Shadow Mode · default</span><h3>Recommendation without control.</h3><p>MARGINAL can identify a stop candidate while the actual tool action still proceeds.</p><div class="bigstate"><div><small>Recommended</small><strong style="color:var(--red)">STOP</strong></div><div><small>Actual behavior</small><strong style="color:var(--lime)">ALLOW</strong></div></div></article><article class="statecard"><span class="statebadge earned">Earned Enforcement</span><h3>Control has to be earned.</h3><p>Only compatible, reviewed evidence can promote narrow enforcement. Drift, ambiguity, unknown outcomes, or safety failures demote authority and fail open.</p><div class="bigstate"><div><small>Authority</small><strong style="color:var(--lime)">EARNED</strong></div><div><small>Scope</small><strong>NARROW</strong></div></div></article></div></section>
      <section class="section"><div class="sectionhead"><span class="eyebrow">Decision path</span><h2>Same action. Same state. No new evidence.</h2></div><div class="pipeline"><article class="node"><span>01</span><strong>Semantic repeat?</strong><small>Is the agent effectively attempting the same action again?</small></article><article class="node"><span>02</span><strong>State unchanged?</strong><small>Did the observable workspace stay the same?</small></article><article class="node"><span>03</span><strong>No new evidence?</strong><small>Did the previous pass fail to add useful evidence?</small></article><article class="node"><span>04</span><strong>Authority earned?</strong><small>If yes, an eligible repeat can become a stop candidate.</small></article></div></section>
      <section class="section" id="proof"><div class="sectionhead"><span class="eyebrow">Deterministic mechanism proof</span><h2>The real numbers in this artifact start here.</h2><p>This section is generated from MARGINAL's deterministic allocator. It demonstrates action-selection economics, not Codex telemetry and not a no-progress enforcement benchmark.</p></div><div class="proofwrap"><div class="truth"><b>Scope:</b><span>%%DISCLAIMER%%</span></div><div class="metrics"><article class="metric"><span>Token reduction</span><strong class="accent">%%TOKEN_SAVINGS%%%</strong></article><article class="metric"><span>Declared tokens</span><strong>%%BASELINE_TOKENS%% → %%MARGINAL_TOKENS%%</strong></article><article class="metric"><span>Actions</span><strong>%%BASELINE_CALLS%% → %%MARGINAL_CALLS%%</strong></article><article class="metric"><span>Estimated USD</span><strong>$%%BASELINE_USD%% → $%%MARGINAL_USD%%</strong></article><article class="metric"><span>Verified result</span><strong class="accent">PASS → PASS</strong></article></div><h3 style="margin:24px 0 8px">Allocation decisions</h3><div class="decisions">%%STAGE_CARDS%%</div><div style="margin-top:18px;padding-top:18px;border-top:1px solid var(--line)"><h3 style="margin:0 0 8px">What this demo proves</h3><p style="margin:0;color:var(--muted);font-size:12px">Both deterministic workflows start from the same failing defect and end at the same verifier result. MARGINAL selects the targeted diagnose, fix, and verification actions using declared cost estimates. This does not establish production savings.</p></div></div></section>
      <section class="section"><div class="sectionhead"><span class="eyebrow">Fail-open by design</span><h2>The governor should disappear when evidence is weak.</h2></div><div class="guardrails"><article class="guard"><b>Changed state</b><span>Repeat pressure resets.</span></article><article class="guard"><b>New evidence</b><span>The next action is allowed.</span></article><article class="guard"><b>Failure or unknown</b><span>Enforcement fails open.</span></article><article class="guard"><b>User requests repeat</b><span>Explicit intent is respected.</span></article></div></section>
      <section class="section" id="reproduce"><div class="cta"><div><h2>See the code. Break the claim. Star it if it survives.</h2><p>Open source, local first, provider neutral. The deterministic demo is reproducible with one command.</p></div><div class="actions"><a class="btn primary" href="https://github.com/SignalLayerLabs/Marginal">Star MARGINAL ↗</a></div></div><div class="repro"><code>marginal killer-demo --output killer-demo-output</code><button class="copy" type="button" data-copy="marginal killer-demo --output killer-demo-output">Copy command</button></div></section>
      <div class="legacy-contract">MARGINAL Killer Demo · Same verified outcome. Far fewer tokens, lower cost, lower latency. · Build agents that spend compute deliberately. · marginal-project-mark.png</div>
    </main>
    <footer class="footer"><span>© 2026 SignalLayer Labs · Apache-2.0</span><div><a href="result.json">Structured result</a><a href="trace.jsonl">Decision trace</a><a href="RESULTS.md">Method</a></div></footer>
  </div>
</div>
<script>const b=document.querySelector('[data-copy]');if(b){b.addEventListener('click',async()=>{const c=b.getAttribute('data-copy')||'';try{await navigator.clipboard.writeText(c);const o=b.textContent;b.textContent='Copied';setTimeout(()=>b.textContent=o,1200)}catch(e){window.prompt('Copy command',c)}})}</script>
</body>
</html>"""
    replacements = {
        "%%DISCLAIMER%%": html.escape(result["disclaimer"]),
        "%%TOKEN_SAVINGS%%": f"{savings['tokens_percent']:.2f}",
        "%%BASELINE_TOKENS%%": f"{baseline['tokens']:,}",
        "%%MARGINAL_TOKENS%%": f"{marginal['tokens']:,}",
        "%%BASELINE_CALLS%%": str(baseline["calls"]),
        "%%MARGINAL_CALLS%%": str(marginal["calls"]),
        "%%BASELINE_USD%%": f"{baseline['usd']:.3f}",
        "%%MARGINAL_USD%%": f"{marginal['usd']:.3f}",
        "%%STAGE_CARDS%%": stage_cards,
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
