from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest
from benchmark.codex_adapter.runner import RunConfig, run_task
from jsonschema import Draft202012Validator


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _worktree(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "benchmark@example.invalid")
    _git(repo, "config", "user.name", "Benchmark")
    (repo / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "source.py")
    _git(repo, "commit", "-qm", "fixture")
    _git(repo, "checkout", "--detach", "-q", "HEAD")
    return repo


def _fake_codex(tmp_path: Path) -> Path:
    executable = tmp_path / "fake-codex"
    executable.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            from pathlib import Path
            import sys
            import time

            prompt = sys.stdin.read()
            log = {
                "args": sys.argv[1:],
                "prompt": prompt,
                "has_hooks": Path(".codex/hooks.json").is_file(),
                "has_socket_env": "MARGINAL_SOCKET" in os.environ,
                "home": os.environ.get("HOME"),
                "codex_home": os.environ.get("CODEX_HOME"),
            }
            Path(os.environ["FAKE_CODEX_LOG"]).write_text(json.dumps(log), encoding="utf-8")
            if os.environ.get("FAKE_HOOK_FAILURE") == "1":
                Path(os.environ["MARGINAL_HOOK_FAILURE_LOG"]).write_text(
                    "hook failed\\n", encoding="utf-8"
                )
            if os.environ.get("FAKE_LEAK_AUTH") == "1":
                Path("leak.txt").write_text(
                    (Path(os.environ["CODEX_HOME"]) / "auth.json").read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            sleep_seconds = float(os.environ.get("FAKE_SLEEP", "0"))
            if sleep_seconds:
                time.sleep(sleep_seconds)
            Path("solution.py").write_text("FIXED = True\\n", encoding="utf-8")
            print(json.dumps({"type": "thread.started", "thread_id": "fake-thread"}))
            print(json.dumps({"type": "turn.started"}))
            if os.environ.get("FAKE_TOOL_EVENT") == "1":
                print(json.dumps({
                    "type": "item.completed",
                    "item": {
                        "id": "item-1",
                        "type": "command_execution",
                        "command": "git status --short",
                        "aggregated_output": "",
                        "exit_code": 0,
                        "status": "completed",
                    },
                }))
            print(json.dumps({
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 2,
                    "output_tokens": 5,
                    "reasoning_output_tokens": 1,
                },
            }))
            raise SystemExit(int(os.environ.get("FAKE_EXIT", "0")))
            """
        ),
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _config(
    tmp_path: Path,
    *,
    condition: str,
    extra_env: dict[str, str] | None = None,
    timeout_seconds: float = 5,
    auth_content: str = "{}\n",
) -> RunConfig:
    worktree = _worktree(tmp_path, f"worktree-{condition}")
    auth = tmp_path / "auth.json"
    auth.write_text(auth_content, encoding="utf-8")
    auth.chmod(0o600)
    return RunConfig(
        instance_id="owner__repo-1",
        condition=condition,
        repetition=1,
        worktree=worktree,
        expected_base_commit=_git(worktree, "rev-parse", "HEAD"),
        run_dir=tmp_path / f"run-{condition}",
        prompt="Fix the issue.",
        codex_executable=_fake_codex(tmp_path),
        auth_source=auth,
        model="fake-model",
        reasoning_effort="high",
        timeout_seconds=timeout_seconds,
        extra_env=extra_env or {},
    )


@pytest.mark.parametrize("contamination", ["dirty", "wrong-commit", "attached-head"])
def test_run_rejects_nonidentical_starting_checkout(tmp_path: Path, contamination: str) -> None:
    config = _config(tmp_path, condition="baseline")
    if contamination == "dirty":
        (config.worktree / "source.py").write_text("VALUE = 2\n", encoding="utf-8")
    elif contamination == "wrong-commit":
        object.__setattr__(config, "expected_base_commit", "0" * 40)
    else:
        _git(config.worktree, "switch", "-q", "-c", "benchmark-attached")

    with pytest.raises(ValueError, match="checkout"):
        run_task(config)

    assert not config.run_dir.exists()


def test_off_has_no_marginal_process_hook_state_or_environment(tmp_path: Path) -> None:
    log = tmp_path / "baseline-log.json"
    config = _config(tmp_path, condition="baseline", extra_env={"FAKE_CODEX_LOG": str(log)})

    record = run_task(config)
    observed = json.loads(log.read_text(encoding="utf-8"))

    assert record["run_status"] == "completed"
    assert record["tokens"]["total"] == 15
    assert record["governance"] == {"tokens": 0, "usd": 0.0, "latency_ms": 0.0}
    assert record["interventions"]["applied_denies"] == 0
    assert observed["has_hooks"] is False
    assert observed["has_socket_env"] is False
    assert observed["home"] != os.environ.get("HOME")
    assert observed["codex_home"] != observed["home"]
    assert 'shell_environment_policy.inherit="none"' in observed["args"]
    assert not (config.worktree / ".codex").exists()
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "benchmark/schemas/run-record-v1.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(record)


def test_on_starts_daemon_and_loads_only_generated_project_hooks(tmp_path: Path) -> None:
    log = tmp_path / "marginal-log.json"
    config = _config(tmp_path, condition="marginal", extra_env={"FAKE_CODEX_LOG": str(log)})

    record = run_task(config)
    observed = json.loads(log.read_text(encoding="utf-8"))

    assert record["run_status"] == "completed"
    assert observed["has_hooks"] is True
    assert observed["has_socket_env"] is True
    assert (config.worktree / ".codex" / "hooks.json").is_file()
    assert record["governance"]["tokens"] == 0
    assert record["files_modified"] == 1
    assert ".codex" not in (config.run_dir / "model.patch").read_text(encoding="utf-8")


def test_on_fails_if_codex_reports_tool_use_without_hook_coverage(tmp_path: Path) -> None:
    log = tmp_path / "marginal-log.json"
    config = _config(
        tmp_path,
        condition="marginal",
        extra_env={"FAKE_CODEX_LOG": str(log), "FAKE_TOOL_EVENT": "1"},
    )

    record = run_task(config)

    assert record["tool_calls"] == 1
    assert record["run_status"] == "integration_failed"
    assert record["error_code"] == "HOOK_COVERAGE_MISSING"


def test_run_rejects_runtime_directory_inside_checkout(tmp_path: Path) -> None:
    config = _config(tmp_path, condition="baseline")
    object.__setattr__(config, "run_dir", config.worktree / "benchmark-output")

    with pytest.raises(ValueError, match="run directory"):
        run_task(config)


def test_auth_material_is_never_written_to_model_patch(tmp_path: Path) -> None:
    sentinel = "benchmark-secret-value-123456"
    config = _config(
        tmp_path,
        condition="baseline",
        extra_env={"FAKE_CODEX_LOG": str(tmp_path / "leak-log.json"), "FAKE_LEAK_AUTH": "1"},
        auth_content=json.dumps({"tokens": {"access_token": sentinel}}),
    )

    record = run_task(config)

    assert record["run_status"] == "security_failed"
    assert record["error_code"] == "AUTH_MATERIAL_EXFILTRATED"
    assert sentinel not in (config.run_dir / "model.patch").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("extra_env", "timeout_seconds", "expected_status", "expected_code"),
    [
        ({"FAKE_SLEEP": "2"}, 0.05, "timeout", "CODEX_TIMEOUT"),
        ({"FAKE_EXIT": "7"}, 5, "codex_failed", "CODEX_EXIT_7"),
        ({"FAKE_HOOK_FAILURE": "1"}, 5, "integration_failed", "HOOK_FAILURE"),
    ],
)
def test_failures_remain_explicit_rows(
    tmp_path: Path,
    extra_env: dict[str, str],
    timeout_seconds: float,
    expected_status: str,
    expected_code: str,
) -> None:
    log = tmp_path / "failure-log.json"
    config = _config(
        tmp_path,
        condition="marginal",
        extra_env={**extra_env, "FAKE_CODEX_LOG": str(log)},
        timeout_seconds=timeout_seconds,
    )

    record = run_task(config)

    assert record["run_status"] == expected_status
    assert record["error_code"] == expected_code
    assert record["resolved"] is None
    assert len(record["patch_sha256"]) == 64
