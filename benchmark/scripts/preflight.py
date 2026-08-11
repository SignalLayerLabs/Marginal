"""Run the frozen Codex/SWE-bench readiness gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark.codex_adapter.preflight import PreflightConfig, PreflightError, run_preflight

_ROOT = Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", type=Path, default=Path("/opt/homebrew/bin/codex"))
    parser.add_argument("--python", type=Path, default=_ROOT / ".venv" / "bin" / "python")
    parser.add_argument("--auth", type=Path, default=Path.home() / ".codex" / "auth.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-verifier", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    environment = json.loads((_ROOT / "benchmark" / "environment.json").read_text())
    try:
        report = run_preflight(
            PreflightConfig(
                repository_root=_ROOT,
                codex_executable=args.codex,
                python_executable=args.python,
                auth_source=args.auth,
                environment_path=_ROOT / "benchmark" / "environment.json",
                tasks_path=_ROOT / "benchmark" / "tasks.json",
                prompt_path=_ROOT / "benchmark" / "prompt_template.txt",
                schema_path=_ROOT / "benchmark" / "schemas" / "run-record-v1.json",
                expected_repository_commit=environment["repository"]["commit"],
                require_verifier=not args.skip_verifier,
                require_task_environment=not args.skip_verifier,
            )
        )
    except PreflightError as exc:
        raise SystemExit(f"preflight failed: {exc}") from None
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
