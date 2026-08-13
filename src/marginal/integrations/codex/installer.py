"""Read-only Codex discovery and reversible native plugin operations."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
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

    def to_dict(self) -> dict[str, object]:
        return {
            "installed": self.installed,
            "changed": self.changed,
            "selector": self.selector,
            "error_code": self.error_code,
            "message": self.message,
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
) -> CodexInstallation:
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
    return CodexInstallation(True, True, message="installed in Shadow Mode")


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

