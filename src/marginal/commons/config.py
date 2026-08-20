"""Owner-controlled configuration for the optional MARGINAL Commons client."""

from __future__ import annotations

import errno
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

_CONFIG_NAME = "user-config.json"
_MAX_CONFIG_BYTES = 65_536


class CommonsMode(str, Enum):
    """Explicit network posture for MARGINAL Commons."""

    LOCAL_ONLY = "local_only"
    READ_ONLY = "read_only"
    CONTRIBUTOR = "contributor"

    @classmethod
    def parse(cls, value: CommonsMode | str) -> CommonsMode:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError("Commons mode must be a string or CommonsMode")
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"unknown Commons mode: {value}") from exc


@dataclass(frozen=True, slots=True)
class CommonsConfig:
    """Validated local Commons configuration."""

    mode: CommonsMode = CommonsMode.LOCAL_ONLY

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", CommonsMode.parse(self.mode))


def _absolute_path(path: str | Path) -> Path:
    supplied = Path(path)
    return Path(os.path.abspath(os.fspath(supplied)))


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("user configuration path must not contain a symbolic link")


def _config_path(data_dir: str | Path) -> Path:
    root = _absolute_path(data_dir)
    _reject_symlink_components(root)
    return root / _CONFIG_NAME


def _read_user_config(data_dir: str | Path) -> dict[str, Any] | None:
    path = _config_path(data_dir)
    if path.is_symlink():
        raise ValueError("user configuration path must not be a symbolic link")
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError("user configuration path must not be a symbolic link") from exc
        raise
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("user configuration must be a regular file")
        if os.name == "posix" and stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError("user configuration must have owner-only permissions")
        raw = os.read(descriptor, _MAX_CONFIG_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > _MAX_CONFIG_BYTES:
        raise ValueError("user configuration is too large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("user configuration must be valid JSON") from exc
    if (
        not isinstance(payload, dict)
        or isinstance(payload.get("schema_version"), bool)
        or payload.get("schema_version") != 1
    ):
        raise ValueError("user configuration must be a schema version 1 object")
    return payload


def _write_user_config(data_dir: str | Path, payload: dict[str, Any]) -> None:
    path = _config_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _reject_symlink_components(path.parent)
    if os.name == "posix":
        path.parent.chmod(0o700)
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".user-config-", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, encoded)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        if path.is_symlink():
            raise ValueError("user configuration path must not be a symbolic link")
        os.replace(temporary, path)
        if os.name == "posix":
            path.chmod(0o600)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _update_user_config(data_dir: str | Path, **changes: object) -> dict[str, Any]:
    """Atomically merge reviewed choices into the one user configuration file."""

    payload = _read_user_config(data_dir)
    if payload is None:
        payload = {"schema_version": 1}
    payload.update(changes)
    _write_user_config(data_dir, payload)
    return payload


def load_commons_config(data_dir: str | Path) -> CommonsConfig:
    """Load the explicit Commons choice, defaulting absence to Local Only."""

    payload = _read_user_config(data_dir)
    if payload is None or "commons_mode" not in payload:
        return CommonsConfig()
    try:
        return CommonsConfig(mode=CommonsMode.parse(payload["commons_mode"]))
    except (TypeError, ValueError):
        return CommonsConfig()


def configure_commons_mode(data_dir: str | Path, *, mode: CommonsMode | str) -> CommonsConfig:
    """Persist one explicit user-level Commons mode without changing Autopilot consent."""

    selected = CommonsMode.parse(mode)
    _update_user_config(data_dir, commons_mode=selected.value)
    return CommonsConfig(mode=selected)
