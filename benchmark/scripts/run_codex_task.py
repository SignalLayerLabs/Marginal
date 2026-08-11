"""Run one frozen SWE-bench task in one Codex benchmark condition."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from benchmark.codex_adapter.dataset import fetch_frozen_tasks, render_prompt
from benchmark.codex_adapter.preflight import PreflightConfig, PreflightError, run_preflight
from benchmark.codex_adapter.runner import RunConfig, run_task

_ROOT = Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--condition", required=True, choices=("baseline", "marginal"))
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--codex", type=Path, default=Path("/opt/homebrew/bin/codex"))
    parser.add_argument("--auth", type=Path, default=Path.home() / ".codex" / "auth.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    environment_path = _ROOT / "benchmark" / "environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    try:
        run_preflight(
            PreflightConfig(
                repository_root=_ROOT,
                codex_executable=args.codex,
                python_executable=Path(sys.executable),
                auth_source=args.auth,
                environment_path=environment_path,
                tasks_path=_ROOT / "benchmark" / "tasks.json",
                prompt_path=_ROOT / "benchmark" / "prompt_template.txt",
                schema_path=_ROOT / "benchmark" / "schemas" / "run-record-v1.json",
                expected_repository_commit=environment["repository"]["commit"],
                require_verifier=True,
                require_task_environment=True,
            )
        )
    except PreflightError as exc:
        raise SystemExit(f"benchmark run blocked: {exc}") from None
    tasks = fetch_frozen_tasks(_ROOT / "benchmark" / "tasks.json")
    task = next((item for item in tasks if item.instance_id == args.instance_id), None)
    if task is None:
        raise SystemExit(f"unknown frozen task: {args.instance_id}")
    prompt = render_prompt(_ROOT / "benchmark" / "prompt_template.txt", task.problem_statement)
    record = run_task(
        RunConfig(
            instance_id=task.instance_id,
            condition=args.condition,
            repetition=1,
            worktree=args.worktree,
            expected_base_commit=task.base_commit,
            run_dir=args.run_dir,
            prompt=prompt,
            codex_executable=args.codex,
            auth_source=args.auth,
        )
    )
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
