"""Read-only Claude Code discovery and reversible native plugin operations.

Installation is delegated to Claude Code's own plugin commands so that removal is
always possible with the same tool the user already trusts. Nothing here reads
credentials, transcripts, or project configuration.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MARKETPLACE_NAME = "marginal"
MARKETPLACE_SOURCE = "SignalLayerLabs/Marginal"
PLUGIN_NAME = "marginal-claude-code"
PLUGIN_SELECTOR = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
_VERSION_PATTERN = re.compile(r"(\d+\.\d+\.\d+)")
_MINIMUM_VERSION = (2, 1, 0)


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, args: list[str]) -> CommandResult: ...


class SubprocessRunner:
    """Run Claude Code without a shell or inherited secret variables."""

    def __init__(self, *, timeout_seconds: float = 30.0, max_output_bytes: int = 1_048_576):
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def run(self, args: list[str]) -> CommandResult:
        environment = {
            name: value
            for name in ("PATH", "HOME", "CLAUDE_CONFIG_DIR", "LANG", "LC_ALL", "SYSTEMROOT")
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
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CommandResult(127, "", type(exc).__name__)
        stdout = completed.stdout[: self.max_output_bytes].decode("utf-8", errors="replace")
        stderr = completed.stderr[: self.max_output_bytes].decode("utf-8", errors="replace")
        return CommandResult(completed.returncode, stdout, stderr)


@dataclass(frozen=True, slots=True)
class ClaudeCodeDoctorReport:
    """What can be established about a Claude Code installation without secrets."""

    available: bool
    version: str
    plugins_supported: bool
    capability_level: str
    blocking_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "version": self.version,
            "plugins_supported": self.plugins_supported,
            "capability_level": self.capability_level,
            "capability_label": "Observe",
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True, slots=True)
class ClaudeCodeInstallation:
    installed: bool
    changed: bool
    selector: str = PLUGIN_SELECTOR
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


def _executable() -> str | None:
    return shutil.which("claude")


def _parse_version(output: str) -> str:
    match = _VERSION_PATTERN.search(output)
    return match.group(1) if match else ""


def _version_tuple(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return ()


def inspect_claude_code(*, runner: CommandRunner | None = None) -> ClaudeCodeDoctorReport:
    """Report installation facts. Absence is a normal answer, not an error."""

    executable = _executable()
    if executable is None:
        return ClaudeCodeDoctorReport(
            available=False,
            version="",
            plugins_supported=False,
            capability_level="none",
            blocking_reasons=("CLAUDE_CODE_NOT_FOUND",),
        )
    selected = runner or SubprocessRunner()
    version_result = selected.run([executable, "--version"])
    version = _parse_version(version_result.stdout or version_result.stderr)
    reasons: list[str] = []
    if version_result.returncode != 0:
        reasons.append("VERSION_UNAVAILABLE")
    parsed = _version_tuple(version)
    plugins_supported = bool(parsed) and parsed >= _MINIMUM_VERSION
    if not plugins_supported:
        reasons.append("PLUGIN_SUPPORT_UNVERIFIED")
    return ClaudeCodeDoctorReport(
        available=True,
        version=version,
        plugins_supported=plugins_supported,
        capability_level="observe" if plugins_supported else "none",
        blocking_reasons=tuple(reasons),
    )


def install(
    *,
    runner: CommandRunner | None = None,
    marketplace_source: str | Path = MARKETPLACE_SOURCE,
) -> ClaudeCodeInstallation:
    """Add the marketplace and install the plugin through Claude Code itself."""

    executable = _executable()
    if executable is None:
        return ClaudeCodeInstallation(
            installed=False,
            changed=False,
            error_code="CLAUDE_CODE_NOT_FOUND",
            message="claude was not found on PATH",
        )
    selected = runner or SubprocessRunner()
    marketplace = selected.run(
        [executable, "plugin", "marketplace", "add", str(marketplace_source)]
    )
    if marketplace.returncode != 0 and "already" not in marketplace.stderr.casefold():
        return ClaudeCodeInstallation(
            installed=False,
            changed=False,
            error_code="MARKETPLACE_FAILED",
            message=marketplace.stderr.strip(),
        )
    installation = selected.run([executable, "plugin", "install", PLUGIN_SELECTOR])
    if installation.returncode != 0:
        return ClaudeCodeInstallation(
            installed=False,
            changed=False,
            error_code="INSTALL_FAILED",
            message=installation.stderr.strip(),
        )
    return ClaudeCodeInstallation(installed=True, changed=True)


def uninstall(*, runner: CommandRunner | None = None) -> ClaudeCodeInstallation:
    """Remove the plugin. A plugin that is already absent is a success."""

    executable = _executable()
    if executable is None:
        return ClaudeCodeInstallation(
            installed=False,
            changed=False,
            error_code="CLAUDE_CODE_NOT_FOUND",
            message="claude was not found on PATH",
        )
    selected = runner or SubprocessRunner()
    removal = selected.run([executable, "plugin", "uninstall", PLUGIN_SELECTOR])
    if removal.returncode != 0 and "not installed" not in removal.stderr.casefold():
        return ClaudeCodeInstallation(
            installed=True,
            changed=False,
            error_code="UNINSTALL_FAILED",
            message=removal.stderr.strip(),
        )
    return ClaudeCodeInstallation(installed=False, changed=removal.returncode == 0)
