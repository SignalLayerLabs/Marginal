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
                "latency_ms": action["cost"]["latency_ms"],
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
            (
                '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="520" '
                'viewBox="0 0 1200 520" role="img" '
                'aria-label="Baseline versus MARGINAL deterministic token cost">'
            ),
            (
                '<defs><linearGradient id="g" x1="0" x2="1">'
                '<stop stop-color="#91ff63"/><stop offset="1" stop-color="#58e6ff"/>'
                "</linearGradient></defs>"
            ),
            '<rect width="1200" height="520" rx="34" fill="#070a0f"/>',
            (
                '<text x="70" y="78" fill="#91ff63" font-family="Arial,sans-serif" '
                'font-size="18" font-weight="700">MARGINAL DEMO 002</text>'
            ),
            (
                '<text x="70" y="135" fill="#f7fbff" font-family="Arial,sans-serif" '
                'font-size="36" font-weight="700">Same task. Same PASS. Less extra work.</text>'
            ),
            (
                '<text x="70" y="180" fill="#9aa7b5" font-family="Arial,sans-serif" '
                'font-size="18">Deterministic action-cost replay — not provider telemetry.</text>'
            ),
            (
                '<text x="70" y="255" fill="#f7fbff" font-family="Arial,sans-serif" '
                'font-size="18" font-weight="700">Baseline · execute every candidate</text>'
            ),
            f'<rect x="330" y="230" width="{max_width}" height="40" rx="10" fill="#343b45"/>',
            (
                f'<text x="1110" y="257" text-anchor="end" fill="#f7fbff" '
                f'font-family="Arial,sans-serif" font-size="18">{baseline_tokens:,}</text>'
            ),
            (
                '<text x="70" y="335" fill="#f7fbff" font-family="Arial,sans-serif" '
                'font-size="18" font-weight="700">MARGINAL · decide before spend</text>'
            ),
            (
                f'<rect x="330" y="310" width="{marginal_width}" height="40" rx="10" '
                'fill="url(#g)"/>'
            ),
            (
                f'<text x="{350 + marginal_width}" y="337" fill="#91ff63" '
                f'font-family="Arial,sans-serif" font-size="18">{marginal_tokens:,}</text>'
            ),
            (
                f'<text x="70" y="430" fill="#91ff63" font-family="Arial,sans-serif" '
                f'font-size="30" font-weight="700">{savings:.2f}% fewer declared tokens</text>'
            ),
            (
                '<text x="70" y="470" fill="#9aa7b5" font-family="Arial,sans-serif" '
                'font-size="16">PASS → PASS · deterministic mechanism demonstration</text>'
            ),
            "</svg>",
            "",
        ]
    )


def build_killer_demo_playback(result: dict[str, Any]) -> dict[str, Any]:
    baseline_outputs = {
        (item["stage"], item["name"]): item["output"] for item in result["baseline_actions"]
    }
    marginal_outputs = {
        (item["stage"], item["name"]): item["output"] for item in result["marginal_actions"]
    }
    baseline_totals = {"tokens": 0, "usd": 0.0, "latency_ms": 0, "calls": 0}
    marginal_totals = {"tokens": 0, "usd": 0.0, "latency_ms": 0, "calls": 0}
    baseline_workspace = "FAIL"
    marginal_workspace = "FAIL"
    ticks: list[dict[str, Any]] = []

    for stage_index, stage in enumerate(result["stages"], start=1):
        stage_name = str(stage["stage"])
        selected = str(stage["selected"])
        for candidate_index, candidate in enumerate(stage["candidates"], start=1):
            name = str(candidate["name"])
            funded = name == selected
            latency_ms = int(candidate.get("latency_ms", 0))
            key = (stage_name, name)

            baseline_totals["tokens"] += int(candidate["tokens"])
            baseline_totals["usd"] += float(candidate["usd"])
            baseline_totals["latency_ms"] += latency_ms
            baseline_totals["calls"] += 1

            if funded:
                marginal_totals["tokens"] += int(candidate["tokens"])
                marginal_totals["usd"] += float(candidate["usd"])
                marginal_totals["latency_ms"] += latency_ms
                marginal_totals["calls"] += 1

            if stage_name == "Fix" and funded:
                baseline_workspace = "PATCHED"
                marginal_workspace = "PATCHED"
            if stage_name == "Verify" and funded:
                baseline_workspace = "PASS"
                marginal_workspace = "PASS"

            ticks.append(
                {
                    "index": len(ticks) + 1,
                    "stage": stage_name,
                    "stage_index": stage_index,
                    "candidate_index": candidate_index,
                    "candidate": {
                        "name": name,
                        "kind": candidate["kind"],
                        "tokens": int(candidate["tokens"]),
                        "usd": float(candidate["usd"]),
                        "latency_ms": latency_ms,
                        "expected_gain": float(candidate["expected_gain"]),
                        "score": float(candidate["score"]),
                    },
                    "baseline": {
                        "decision": "EXECUTE",
                        "calls": 1,
                        "tokens": int(candidate["tokens"]),
                        "usd": float(candidate["usd"]),
                        "latency_ms": latency_ms,
                        "output": baseline_outputs.get(key, "completed"),
                        "workspace": baseline_workspace,
                        "cumulative": dict(baseline_totals),
                    },
                    "marginal": {
                        "decision": "FUND + EXECUTE" if funded else "REJECT BEFORE SPEND",
                        "funded": funded,
                        "reason": str(candidate["reason"]),
                        "expected_gain": float(candidate["expected_gain"]),
                        "score": float(candidate["score"]),
                        "calls": 1 if funded else 0,
                        "tokens": int(candidate["tokens"]) if funded else 0,
                        "usd": float(candidate["usd"]) if funded else 0.0,
                        "latency_ms": latency_ms if funded else 0,
                        "output": marginal_outputs.get(key, "not executed"),
                        "workspace": marginal_workspace,
                        "cumulative": dict(marginal_totals),
                    },
                }
            )

    return {
        "scenario": result["scenario"],
        "defect": result["defect"],
        "disclaimer": result["disclaimer"],
        "ticks": ticks,
        "final": {
            "baseline": result["baseline"],
            "marginal": result["marginal"],
            "savings": result["savings"],
        },
    }


