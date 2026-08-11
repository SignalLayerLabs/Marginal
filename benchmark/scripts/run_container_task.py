"""Run one frozen Codex benchmark lane in its pinned SWE-bench container."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark.codex_adapter.container_runner import ContainerTaskConfig, run_container_task
from benchmark.codex_adapter.dataset import fetch_frozen_tasks, render_prompt

_ROOT = Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--condition", choices=("baseline", "marginal"), required=True)
    parser.add_argument("--task-image", required=True)
    parser.add_argument("--overlay-image", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--auth", type=Path, default=Path.home() / ".codex" / "auth.json")
    parser.add_argument("--tasks", type=Path, default=_ROOT / "benchmark" / "tasks.json")
    parser.add_argument(
        "--prompt-template",
        type=Path,
        default=_ROOT / "benchmark" / "prompt_template.txt",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    tasks = fetch_frozen_tasks(args.tasks)
    task = next((item for item in tasks if item.instance_id == args.instance_id), None)
    if task is None:
        raise SystemExit(f"unknown frozen task: {args.instance_id}")
    prompt = render_prompt(args.prompt_template, task.problem_statement)
    record = run_container_task(
        ContainerTaskConfig(
            instance_id=task.instance_id,
            condition=args.condition,
            repetition=args.repetition,
            expected_base_commit=task.base_commit,
            task_image=args.task_image,
            overlay_image=args.overlay_image,
            run_dir=args.run_dir,
            source_root=_ROOT,
            auth_source=args.auth,
            prompt=prompt,
            source_commit=args.source_commit,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
