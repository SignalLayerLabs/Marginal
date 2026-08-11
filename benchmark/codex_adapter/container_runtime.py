"""Fail-closed Docker boundary for official SWE-bench task images."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]*(?::[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_INSTANCE_ID = re.compile(r"^[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-[0-9]+$")
_CONTAINER_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")


def official_instance_image(instance_id: str) -> str:
    """Return the official SWE-bench Docker Hub tag for an instance ID."""

    if _INSTANCE_ID.fullmatch(instance_id) is None:
        raise ValueError("instance_id is not a valid SWE-bench instance ID")
    escaped = instance_id.lower().replace("__", "_1776_")
    return f"swebench/sweb.eval.x86_64.{escaped}:latest"


def _resolved_directory(path: Path, field: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"{field} must be an existing directory")
    if "," in str(resolved):
        raise ValueError(f"{field} cannot contain a comma")
    return resolved


def _resolved_file(path: Path, field: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"{field} must be an existing file")
    if "," in str(resolved):
        raise ValueError(f"{field} cannot contain a comma")
    return resolved


@dataclass(frozen=True, slots=True)
class ContainerRunConfig:
    """All public, non-secret inputs required to launch one disposable task container."""

    instance_id: str
    condition: str
    expected_base_commit: str
    task_image: str
    overlay_image: str
    container_name: str
    run_dir: Path
    source_root: Path
    auth_source: Path
    prompt_file: Path
    model: str = "gpt-5.6-sol"
    reasoning_effort: str = "high"
    timeout_seconds: int = 1800
    memory: str = "12g"
    cpus: str = "6"

    def __post_init__(self) -> None:
        if _INSTANCE_ID.fullmatch(self.instance_id) is None:
            raise ValueError("instance_id is not a valid SWE-bench instance ID")
        if self.condition not in {"baseline", "marginal"}:
            raise ValueError("condition must be baseline or marginal")
        if _COMMIT.fullmatch(self.expected_base_commit) is None:
            raise ValueError("expected_base_commit must be a lowercase 40-character SHA")
        if _DIGEST_IMAGE.fullmatch(self.task_image) is None:
            raise ValueError("task_image must be digest-pinned")
        if (
            _DIGEST_IMAGE.fullmatch(self.overlay_image) is None
            and _IMAGE_ID.fullmatch(self.overlay_image) is None
        ):
            raise ValueError("overlay_image must be digest-pinned")
        if _CONTAINER_NAME.fullmatch(self.container_name) is None:
            raise ValueError("container_name is invalid")
        if not self.model.strip():
            raise ValueError("model must not be empty")
        if not self.reasoning_effort.strip():
            raise ValueError("reasoning_effort must not be empty")
        if isinstance(self.timeout_seconds, bool) or self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")

        source_root = _resolved_directory(self.source_root, "source_root")
        run_dir = _resolved_directory(self.run_dir, "run_dir")
        prompt_file = _resolved_file(self.prompt_file, "prompt_file")
        _resolved_file(self.auth_source, "auth_source")
        if run_dir == source_root or run_dir.is_relative_to(source_root):
            raise ValueError("run_dir must be outside source_root")
        if prompt_file.parent != run_dir:
            raise ValueError("prompt_file must be directly inside run_dir")


def _bind(source: Path, destination: str, *, readonly: bool = False) -> str:
    options = f",dst={destination}"
    if readonly:
        options += ",readonly"
    return f"type=bind,src={source.resolve()}{options}"


def build_container_command(config: ContainerRunConfig) -> list[str]:
    """Build a shell-free Docker command with a symmetric OFF/ON runtime boundary."""

    return [
        "docker",
        "run",
        "--rm",
        "--init",
        "--platform",
        "linux/amd64",
        "--name",
        config.container_name,
        "--label",
        f"org.marginal.benchmark.instance={config.instance_id}",
        "--label",
        f"org.marginal.benchmark.condition={config.condition}",
        "--cap-add=SYS_ADMIN",
        "--security-opt",
        "seccomp=unconfined",
        "--security-opt",
        "apparmor=unconfined",
        "--security-opt",
        "systempaths=unconfined",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "2048",
        "--memory",
        config.memory,
        "--cpus",
        config.cpus,
        "--network",
        "bridge",
        "--tmpfs",
        "/marginal-home:rw,noexec,nosuid,nodev,size=64m",
        "--tmpfs",
        "/tmp:rw,exec,nosuid,nodev,size=2g",
        "--mount",
        _bind(config.run_dir, "/marginal-run"),
        "--mount",
        _bind(config.auth_source, "/run/secrets/codex-auth.json", readonly=True),
        "--env",
        f"MARGINAL_INSTANCE_ID={config.instance_id}",
        "--env",
        f"MARGINAL_CONDITION={config.condition}",
        "--env",
        f"MARGINAL_EXPECTED_BASE_COMMIT={config.expected_base_commit}",
        "--env",
        f"MARGINAL_MODEL={config.model}",
        "--env",
        f"MARGINAL_REASONING_EFFORT={config.reasoning_effort}",
        "--env",
        f"MARGINAL_TIMEOUT_SECONDS={config.timeout_seconds}",
        "--entrypoint",
        "/opt/marginal/benchmark/container/entrypoint.sh",
        config.overlay_image,
    ]
