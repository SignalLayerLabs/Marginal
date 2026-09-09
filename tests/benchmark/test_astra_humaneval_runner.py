from __future__ import annotations

import hashlib
import json
import subprocess
import threading
from pathlib import Path

import pytest
from benchmark.astra.humaneval_runner import (
    BenchmarkConfig,
    TaskInputError,
    load_tasks,
    run_benchmark,
)
from benchmark.codex_adapter.runner import RunConfig


def _write_tasks(path: Path, *, count: int = 164) -> None:
    rows = [
        {
            "task_id": f"HumanEval/{index}",
            "prompt": f'def function_{index}():\n    """Return {index}."""\n',
            "entry_point": f"function_{index}",
        }
        for index in range(count)
    ]
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )


def _config(tmp_path: Path, *, maximum_new_lanes: int | None = None) -> BenchmarkConfig:
    tasks_path = tmp_path / "tasks.jsonl"
    _write_tasks(tasks_path)
    protocol_path = tmp_path / "protocol.md"
    protocol_path.write_text(
        json.dumps(
            {
                "dataset": "FixtureEval+",
                "dataset_version": "v-test",
                "task_inputs_sha256": hashlib.sha256(tasks_path.read_bytes()).hexdigest(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    executable = tmp_path / "codex"
    executable.write_text("fixture\n", encoding="utf-8")
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    return BenchmarkConfig(
        tasks_path=tasks_path,
        protocol_path=protocol_path,
        protocol_sha256=hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        run_root=tmp_path / "runs",
        codex_executable=executable,
        auth_source=auth,
        model="gpt-6-astra",
        reasoning_effort="low",
        codex_version="0.153.4",
        maximum_new_lanes=maximum_new_lanes,
    )


def _record(config: RunConfig, *, tokens: int | None = 12) -> dict[str, object]:
    return {
        "schema_version": 1,
        "instance_id": config.instance_id,
        "condition": config.condition,
        "repetition": 1,
        "run_status": "completed",
        "resolved": None,
        "configuration_sha256": "a" * 64,
        "patch_sha256": "b" * 64,
        "tokens": {
            "input": tokens,
            "cached_input": 0 if tokens is not None else None,
            "output": 1 if tokens is not None else None,
            "reasoning": 0 if tokens is not None else None,
            "total": tokens,
        },
        "wall_time_ms": 1,
        "tool_calls": 0,
        "shell_commands": 0,
        "file_operations": 1,
        "searches": 0,
        "test_executions": 0,
        "repeated_calls": 0,
        "files_modified": 1,
        "diff_lines": 2,
        "model_reroutes": None,
        "interventions": {
            "recommended_denies": 0,
            "applied_denies": 0,
            "reviewed": 0,
            "false_stops": 0,
        },
        "governance": {"tokens": 0, "usd": 0.0, "latency_ms": 0.0},
        "error_code": None,
    }


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_load_tasks_accepts_only_the_unique_full_humaneval_plus_id_set(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.jsonl"
    _write_tasks(tasks_path)

    tasks = load_tasks(tasks_path)

    assert len(tasks) == 164
    assert [task.task_id for task in tasks[:4]] == [
        "HumanEval/145",
        "HumanEval/91",
        "HumanEval/84",
        "HumanEval/85",
    ]


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "missing", "out-of-range", "grading-field"],
)
def test_load_tasks_rejects_nonpublic_or_nonfull_inputs(tmp_path: Path, mutation: str) -> None:
    tasks_path = tmp_path / "tasks.jsonl"
    _write_tasks(tasks_path)
    rows = [json.loads(line) for line in tasks_path.read_text(encoding="utf-8").splitlines()]
    if mutation == "duplicate":
        rows[-1]["task_id"] = "HumanEval/0"
    elif mutation == "missing":
        rows.pop()
    elif mutation == "out-of-range":
        rows[-1]["task_id"] = "HumanEval/164"
    else:
        rows[0]["canonical_solution"] = "return 0"
    tasks_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    with pytest.raises(TaskInputError):
        load_tasks(tasks_path)


def test_bounded_run_creates_independent_detached_lanes_in_frozen_order(tmp_path: Path) -> None:
    config = _config(tmp_path, maximum_new_lanes=2)
    observed: list[tuple[str, str, str, str]] = []
    lock = threading.Lock()

    def fake_run_task(run_config: RunConfig) -> dict[str, object]:
        files = sorted(path.name for path in run_config.worktree.iterdir() if path.name != ".git")
        assert files == ["solution.py"]
        assert _git(run_config.worktree, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
        assert _git(run_config.worktree, "status", "--porcelain") == ""
        initial = (run_config.worktree / "solution.py").read_text(encoding="utf-8")
        assert initial.endswith('    """Return 145."""\n    pass\n')
        assert run_config.model == "gpt-6-astra"
        assert run_config.reasoning_effort == "low"
        assert run_config.codex_version == "0.153.4"
        assert run_config.timeout_seconds == 180
        with lock:
            observed.append(
                (
                    run_config.instance_id,
                    run_config.condition,
                    str(run_config.worktree),
                    run_config.prompt,
                )
            )
        (run_config.worktree / "solution.py").write_text(
            initial.replace("    pass\n", "    return 145\n"), encoding="utf-8"
        )
        return _record(run_config)

    summary = run_benchmark(config, run_task_fn=fake_run_task)

    assert summary["launched"] == ["HumanEval/145:off", "HumanEval/145:on"]
    assert summary["benchmark"] == "FixtureEval+ v-test"
    assert {(row[0], row[1]) for row in observed} == {
        ("HumanEval/145", "baseline"),
        ("HumanEval/145", "marginal"),
    }
    assert len({row[2] for row in observed}) == 2
    assert len({row[3] for row in observed}) == 1
    assert summary["complete"] is False
    assert summary["recorded_lanes"] == 2
    assert summary["pending_lanes"] == 326
    assert summary["missing_telemetry_lanes"] == []
    for lane in ("off", "on"):
        lane_dir = config.run_root / "lanes" / "HumanEval_145" / lane
        assert (lane_dir / "solution.py").read_text(encoding="utf-8").endswith("    return 145\n")
        assert json.loads((lane_dir / "run" / "run-record.json").read_text())["resolved"] is None
        manifest = json.loads((lane_dir / "lane-manifest.json").read_text())
        assert manifest["task_id"] == "HumanEval/145"
        assert manifest["lane"] == lane
    off_samples = [
        json.loads(line)
        for line in (config.run_root / "samples" / "off.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert off_samples == [
        {
            "task_id": "HumanEval/145",
            "solution": 'def function_145():\n    """Return 145."""\n    return 145\n',
        }
    ]


def test_resume_trusts_matching_records_without_reexecution_and_blocks_hash_drift(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, maximum_new_lanes=1)
    calls: list[str] = []

    def fake_run_task(run_config: RunConfig) -> dict[str, object]:
        calls.append(f"{run_config.instance_id}:{run_config.condition}")
        source = (run_config.worktree / "solution.py").read_text(encoding="utf-8")
        (run_config.worktree / "solution.py").write_text(
            source.replace("    pass\n", "    return 1\n"), encoding="utf-8"
        )
        return _record(run_config)

    first = run_benchmark(config, run_task_fn=fake_run_task)
    second = run_benchmark(config, run_task_fn=fake_run_task)

    assert first["launched"] == ["HumanEval/145:off"]
    assert second["resumed"] == ["HumanEval/145:off"]
    assert second["launched"] == ["HumanEval/145:on"]
    assert calls == ["HumanEval/145:baseline", "HumanEval/145:marginal"]

    protocol = json.loads(config.protocol_path.read_text(encoding="utf-8"))
    protocol["experiment"] = "changed-protocol"
    config.protocol_path.write_text(json.dumps(protocol) + "\n", encoding="utf-8")
    changed = BenchmarkConfig(
        **{
            **config.as_kwargs(),
            "protocol_sha256": hashlib.sha256(config.protocol_path.read_bytes()).hexdigest(),
        }
    )
    drift = run_benchmark(changed, run_task_fn=fake_run_task)

    assert drift["launched"] == []
    assert drift["hash_mismatch_lanes"] == ["HumanEval/145:off", "HumanEval/145:on"]
    assert drift["complete"] is False
    assert calls == ["HumanEval/145:baseline", "HumanEval/145:marginal"]


def test_protocol_must_bind_the_exact_task_only_input_before_creating_run_root(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, maximum_new_lanes=1)
    protocol = json.loads(config.protocol_path.read_text(encoding="utf-8"))
    protocol["task_inputs_sha256"] = "0" * 64
    config.protocol_path.write_text(json.dumps(protocol) + "\n", encoding="utf-8")
    mismatched = BenchmarkConfig(
        **{
            **config.as_kwargs(),
            "protocol_sha256": hashlib.sha256(config.protocol_path.read_bytes()).hexdigest(),
        }
    )

    with pytest.raises(ValueError, match="task input SHA256"):
        run_benchmark(mismatched)

    assert not config.run_root.exists()


def test_partial_lane_is_retained_diagnosed_and_blocks_new_launches(tmp_path: Path) -> None:
    config = _config(tmp_path, maximum_new_lanes=2)
    partial = config.run_root / "lanes" / "HumanEval_145" / "off"
    partial.mkdir(parents=True)
    marker = partial / "keep-me"
    marker.write_text("partial\n", encoding="utf-8")

    def unexpected_run(_: RunConfig) -> dict[str, object]:
        raise AssertionError("a partial run root must block new launches")

    summary = run_benchmark(config, run_task_fn=unexpected_run)

    assert summary["partial_lanes"] == ["HumanEval/145:off"]
    assert summary["launched"] == []
    assert summary["complete"] is False
    assert marker.read_text(encoding="utf-8") == "partial\n"


def test_recorded_lane_with_missing_usage_remains_truthfully_incomplete(tmp_path: Path) -> None:
    config = _config(tmp_path, maximum_new_lanes=1)

    def missing_usage(run_config: RunConfig) -> dict[str, object]:
        source = (run_config.worktree / "solution.py").read_text(encoding="utf-8")
        (run_config.worktree / "solution.py").write_text(
            source.replace("    pass\n", "    return None\n"), encoding="utf-8"
        )
        return _record(run_config, tokens=None)

    summary = run_benchmark(config, run_task_fn=missing_usage)

    assert summary["recorded_lanes"] == 1
    assert summary["missing_telemetry_lanes"] == ["HumanEval/145:off"]
    assert summary["complete"] is False


def test_failure_stops_queued_lanes_and_blocks_new_work_on_resume(tmp_path: Path) -> None:
    config = _config(tmp_path, maximum_new_lanes=5)
    calls: list[str] = []

    def missing_usage(run_config: RunConfig) -> dict[str, object]:
        calls.append(f"{run_config.instance_id}:{run_config.condition}")
        return _record(run_config, tokens=None)

    first = run_benchmark(config, run_task_fn=missing_usage)

    assert first["launched"] == ["HumanEval/145:off", "HumanEval/145:on"]
    assert len(calls) == config.lane_concurrency
    assert first["stop_rule_lanes"] == ["HumanEval/145:off", "HumanEval/145:on"]

    def unexpected_run(_: RunConfig) -> dict[str, object]:
        raise AssertionError("failed resumed lanes must block new work")

    resumed = run_benchmark(config, run_task_fn=unexpected_run)

    assert resumed["launched"] == []
    assert resumed["stop_rule_lanes"] == ["HumanEval/145:off", "HumanEval/145:on"]


def test_recorded_hook_failure_is_not_misreported_as_missing_usage(tmp_path: Path) -> None:
    config = _config(tmp_path, maximum_new_lanes=1)

    def hook_failure(run_config: RunConfig) -> dict[str, object]:
        source = (run_config.worktree / "solution.py").read_text(encoding="utf-8")
        (run_config.worktree / "solution.py").write_text(
            source.replace("    pass\n", "    return None\n"), encoding="utf-8"
        )
        record = _record(run_config)
        record["run_status"] = "integration_failed"
        record["error_code"] = "HOOK_FAILURE"
        return record

    summary = run_benchmark(config, run_task_fn=hook_failure)

    assert summary["failed_lanes"] == ["HumanEval/145:off"]
    assert summary["missing_telemetry_lanes"] == []
    assert summary["complete"] is False
