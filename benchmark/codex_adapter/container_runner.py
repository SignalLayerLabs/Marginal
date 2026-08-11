"""Run one Codex lane in a pinned SWE-bench container and attest its evidence."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .codex_events import EventParseError, parse_codex_jsonl
from .container_runtime import ContainerRunConfig, build_container_command


class ContainerTaskError(RuntimeError):
    """Raised when a run cannot satisfy the frozen integrity contract."""


@dataclass(frozen=True, slots=True)
class ContainerTaskConfig:
    instance_id: str
    condition: str
    repetition: int
    expected_base_commit: str
    task_image: str
    overlay_image: str
    run_dir: Path
    source_root: Path
    auth_source: Path
    prompt: str
    source_commit: str
    model: str = "gpt-5.6-sol"
    reasoning_effort: str = "high"
    codex_version: str = "0.147.0"
    timeout_seconds: int = 1800

    def __post_init__(self) -> None:
        if self.repetition < 1:
            raise ValueError("repetition must be positive")
        if not self.prompt.strip():
            raise ValueError("prompt must not be empty")
        if re.fullmatch(r"[0-9a-f]{40}", self.source_commit) is None:
            raise ValueError("source_commit must be a lowercase 40-character SHA")


Executor = Callable[..., subprocess.CompletedProcess[Any]]


def _stdout_text(completed: subprocess.CompletedProcess[Any]) -> str:
    output = completed.stdout
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return str(output or "")


def _inspect_runtime(config: ContainerTaskConfig, executor: Executor) -> None:
    try:
        info = executor(
            ["docker", "info", "--format", "{{.Architecture}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContainerTaskError(f"container engine inspection failed: {exc}") from exc
    if info.returncode != 0 or _stdout_text(info).strip() != "x86_64":
        raise ContainerTaskError("container engine must expose an x86_64 Docker runtime")

    inspected: dict[str, dict[str, Any]] = {}
    for role, image in (("task", config.task_image), ("overlay", config.overlay_image)):
        completed = executor(
            ["docker", "image", "inspect", image],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        try:
            values = json.loads(_stdout_text(completed))
        except json.JSONDecodeError as exc:
            raise ContainerTaskError(f"{role} image inspection returned invalid JSON") from exc
        if completed.returncode != 0 or not isinstance(values, list) or len(values) != 1:
            raise ContainerTaskError(f"{role} image is unavailable or ambiguous")
        value = values[0]
        if not isinstance(value, dict) or value.get("Architecture") != "amd64":
            raise ContainerTaskError(f"{role} image architecture is not amd64")
        inspected[role] = value

    task_digests = inspected["task"].get("RepoDigests")
    if not isinstance(task_digests, list) or config.task_image not in task_digests:
        raise ContainerTaskError("task image digest provenance mismatch")
    overlay = inspected["overlay"]
    overlay_identity = overlay.get("Id")
    overlay_digests = overlay.get("RepoDigests")
    if config.overlay_image != overlay_identity and (
        not isinstance(overlay_digests, list) or config.overlay_image not in overlay_digests
    ):
        raise ContainerTaskError("overlay image digest provenance mismatch")
    config_value = overlay.get("Config")
    labels = config_value.get("Labels") if isinstance(config_value, dict) else None
    if not isinstance(labels, dict):
        raise ContainerTaskError("overlay image has no provenance labels")
    if labels.get("org.marginal.codex.version") != config.codex_version:
        raise ContainerTaskError("overlay Codex version provenance mismatch")
    if labels.get("org.marginal.source.commit") != config.source_commit:
        raise ContainerTaskError("overlay source commit provenance mismatch")
    if labels.get("org.marginal.task.image") != config.task_image:
        raise ContainerTaskError("overlay task image provenance mismatch")


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContainerTaskError(f"invalid or missing runtime artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise ContainerTaskError(f"runtime artifact must be an object: {path.name}")
    return value


def _secret_markers(path: Path) -> tuple[bytes, ...]:
    raw = path.read_bytes()
    markers: set[bytes] = {raw.strip()} if len(raw.strip()) >= 16 else set()
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        decoded = None

    def collect(value: object) -> None:
        if isinstance(value, str):
            encoded = value.encode("utf-8")
            if len(encoded) >= 16:
                markers.add(encoded)
        elif isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(decoded)
    return tuple(markers)


def _assert_no_auth_material(run_dir: Path, auth_source: Path) -> None:
    markers = _secret_markers(auth_source)
    for artifact in run_dir.iterdir():
        if not artifact.is_file():
            continue
        try:
            content = artifact.read_bytes()
        except OSError:
            continue
        if any(marker in content for marker in markers):
            raise ContainerTaskError(
                f"authentication material detected in runtime artifact: {artifact.name}"
            )


def _patch_stats(path: Path) -> tuple[int, int | None]:
    files: set[str] = set()
    diff_lines = 0
    binary = False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ContainerTaskError("invalid or missing runtime artifact: model.numstat") from exc
    for line in lines:
        fields = line.split("\t", maxsplit=2)
        if len(fields) != 3:
            raise ContainerTaskError("malformed model.numstat")
        added, deleted, filename = fields
        files.add(filename)
        if added == "-" or deleted == "-":
            binary = True
        else:
            try:
                diff_lines += int(added) + int(deleted)
            except ValueError as exc:
                raise ContainerTaskError("malformed model.numstat") from exc
    return len(files), None if binary else diff_lines


def _configuration_hash(config: ContainerTaskConfig) -> str:
    payload = {
        "schema_version": 1,
        "instance_id": config.instance_id,
        "condition": config.condition,
        "repetition": config.repetition,
        "base_commit": config.expected_base_commit,
        "source_commit": config.source_commit,
        "task_image": config.task_image,
        "overlay_image": config.overlay_image,
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "codex_version": config.codex_version,
        "timeout_seconds": config.timeout_seconds,
        "prompt_sha256": hashlib.sha256(config.prompt.encode("utf-8")).hexdigest(),
        "sandbox": "workspace-write",
        "tool_network_access": False,
        "marginal": "absent" if config.condition == "baseline" else "enforce",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _attest_marginal(run_dir: Path, tool_calls: int) -> tuple[dict[str, int], dict[str, Any]]:
    if (run_dir / "hook-failures.log").exists():
        raise ContainerTaskError("hook failure artifact exists")
    summary = _json_object(run_dir / "daemon-summary.json")
    counts = {
        key: int(summary.get(key, -1))
        for key in ("approved", "committed", "denied", "aborted", "failed_settled", "pending")
    }
    governance = summary.get("governance")
    interventions = summary.get("interventions")
    if not isinstance(governance, dict) or not isinstance(interventions, dict):
        raise ContainerTaskError("daemon summary is missing accounting objects")
    decisions = int(governance.get("decisions", -1))
    coverage_ok = (
        counts["pending"] == 0
        and counts["aborted"] == 0
        and counts["failed_settled"] == 0
        and counts["approved"] == counts["committed"]
        and counts["committed"] == tool_calls
        and decisions == counts["approved"] + counts["denied"]
    )
    if not coverage_ok:
        raise ContainerTaskError("MARGINAL hook coverage is incomplete or inconsistent")
    expected_denies = int(interventions.get("applied_denies", -1))
    if expected_denies != counts["denied"]:
        raise ContainerTaskError("MARGINAL denial accounting is inconsistent")
    return counts, {"governance": governance, "interventions": interventions}


def run_container_task(
    config: ContainerTaskConfig,
    *,
    executor: Executor = subprocess.run,
) -> dict[str, Any]:
    """Execute one disposable lane, fail closed, and write a schema-v1 record."""

    _inspect_runtime(config, executor)
    run_dir = config.run_dir.resolve()
    if run_dir.exists():
        raise ContainerTaskError(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    prompt_path = run_dir / "prompt.txt"
    prompt_path.write_text(config.prompt, encoding="utf-8")
    runtime = ContainerRunConfig(
        instance_id=config.instance_id,
        condition=config.condition,
        expected_base_commit=config.expected_base_commit,
        task_image=config.task_image,
        overlay_image=config.overlay_image,
        container_name=(
            f"marginal-{config.condition}-{config.instance_id.replace('__', '-')}-"
            f"{config.repetition}"
        ).lower(),
        run_dir=run_dir,
        source_root=config.source_root,
        auth_source=config.auth_source,
        prompt_file=prompt_path,
        model=config.model,
        reasoning_effort=config.reasoning_effort,
        timeout_seconds=config.timeout_seconds,
    )
    started = time.perf_counter_ns()
    try:
        completed = executor(
            build_container_command(runtime),
            check=False,
            timeout=config.timeout_seconds + 60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContainerTaskError(f"container execution failed: {exc}") from exc
    wall_time_ms = max(0, round((time.perf_counter_ns() - started) / 1_000_000))

    status = _json_object(run_dir / "container-status.json")
    if status != {
        "codex_exit_code": completed.returncode,
        "condition": config.condition,
        "instance_id": config.instance_id,
    }:
        raise ContainerTaskError("container exit status provenance mismatch")
    if completed.returncode != 0:
        raise ContainerTaskError(f"Codex container exited with {completed.returncode}")
    try:
        metrics = parse_codex_jsonl(run_dir / "codex-events.jsonl")
    except (OSError, EventParseError) as exc:
        raise ContainerTaskError(f"Codex event stream is invalid: {exc}") from exc
    if not metrics.completed or metrics.tokens is None or metrics.errors:
        raise ContainerTaskError("Codex event lifecycle or token telemetry is incomplete")

    if config.condition == "marginal":
        _, marginal = _attest_marginal(run_dir, metrics.tool_calls)
        raw_governance = marginal["governance"]
        raw_interventions = marginal["interventions"]
    else:
        forbidden = (
            "daemon-summary.json",
            "treasury-events.jsonl",
            "hook-failures.log",
            "daemon.stdout.log",
            "daemon.stderr.log",
        )
        if any((run_dir / name).exists() for name in forbidden):
            raise ContainerTaskError("baseline contains a MARGINAL runtime artifact")
        raw_governance = {}
        raw_interventions = {}

    _assert_no_auth_material(run_dir, config.auth_source)
    patch = (run_dir / "model.patch").read_bytes()
    files_modified, diff_lines = _patch_stats(run_dir / "model.numstat")
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
    record: dict[str, Any] = {
        "schema_version": 1,
        "instance_id": config.instance_id,
        "condition": config.condition,
        "repetition": config.repetition,
        "run_status": "completed",
        "resolved": None,
        "configuration_sha256": _configuration_hash(config),
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "tokens": metrics.tokens,
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
        "error_code": None,
    }
    (run_dir / "run-record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / "run-provenance.json").write_text(
        json.dumps(
            {
                "base_commit": config.expected_base_commit,
                "source_commit": config.source_commit,
                "task_image": config.task_image,
                "overlay_image": config.overlay_image,
                "prompt_sha256": hashlib.sha256(config.prompt.encode()).hexdigest(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return record
