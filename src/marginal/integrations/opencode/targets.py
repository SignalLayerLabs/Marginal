"""OpenCode-compatible engines MARGINAL can install into.

OpenCode's plugin loader is reused by compatible forks. A target records only what
differs between them: the executable name, where global configuration lives, and
where the ledger belongs. Nothing about the governance contract is per-target.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PLUGIN_FILENAME = "marginal.js"
PLUGIN_MARKER = "marginal-opencode-plugin"
"""Marker the installer writes so uninstall only ever removes its own file."""


@dataclass(frozen=True, slots=True)
class OpenCodeTarget:
    """One OpenCode-compatible CLI installation layout."""

    name: str
    engine: str
    executable: str
    config_directory_name: str
    data_directory_name: str

    def __post_init__(self) -> None:
        for field_name in (
            "name",
            "engine",
            "executable",
            "config_directory_name",
            "data_directory_name",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

    def config_home(self) -> Path:
        """Return the global configuration directory this CLI reads."""

        configured = os.environ.get("XDG_CONFIG_HOME")
        base = Path(configured) if configured else Path.home() / ".config"
        return base / self.config_directory_name

    def plugin_directory(self) -> Path:
        """Return the global plugin directory this CLI loads plugins from."""

        return self.config_home() / "plugins"

    def plugin_path(self) -> Path:
        return self.plugin_directory() / PLUGIN_FILENAME

    def data_root(self) -> Path:
        """Return the directory the Decision Ledger is written under."""

        override = os.environ.get(f"MARGINAL_{self.name.upper().replace('-', '_')}_DATA")
        if override:
            return Path(override)
        configured = os.environ.get("XDG_DATA_HOME")
        base = Path(configured) if configured else Path.home() / ".local" / "share"
        return base / "marginal" / self.data_directory_name


OPENCODE = OpenCodeTarget(
    name="opencode",
    engine="opencode",
    executable="opencode",
    config_directory_name="opencode",
    data_directory_name="opencode",
)

TARGETS: dict[str, OpenCodeTarget] = {OPENCODE.name: OPENCODE}


def resolve_target(name: str) -> OpenCodeTarget:
    """Return a supported target by name."""

    try:
        return TARGETS[name.strip().casefold()]
    except (AttributeError, KeyError) as exc:
        supported = ", ".join(sorted(TARGETS))
        raise ValueError(f"unsupported target {name!r}; supported targets: {supported}") from exc
