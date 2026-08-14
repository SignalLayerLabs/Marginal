"""Read-only Codex discovery and reversible native plugin operations."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, args: list[str]) -> CommandResult: ...


class SubprocessRunner:
    """Run Codex without a shell, credential inspection, or inherited secret variables."""

    def __init__(self, *, timeout_seconds: float = 15.0, max_output_bytes: int = 1_048_576):
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def run(self, args: list[str]) -> CommandResult:
        environment = {
            name: value
            for name in ("PATH", "HOME", "CODEX_HOME", "LANG", "LC_ALL", "SYSTEMROOT")
            if (value := os.environ.get(name)) is not None
        }
        try:
            completed = subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=False,
                timeout=self.timeout_seconds,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CommandResult(127, "", type(exc).__name__)
        stdout = completed.stdout[: self.max_output_bytes].decode("utf-8", errors="replace")
        stderr = completed.stderr[: self.max_output_bytes].decode("utf-8", errors="replace")
        return CommandResult(completed.returncode, stdout, stderr)


@dataclass(frozen=True, slots=True)
class CodexDoctorReport:
    available: bool
    version: str
    hooks_enabled: bool
    plugins_enabled: bool
    capability_level: str
    blocking_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "version": self.version,
            "hooks_enabled": self.hooks_enabled,
            "plugins_enabled": self.plugins_enabled,
            "capability_level": self.capability_level,
            "capability_label": (
                "Tool Enforcement" if self.capability_level == "tool_enforcement" else "Observe"
            ),
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True, slots=True)
class CodexInstallation:
    installed: bool
    changed: bool
    selector: str = "marginal@marginal"
    error_code: str = ""
    message: str = ""
    autopilot_consent: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "installed": self.installed,
            "changed": self.changed,
            "selector": self.selector,
            "error_code": self.error_code,
            "message": self.message,
            "autopilot_consent": self.autopilot_consent,
        }


def _feature_enabled(output: str, name: str) -> bool:
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0] == name:
            return fields[-1].casefold() == "true"
    return False


def inspect_codex(*, runner: CommandRunner | None = None) -> CodexDoctorReport:
    """Discover stable features exclusively through public Codex CLI commands."""

    selected = runner or SubprocessRunner()
    if runner is None and shutil.which("codex") is None:
        return CodexDoctorReport(False, "", False, False, "observe", ("CODEX_NOT_FOUND",))
    version_result = selected.run(["codex", "--version"])
    if version_result.returncode != 0:
        return CodexDoctorReport(False, "", False, False, "observe", ("CODEX_NOT_FOUND",))
    match = re.search(r"(\d+\.\d+\.\d+)", version_result.stdout)
    version = match.group(1) if match else version_result.stdout.strip()
    features = selected.run(["codex", "features", "list"])
    hooks = features.returncode == 0 and _feature_enabled(features.stdout, "hooks")
    plugins = features.returncode == 0 and _feature_enabled(features.stdout, "plugins")
    reasons: list[str] = []
    if not hooks:
        reasons.append("HOOKS_UNAVAILABLE")
    if not plugins:
        reasons.append("PLUGINS_UNAVAILABLE")
    level = "tool_enforcement" if hooks and plugins else "observe"
    return CodexDoctorReport(True, version, hooks, plugins, level, tuple(reasons))


def install(
    *,
    runner: CommandRunner | None = None,
    repository: str = "SignalLayerLabs/Marginal",
    ref: str = "main",
    data_dir: str | Path | None = None,
    autopilot_consent: bool = False,
) -> CodexInstallation:
    if not isinstance(autopilot_consent, bool):
        raise TypeError("autopilot_consent must be a bool")
    selected = runner or SubprocessRunner()
    report = inspect_codex(runner=selected)
    if report.capability_level != "tool_enforcement":
        return CodexInstallation(
            False,
            False,
            error_code="CODEX_CAPABILITIES_UNAVAILABLE",
            message=", ".join(report.blocking_reasons),
        )
    marketplace = selected.run(
        [
            "codex",
            "plugin",
            "marketplace",
            "add",
            repository,
            "--ref",
            ref,
            "--json",
        ]
    )
    if marketplace.returncode != 0 and "already" not in marketplace.stderr.casefold():
        return CodexInstallation(
            False,
            False,
            error_code="MARKETPLACE_ADD_FAILED",
            message=marketplace.stderr.strip(),
        )
    plugin = selected.run(["codex", "plugin", "add", "marginal@marginal", "--json"])
    if plugin.returncode != 0 and "already" not in plugin.stderr.casefold():
        return CodexInstallation(
            False,
            False,
            error_code="PLUGIN_ADD_FAILED",
            message=plugin.stderr.strip(),
        )
    if autopilot_consent:
        if data_dir is None:
            return CodexInstallation(
                True,
                True,
                error_code="AUTOPILOT_CONSENT_DATA_DIR_REQUIRED",
                message="installed in Shadow Mode; Autopilot consent was not persisted",
            )
        configure_autopilot_consent(data_dir, granted=True)
    return CodexInstallation(
        True,
        True,
        message="installed in Shadow Mode",
        autopilot_consent=autopilot_consent,
    )


def uninstall(*, runner: CommandRunner | None = None) -> CodexInstallation:
    selected = runner or SubprocessRunner()
    result = selected.run(["codex", "plugin", "remove", "marginal@marginal", "--json"])
    if result.returncode != 0 and "not installed" not in result.stderr.casefold():
        return CodexInstallation(
            True,
            False,
            error_code="PLUGIN_REMOVE_FAILED",
            message=result.stderr.strip(),
        )
    return CodexInstallation(False, True, message="plugin removed; local evidence preserved")


def _user_config_path(data_dir: str | Path) -> Path:
    return Path(data_dir).resolve() / "user-config.json"


def configure_autopilot_consent(data_dir: str | Path, *, granted: bool) -> None:
    """Persist an explicit user-level Autopilot choice outside every repository.

    Repository configuration is deliberately not read here: it can constrain
    local behavior but cannot grant a user's authority to enforce actions.
    """

    if not isinstance(granted, bool):
        raise TypeError("granted must be a bool")
    path = _user_config_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        path.parent.chmod(0o700)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.write(
            descriptor,
            (
                json.dumps({"schema_version": 1, "autopilot_consent": granted}, sort_keys=True)
                + "\n"
            ).encode(),
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    if os.name == "posix":
        path.chmod(0o600)


def autopilot_consent_configured(data_dir: str | Path) -> bool:
    """Return only a valid, explicit consent bit from the user-owned config."""

    try:
        value = json.loads(_user_config_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return bool(isinstance(value, dict) and value.get("autopilot_consent") is True)
