"""Fetch and materialize the frozen SWE-bench Lite smoke tasks."""

from __future__ import annotations

import argparse
from pathlib import Path

from benchmark.codex_adapter.dataset import fetch_frozen_tasks, materialize_task

_ROOT = Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--instance-id", action="append")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    tasks = fetch_frozen_tasks(_ROOT / "benchmark" / "tasks.json")
    selected = set(args.instance_id or (task.instance_id for task in tasks))
    unknown = selected - {task.instance_id for task in tasks}
    if unknown:
        raise SystemExit(f"unknown frozen task IDs: {sorted(unknown)}")
    for task in tasks:
        if task.instance_id in selected:
            target = args.destination / task.instance_id
            materialize_task(task, target)
            print(f"{task.instance_id}\t{task.base_commit}\t{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
