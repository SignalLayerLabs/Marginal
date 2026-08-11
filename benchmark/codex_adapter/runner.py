"""Hermetic single-task runner for matched Codex OFF/ON conditions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .codex_events import CodexMetrics, EventParseError, parse_codex_jsonl
from .hook_config import install_project_hooks

_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_HOOK_CLIENT = Path(__file__).resolve().with_name("hook_client.py")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_FEATURES_DISABLED = (
    "apps",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "computer_use",
    "goals",
    "image_generation",
    "in_app_browser",
    "multi_agent",
    "multi_agent_v2",
    "plugins",
    "search_tool",
    "skill_search",
    "standalone_web_search",
    "tool_suggest",
    "web_search_request",
    "workspace_dependencies",
)


@dataclass(frozen=True, slots=True)
class RunConfig:
    instance_id: str
    condition: str
    repetition: int
    worktree: Path
    expected_base_commit: str
    run_dir: Path
    prompt: str
    codex_executable: Path
    auth_source: Path
    model: str = "gpt-5.6-sol"
    reasoning_effort: str = "high"
    timeout_seconds: float = 1800
    codex_version: str = "0.147.0"
    extra_env: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.condition not in {"baseline", "marginal"}:
            raise ValueError("condition must be baseline or marginal")
        if self.repetition < 1:
            raise ValueError("repetition must be positive")
        if _COMMIT_SHA.fullmatch(self.expected_base_commit) is None:
            raise ValueError("expected_base_commit must be a lowercase 40-character SHA")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


def _safe_environment(config: RunConfig, codex_home: Path, runtime_home: Path) -> dict[str, str]:
    retained = ("LANG", "LC_ALL", "LOGNAME", "PATH", "SHELL", "TMPDIR", "USER")
    environment = {key: os.environ[key] for key in retained if key in os.environ}
    environment.update(config.extra_env)
    environment.update(
        {
            "CODEX_HOME": str(codex_home),
            "HOME": str(runtime_home),
            "CLICOLOR": "0",
            "TERM": "dumb",
        }
    )
    return environment


def _toml_inline_table(values: Mapping[str, str]) -> str:
    fields = ",".join(f"{key}={json.dumps(value)}" for key, value in sorted(values.items()))
    return "{" + fields + "}"


def _command(config: RunConfig, shell_environment: Mapping[str, str]) -> list[str]:
    command = [
        str(config.codex_executable),
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--json",
        "--color",
        "never",
        "--strict-config",
        "--dangerously-bypass-hook-trust",
        "-m",
        config.model,
        "-c",
        f'model_reasoning_effort="{config.reasoning_effort}"',
        "-c",
        "sandbox_workspace_write.network_access=false",
        "-c",
        'shell_environment_policy.inherit="none"',
        "-c",
        "shell_environment_policy.ignore_default_excludes=false",
        "-c",
        f"shell_environment_policy.set={_toml_inline_table(shell_environment)}",
        "-s",
        "workspace-write",
        "-a",
        "never",
        "-C",
        str(config.worktree),
    ]
    for feature in _FEATURES_DISABLED:
        command.extend(("--disable", feature))
    command.append("-")
    return command


def _daemon_request(socket_path: Path, operation: str) -> dict[str, Any]:
    request = json.dumps({"operation": operation, "payload": {}}).encode("utf-8") + b"\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(1)
        client.connect(str(socket_path))
        client.sendall(request)
        raw = client.makefile("rb").readline(16 * 1024 * 1024)
    response = json.loads(raw)
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise RuntimeError(f"daemon request failed: {response!r}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("daemon response has no object result")
    return result


def _wait_for_daemon(process: subprocess.Popen[bytes], socket_path: Path) -> None:
    deadline = time.monotonic() + 10
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"MARGINAL daemon exited with {process.returncode}")
        if socket_path.exists():
            try:
                if _daemon_request(socket_path, "health").get("status") == "ready":
                    return
            except (OSError, RuntimeError, json.JSONDecodeError) as exc:
                last_error = exc
        time.sleep(0.02)
    raise RuntimeError(f"MARGINAL daemon did not become ready: {last_error}")


def _git(worktree: Path, *args: str, allowed_codes: tuple[int, ...] = (0,)) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=worktree,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if completed.returncode not in allowed_codes:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def _instrumentation_path(relative: str) -> bool:
    return ".codex" in PurePosixPath(relative).parts


def _validate_starting_checkout(config: RunConfig, worktree: Path) -> None:
    try:
        head = _git(worktree, "rev-parse", "HEAD").decode("ascii").strip()
        head_name = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD").decode("ascii").strip()
        status = _git(worktree, "status", "--porcelain", "--untracked-files=all")
    except (UnicodeDecodeError, RuntimeError) as exc:
        raise ValueError(f"task checkout validation failed: {exc}") from exc
    if head != config.expected_base_commit:
        raise ValueError(
            f"task checkout commit mismatch: expected {config.expected_base_commit}, got {head}"
        )
    if head_name != "HEAD":
        raise ValueError("task checkout must have a detached HEAD")
    if status:
        raise ValueError("task checkout must be clean before the run")


def _untracked(worktree: Path) -> list[str]:
    output = _git(worktree, "ls-files", "--others", "--exclude-standard", "-z")
    paths = output.decode("utf-8", errors="surrogateescape").split("\0")
    return sorted(path for path in paths if path and not _instrumentation_path(path))


def _changed_paths(worktree: Path) -> list[str]:
    tracked = _git(worktree, "diff", "--name-only", "-z", "HEAD", "--", ".")
    decoded = tracked.decode("utf-8", errors="surrogateescape").split("\0")
    return sorted(
        {
            path
            for path in (*decoded, *_untracked(worktree))
            if path and not _instrumentation_path(path)
        }
    )


def _auth_markers(auth_source: Path) -> tuple[bytes, ...]:
    raw = auth_source.read_bytes()
    markers: set[bytes] = {raw.strip()} if len(raw.strip()) >= 16 else set()
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        decoded = None

    def collect(value: object) -> None:
        if isinstance(value, str) and len(value.encode("utf-8")) >= 16:
            markers.add(value.encode("utf-8"))
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(decoded)
    return tuple(markers)


def _auth_material_exposed(worktree: Path, patch: bytes, auth_source: Path) -> bool:
    markers = _auth_markers(auth_source)
    if not markers:
        return False
    if any(marker in patch for marker in markers):
        return True
    for relative in _changed_paths(worktree):
        candidate = (worktree / relative).resolve()
        if not candidate.is_relative_to(worktree) or not candidate.is_file():
            continue
        try:
            content = candidate.read_bytes()
        except OSError:
            continue
        if any(marker in content for marker in markers):
            return True
    return False


def _patch_and_stats(worktree: Path) -> tuple[bytes, int, int | None]:
    patch_parts = [_git(worktree, "diff", "--binary", "HEAD", "--", ".", ":(exclude).codex")]
    numstat_parts = [_git(worktree, "diff", "--numstat", "HEAD", "--", ".", ":(exclude).codex")]
    for relative in _untracked(worktree):
        patch_parts.append(
            _git(
                worktree,
                "diff",
                "--binary",
                "--no-index",
                "--",
                "/dev/null",
                relative,
                allowed_codes=(0, 1),
            )
        )
        numstat_parts.append(
            _git(
                worktree,
                "diff",
                "--numstat",
                "--no-index",
                "--",
                "/dev/null",
                relative,
                allowed_codes=(0, 1),
            )
        )
    patch = b"".join(patch_parts)
    files: set[str] = set()
    diff_lines = 0
    binary = False
    for raw_line in b"".join(numstat_parts).splitlines():
        fields = raw_line.split(b"\t", maxsplit=2)
        if len(fields) != 3:
            continue
        added, deleted, path = fields
        files.add(path.decode("utf-8", errors="replace"))
        if added == b"-" or deleted == b"-":
            binary = True
        else:
            diff_lines += int(added) + int(deleted)
    return patch, len(files), None if binary else diff_lines


def _empty_metrics() -> CodexMetrics:
    return CodexMetrics(None, False, None, 0, 0, 0, 0, 0, 0, ())


def _configuration_hash(config: RunConfig) -> str:
    payload = {
        "schema_version": 1,
        "instance_id": config.instance_id,
        "base_commit": config.expected_base_commit,
        "condition": config.condition,
        "repetition": config.repetition,
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "codex_version": config.codex_version,
        "sandbox": "workspace-write",
        "network_access": False,
        "timeout_seconds": config.timeout_seconds,
        "prompt_sha256": hashlib.sha256(config.prompt.encode("utf-8")).hexdigest(),
        "disabled_features": _FEATURES_DISABLED,
        "marginal": (
            "absent" if config.condition == "baseline" else "balanced+diminishing-defaults+enforce"
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_task(config: RunConfig) -> dict[str, Any]:
    """Run one already-materialized task and write local raw evidence plus one record."""

    worktree = config.worktree.resolve()
    run_dir = config.run_dir.resolve()
    if not worktree.is_dir():
        raise ValueError(f"worktree does not exist: {worktree}")
    if run_dir.is_relative_to(worktree):
        raise ValueError("run directory must be outside the task checkout")
    if not config.codex_executable.is_file():
        raise ValueError(f"Codex executable does not exist: {config.codex_executable}")
    if not config.auth_source.is_file():
        raise ValueError(f"Codex auth source does not exist: {config.auth_source}")
    if (worktree / ".codex" / "hooks.json").exists():
        raise ValueError("task checkout already contains .codex/hooks.json")
    _validate_starting_checkout(config, worktree)
    run_dir.mkdir(parents=True, exist_ok=False)

    events_path = run_dir / "codex-events.jsonl"
    stderr_path = run_dir / "codex-stderr.log"
    model_patch_path = run_dir / "model.patch"
    hook_failure_path = run_dir / "hook-failures.log"
    daemon_events_path = run_dir / "marginal-events.jsonl"
    daemon_summary_path = run_dir / "marginal-summary.json"
    daemon_stdout_path = run_dir / "marginal-daemon.stdout.log"
    daemon_stderr_path = run_dir / "marginal-daemon.stderr.log"

    timed_out = False
    exit_code: int | None = None
    infrastructure_error: str | None = None
    daemon_summary: dict[str, Any] | None = None
    started = time.perf_counter_ns()

    with (
        tempfile.TemporaryDirectory(prefix="codex-home-") as codex_home_value,
        tempfile.TemporaryDirectory(prefix="task-home-") as runtime_home_value,
        tempfile.TemporaryDirectory(prefix="mg-", dir="/tmp") as socket_dir_value,
    ):
        codex_home = Path(codex_home_value)
        auth_target = codex_home / "auth.json"
        shutil.copyfile(config.auth_source, auth_target)
        auth_target.chmod(0o600)
        runtime_home = Path(runtime_home_value)
        environment = _safe_environment(config, codex_home, runtime_home)
        shell_environment: dict[str, str] = {
            key: environment[key]
            for key in ("HOME", "LANG", "LC_ALL", "LOGNAME", "PATH", "SHELL", "TMPDIR", "USER")
            if key in environment
        }
        daemon: subprocess.Popen[bytes] | None = None
        socket_path = Path(socket_dir_value) / "m.sock"

        try:
            if config.condition == "marginal":
                install_project_hooks(
                    worktree,
                    python_executable=Path(sys.executable),
                    hook_client=_HOOK_CLIENT,
                )
                environment["MARGINAL_SOCKET"] = str(socket_path)
                environment["MARGINAL_HOOK_FAILURE_LOG"] = str(hook_failure_path)
                daemon_environment = dict(environment)
                daemon_environment["PYTHONPATH"] = str(_SOURCE_ROOT)
                with (
                    daemon_stdout_path.open("wb") as daemon_stdout,
                    daemon_stderr_path.open("wb") as daemon_stderr,
                ):
                    daemon = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "benchmark.codex_adapter.daemon",
                            "--socket",
                            str(socket_path),
                            "--events",
                            str(daemon_events_path),
                            "--summary",
                            str(daemon_summary_path),
                        ],
                        cwd=_SOURCE_ROOT,
                        env=daemon_environment,
                        stdout=daemon_stdout,
                        stderr=daemon_stderr,
                    )
                    _wait_for_daemon(daemon, socket_path)

                    with events_path.open("wb") as events, stderr_path.open("wb") as stderr:
                        process = subprocess.Popen(
                            _command(config, shell_environment),
                            cwd=worktree,
                            env=environment,
                            stdin=subprocess.PIPE,
                            stdout=events,
                            stderr=stderr,
                        )
                        try:
                            process.communicate(
                                config.prompt.encode("utf-8"), timeout=config.timeout_seconds
                            )
                        except subprocess.TimeoutExpired:
                            timed_out = True
                            process.terminate()
                            try:
                                process.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=10)
                        exit_code = process.returncode
            else:
                with events_path.open("wb") as events, stderr_path.open("wb") as stderr:
                    process = subprocess.Popen(
                        _command(config, shell_environment),
                        cwd=worktree,
                        env=environment,
                        stdin=subprocess.PIPE,
                        stdout=events,
                        stderr=stderr,
                    )
                    try:
                        process.communicate(
                            config.prompt.encode("utf-8"), timeout=config.timeout_seconds
                        )
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=10)
                    exit_code = process.returncode
        except Exception as exc:
            infrastructure_error = f"{type(exc).__name__}: {exc}"
        finally:
            if daemon is not None:
                if daemon.poll() is None:
                    daemon.terminate()
                try:
                    daemon.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    daemon.kill()
                    daemon.wait(timeout=5)
                if daemon_summary_path.is_file():
                    try:
                        loaded = json.loads(daemon_summary_path.read_text(encoding="utf-8"))
                        if isinstance(loaded, dict):
                            daemon_summary = loaded
                    except json.JSONDecodeError:
                        infrastructure_error = infrastructure_error or "invalid daemon summary"
                else:
                    infrastructure_error = infrastructure_error or "missing daemon summary"

    wall_time_ms = max(0, round((time.perf_counter_ns() - started) / 1_000_000))
    try:
        metrics = parse_codex_jsonl(events_path)
    except (OSError, EventParseError) as exc:
        metrics = _empty_metrics()
        infrastructure_error = infrastructure_error or f"event parse failed: {exc}"

    try:
        patch, files_modified, diff_lines = _patch_and_stats(worktree)
    except Exception as exc:
        patch, files_modified, diff_lines = b"", 0, None
        infrastructure_error = infrastructure_error or f"patch extraction failed: {exc}"
    security_violation = _auth_material_exposed(worktree, patch, config.auth_source)
    if security_violation:
        patch = b""
        infrastructure_error = infrastructure_error or "authentication material exposure blocked"
    model_patch_path.write_bytes(patch)

    run_status = "completed"
    error_code: str | None = None
    hook_coverage_missing = bool(
        config.condition == "marginal"
        and daemon_summary is not None
        and int(daemon_summary.get("committed", 0)) != metrics.tool_calls
    )
    if security_violation:
        run_status = "security_failed"
        error_code = "AUTH_MATERIAL_EXFILTRATED"
    elif config.condition == "marginal" and (
        infrastructure_error is not None
        or hook_failure_path.exists()
        or daemon_summary is None
        or daemon_summary.get("pending") != 0
        or hook_coverage_missing
    ):
        run_status = "integration_failed"
        if hook_failure_path.exists():
            error_code = "HOOK_FAILURE"
        elif hook_coverage_missing:
            error_code = "HOOK_COVERAGE_MISSING"
        elif daemon_summary is not None and daemon_summary.get("pending") != 0:
            error_code = "ORPHANED_RESERVATION"
        else:
            error_code = "MARGINAL_INFRASTRUCTURE"
    elif infrastructure_error is not None:
        run_status = "codex_failed"
        error_code = "RUNNER_INFRASTRUCTURE"
    elif timed_out:
        run_status = "timeout"
        error_code = "CODEX_TIMEOUT"
    elif exit_code != 0:
        run_status = "codex_failed"
        error_code = f"CODEX_EXIT_{exit_code}"
    elif not metrics.completed or metrics.tokens is None:
        run_status = "codex_failed"
        error_code = "TOKEN_TELEMETRY_MISSING"
    elif metrics.errors:
        run_status = "codex_failed"
        error_code = "CODEX_STREAM_ERROR"

    if daemon_summary is None:
        interventions = {
            "recommended_denies": 0,
            "applied_denies": 0,
            "reviewed": 0,
            "false_stops": 0,
        }
        governance = {"tokens": 0, "usd": 0.0, "latency_ms": 0.0}
    else:
        raw_interventions = daemon_summary.get("interventions", {})
        raw_governance = daemon_summary.get("governance", {})
        interventions = {
            "recommended_denies": int(raw_interventions.get("recommended_denies", 0)),
            "applied_denies": int(raw_interventions.get("applied_denies", 0)),
            "reviewed": int(raw_interventions.get("reviewed", 0)),
            "false_stops": int(raw_interventions.get("false_stops", 0)),
        }
        governance = {
            "tokens": int(raw_governance.get("external_tokens", 0)),
            "usd": float(raw_governance.get("external_usd", 0.0)),
            "latency_ms": float(raw_governance.get("total_latency_ms", 0.0)),
        }

    tokens: dict[str, int | None]
    if metrics.tokens is None:
        tokens = {
            "input": None,
            "cached_input": None,
            "output": None,
            "reasoning": None,
            "total": None,
        }
    else:
        tokens = {key: value for key, value in metrics.tokens.items()}
    record: dict[str, Any] = {
        "schema_version": 1,
        "instance_id": config.instance_id,
        "condition": config.condition,
        "repetition": config.repetition,
        "run_status": run_status,
        "resolved": None,
        "configuration_sha256": _configuration_hash(config),
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "tokens": tokens,
        "wall_time_ms": wall_time_ms,
        "tool_calls": metrics.tool_calls,
        "shell_commands": metrics.shell_commands,
        "file_operations": metrics.file_operations,
        "searches": metrics.searches,
        "test_executions": metrics.test_executions,
        "repeated_calls": metrics.repeated_calls,
        "files_modified": files_modified,
        "diff_lines": diff_lines,
        "model_reroutes": None,
        "interventions": interventions,
        "governance": governance,
        "error_code": error_code,
    }
    if infrastructure_error is not None:
        (run_dir / "runner-error.txt").write_text(infrastructure_error + "\n", encoding="utf-8")
    (run_dir / "run-record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record
