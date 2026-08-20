"""Command-line interface for MARGINAL traces, ledgers, replay, and demos."""

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
        elif event.get("event") in {"commit", "failure_settlement"}:
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

    report = subparsers.add_parser("report", help="summarize a v0.1 MARGINAL JSONL trace")
    report.add_argument("trace", type=Path)
    report.add_argument("--json", action="store_true", dest="as_json")

    validate = subparsers.add_parser("validate", help="validate a v0.1 MARGINAL JSONL trace")
    validate.add_argument("trace", type=Path)

    ledger_report = subparsers.add_parser(
        "ledger-report", help="summarize a MARGINAL decision ledger v2"
    )
    ledger_report.add_argument("ledger", type=Path)
    ledger_report.add_argument("--json", action="store_true", dest="as_json")

    ledger_validate = subparsers.add_parser(
        "ledger-validate", help="validate a MARGINAL decision ledger v2"
    )
    ledger_validate.add_argument("ledger", type=Path)

    verify = subparsers.add_parser("verify", help="verify a MARGINAL governance ledger v3")
    verify.add_argument("ledger", type=Path)
    verify.add_argument("--expected-root")
    verify.add_argument("--json", action="store_true", dest="as_json")

    ledger_migrate = subparsers.add_parser(
        "ledger-migrate", help="migrate a MARGINAL decision ledger v2 to governance ledger v3"
    )
    ledger_migrate.add_argument("source", type=Path)
    ledger_migrate.add_argument("destination", type=Path)

    ledger_export = subparsers.add_parser(
        "ledger-export",
        help="export a decision ledger with a privacy-preserving profile",
    )
    ledger_export.add_argument("source", type=Path)
    ledger_export.add_argument("destination", type=Path)
    ledger_export.add_argument(
        "--privacy-profile",
        required=True,
        choices=["safe_telemetry", "aggregate_export"],
    )
    ledger_export.add_argument("--privacy-key-file", type=Path)
    ledger_export.add_argument(
        "--minimum-group-size",
        type=int,
        default=5,
        help=(
            "suppress aggregate groups smaller than this count (default: 5; aggregate_export only)"
        ),
    )

    replay = subparsers.add_parser(
        "replay", help="re-evaluate ledger decisions with a reference policy profile"
    )
    replay.add_argument("ledger", type=Path)
    replay.add_argument(
        "--profile",
        choices=["quality-first", "balanced", "token-saver", "strict-budget"],
        default="balanced",
    )
    replay.add_argument("--json", action="store_true", dest="as_json")

    subparsers.add_parser("demo", help="run the deterministic bundled benchmark")

    killer = subparsers.add_parser(
        "killer-demo", help="run the end-to-end compute allocation demonstration"
    )
    killer.add_argument(
        "--output",
        type=Path,
        default=Path("killer-demo-output"),
        help="directory for HTML, Markdown, JSON, SVG, and trace artifacts",
    )

    public_eval = subparsers.add_parser(
        "public-eval", help="compare matched baseline and MARGINAL public-benchmark runs"
    )
    public_eval.add_argument("baseline", type=Path)
    public_eval.add_argument("marginal", type=Path)
    public_eval.add_argument("--json", action="store_true", dest="as_json")
    public_eval.add_argument("--bootstrap-samples", type=int, default=2_000)
    public_eval.add_argument("--confidence-level", type=float, default=0.95)
    public_eval.add_argument("--quality-margin-pp", type=float, default=1.0)
    public_eval.add_argument(
        "--minimum-net-token-savings-percent",
        type=float,
        default=0.0,
        help="minimum net token saving required before intervention is classified supported",
    )
    public_eval.add_argument(
        "--max-false-stop-rate",
        type=float,
        default=0.0,
        help="maximum reviewed false-stop rate allowed for a supported intervention",
    )
    public_eval.add_argument("--seed", type=int, default=42)

    install_parser = subparsers.add_parser("install", help="install a native integration")
    install_parser.add_argument(
        "target", choices=["codex", "claude-code", "opencode", "privacycode"]
    )
    install_parser.add_argument("--repository", default="SignalLayerLabs/Marginal")
    install_parser.add_argument("--ref", default="main")
    install_parser.add_argument("--data-dir", type=Path)
    install_parser.add_argument("--autopilot-consent", action="store_true")
    install_parser.add_argument(
        "--commons-mode",
        choices=["local_only", "read_only", "contributor"],
        help="persist one explicit Commons network posture (default: local_only)",
    )
    install_parser.add_argument("--json", action="store_true", dest="as_json")

    uninstall_parser = subparsers.add_parser("uninstall", help="remove a native integration")
    uninstall_parser.add_argument(
        "target", choices=["codex", "claude-code", "opencode", "privacycode"]
    )
    uninstall_parser.add_argument("--purge-data", action="store_true")
    uninstall_parser.add_argument("--yes", action="store_true")
    uninstall_parser.add_argument("--data-dir", type=Path)
    uninstall_parser.add_argument("--json", action="store_true", dest="as_json")

    codex = subparsers.add_parser("codex", help="manage the Codex integration")
    codex.add_argument("codex_command", choices=["status", "doctor", "review", "promote", "demote"])
    codex.add_argument("--data-dir", type=Path)
    codex.add_argument("--workspace", type=Path)
    codex.add_argument("--candidate")
    codex.add_argument("--verdict", choices=["helpful", "waste"])
    codex.add_argument("--json", action="store_true", dest="as_json")

    for name, help_text in (
        ("status", "show authority, trust, evidence, and readiness"),
        ("doctor", "diagnose the local Codex integration"),
    ):
        diagnostic = subparsers.add_parser(name, help=help_text)
        diagnostic.add_argument("--data-dir", type=Path)
        diagnostic.add_argument("--workspace", type=Path)
        diagnostic.add_argument("--json", action="store_true", dest="as_json")
    explain = subparsers.add_parser("explain", help="explain a redacted decision receipt")
    explain.add_argument("decision_id")
    explain.add_argument("--data-dir", type=Path)
    explain.add_argument("--workspace", type=Path)
    explain.add_argument("--json", action="store_true", dest="as_json")
    privacy = subparsers.add_parser("privacy", help="inspect local persistence categories")
    privacy_commands = privacy.add_subparsers(dest="privacy_command", required=True)
    privacy_inspect = privacy_commands.add_parser("inspect", help="show persisted data categories")
    privacy_inspect.add_argument("--data-dir", type=Path)
    privacy_inspect.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "install":
        if args.target == "claude-code":
            from .integrations.claude_code.installer import (
                MARKETPLACE_SOURCE,
            )
            from .integrations.claude_code.installer import (
                install as install_claude_code,
            )

            claude_result = install_claude_code(
                marketplace_source=args.repository or MARKETPLACE_SOURCE
            )
            if args.as_json:
                print(json.dumps(claude_result.to_dict(), sort_keys=True))
            else:
                print(claude_result.message or claude_result.error_code or claude_result.selector)
            return 0 if claude_result.installed else 1

        if args.target in {"opencode", "privacycode"}:
            from .integrations.opencode.installer import install as install_opencode
            from .integrations.opencode.targets import resolve_target

            opencode_result = install_opencode(target=resolve_target(args.target))
            if args.as_json:
                print(json.dumps(opencode_result.to_dict(), sort_keys=True))
            else:
                print(opencode_result.message or opencode_result.error_code or opencode_result.path)
            return 0 if opencode_result.installed else 1

        from .integrations.codex.installer import install

        result = install(
            repository=args.repository,
            ref=args.ref,
            data_dir=args.data_dir,
            autopilot_consent=args.autopilot_consent,
            commons_mode=args.commons_mode,
        )
        payload = result.to_dict()
        if args.as_json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(result.message or result.error_code)
        return 0 if result.installed else 1

    if args.command == "uninstall":
        if args.target == "claude-code":
            from .integrations.claude_code.installer import uninstall as uninstall_claude_code

            claude_result = uninstall_claude_code()
            if args.as_json:
                print(json.dumps(claude_result.to_dict(), sort_keys=True))
            else:
                print(claude_result.message or claude_result.error_code or claude_result.selector)
            return 0 if not claude_result.installed else 1

        if args.target in {"opencode", "privacycode"}:
            from .integrations.opencode.installer import uninstall as uninstall_opencode
            from .integrations.opencode.targets import resolve_target

            opencode_result = uninstall_opencode(target=resolve_target(args.target))
            if args.as_json:
                print(json.dumps(opencode_result.to_dict(), sort_keys=True))
            else:
                print(opencode_result.message or opencode_result.error_code or opencode_result.path)
            return 0 if not opencode_result.installed else 1

        from .integrations.codex.commands import default_data_dir, purge_data
        from .integrations.codex.installer import uninstall

        if args.purge_data and not args.yes:
            print("--purge-data requires --yes", file=sys.stderr)
            return 2
        result = uninstall()
        if args.purge_data and not result.installed:
            purge_data(args.data_dir or default_data_dir(), confirmed=True)
        if args.as_json:
            print(json.dumps(result.to_dict(), sort_keys=True))
        else:
            print(result.message or result.error_code)
        return 0 if not result.installed else 1

    if args.command == "codex":
        from .integrations.codex.commands import codex_command

        return codex_command(
            args.codex_command,
            data_dir=args.data_dir,
            workspace=args.workspace,
            candidate=args.candidate,
            verdict=args.verdict,
            as_json=args.as_json,
        )

    if args.command in {"status", "doctor", "explain", "privacy"}:
        from .diagnostics import (
            decision_explanation,
            doctor_report,
            inspect_privacy,
            render_human,
            status_report,
        )
        from .integrations.codex.commands import default_data_dir

        data_dir = getattr(args, "data_dir", None) or default_data_dir()
        workspace = getattr(args, "workspace", None) or Path.cwd()
        if args.command == "status":
            payload = status_report(data_root=data_dir, workspace=workspace).to_dict()
            exit_code = 0
        elif args.command == "doctor":
            payload = doctor_report(data_root=data_dir, workspace=workspace).to_dict()
            exit_code = 0
        elif args.command == "explain":
            payload = decision_explanation(
                args.decision_id, data_root=data_dir, workspace=workspace
            ).to_dict()
            exit_code = 0 if payload["found"] is True else 1
        else:
            payload = inspect_privacy(data_root=data_dir).to_dict()
            exit_code = 0
        if args.as_json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(render_human(payload), end="")
        return exit_code

    if args.command == "ledger-export":
        from .ledger import export_decision_ledger

        try:
            exported = export_decision_ledger(
                args.source,
                args.destination,
                privacy_profile=args.privacy_profile,
                privacy_key_path=args.privacy_key_file,
                minimum_group_size=args.minimum_group_size,
            )
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"exported {exported} records to {args.destination} with {args.privacy_profile}")
        return 0

    if args.command == "verify":
        from .governance_ledger import GovernanceLedger, LedgerVerificationReport

        try:
            verification_report = GovernanceLedger(args.ledger).verify(
                expected_root=args.expected_root
            )
        except (OSError, ValueError):
            verification_report = LedgerVerificationReport(False, 0, None, None, ("IO_ERROR",))
        payload = {
            "valid": verification_report.valid,
            "records": verification_report.records,
            "root_hash": verification_report.root_hash,
            "first_invalid_sequence": verification_report.first_invalid_sequence,
            "error_codes": list(verification_report.error_codes),
        }
        if args.as_json:
            print(json.dumps(payload, sort_keys=True))
        elif verification_report.valid:
            print(
                "valid governance ledger: "
                f"{verification_report.records} records; root {verification_report.root_hash}"
            )
        else:
            print(
                "invalid governance ledger: " + ", ".join(verification_report.error_codes),
                file=sys.stderr,
            )
        return 0 if verification_report.valid else 1

    if args.command == "ledger-migrate":
        from .governance_ledger import migrate_v2_to_v3

        try:
            migration_report = migrate_v2_to_v3(args.source, args.destination)
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(
            "migrated "
            f"{migration_report.records} records to {args.destination}; "
            f"root {migration_report.root_hash}",
        )
        return 0 if migration_report.valid else 1

    if args.command in {"ledger-report", "ledger-validate"}:
        from .ledger import read_decision_ledger, summarize_decision_ledger

        try:
            records = read_decision_ledger(args.ledger)
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if args.command == "ledger-validate":
            print(f"valid decision ledger: {len(records)} events")
            return 0
        summary = summarize_decision_ledger(records)
        if args.as_json:
            print(json.dumps(summary, sort_keys=True))
        else:
            print("MARGINAL decision ledger report")
            print(f"Events: {summary['events']}")
            print(f"Authorizations: {summary['authorizations']}")
            print(f"Recommended allowed: {summary['recommended_allowed']}")
            print(f"Applied allowed: {summary['applied_allowed']}")
            print(f"Non-blocking overrides: {summary['nonblocking_overrides']}")
            print(f"Outcomes: {summary['outcomes']}")
            print(f"Privacy profiles: {', '.join(summary['privacy_profiles'])}")
        return 0

    if args.command == "replay":
        from .profiles import build_policy
        from .replay import render_replay_report, replay_ledger

        try:
            replay_result = replay_ledger(args.ledger, build_policy(args.profile))
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if args.as_json:
            print(json.dumps(replay_result.to_dict(), sort_keys=True))
        else:
            print(render_replay_report(replay_result), end="")
        return 0

    if args.command == "demo":
        from .benchmark import render_markdown, run_benchmark

        print(render_markdown(run_benchmark()), end="")
        return 0

    if args.command == "public-eval":
        from .public_eval import compare_runs, load_runs, render_public_report

        try:
            report = compare_runs(
                load_runs(args.baseline),
                load_runs(args.marginal),
                bootstrap_samples=args.bootstrap_samples,
                confidence_level=args.confidence_level,
                quality_margin_pp=args.quality_margin_pp,
                minimum_net_token_savings_percent=(args.minimum_net_token_savings_percent),
                max_false_stop_rate=args.max_false_stop_rate,
                seed=args.seed,
            )
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if args.as_json:
            print(json.dumps(report, sort_keys=True))
        else:
            print(render_public_report(report), end="")
        return 0

    if args.command == "killer-demo":
        from .killer_demo import run_killer_demo

        demo_result = run_killer_demo(args.output)
        if "savings" in demo_result:
            savings = demo_result["savings"]
            print("MARGINAL Killer Demo")
            print(
                f"Declared tokens: {demo_result['baseline']['tokens']:,} -> "
                f"{demo_result['marginal']['tokens']:,} "
                f"({savings['tokens_percent']:.2f}% fewer)"
            )
            print("Verified outcome: preserved")
            print(f"Artifacts: {args.output.resolve()}")
        else:
            print("MARGINAL Killer Demo completed")
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
