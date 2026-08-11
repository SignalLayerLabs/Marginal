"""Fail-closed readiness checks performed before any Codex benchmark inference."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from .dataset import FrozenTask, fetch_frozen_tasks


class PreflightError(RuntimeError):
    """Raised when execution would violate the frozen benchmark contract."""


@dataclass(frozen=True, slots=True)
class PreflightConfig:
    repository_root: Path
    codex_executable: Path
    python_executable: Path
    auth_source: Path
    environment_path: Path
    tasks_path: Path
    prompt_path: Path
    schema_path: Path
    expected_repository_commit: str
    require_verifier: bool = True
    require_task_environment: bool = True


TaskLoader = Callable[[str | Path], tuple[FrozenTask, ...]]


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PreflightError(f"command failed ({' '.join(command)}): {detail}")
    return "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"JSON file must contain an object: {path}")
    return value


def _nested_text(value: dict[str, Any], *keys: str) -> str:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            raise PreflightError(f"missing environment field: {'.'.join(keys)}")
        current = current.get(key)
    if not isinstance(current, str) or not current:
        raise PreflightError(f"missing environment field: {'.'.join(keys)}")
    return current


def run_preflight(
    config: PreflightConfig,
    *,
    task_loader: TaskLoader = fetch_frozen_tasks,
) -> dict[str, Any]:
    """Verify code, CLI, model, auth, schema, prompt, and task identities."""

    root = config.repository_root.resolve()
    for path, label in (
        (root, "repository"),
        (config.codex_executable, "Codex executable"),
        (config.python_executable, "Python executable"),
        (config.auth_source, "Codex auth file"),
    ):
        if not path.exists():
            raise PreflightError(f"{label} does not exist: {path}")

    head = _run(["git", "rev-parse", "HEAD"], cwd=root)
    if head != config.expected_repository_commit:
        raise PreflightError(f"MARGINAL commit mismatch: {head}")
    core_status = _run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=no",
            "--",
            "src/marginal",
            "pyproject.toml",
        ],
        cwd=root,
    )
    if core_status:
        raise PreflightError("MARGINAL core source is dirty")

    environment = _json_object(config.environment_path)
    if _nested_text(environment, "repository", "commit") != head:
        raise PreflightError("environment repository commit does not match HEAD")
    expected_python = _nested_text(environment, "python")
    python_output = _run([str(config.python_executable), "--version"], cwd=root)
    actual_python = python_output.removeprefix("Python ").strip()
    if actual_python != expected_python:
        raise PreflightError(f"Python version mismatch: {actual_python}")

    expected_codex = _nested_text(environment, "codex", "cli_version")
    version_output = _run([str(config.codex_executable), "--version"], cwd=root)
    match = re.search(r"(\d+\.\d+\.\d+)", version_output)
    actual_codex = match.group(1) if match else ""
    if actual_codex != expected_codex:
        raise PreflightError(f"Codex version mismatch: {actual_codex or version_output}")
    features = _run([str(config.codex_executable), "features", "list"], cwd=root)
    if re.search(r"(?m)^hooks\s+stable\s+true\s*$", features) is None:
        raise PreflightError("Codex hooks feature is not stable and enabled")

    model = _nested_text(environment, "codex", "model")
    reasoning_effort = _nested_text(environment, "codex", "reasoning_effort")
    model_catalog_output = _run(
        [str(config.codex_executable), "debug", "models", "--bundled"], cwd=root
    )
    try:
        catalog = json.loads(model_catalog_output)
    except json.JSONDecodeError as exc:
        raise PreflightError("Codex bundled model catalog is invalid") from exc
    models = catalog.get("models") if isinstance(catalog, dict) else None
    if not isinstance(models, list):
        raise PreflightError("Codex bundled model catalog has no models list")
    selected = next(
        (entry for entry in models if isinstance(entry, dict) and entry.get("slug") == model),
        None,
    )
    if selected is None:
        raise PreflightError(f"frozen model is unavailable: {model}")
    levels = selected.get("supported_reasoning_levels")
    if not isinstance(levels, list) or not any(
        isinstance(level, dict) and level.get("effort") == reasoning_effort for level in levels
    ):
        raise PreflightError(f"model does not support reasoning effort: {reasoning_effort}")

    mode = stat.S_IMODE(config.auth_source.stat().st_mode)
    if mode != 0o600:
        raise PreflightError("Codex auth file permissions must be 0600")
    with tempfile.TemporaryDirectory(prefix="codex-preflight-") as home_value:
        temporary_home = Path(home_value)
        auth_copy = temporary_home / "auth.json"
        shutil.copyfile(config.auth_source, auth_copy)
        auth_copy.chmod(0o600)
        auth_environment = {
            key: os.environ[key]
            for key in ("HOME", "LANG", "LC_ALL", "PATH", "SHELL", "TMPDIR", "USER")
            if key in os.environ
        }
        auth_environment["CODEX_HOME"] = str(temporary_home)
        login_status = _run(
            [str(config.codex_executable), "login", "status"],
            cwd=root,
            env=auth_environment,
        )
    if "Logged in" not in login_status:
        raise PreflightError("Codex authentication is not ready")

    prompt_hash = hashlib.sha256(config.prompt_path.read_bytes()).hexdigest()
    frozen_prompt_hash = _nested_text(environment, "benchmark", "prompt_template_sha256")
    if prompt_hash != frozen_prompt_hash:
        raise PreflightError("prompt template hash mismatch")
    tasks_manifest = _json_object(config.tasks_path)
    task_ids = tasks_manifest.get("task_ids")
    if not isinstance(task_ids, list) or not all(isinstance(item, str) for item in task_ids):
        raise PreflightError("task manifest has invalid task_ids")
    if len(task_ids) != len(set(task_ids)):
        raise PreflightError("task manifest has duplicate task IDs")
    loaded_tasks = task_loader(config.tasks_path)
    if [task.instance_id for task in loaded_tasks] != task_ids:
        raise PreflightError("Dataset Viewer task order does not match the frozen manifest")
    task_digest = hashlib.sha256("\n".join(task_ids).encode("utf-8")).hexdigest()
    declared_digest = tasks_manifest.get("task_set_sha256")
    if declared_digest is not None and declared_digest != task_digest:
        raise PreflightError("task-set digest mismatch")

    schema = _json_object(config.schema_path)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise PreflightError("run-record JSON Schema is invalid") from exc

    if config.require_task_environment:
        raise PreflightError(
            "benchmark execution blocked: Codex 0.147 PostToolUse omits shell exit status, "
            "so successful repeat detection is not observable; an official per-instance "
            "Codex execution backend is also not implemented"
        )

    verifier = "not-required"
    if config.require_verifier:
        modal_credentials = bool(os.environ.get("MODAL_TOKEN_ID")) and bool(
            os.environ.get("MODAL_TOKEN_SECRET")
        )
        modal_packages = (
            importlib.util.find_spec("modal") is not None
            and importlib.util.find_spec("swebench") is not None
        )
        docker = shutil.which("docker")
        docker_ready = False
        if docker is not None and importlib.util.find_spec("swebench") is not None:
            probe = subprocess.run(
                [docker, "info"],
                cwd=root,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            docker_ready = probe.returncode == 0
        if modal_credentials and modal_packages:
            verifier = "official-swebench-modal"
        elif docker_ready:
            verifier = "official-swebench-docker"
        else:
            raise PreflightError(
                "official SWE-bench verifier unavailable: configure Modal credentials plus "
                "swebench[modal], or provide a running Docker engine plus swebench"
            )

    return {
        "ready": True,
        "repository_commit": head,
        "python_version": actual_python,
        "codex_version": actual_codex,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "hooks": "stable-enabled",
        "prompt_template_sha256": prompt_hash,
        "task_set_sha256": task_digest,
        "task_ids": task_ids,
        "verifier": verifier,
        "credentials_recorded": False,
    }
