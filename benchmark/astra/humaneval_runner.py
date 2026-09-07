"""Run the complete HumanEval+ suite in isolated paired Codex lanes."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from benchmark.codex_adapter.runner import RunConfig, run_task

_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_EXPECTED_IDS = frozenset(f"HumanEval/{index}" for index in range(164))
_LANES = {"off": "baseline", "on": "marginal"}
_INSTRUCTION = (
    "Implement the requested function in solution.py. Validate your implementation using only "
    "local, self-authored checks. Do not use network access or read files outside this task "
    "workspace. Avoid unnecessary repeated actions."
)
_HEX_DIGITS = frozenset("0123456789abcdef")
RunTask = Callable[[RunConfig], dict[str, Any]]


class TaskInputError(ValueError):
    """The public task-only input is malformed or incomplete."""


@dataclass(frozen=True, slots=True)
class HumanEvalTask:
    task_id: str
    prompt: str
    entry_point: str


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    tasks_path: Path
    protocol_path: Path
    protocol_sha256: str
    run_root: Path
    codex_executable: Path
    auth_source: Path
    model: str
    reasoning_effort: str
    codex_version: str
    timeout_seconds: float = 180
    lane_concurrency: int = 2
    maximum_new_lanes: int | None = None

    def __post_init__(self) -> None:
        if len(self.protocol_sha256) != 64 or any(
            character not in _HEX_DIGITS for character in self.protocol_sha256
        ):
            raise ValueError("protocol_sha256 must be a lowercase SHA256 digest")
        if not self.model or not self.reasoning_effort or not self.codex_version:
            raise ValueError("model, reasoning effort, and Codex version must be explicit")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.lane_concurrency < 1:
            raise ValueError("lane_concurrency must be positive")
        if self.maximum_new_lanes is not None and self.maximum_new_lanes < 0:
            raise ValueError("maximum_new_lanes cannot be negative")

    def as_kwargs(self) -> dict[str, object]:
        """Return constructor values for a deliberate immutable-config replacement."""

        return asdict(self)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256(encoded)


def load_tasks(path: Path) -> tuple[HumanEvalTask, ...]:
    """Load the exact public task-only HumanEval+ suite in frozen order."""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise TaskInputError(f"cannot read task input: {exc}") from exc
    tasks: list[HumanEvalTask] = []
    seen: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise TaskInputError(f"blank JSONL row at line {line_number}")
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TaskInputError(f"invalid JSON at line {line_number}: {exc.msg}") from exc
        if not isinstance(raw, dict) or set(raw) != {"task_id", "prompt", "entry_point"}:
            raise TaskInputError(
                f"line {line_number} must contain only task_id, prompt, and entry_point"
            )
        task_id = raw["task_id"]
        prompt = raw["prompt"]
        entry_point = raw["entry_point"]
        if not isinstance(task_id, str) or task_id not in _EXPECTED_IDS or task_id in seen:
            raise TaskInputError(f"invalid or duplicate task_id at line {line_number}")
        if not isinstance(prompt, str) or not prompt or not prompt.endswith("\n"):
            raise TaskInputError(f"prompt at line {line_number} must be nonempty and newline-ended")
        if not isinstance(entry_point, str) or not entry_point:
            raise TaskInputError(f"entry_point at line {line_number} must be nonempty")
        seen.add(task_id)
        tasks.append(HumanEvalTask(task_id, prompt, entry_point))
    if seen != _EXPECTED_IDS:
        missing = sorted(_EXPECTED_IDS - seen)
        raise TaskInputError(
            f"task input must contain all 164 HumanEval IDs; missing {missing[:3]}"
        )
    return tuple(sorted(tasks, key=lambda task: _sha256(task.task_id.encode("utf-8"))))


def _lane_key(task: HumanEvalTask, lane: str) -> str:
    return f"{task.task_id}:{lane}"


def _lane_dir(run_root: Path, task: HumanEvalTask, lane: str) -> Path:
    return run_root / "lanes" / task.task_id.replace("/", "_") / lane


def _ordered_lanes(tasks: tuple[HumanEvalTask, ...]) -> list[tuple[HumanEvalTask, str]]:
    ordered: list[tuple[HumanEvalTask, str]] = []
    for position, task in enumerate(tasks):
        lane_order = ("off", "on") if position % 2 == 0 else ("on", "off")
        ordered.extend((task, lane) for lane in lane_order)
    return ordered


def _task_hash(task: HumanEvalTask) -> str:
    return _json_hash(
        {"task_id": task.task_id, "prompt": task.prompt, "entry_point": task.entry_point}
    )


def _invocation_hash(
    config: BenchmarkConfig,
    task: HumanEvalTask,
    lane: str,
    input_sha256: str,
) -> str:
    return _json_hash(
        {
            "schema_version": 1,
            "task_sha256": _task_hash(task),
            "lane": lane,
            "condition": _LANES[lane],
            "input_sha256": input_sha256,
            "protocol_sha256": config.protocol_sha256,
            "model": config.model,
            "reasoning_effort": config.reasoning_effort,
            "codex_version": config.codex_version,
            "timeout_seconds": config.timeout_seconds,
            "instruction": _INSTRUCTION,
        }
    )


def _expected_manifest(
    config: BenchmarkConfig,
    task: HumanEvalTask,
    lane: str,
    input_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "orchestration_status": "recorded",
        "task_id": task.task_id,
        "task_sha256": _task_hash(task),
        "lane": lane,
        "condition": _LANES[lane],
        "input_sha256": input_sha256,
        "protocol_sha256": config.protocol_sha256,
        "invocation_sha256": _invocation_hash(config, task, lane, input_sha256),
    }


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _classify_existing_lane(
    config: BenchmarkConfig,
    task: HumanEvalTask,
    lane: str,
    input_sha256: str,
) -> tuple[str, dict[str, Any] | None]:
    lane_dir = _lane_dir(config.run_root, task, lane)
    if not lane_dir.exists():
        return "new", None
    manifest = _read_json_object(lane_dir / "lane-manifest.json")
    record = _read_json_object(lane_dir / "run" / "run-record.json")
    if manifest is None:
        return "partial", None
    expected = _expected_manifest(config, task, lane, input_sha256)
    if manifest != expected:
        return "hash_mismatch", None
    if (
        record is None
        or not (lane_dir / "solution.py").is_file()
        or record.get("instance_id") != task.task_id
        or record.get("condition") != _LANES[lane]
        or record.get("repetition") != 1
        or record.get("resolved") is not None
    ):
        return "partial", None
    return "recorded", record


def _git(worktree: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=worktree,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _materialize_checkout(lane_dir: Path, task: HumanEvalTask) -> tuple[Path, str]:
    lane_dir.mkdir(parents=True, exist_ok=False)
    worktree = lane_dir / "worktree"
    worktree.mkdir()
    _git(worktree, "init", "-q")
    (worktree / "solution.py").write_text(task.prompt + "    pass\n", encoding="utf-8")
    _git(worktree, "add", "solution.py")
    fixed_environment = {
        "GIT_AUTHOR_NAME": "HumanEval Benchmark",
        "GIT_AUTHOR_EMAIL": "benchmark@example.invalid",
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
        "GIT_COMMITTER_NAME": "HumanEval Benchmark",
        "GIT_COMMITTER_EMAIL": "benchmark@example.invalid",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
    }
    _git(worktree, "commit", "-qm", "frozen HumanEval task", env=fixed_environment)
    _git(worktree, "checkout", "--detach", "-q", "HEAD")
    return worktree, _git(worktree, "rev-parse", "HEAD")


def _record_lane(
    config: BenchmarkConfig,
    task: HumanEvalTask,
    lane: str,
    input_sha256: str,
    run_task_fn: RunTask,
) -> None:
    lane_dir = _lane_dir(config.run_root, task, lane)
    worktree, base_commit = _materialize_checkout(lane_dir, task)
    run_dir = lane_dir / "run"
    record = run_task_fn(
        RunConfig(
            instance_id=task.task_id,
            condition=_LANES[lane],
            repetition=1,
            worktree=worktree,
            expected_base_commit=base_commit,
            run_dir=run_dir,
            prompt=_INSTRUCTION,
            codex_executable=config.codex_executable,
            auth_source=config.auth_source,
            model=config.model,
            reasoning_effort=config.reasoning_effort,
            timeout_seconds=config.timeout_seconds,
            codex_version=config.codex_version,
        )
    )
    if not isinstance(record, dict) or record.get("resolved") is not None:
        raise RuntimeError("run_task returned an invalid or prematurely graded record")
    run_dir.mkdir(parents=True, exist_ok=True)
    record_path = run_dir / "run-record.json"
    existing_record = _read_json_object(record_path) if record_path.exists() else None
    if record_path.exists() and existing_record != record:
        raise RuntimeError("run_task record differs from its persisted evidence")
    if not record_path.exists():
        record_path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    solution_path = worktree / "solution.py"
    if not solution_path.is_file():
        raise RuntimeError("run_task did not leave solution.py in the task checkout")
    shutil.copyfile(solution_path, lane_dir / "solution.py")
    (lane_dir / "lane-manifest.json").write_text(
        json.dumps(_expected_manifest(config, task, lane, input_sha256), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _has_complete_telemetry(record: dict[str, Any]) -> bool:
    tokens = record.get("tokens")
    return bool(
        isinstance(tokens, dict)
        and all(
            isinstance(tokens.get(name), int)
            for name in ("input", "cached_input", "output", "reasoning", "total")
        )
    )


def _write_samples(
    config: BenchmarkConfig,
    tasks: tuple[HumanEvalTask, ...],
    recorded: dict[str, dict[str, Any]],
) -> None:
    samples_dir = config.run_root / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    for lane in _LANES:
        rows: list[str] = []
        for task in tasks:
            key = _lane_key(task, lane)
            if key not in recorded:
                continue
            solution = (_lane_dir(config.run_root, task, lane) / "solution.py").read_text(
                encoding="utf-8"
            )
            rows.append(json.dumps({"task_id": task.task_id, "solution": solution}, sort_keys=True))
        temporary = samples_dir / f".{lane}.jsonl.tmp"
        temporary.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
        temporary.replace(samples_dir / f"{lane}.jsonl")


def _validate_config(
    config: BenchmarkConfig,
) -> tuple[tuple[HumanEvalTask, ...], str, str]:
    tasks = load_tasks(config.tasks_path)
    input_sha256 = _sha256(config.tasks_path.read_bytes())
    try:
        protocol = config.protocol_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read immutable protocol: {exc}") from exc
    actual_protocol_hash = _sha256(protocol)
    if actual_protocol_hash != config.protocol_sha256:
        raise ValueError(
            "protocol SHA256 mismatch: "
            f"expected {config.protocol_sha256}, got {actual_protocol_hash}"
        )
    try:
        protocol_data = json.loads(protocol)
    except json.JSONDecodeError as exc:
        raise ValueError(f"immutable protocol is not valid JSON: {exc.msg}") from exc
    if not isinstance(protocol_data, dict):
        raise ValueError("immutable protocol must be a JSON object")
    if protocol_data.get("task_inputs_sha256") != input_sha256:
        raise ValueError("immutable protocol task input SHA256 does not match the task-only JSONL")
    dataset = protocol_data.get("dataset")
    dataset_version = protocol_data.get("dataset_version")
    if not isinstance(dataset, str) or not dataset or not isinstance(dataset_version, str):
        raise ValueError("immutable protocol must name its dataset and dataset version")
    if not config.codex_executable.is_file():
        raise ValueError(f"Codex executable does not exist: {config.codex_executable}")
    if not config.auth_source.is_file():
        raise ValueError(f"Codex auth source does not exist: {config.auth_source}")
    run_root = config.run_root.resolve()
    if run_root == _SOURCE_ROOT or run_root.is_relative_to(_SOURCE_ROOT):
        raise ValueError("run root must be outside the source tree")
    return tasks, input_sha256, f"{dataset} {dataset_version}".strip()


def run_benchmark(
    config: BenchmarkConfig,
    *,
    run_task_fn: RunTask = run_task,
) -> dict[str, Any]:
    """Run a bounded number of new lanes and report exact resumable state."""

    tasks, input_sha256, benchmark_name = _validate_config(config)
    config.run_root.mkdir(parents=True, exist_ok=True)
    schedule = _ordered_lanes(tasks)
    initial: dict[str, tuple[str, dict[str, Any] | None]] = {
        _lane_key(task, lane): _classify_existing_lane(config, task, lane, input_sha256)
        for task, lane in schedule
    }
    blockers = {
        key: status
        for key, (status, _) in initial.items()
        if status in {"partial", "hash_mismatch"}
    }
    for key, (status, record) in initial.items():
        if (
            status == "recorded"
            and record is not None
            and (record.get("run_status") != "completed" or not _has_complete_telemetry(record))
        ):
            blockers[key] = "stop_rule"
    new_lanes = [
        (task, lane) for task, lane in schedule if initial[_lane_key(task, lane)][0] == "new"
    ]
    limit = len(new_lanes) if config.maximum_new_lanes is None else config.maximum_new_lanes
    selected = [] if blockers else new_lanes[:limit]
    launched: list[str] = []
    execution_errors: dict[str, str] = {}
    if selected:
        remaining = iter(selected)
        stop_launching = False
        with ThreadPoolExecutor(max_workers=config.lane_concurrency) as executor:
            futures: dict[Future[None], tuple[HumanEvalTask, str]] = {}

            def submit_next() -> bool:
                try:
                    task, lane = next(remaining)
                except StopIteration:
                    return False
                launched.append(_lane_key(task, lane))
                future = executor.submit(
                    _record_lane, config, task, lane, input_sha256, run_task_fn
                )
                futures[future] = (task, lane)
                return True

            for _ in range(min(config.lane_concurrency, len(selected))):
                submit_next()
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    task, lane = futures.pop(future)
                    key = _lane_key(task, lane)
                    try:
                        future.result()
                    except Exception as exc:
                        execution_errors[key] = f"{type(exc).__name__}: {exc}"
                        stop_launching = True
                        continue
                    status, record = _classify_existing_lane(config, task, lane, input_sha256)
                    if (
                        status != "recorded"
                        or record is None
                        or (
                            record.get("run_status") != "completed"
                            or not _has_complete_telemetry(record)
                        )
                    ):
                        stop_launching = True
                while not stop_launching and len(futures) < config.lane_concurrency:
                    if not submit_next():
                        break

    final: dict[str, tuple[str, dict[str, Any] | None]] = {
        _lane_key(task, lane): _classify_existing_lane(config, task, lane, input_sha256)
        for task, lane in schedule
    }
    recorded = {
        key: record
        for key, (status, record) in final.items()
        if status == "recorded" and record is not None
    }
    partial_lanes = [key for key, (status, _) in final.items() if status == "partial"]
    mismatch_lanes = [key for key, (status, _) in final.items() if status == "hash_mismatch"]
    missing_telemetry = [
        key for key, record in recorded.items() if not _has_complete_telemetry(record)
    ]
    failed_lanes = [
        key for key, record in recorded.items() if record.get("run_status") != "completed"
    ]
    stop_rule_lanes = list(
        dict.fromkeys([*partial_lanes, *mismatch_lanes, *missing_telemetry, *failed_lanes])
    )
    resumed = [key for key, (status, _) in initial.items() if status == "recorded"]
    _write_samples(config, tasks, recorded)
    pending_lanes = 328 - len(recorded)
    complete = bool(
        len(recorded) == 328
        and not partial_lanes
        and not mismatch_lanes
        and not missing_telemetry
        and not failed_lanes
        and not execution_errors
    )
    summary: dict[str, Any] = {
        "schema_version": 1,
        "benchmark": benchmark_name,
        "input_sha256": input_sha256,
        "protocol_sha256": config.protocol_sha256,
        "expected_tasks": 164,
        "expected_lanes": 328,
        "recorded_lanes": len(recorded),
        "pending_lanes": pending_lanes,
        "launched": launched,
        "resumed": resumed,
        "partial_lanes": partial_lanes,
        "hash_mismatch_lanes": mismatch_lanes,
        "missing_telemetry_lanes": missing_telemetry,
        "failed_lanes": failed_lanes,
        "stop_rule_lanes": stop_rule_lanes,
        "execution_errors": execution_errors,
        "complete": complete,
        "official_grading_complete": False,
    }
    (config.run_root / "orchestration-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--codex", required=True, type=Path)
    parser.add_argument("--auth", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort", required=True)
    parser.add_argument("--codex-version", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180)
    parser.add_argument("--lane-concurrency", type=int, default=2)
    parser.add_argument("--maximum-new-lanes", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run_benchmark(
        BenchmarkConfig(
            tasks_path=args.tasks,
            protocol_path=args.protocol,
            protocol_sha256=args.protocol_sha256,
            run_root=args.run_root,
            codex_executable=args.codex,
            auth_source=args.auth,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            codex_version=args.codex_version,
            timeout_seconds=args.timeout_seconds,
            lane_concurrency=args.lane_concurrency,
            maximum_new_lanes=args.maximum_new_lanes,
        )
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