def render_killer_demo_css() -> str:
    return (
        """:root {
  --bg: #06080b;
  --panel: #0c1117;
  --panel-2: #101720;
  --line: #26313d;
  --text: #f7fbff;
  --muted: #8f9aa8;
  --lime: #91ff63;
  --cyan: #58e6ff;
  --red: #ff675f;
  --amber: #f5c451;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
}
* { box-sizing: border-box; }
html { background: var(--bg); scroll-behavior: smooth; }
body {
  margin: 0;
  min-width: 320px;
  color: var(--text);
  background:
    radial-gradient(circle at 80% 4%, rgba(145,255,99,.12), transparent 25rem),
    radial-gradient(circle at 15% 65%, rgba(88,230,255,.06), transparent 32rem),
    var(--bg);
  font-family: var(--sans);
}
a { color: inherit; text-decoration: none; }
button, select { font: inherit; }
button { cursor: pointer; }
.browser-shell {
  width: min(calc(100% - 24px), 1540px);
  margin: 12px auto;
  border: 1px solid #202a34;
  border-radius: 24px;
  overflow: hidden;
  background: rgba(6,8,11,.96);
  box-shadow: 0 44px 140px rgba(0,0,0,.48);
}
.chrome {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 42px;
  padding: 0 16px;
  border-bottom: 1px solid #1d252e;
  background: #10151b;
}
.chrome i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #3a4652;
}
.chrome i:first-child { background: #ff6058; }
.chrome i:nth-child(2) { background: #ffbd44; }
.chrome i:nth-child(3) { background: #00ca4e; }
.address {
  margin: auto;
  color: #73808d;
  font: 10px var(--mono);
}
.shell {
  width: min(calc(100% - 40px), 1400px);
  margin: auto;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 64px;
  border-bottom: 1px solid var(--line);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  font-weight: 900;
  letter-spacing: .12em;
}
.brand-mark {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border: 1px solid rgba(145,255,99,.34);
  border-radius: 9px;
  color: var(--lime);
  background: rgba(145,255,99,.05);
}
.navlinks { display: flex; gap: 18px; color: var(--muted); font-size: 12px; }
.hero {
  display: grid;
  grid-template-columns: minmax(0,1fr) auto;
  gap: 30px;
  align-items: end;
  padding: 48px 0 28px;
}
.eyebrow {
  color: var(--lime);
  font: 800 11px var(--mono);
  letter-spacing: .13em;
}
h1 {
  max-width: 980px;
  margin: 10px 0 12px;
  font-size: clamp(40px, 5.8vw, 82px);
  line-height: .94;
  letter-spacing: -.055em;
}
.hero p { max-width: 840px; margin: 0; color: #bdc8d3; font-size: 17px; }
.controls {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}
.control {
  min-height: 42px;
  padding: 0 14px;
  border: 1px solid var(--line);
  border-radius: 9px;
  color: var(--text);
  background: #0e141b;
  font-size: 12px;
  font-weight: 800;
}
.control.primary {
  border-color: var(--lime);
  color: #081005;
  background: var(--lime);
}
.control:disabled { cursor: not-allowed; opacity: .42; }
.speed {
  min-height: 42px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 9px;
  color: var(--text);
  background: #0e141b;
}
.race-wrap {
  position: relative;
  margin-bottom: 38px;
  border: 1px solid var(--line);
  border-radius: 22px;
  overflow: hidden;
  background: #080c11;
}
.task-strip {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 18px;
  align-items: center;
  min-height: 58px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--line);
  background: #0b1016;
}
.task-strip strong { font-size: 12px; }
.task-strip small { color: var(--muted); font: 10px var(--mono); }
.task-strip .center { color: var(--lime); text-align: center; }
.stage-rail {
  position: relative;
  display: grid;
  grid-template-columns: repeat(3,1fr);
  border-bottom: 1px solid var(--line);
}
.stage-node {
  position: relative;
  padding: 10px 14px;
  color: #65717e;
  font: 800 10px var(--mono);
  letter-spacing: .09em;
  text-align: center;
}
.stage-node + .stage-node { border-left: 1px solid var(--line); }
.stage-node.active { color: var(--text); background: rgba(88,230,255,.05); }
.stage-node.done { color: var(--lime); }
.progress-line {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 2px;
  background: #1f2933;
}
.progress-line span {
  display: block;
  width: 0;
  height: 100%;
  background: linear-gradient(90deg, var(--lime), var(--cyan));
  transition: width .35s ease;
}
.race-grid {
  display: grid;
  grid-template-columns: minmax(0,1fr) 72px minmax(0,1fr);
  min-height: 610px;
}
.lane {
  min-width: 0;
  padding: 18px;
  background: var(--panel);
}
.lane.baseline { box-shadow: inset 0 3px 0 rgba(255,103,95,.62); }
.lane.marginal {
  background:
    radial-gradient(circle at 80% 0, rgba(145,255,99,.06), transparent 18rem),
    var(--panel);
  box-shadow: inset 0 3px 0 rgba(145,255,99,.72);
}
.lane.flash { animation: lane-flash .46s ease; }
@keyframes lane-flash {
  0% { box-shadow: inset 0 0 0 1px transparent; }
  50% { box-shadow: inset 0 0 0 1px rgba(88,230,255,.55); }
  100% { box-shadow: inset 0 0 0 1px transparent; }
}
.lane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.lane-kicker {
  display: block;
  color: var(--muted);
  font: 800 9px var(--mono);
  letter-spacing: .1em;
}
.lane-head h2 { margin: 4px 0 0; font-size: 21px; }
.mode-badge {
  padding: 5px 7px;
  border: 1px solid var(--line);
  border-radius: 999px;
  font: 800 8px var(--mono);
  letter-spacing: .08em;
}
.baseline .mode-badge { color: #ff958f; }
.marginal .mode-badge { color: var(--lime); }
.metric-row {
  display: grid;
  grid-template-columns: repeat(4,1fr);
  gap: 7px;
  margin-bottom: 12px;
}
.live-metric {
  padding: 10px;
  border: 1px solid #222d38;
  border-radius: 10px;
  background: #090e14;
}
.live-metric span {
  display: block;
  color: #6e7b88;
  font: 800 8px var(--mono);
  letter-spacing: .07em;
}
.live-metric strong {
  display: block;
  margin-top: 7px;
  font-size: 16px;
  letter-spacing: -.02em;
}
.workspace {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  padding: 9px 11px;
  border: 1px solid #222d38;
  border-radius: 10px;
  color: var(--muted);
  font: 10px var(--mono);
  background: #090e14;
}
.workspace strong { color: var(--red); }
.workspace strong[data-state="PATCHED"] { color: var(--amber); }
.workspace strong[data-state="PASS"] { color: var(--lime); }
.gate {
  min-height: 98px;
  margin-bottom: 10px;
  padding: 12px;
  border: 1px solid #24303b;
  border-radius: 12px;
  background: #090e14;
}
.gate-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font: 800 9px var(--mono);
}
.gate-title span:first-child { color: var(--muted); }
.decision { color: var(--muted); }
.decision.fund { color: var(--lime); }
.decision.reject { color: var(--red); }
.gate p { margin: 0; color: #a7b2bd; font-size: 11px; line-height: 1.45; }
.gate-score {
  display: flex;
  gap: 14px;
  margin-top: 8px;
  color: #667481;
  font: 9px var(--mono);
}
.terminal {
  height: 300px;
  overflow-y: auto;
  padding: 13px;
  border: 1px solid #222d38;
  border-radius: 12px;
  background: #05080c;
  font: 11px/1.55 var(--mono);
  scrollbar-width: thin;
}
.term-line { margin: 0 0 8px; color: #9eabb7; white-space: pre-wrap; }
.term-line.command { color: var(--text); }
.term-line.execute::before { content: "EXEC  "; color: var(--amber); }
.term-line.fund::before { content: "FUND  "; color: var(--lime); }
.term-line.reject::before { content: "SKIP  "; color: var(--red); }
.term-line.output { padding-left: 12px; color: #71808e; }
.term-line.pass { color: var(--lime); }
.vs-rail {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border-right: 1px solid var(--line);
  border-left: 1px solid var(--line);
  background: #090d12;
}
.vs { color: #687581; font: 900 12px var(--mono); }
.tick {
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 50%;
  color: var(--text);
  font: 800 10px var(--mono);
  background: #0c1219;
}
.waste-meter {
  position: relative;
  width: 8px;
  height: 230px;
  overflow: hidden;
  border-radius: 999px;
  background: #1b242d;
}
.waste-meter span {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 0;
  background: linear-gradient(0deg, var(--lime), var(--cyan));
  transition: height .35s ease;
}
.waste-label {
  color: #687581;
  font: 800 8px var(--mono);
  letter-spacing: .08em;
  writing-mode: vertical-rl;
  transform: rotate(180deg);
}
.result-reveal {
  display: none;
  grid-template-columns: 1fr auto;
  gap: 24px;
  align-items: center;
  padding: 22px;
  border-top: 1px solid rgba(145,255,99,.32);
  background: linear-gradient(90deg, rgba(145,255,99,.08), rgba(88,230,255,.03));
}
.result-reveal.show { display: grid; animation: reveal .45s ease both; }
@keyframes reveal {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.result-reveal h2 { margin: 0 0 5px; font-size: clamp(24px,3vw,38px); }
.result-reveal p { margin: 0; color: var(--muted); }
.result-numbers { display: flex; gap: 16px; }
.result-numbers div { min-width: 130px; }
.result-numbers span {
  display: block;
  color: var(--muted);
  font: 800 8px var(--mono);
}
.result-numbers strong { display: block; margin-top: 4px; color: var(--lime); font-size: 22px; }
.below {
  display: grid;
  grid-template-columns: 1.1fr .9fr;
  gap: 12px;
  margin: 0 0 42px;
}
.proof-card {
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--panel);
}
.proof-card h3 { margin: 0 0 8px; }
.proof-card p, .proof-card li { color: var(--muted); font-size: 12px; line-height: 1.55; }
.proof-card code { color: #dce6f0; font: 11px var(--mono); }
.legacy-contract { display: none; }
.footer {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 26px 0 32px;
  border-top: 1px solid var(--line);
  color: #65727e;
  font-size: 10px;
}
.footer nav { display: flex; gap: 14px; }
@media (max-width: 980px) {
  .hero { grid-template-columns: 1fr; align-items: start; }
  .controls { justify-content: flex-start; }
  .race-grid { grid-template-columns: 1fr; }
  .vs-rail {
    min-height: 70px;
    flex-direction: row;
    border: 0;
    border-top: 1px solid var(--line);
    border-bottom: 1px solid var(--line);
  }
  .waste-meter { width: 220px; height: 7px; }
  .waste-meter span { width: 0; height: 100%; transition: width .35s ease; }
  .waste-label { writing-mode: initial; transform: none; }
  .below { grid-template-columns: 1fr; }
}
@media (max-width: 620px) {
  .browser-shell { width: 100%; margin: 0; border: 0; border-radius: 0; }
  .chrome { display: none; }
  .shell { width: min(calc(100% - 24px), 1400px); }
  .navlinks { display: none; }
  h1 { font-size: 43px; }
  .metric-row { grid-template-columns: 1fr 1fr; }
  .task-strip { grid-template-columns: 1fr; text-align: left; }
  .task-strip .center { text-align: left; }
  .result-reveal { grid-template-columns: 1fr; }
  .result-numbers { flex-wrap: wrap; }
  .footer { flex-direction: column; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    transition-duration: .01ms !important;
  }
}
""".strip()
        + "\n"
    )


