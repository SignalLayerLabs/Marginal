"""Command-line interface for MARGINAL traces and demos."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _read_trace(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number}: {exc.msg}") from exc
            if not isinstance(event, dict) or not isinstance(event.get("event"), str):
                raise ValueError(f"invalid event on line {line_number}")
            events.append(event)
    return events


def summarize_trace(events: list[dict[str, Any]]) -> dict[str, Any]:
    approved = 0
    denied = 0
    committed = 0
    usage: dict[str, Any] = {"tokens": 0, "usd": 0.0, "latency_ms": 0, "risk": 0.0}
    for event in events:
        if event.get("event") == "authorization":
            if event.get("decision", {}).get("allowed"):
                approved += 1
            else:
                denied += 1
        elif event.get("event") == "commit":
            committed += 1
            usage.update(event.get("usage", {}))
    return {
        "events": len(events),
        "approved": approved,
        "denied": denied,
        "committed": committed,
        "usage": usage,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="marginal",
        description="Allocate agent compute only when marginal value justifies cost.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    report = subparsers.add_parser("report", help="summarize a MARGINAL JSONL trace")
    report.add_argument("trace", type=Path)
    report.add_argument("--json", action="store_true", dest="as_json")

    validate = subparsers.add_parser("validate", help="validate a MARGINAL JSONL trace")
    validate.add_argument("trace", type=Path)

    subparsers.add_parser("demo", help="run the deterministic bundled benchmark")

    killer = subparsers.add_parser(
        "killer-demo",
        help="run the end-to-end compute allocation demonstration",
    )
    public_eval = subparsers.add_parser(
        "public-eval",
        help="compare matched baseline and MARGINAL public-benchmark runs",
    )
    public_eval.add_argument("baseline", type=Path)
    public_eval.add_argument("marginal", type=Path)
    public_eval.add_argument("--json", action="store_true", dest="as_json")
    public_eval.add_argument("--bootstrap-samples", type=int, default=2_000)

    killer.add_argument(
        "--output",
        type=Path,
        default=Path("killer-demo-output"),
        help="directory for HTML, Markdown, JSON, SVG, and trace artifacts",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "demo":
        from .benchmark import render_markdown, run_benchmark

        print(render_markdown(run_benchmark()), end="")
        return 0

    if args.command == "public-eval":
        from .public_eval import compare_runs, load_runs, render_public_report

        try:
            result = compare_runs(
                load_runs(args.baseline),
                load_runs(args.marginal),
                bootstrap_samples=args.bootstrap_samples,
            )
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if args.as_json:
            print(json.dumps(result, sort_keys=True))
        else:
            print(render_public_report(result), end="")
        return 0

    if args.command == "killer-demo":
        from .killer_demo import run_killer_demo

        result = run_killer_demo(args.output)
        savings = result["savings"]
        print("MARGINAL Killer Demo")
        token_summary = (
            f"Declared tokens: {result['baseline']['tokens']:,} → "
            f"{result['marginal']['tokens']:,} "
            f"({savings['tokens_percent']:.2f}% fewer)"
        )
        print(token_summary)
        print("Verified outcome: preserved")
        print(f"Artifacts: {args.output.resolve()}")
        return 0

    try:
        events = _read_trace(args.trace)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.command == "validate":
        print(f"valid trace: {len(events)} events")
        return 0

    summary = summarize_trace(events)
    if args.as_json:
        print(json.dumps(summary, sort_keys=True))
    else:
        usage = summary["usage"]
        print("MARGINAL trace report")
        print(f"Events: {summary['events']}")
        print(f"Approved actions: {summary['approved']}")
        print(f"Denied actions: {summary['denied']}")
        print(f"Committed actions: {summary['committed']}")
        print(f"Tokens: {usage['tokens']}")
        print(f"USD: ${float(usage['usd']):.6f}")
        print(f"Latency: {usage['latency_ms']} ms")
        print(f"Risk: {float(usage['risk']):.6f}")
    return 0
