from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from benchmark.codex_adapter.container_runner import (
    ContainerTaskConfig,
    ContainerTaskError,
    run_container_task,
)

_BASE = "04a523fafbd61bc2e49420963b84ed8e2bd1b3cf"
_TASK = "swebench/task@sha256:" + "a" * 64
_OVERLAY = "sha256:" + "b" * 64
_SOURCE = "c" * 40


def _config(tmp_path: Path, condition: str) -> ContainerTaskConfig:
    auth = tmp_path / "auth.json"
    auth.write_text('{"tokens":{"access_token":"fixture-secret-marker-123456"}}\n')
    auth.chmod(0o600)
    source = tmp_path / "source"
    source.mkdir()
    return ContainerTaskConfig(
        instance_id="pvlib__pvlib-python-1072",
        condition=condition,
        repetition=1,
        expected_base_commit=_BASE,
        task_image=_TASK,
        overlay_image=_OVERLAY,
        run_dir=tmp_path / f"run-{condition}",
        source_root=source,
        auth_source=auth,
        prompt="Fix the issue.\n",
        source_commit=_SOURCE,
        timeout_seconds=30,
    )


def _events(tool_calls: int = 1) -> str:
    rows: list[dict[str, object]] = [
        {"type": "thread.started", "thread_id": "thread-1"},
        {"type": "turn.started"},
    ]
    for index in range(tool_calls):
        rows.append(
            {
                "type": "item.completed",
                "item": {
                    "id": f"exec-{index}",
                    "type": "command_execution",
                    "command": f"rg pattern-{index}",
                    "status": "completed",
                    "exit_code": 0,
                },
            }
        )
    rows.append(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 40,
                "output_tokens": 20,
                "reasoning_output_tokens": 5,
            },
        }
    )
    return "".join(json.dumps(row) + "\n" for row in rows)


def _executor(
    *,
    committed: int = 1,
    approved: int = 1,
    denied: int = 0,
    overlay_source: str = _SOURCE,
):
    def execute(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        if command[:2] == ["docker", "info"]:
            return subprocess.CompletedProcess(command, 0, stdout="x86_64\n")
        if command[:3] == ["docker", "image", "inspect"]:
            image = command[3]
            if image == _OVERLAY:
                payload = [
                    {
                        "Id": _OVERLAY,
                        "Architecture": "amd64",
                        "RepoDigests": [],
                        "Config": {
                            "Labels": {
                                "org.marginal.codex.version": "0.147.0",
                                "org.marginal.source.commit": overlay_source,
                                "org.marginal.task.image": _TASK,
                            }
                        },
                    }
                ]
            else:
                payload = [
                    {
                        "Id": "sha256:" + "d" * 64,
                        "Architecture": "amd64",
                        "RepoDigests": [_TASK],
                        "Config": {"Labels": {}},
                    }
                ]
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload))
        run_mount = command[command.index("--mount") + 1]
        run_dir = Path(run_mount.split("src=", 1)[1].split(",dst=", 1)[0])
        condition = next(
            item.split("=", 1)[1] for item in command if item.startswith("MARGINAL_CONDITION=")
        )
        (run_dir / "codex-events.jsonl").write_text(_events(committed))
        (run_dir / "codex-stderr.log").write_text("")
        (run_dir / "model.patch").write_text("diff --git a/a.py b/a.py\n")
        (run_dir / "model.numstat").write_text("1\t0\ta.py\n")
        (run_dir / "worktree.status").write_text(" M a.py\n")
        (run_dir / "container-status.json").write_text(
            json.dumps(
                {
                    "codex_exit_code": 0,
                    "condition": condition,
                    "instance_id": "pvlib__pvlib-python-1072",
                }
            )
            + "\n"
        )
        if condition == "marginal":
            (run_dir / "daemon-summary.json").write_text(
                json.dumps(
                    {
                        "approved": approved,
                        "committed": committed,
                        "denied": denied,
                        "aborted": 0,
                        "failed_settled": 0,
                        "pending": 0,
                        "governance": {
                            "decisions": approved + denied,
                            "external_tokens": 0,
                            "external_usd": 0.0,
                            "total_latency_ms": 3.5,
                        },
                        "interventions": {
                            "recommended_denies": denied,
                            "applied_denies": denied,
                            "reviewed": 0,
                            "false_stops": 0,
                        },
                    }
                )
                + "\n"
            )
            (run_dir / "treasury-events.jsonl").write_text("{}\n")
        return subprocess.CompletedProcess(command, 0)

    return execute


@pytest.mark.parametrize("condition", ["baseline", "marginal"])
def test_container_runner_accepts_only_attested_completed_runs(
    tmp_path: Path, condition: str
) -> None:
    record = run_container_task(_config(tmp_path, condition), executor=_executor())

    assert record["run_status"] == "completed"
    assert record["condition"] == condition
    assert record["tokens"]["total"] == 120
    assert record["tool_calls"] == 1
    assert len(record["configuration_sha256"]) == 64
    assert len(record["patch_sha256"]) == 64


def test_container_runner_rejects_partial_hook_coverage(tmp_path: Path) -> None:
    with pytest.raises(ContainerTaskError, match="hook coverage"):
        run_container_task(
            _config(tmp_path, "marginal"),
            executor=_executor(committed=1, approved=2),
        )


def test_container_runner_rejects_auth_material_in_raw_outputs(tmp_path: Path) -> None:
    config = _config(tmp_path, "baseline")

    def leaking_executor(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        result = _executor()(command, **kwargs)
        if command[:2] == ["docker", "run"]:
            (config.run_dir / "codex-stderr.log").write_text("fixture-secret-marker-123456\n")
        return result

    with pytest.raises(ContainerTaskError, match="authentication material"):
        run_container_task(config, executor=leaking_executor)


def test_container_runner_rejects_overlay_from_wrong_source_commit(tmp_path: Path) -> None:
    with pytest.raises(ContainerTaskError, match="source commit"):
        run_container_task(
            _config(tmp_path, "baseline"),
            executor=_executor(overlay_source="d" * 40),
        )
