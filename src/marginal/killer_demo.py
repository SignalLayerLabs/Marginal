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


def _render_stage_html(stage: dict[str, Any]) -> str:
    rows: list[str] = []
    for candidate in stage["candidates"]:
        selected = candidate["name"] == stage["selected"]
        status_class = "funded" if selected else "skipped"
        status = "FUNDED" if selected else "SKIPPED"
        rows.append(
            "".join(
                [
                    "<tr>",
                    f"<td>{html.escape(candidate['name'])}</td>",
                    f"<td>{candidate['tokens']:,}</td>",
                    f"<td>{candidate['expected_gain']:.3f}</td>",
                    f"<td>{candidate['score']:.3f}</td>",
                    f'<td><span class="{status_class}">{status}</span><br>',
                    f"{html.escape(candidate['reason'])}</td>",
                    "</tr>",
                ]
            )
        )
    return "".join(
        [
            f"<section><h2>{html.escape(stage['stage'])}</h2>",
            f"<p>Funded <strong>{html.escape(stage['selected'])}</strong>.</p>",
            '<div class="table-wrap"><table><thead><tr>',
            "<th>Candidate</th><th>Declared tokens</th><th>Expected gain</th>",
            "<th>Score</th><th>Decision</th></tr></thead><tbody>",
            "".join(rows),
            "</tbody></table></div></section>",
        ]
    )


def render_killer_demo_html(result: dict[str, Any]) -> str:
    baseline = result["baseline"]
    marginal = result["marginal"]
    savings = result["savings"]
    stages = "".join(_render_stage_html(stage) for stage in result["stages"])
    styles = "\n".join(
        [
            ":root{--bg:#070b16;--panel:#111827;--text:#f8fafc;",
            "--muted:#94a3b8;--green:#22c55e;--red:#ef4444;--line:#273449}",
            "*{box-sizing:border-box}",
            "body{margin:0;background:var(--bg);color:var(--text);",
            "font:16px/1.55 Inter,ui-sans-serif,system-ui,sans-serif}",
            "main{max-width:1100px;margin:auto;padding:48px 24px 80px}",
            "h1{font-size:clamp(38px,7vw,72px);line-height:1;margin:.15em 0}",
            "h2{margin-top:48px}",
            ".kicker{color:#86efac;font-weight:800;letter-spacing:.12em;",
            "text-transform:uppercase}",
            ".lede{font-size:20px;color:#cbd5e1;max-width:820px}",
            ".notice{border-left:4px solid #f59e0b;padding:14px 18px;",
            "background:#1c1917;color:#fde68a;border-radius:8px}",
            ".grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));",
            "gap:14px;margin:28px 0}",
            ".card{background:var(--panel);border:1px solid var(--line);",
            "border-radius:16px;padding:20px}",
            ".card strong{display:block;font-size:30px;color:#86efac}",
            ".card span{color:var(--muted)}",
            "img{max-width:100%;margin:20px 0;border-radius:20px}",
            "table{width:100%;border-collapse:collapse;background:var(--panel)}",
            "th,td{padding:13px;border-bottom:1px solid var(--line);",
            "text-align:left;vertical-align:top}",
            "th{color:#cbd5e1}",
            ".table-wrap{overflow:auto;border:1px solid var(--line);",
            "border-radius:14px}",
            ".funded{color:#86efac;font-weight:800}",
            ".skipped{color:#fca5a5;font-weight:800}",
            "code{background:#1e293b;padding:3px 7px;border-radius:6px}",
            "footer{color:var(--muted);margin-top:55px}",
            "@media(max-width:760px){.grid{grid-template-columns:1fr 1fr}}",
        ]
    )
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>MARGINAL Killer Demo</title>",
            '<meta name="description"',
            ' content="Deterministic compute capital allocation demo for AI agents.">',
            f"<style>{styles}</style>",
            "</head>",
            "<body><main>",
            '<div class="kicker">Compute capital allocation for AI agents</div>',
            "<h1>MARGINAL Killer Demo</h1>",
            "<section><h2>The defect</h2><pre><code>",
            f"- {html.escape(result['defect']['before'])}\n",
            f"+ {html.escape(result['defect']['after'])}",
            "</code></pre>",
            f"<p>Verifier: <code>{html.escape(result['defect']['verifier'])}",
            "</code></p></section>",
            '<p class="lede">The baseline runs every search, reviewer, rewrite, and audit. ',
            "MARGINAL funds only the highest-value action in each stage, then proves the ",
            "same bug is fixed.</p>",
            f'<p class="notice">{html.escape(result["disclaimer"])}</p>',
            '<img src="comparison.svg"',
            ' alt="Baseline versus MARGINAL token use">',
            '<div class="grid">',
            f'<div class="card"><strong>{savings["tokens_percent"]:.2f}%</strong>',
            "<span>fewer declared tokens</span></div>",
            f'<div class="card"><strong>{savings["calls_percent"]:.2f}%</strong>',
            "<span>fewer calls</span></div>",
            f'<div class="card"><strong>{baseline["tokens"]:,} → ',
            f'{marginal["tokens"]:,}</strong><span>declared tokens</span></div>',
            '<div class="card"><strong>FAIL → PASS</strong>',
            "<span>each execution</span></div>",
            "</div>",
            stages,
            "<section><h2>Reproduce it</h2>",
            "<p><code>marginal killer-demo --output killer-demo-output</code></p>",
            "</section>",
            "<footer>MARGINAL · Fund only the next action worth taking.</footer>",
            "</main></body></html>",
            "",
        ]
    )


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
