"""Read-only OpenCode discovery and reversible plugin installation.

OpenCode loads plugins from a directory rather than from a marketplace, so
installation copies one file and uninstallation removes it. Uninstall only ever
deletes a file that carries MARGINAL's own marker, so a hand-written plugin with the
same name is never destroyed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .targets import OPENCODE, PLUGIN_FILENAME, PLUGIN_MARKER, OpenCodeTarget

_VERSION_PATTERN = re.compile(r"(\d+\.\d+\.\d+)")
_MINIMUM_VERSION = (1, 18, 0)
_TARGET_PATTERN = re.compile(
    r'(const ENGINE_TARGET = process\.env\.MARGINAL_TARGET \|\| ")[A-Za-z0-9._-]+(")'
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, args: list[str]) -> CommandResult: ...


class SubprocessRunner:
    """Run the engine without a shell or inherited secret variables."""

    def __init__(self, *, timeout_seconds: float = 30.0, max_output_bytes: int = 1_048_576):
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def run(self, args: list[str]) -> CommandResult:
        environment = {
            name: value
            for name in ("PATH", "HOME", "XDG_CONFIG_HOME", "LANG", "LC_ALL", "SYSTEMROOT")
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
class OpenCodeDoctorReport:
    target: str
    available: bool
    version: str
    plugins_supported: bool
    plugin_installed: bool
    capability_level: str
    blocking_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "available": self.available,
            "version": self.version,
            "plugins_supported": self.plugins_supported,
            "plugin_installed": self.plugin_installed,
            "capability_level": self.capability_level,
            "capability_label": "Observe",
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True, slots=True)
class OpenCodeInstallation:
    installed: bool
    changed: bool
    target: str = OPENCODE.name
    path: str = ""
    error_code: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "installed": self.installed,
            "changed": self.changed,
            "target": self.target,
            "path": self.path,
            "error_code": self.error_code,
            "message": self.message,
        }


def bundled_plugin_path() -> Path:
    """Return the plugin source shipped in this repository."""

    return Path(__file__).resolve().parents[4] / "plugins" / "marginal-opencode" / PLUGIN_FILENAME


def _version_tuple(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return ()


def render_plugin(source: str, target: OpenCodeTarget) -> str:
    """Return the plugin source with its bridge target bound to one engine.

    The bundled plugin defaults to OpenCode so the shipped file is valid as written.
    Installing for a compatible fork rewrites exactly that default, so the plugin
    reports the right engine without depending on an environment variable.
    """

    rendered, replacements = _TARGET_PATTERN.subn(
        lambda match: f"{match.group(1)}{target.engine}{match.group(2)}",
        source,
        count=1,
    )
    if replacements != 1:
        raise ValueError("plugin source does not declare a bridge target")
    return rendered


def is_marginal_plugin(path: Path) -> bool:
    """Return True only for a plugin file MARGINAL wrote."""

    try:
        return PLUGIN_MARKER in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def inspect_opencode(
    *,
    target: OpenCodeTarget = OPENCODE,
    runner: CommandRunner | None = None,
) -> OpenCodeDoctorReport:
    """Report installation facts. Absence is a normal answer, not an error."""

    executable = shutil.which(target.executable)
    installed = is_marginal_plugin(target.plugin_path())
    if executable is None:
        return OpenCodeDoctorReport(
            target=target.name,
            available=False,
            version="",
            plugins_supported=False,
            plugin_installed=installed,
            capability_level="none",
            blocking_reasons=(f"{target.name.upper().replace('-', '_')}_NOT_FOUND",),
        )
    selected = runner or SubprocessRunner()
    result = selected.run([executable, "--version"])
    match = _VERSION_PATTERN.search(result.stdout or result.stderr)
    version = match.group(1) if match else ""
    reasons: list[str] = []
    if result.returncode != 0:
        reasons.append("VERSION_UNAVAILABLE")
    parsed = _version_tuple(version)
    plugins_supported = bool(parsed) and parsed >= _MINIMUM_VERSION
    if not plugins_supported:
        reasons.append("PLUGIN_SUPPORT_UNVERIFIED")
    return OpenCodeDoctorReport(
        target=target.name,
        available=True,
        version=version,
        plugins_supported=plugins_supported,
        plugin_installed=installed,
        capability_level="observe" if plugins_supported else "none",
        blocking_reasons=tuple(reasons),
    )


def install(
    *,
    target: OpenCodeTarget = OPENCODE,
    source: str | Path | None = None,
) -> OpenCodeInstallation:
    """Copy the plugin into the engine's global plugin directory."""

    origin = Path(source) if source is not None else bundled_plugin_path()
    if not origin.is_file():
        return OpenCodeInstallation(
            installed=False,
            changed=False,
            target=target.name,
            error_code="PLUGIN_SOURCE_MISSING",
            message=str(origin),
        )
    if not is_marginal_plugin(origin):
        return OpenCodeInstallation(
            installed=False,
            changed=False,
            target=target.name,
            error_code="PLUGIN_SOURCE_UNRECOGNIZED",
            message=str(origin),
        )
    destination = target.plugin_path()
    if destination.exists() and not is_marginal_plugin(destination):
        return OpenCodeInstallation(
            installed=False,
            changed=False,
            target=target.name,
            path=str(destination),
            error_code="FOREIGN_PLUGIN_PRESENT",
            message="a different plugin already owns this filename",
        )
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = render_plugin(origin.read_text(encoding="utf-8"), target)
        changed = not destination.exists() or destination.read_text(encoding="utf-8") != payload
        if changed:
            destination.write_text(payload, encoding="utf-8")
    except (OSError, ValueError) as exc:
        return OpenCodeInstallation(
            installed=False,
            changed=False,
            target=target.name,
            path=str(destination),
            error_code="INSTALL_FAILED",
            message=type(exc).__name__,
        )
    return OpenCodeInstallation(
        installed=True,
        changed=changed,
        target=target.name,
        path=str(destination),
    )


def uninstall(*, target: OpenCodeTarget = OPENCODE) -> OpenCodeInstallation:
    """Remove only a plugin file MARGINAL wrote. An absent plugin is a success."""

    destination = target.plugin_path()
    if not destination.exists():
        return OpenCodeInstallation(
            installed=False,
            changed=False,
            target=target.name,
            path=str(destination),
        )
    if not is_marginal_plugin(destination):
        return OpenCodeInstallation(
            installed=False,
            changed=False,
            target=target.name,
            path=str(destination),
            error_code="FOREIGN_PLUGIN_PRESENT",
            message="refusing to remove a plugin MARGINAL did not write",
        )
    try:
        destination.unlink()
    except OSError as exc:
        return OpenCodeInstallation(
            installed=True,
            changed=False,
            target=target.name,
            path=str(destination),
            error_code="UNINSTALL_FAILED",
            message=type(exc).__name__,
        )
    return OpenCodeInstallation(
        installed=False,
        changed=True,
        target=target.name,
        path=str(destination),
    )