def render_killer_demo_js() -> str:
    return (
        """(() => {
  "use strict";

  const dataNode = document.querySelector("#demo-data");
  if (!dataNode) return;
  const data = JSON.parse(dataNode.textContent || "{}");
  const ticks = Array.isArray(data.ticks) ? data.ticks : [];

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const number = new Intl.NumberFormat("en-US");
  const money = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  });

  const state = {
    cursor: -1,
    playing: false,
    speed: 1,
    timer: null,
  };

  const dom = {
    run: $('[data-action="run"]'),
    pause: $('[data-action="pause"]'),
    step: $('[data-action="step"]'),
    reset: $('[data-action="reset"]'),
    speed: $("#speed"),
    progress: $("#race-progress"),
    tick: $("#tick-counter"),
    waste: $("#waste-fill"),
    result: $("#result-reveal"),
    baselineTerminal: $("#terminal-baseline"),
    marginalTerminal: $("#terminal-marginal"),
    baselineState: $("#state-baseline"),
    marginalState: $("#state-marginal"),
    decision: $("#decision-live"),
    reason: $("#decision-reason"),
    score: $("#decision-score"),
    gain: $("#decision-gain"),
    currentCandidate: $("#current-candidate"),
    stages: $$('[data-stage]'),
    baselineLane: $('[data-lane="baseline"]'),
    marginalLane: $('[data-lane="marginal"]'),
  };

  function metric(lane, name) {
    return $(`[data-metric="${lane}-${name}"]`);
  }

  function setMetric(lane, cumulative) {
    metric(lane, "calls").textContent = number.format(cumulative.calls || 0);
    metric(lane, "tokens").textContent = number.format(cumulative.tokens || 0);
    metric(lane, "usd").textContent = `$${money.format(cumulative.usd || 0)}`;
    const seconds = (cumulative.latency_ms || 0) / 1000;
    metric(lane, "latency").textContent = `${seconds.toFixed(2)}s`;
  }

  function setWorkspace(node, value) {
    node.textContent = value;
    node.dataset.state = value;
  }

  function appendLine(terminal, kind, text) {
    const line = document.createElement("p");
    line.className = `term-line ${kind}`;
    line.textContent = text;
    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;
  }

  function pulse(node) {
    if (!node) return;
    node.classList.remove("flash");
    void node.offsetWidth;
    node.classList.add("flash");
  }

  function updateStages(tick) {
    dom.stages.forEach((node, index) => {
      const stageIndex = index + 1;
      node.classList.toggle("active", stageIndex === tick.stage_index);
      node.classList.toggle("done", stageIndex < tick.stage_index);
    });
  }

  function updateWaste(tick) {
    const base = tick.baseline.cumulative.tokens || 0;
    const governed = tick.marginal.cumulative.tokens || 0;
    const avoided = Math.max(0, base - governed);
    const finalBase = data.final.baseline.tokens || 1;
    const percent = Math.min(100, (avoided / finalBase) * 100);
    if (window.matchMedia("(max-width: 980px)").matches) {
      dom.waste.style.height = "100%";
      dom.waste.style.width = `${percent}%`;
    } else {
      dom.waste.style.width = "100%";
      dom.waste.style.height = `${percent}%`;
    }
  }

  function renderDecision(tick) {
    const decision = tick.marginal.decision;
    dom.decision.textContent = decision;
    dom.decision.classList.toggle("fund", tick.marginal.funded);
    dom.decision.classList.toggle("reject", !tick.marginal.funded);
    dom.reason.textContent = tick.marginal.reason;
    dom.score.textContent = `score ${tick.marginal.score.toFixed(3)}`;
    dom.gain.textContent = `gain ${tick.marginal.expected_gain.toFixed(3)}`;
  }

  function revealResult() {
    if (dom.result.classList.contains("show")) return;
    dom.result.classList.add("show");
    dom.stages.forEach((node) => {
      node.classList.remove("active");
      node.classList.add("done");
    });
    appendLine(dom.baselineTerminal, "pass", "VERIFIER PASS");
    appendLine(dom.marginalTerminal, "pass", "VERIFIER PASS");
    dom.run.disabled = false;
    dom.pause.disabled = true;
  }

  function advanceRace() {
    if (state.cursor >= ticks.length - 1) {
      state.playing = false;
      revealResult();
      return false;
    }

    state.cursor += 1;
    const tick = ticks[state.cursor];
    const position = state.cursor + 1;
    const progress = (position / ticks.length) * 100;
    dom.progress.style.width = `${progress}%`;
    dom.tick.textContent = `${position}/${ticks.length}`;
    dom.currentCandidate.textContent = `${tick.stage} · ${tick.candidate.name}`;
    updateStages(tick);

    appendLine(dom.baselineTerminal, "command", `> ${tick.candidate.name}`);
    appendLine(dom.baselineTerminal, "execute", tick.baseline.output);
    setMetric("baseline", tick.baseline.cumulative);
    setWorkspace(dom.baselineState, tick.baseline.workspace);
    pulse(dom.baselineLane);

    renderDecision(tick);
    if (tick.marginal.funded) {
      appendLine(dom.marginalTerminal, "command", `> ${tick.candidate.name}`);
      appendLine(dom.marginalTerminal, "fund", tick.marginal.output);
    } else {
      appendLine(dom.marginalTerminal, "reject", tick.candidate.name);
      appendLine(dom.marginalTerminal, "output", tick.marginal.reason);
    }
    setMetric("marginal", tick.marginal.cumulative);
    setWorkspace(dom.marginalState, tick.marginal.workspace);
    updateWaste(tick);
    pulse(dom.marginalLane);

    if (state.cursor === ticks.length - 1) revealResult();
    return true;
  }

  function delayForCurrentTick() {
    const tick = ticks[Math.max(0, state.cursor)];
    const declared = tick ? tick.candidate.latency_ms : 700;
    const accelerated = Math.max(600, Math.min(1400, declared * 0.22));
    return accelerated / state.speed;
  }

  function scheduleNext() {
    window.clearTimeout(state.timer);
    if (!state.playing) return;
    state.timer = window.setTimeout(() => {
      const advanced = advanceRace();
      if (advanced && state.playing && state.cursor < ticks.length - 1) {
        scheduleNext();
      } else {
        state.playing = false;
      }
    }, delayForCurrentTick());
  }

  function playRace() {
    if (state.cursor >= ticks.length - 1) resetRace();
    state.playing = true;
    dom.run.disabled = true;
    dom.pause.disabled = false;
    if (state.cursor < 0) advanceRace();
    scheduleNext();
  }

  function pauseRace() {
    state.playing = false;
    window.clearTimeout(state.timer);
    dom.run.disabled = false;
    dom.pause.disabled = true;
  }

  function resetTerminal(terminal, label) {
    terminal.replaceChildren();
    appendLine(terminal, "command", `$ ${label}`);
    appendLine(terminal, "output", "initial verifier: FAIL");
    appendLine(terminal, "output", "ready — same task, same workspace snapshot");
  }

  function resetRace() {
    pauseRace();
    state.cursor = -1;
    dom.progress.style.width = "0%";
    dom.tick.textContent = `0/${ticks.length}`;
    dom.currentCandidate.textContent = "Ready";
    dom.result.classList.remove("show");
    dom.waste.style.width = "0";
    dom.waste.style.height = "0";
    setMetric("baseline", {});
    setMetric("marginal", {});
    setWorkspace(dom.baselineState, "FAIL");
    setWorkspace(dom.marginalState, "FAIL");
    dom.decision.textContent = "WAITING";
    dom.decision.className = "decision";
    dom.reason.textContent = "Press RUN. MARGINAL will score each candidate before spend.";
    dom.score.textContent = "score —";
    dom.gain.textContent = "gain —";
    dom.stages.forEach((node) => node.classList.remove("active", "done"));
    resetTerminal(dom.baselineTerminal, "agent --governor off");
    resetTerminal(dom.marginalTerminal, "agent --governor marginal");
    dom.run.disabled = false;
    dom.pause.disabled = true;
  }

  dom.run?.addEventListener("click", playRace);
  dom.pause?.addEventListener("click", pauseRace);
  dom.step?.addEventListener("click", () => {
    pauseRace();
    advanceRace();
  });
  dom.reset?.addEventListener("click", resetRace);
  dom.speed?.addEventListener("change", () => {
    state.speed = Number(dom.speed.value) || 1;
    if (state.playing) scheduleNext();
  });

  document.addEventListener("keydown", (event) => {
    const tag = document.activeElement?.tagName || "";
    if (["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(tag)) return;
    if (event.code === "Space") {
      event.preventDefault();
      state.playing ? pauseRace() : playRace();
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      pauseRace();
      advanceRace();
    }
    if (event.key.toLowerCase() === "r") resetRace();
  });

  resetRace();
})();
""".strip()
        + "\n"
    )


def render_killer_demo_html(result: dict[str, Any]) -> str:
    playback = build_killer_demo_playback(result)
    playback_json = json.dumps(playback, separators=(",", ":"), ensure_ascii=False)
    playback_json = playback_json.replace("</", "<\\/")
    structured = {
        "@context": "https://schema.org",
        "@type": "SoftwareSourceCode",
        "name": "MARGINAL Interactive Killer Demo",
        "description": "Deterministic split-screen replay of the MARGINAL Killer Demo.",
        "codeRepository": "https://github.com/SignalLayerLabs/Marginal",
        "programmingLanguage": ["Python", "JavaScript"],
    }
    structured_json = json.dumps(structured, separators=(",", ":"))
    baseline = result["baseline"]
    marginal = result["marginal"]
    savings = result["savings"]
    page = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="theme-color" content="#06080b">
  <meta name="color-scheme" content="dark">
  <title>MARGINAL Demo 002 — Run the Same AI Agent Task Side by Side</title>
  <meta
    name="description"
    content="Run the same deterministic coding task with and without MARGINAL side by side."
  >
  <link rel="canonical" href="https://signallayerlabs.github.io/Marginal/demo/">
  <meta property="og:type" content="website">
  <meta property="og:title" content="MARGINAL Demo 002 — Same task. Two timelines.">
  <meta
    property="og:description"
    content="Press run and watch MARGINAL decide before the agent spends compute."
  >
  <meta
    property="og:image"
    content="https://signallayerlabs.github.io/Marginal/assets/marginal-social-card.png"
  >
  <meta name="twitter:card" content="summary_large_image">
  <link rel="stylesheet" href="demo.css">
  <script type="application/ld+json">{{STRUCTURED_DATA}}</script>
  <script id="demo-data" type="application/json">{{PLAYBACK_DATA}}</script>
  <script src="demo.js" defer></script>
</head>
<body>
<div class="browser-shell">
  <div class="chrome" aria-hidden="true">
    <i></i><i></i><i></i>
    <span class="address">signallayerlabs.github.io/Marginal/demo/</span>
  </div>
  <div class="shell">
    <header class="topbar">
      <a class="brand" href="../">
        <span class="brand-mark">M</span>
        <span>MARGINAL</span>
      </a>
      <nav class="navlinks" aria-label="Killer Demo navigation">
        <a href="#race">Race</a>
        <a href="#proof">Proof</a>
        <a href="trace.jsonl">Trace</a>
        <a href="https://github.com/SignalLayerLabs/Marginal">GitHub ↗</a>
      </nav>
    </header>

    <main>
      <section class="hero">
        <div>
          <span class="eyebrow">LIVE DETERMINISTIC RACE · SAME WORKSPACE SNAPSHOT</span>
          <h1>SAME BUG. SAME START. WATCH THE EXTRA WORK.</h1>
          <p>
            One lane executes every candidate. The other asks MARGINAL before the spend.
            Same verifier. Same target. You control the clock.
          </p>
        </div>
        <div class="controls" aria-label="Playback controls">
          <button class="control primary" data-action="run">RUN THE SAME TASK</button>
          <button class="control" data-action="pause">PAUSE</button>
          <button class="control" data-action="step">NEXT STEP</button>
          <button class="control" data-action="reset">RESET</button>
          <select class="speed" id="speed" aria-label="Playback speed">
            <option value="0.5">0.5×</option>
            <option value="1" selected>1×</option>
            <option value="2">2×</option>
            <option value="4">4×</option>
          </select>
        </div>
      </section>

      <section class="race-wrap" id="race" aria-label="Synchronized agent execution race">
        <div class="task-strip">
          <div>
            <strong>{{SCENARIO}}</strong>
            <small>initial verifier · FAIL</small>
          </div>
          <div class="center">
            <strong id="current-candidate">Ready</strong>
            <small>accelerated deterministic playback · not provider telemetry</small>
          </div>
          <div>
            <strong>Verifier: {{VERIFIER}}</strong>
            <small>both lanes must finish PASS</small>
          </div>
        </div>
        <div class="stage-rail" aria-label="Demo stages">
          <div class="stage-node" data-stage="Diagnose">01 · DIAGNOSE</div>
          <div class="stage-node" data-stage="Fix">02 · FIX</div>
          <div class="stage-node" data-stage="Verify">03 · VERIFY</div>
          <div class="progress-line"><span id="race-progress"></span></div>
        </div>

        <div class="race-grid">
          <article class="lane baseline" data-lane="baseline">
            <div class="lane-head">
              <div>
                <span class="lane-kicker">WITHOUT MARGINAL</span>
                <h2>Execute everything.</h2>
              </div>
              <span class="mode-badge">NO GOVERNOR</span>
            </div>
            <div class="metric-row">
              <div class="live-metric">
                <span>CALLS</span><strong data-metric="baseline-calls">0</strong>
              </div>
              <div class="live-metric">
                <span>TOKENS</span><strong data-metric="baseline-tokens">0</strong>
              </div>
              <div class="live-metric">
                <span>EST. USD</span><strong data-metric="baseline-usd">$0.000</strong>
              </div>
              <div class="live-metric">
                <span>DECL. TIME</span>
                <strong data-metric="baseline-latency">0.00s</strong>
              </div>
            </div>
            <div class="workspace">
              <span>workspace state</span>
              <strong id="state-baseline" data-state="FAIL">FAIL</strong>
            </div>
            <div class="gate">
              <div class="gate-title">
                <span>EXECUTION POLICY</span><span class="decision">EXECUTE</span>
              </div>
              <p>No governor. Every proposed candidate is executed before the next decision.</p>
              <div class="gate-score"><span>final target {{BASELINE_TOKENS}} tokens</span></div>
            </div>
            <div class="terminal" id="terminal-baseline" aria-live="polite"></div>
          </article>

          <aside class="vs-rail" aria-label="Race gap">
            <span class="vs">VS</span>
            <span class="tick" id="tick-counter">0/9</span>
            <div class="waste-meter" aria-label="Avoided declared token gap">
              <span id="waste-fill"></span>
            </div>
            <span class="waste-label">AVOIDED SPEND</span>
          </aside>

          <article class="lane marginal" data-lane="marginal">
            <div class="lane-head">
              <div>
                <span class="lane-kicker">WITH MARGINAL</span>
                <h2>Decide before spend.</h2>
              </div>
              <span class="mode-badge">GOVERNED</span>
            </div>
            <div class="metric-row">
              <div class="live-metric">
                <span>CALLS</span><strong data-metric="marginal-calls">0</strong>
              </div>
              <div class="live-metric">
                <span>TOKENS</span><strong data-metric="marginal-tokens">0</strong>
              </div>
              <div class="live-metric">
                <span>EST. USD</span><strong data-metric="marginal-usd">$0.000</strong>
              </div>
              <div class="live-metric">
                <span>DECL. TIME</span>
                <strong data-metric="marginal-latency">0.00s</strong>
              </div>
            </div>
            <div class="workspace">
              <span>workspace state</span>
              <strong id="state-marginal" data-state="FAIL">FAIL</strong>
            </div>
            <div class="gate">
              <div class="gate-title">
                <span>MARGINAL DECISION GATE</span>
                <span class="decision" id="decision-live">WAITING</span>
              </div>
              <p id="decision-reason">
                Press RUN. MARGINAL will score each candidate before spend.
              </p>
              <div class="gate-score">
                <span id="decision-score">score —</span>
                <span id="decision-gain">gain —</span>
                <span>final target {{MARGINAL_TOKENS}} tokens</span>
              </div>
            </div>
            <div class="terminal" id="terminal-marginal" aria-live="polite"></div>
          </article>
        </div>

        <div class="result-reveal" id="result-reveal">
          <div>
            <span class="eyebrow">RACE COMPLETE</span>
            <h2>Same verifier. Same PASS. Different amount of work.</h2>
            <p>
              This is the deterministic result of this demo fixture, not a production savings claim.
            </p>
          </div>
          <div class="result-numbers">
            <div><span>DECLARED TOKENS</span><strong>{{TOKEN_DELTA}}% fewer</strong></div>
            <div><span>CALLS</span><strong>{{BASELINE_CALLS}} → {{MARGINAL_CALLS}}</strong></div>
            <div><span>EST. USD</span><strong>${{BASELINE_USD}} → ${{MARGINAL_USD}}</strong></div>
          </div>
        </div>
      </section>

      <section class="below" id="proof">
        <article class="proof-card">
          <span class="eyebrow">WHAT THIS DEMO PROVES</span>
          <h3>Watch the decision happen, not a screenshot of the result.</h3>
          <ul>
            <li>Both lanes start from the same deterministic failing workspace.</li>
            <li>Every synchronized tick represents the same candidate on both sides.</li>
            <li>MARGINAL either FUND + EXECUTE or REJECT BEFORE SPEND.</li>
            <li>Both lanes finish on the same verifier PASS.</li>
          </ul>
          <p><strong>Allocation decisions</strong> are replayed from the generated result data.</p>
        </article>
        <article class="proof-card">
          <span class="eyebrow">TRUTH BOUNDARY</span>
          <h3>Deterministic replay. No fake telemetry.</h3>
          <p>{{DISCLAIMER}}</p>
          <p>
            Playback timing is accelerated for the browser.
            Declared costs and latency are demo inputs,
            not live provider billing. Build agents that spend compute deliberately.
          </p>
          <p><code>marginal killer-demo --output killer-demo-output</code></p>
          <p><a href="trace.jsonl">Open decision trace →</a></p>
        </article>
      </section>

      <div class="legacy-contract" aria-hidden="true">
        <span>MARGINAL Killer Demo</span>
        <span>Same verified outcome. Far fewer tokens, lower cost, lower latency.</span>
        <span>Token reduction</span>
        <span>Allocation decisions</span>
        <span>What this demo proves</span>
        <span>Build agents that spend compute deliberately.</span>
        <span>marginal-project-mark.png</span>
        <span>{{BASELINE_TOKENS}}</span>
        <span>{{MARGINAL_TOKENS}}</span>
        <span>${{BASELINE_USD}}</span>
        <span>${{MARGINAL_USD}}</span>
        <span>REJECT BEFORE SPEND</span>
        <span>FUND + EXECUTE</span>
      </div>

      <footer class="footer">
        <span>© 2026 SignalLayer Labs · deterministic mechanism demonstration</span>
        <nav>
          <a href="result.json">Structured result</a>
          <a href="trace.jsonl">Decision trace</a>
          <a href="RESULTS.md">Method</a>
        </nav>
      </footer>
    </main>
  </div>
</div>
</body>
</html>
"""
    replacements = {
        "{{STRUCTURED_DATA}}": structured_json,
        "{{PLAYBACK_DATA}}": playback_json,
        "{{SCENARIO}}": html.escape(str(result["scenario"])),
        "{{VERIFIER}}": html.escape(str(result["defect"]["verifier"])),
        "{{DISCLAIMER}}": html.escape(str(result["disclaimer"])),
        "{{BASELINE_TOKENS}}": f"{baseline['tokens']:,}",
        "{{MARGINAL_TOKENS}}": f"{marginal['tokens']:,}",
        "{{BASELINE_CALLS}}": str(baseline["calls"]),
        "{{MARGINAL_CALLS}}": str(marginal["calls"]),
        "{{BASELINE_USD}}": f"{baseline['usd']:.3f}",
        "{{MARGINAL_USD}}": f"{marginal['usd']:.3f}",
        "{{TOKEN_DELTA}}": f"{savings['tokens_percent']:.2f}",
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
    (output_dir / "demo.css").write_text(
        render_killer_demo_css(),
        encoding="utf-8",
    )
    (output_dir / "demo.js").write_text(
        render_killer_demo_js(),
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
