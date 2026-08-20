"""Owner-controlled configuration for the optional MARGINAL Commons client."""

from __future__ import annotations

import errno
import json
import os
import secrets
import stat
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from marginal.governance_ledger import (
    _lock_exclusive,
    _open_parent_directory,
    _unlock,
    _write_all,
)

_CONFIG_NAME = "user-config.json"
_LOCK_NAME = ".user-config.lock"
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
    if ".." in supplied.parts:
        raise ValueError("user configuration path must not contain traversal components")
    return supplied if supplied.is_absolute() else Path.cwd() / supplied


def _config_path(data_dir: str | Path) -> Path:
    root = _absolute_path(data_dir)
    return root / _CONFIG_NAME


def _open_config_directory(data_dir: str | Path, *, create: bool) -> int:
    try:
        return _open_parent_directory(_config_path(data_dir), create_parents=create)
    except ValueError as exc:
        if "symbolic" in str(exc):
            raise ValueError("user configuration path must not contain a symbolic link") from exc
        raise
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError("user configuration path must not contain a symbolic link") from exc
        raise


def _read_bounded(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    remaining = _MAX_CONFIG_BYTES + 1
    while remaining > 0:
        chunk = os.read(descriptor, min(64 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_user_config_at(directory_descriptor: int) -> dict[str, Any] | None:
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(_CONFIG_NAME, flags, dir_fd=directory_descriptor)
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
        raw = _read_bounded(descriptor)
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


def _read_user_config(data_dir: str | Path) -> dict[str, Any] | None:
    try:
        directory_descriptor = _open_config_directory(data_dir, create=False)
    except FileNotFoundError:
        return None
    try:
        return _read_user_config_at(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _temporary_name() -> str:
    return f".user-config-{secrets.token_hex(12)}.tmp"


def _open_temporary(directory_descriptor: int) -> tuple[int, str]:
    for _ in range(16):
        name = _temporary_name()
        try:
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_descriptor,
            )
        except FileExistsError:
            continue
        return descriptor, name
    raise FileExistsError("unable to allocate a private user configuration temporary file")


def _require_config_write_safety() -> None:
    if os.rename not in os.supports_dir_fd or os.unlink not in os.supports_dir_fd:
        raise OSError("descriptor-relative replace and cleanup operations are unavailable")


def _open_config_lock(directory_descriptor: int) -> int:
    try:
        descriptor = os.open(
            _LOCK_NAME,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_descriptor,
        )
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError("user configuration lock must not be a symbolic link") from exc
        raise
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("user configuration lock must be a regular file")
        if os.name == "posix" and stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError("user configuration lock must have owner-only permissions")
        return descriptor
    except BaseException:
        with suppress(BaseException):
            os.close(descriptor)
        raise


def _rename_config_at(directory_descriptor: int, temporary_name: str) -> None:
    os.rename(
        temporary_name,
        _CONFIG_NAME,
        src_dir_fd=directory_descriptor,
        dst_dir_fd=directory_descriptor,
    )


def _unlink_config_at(directory_descriptor: int, temporary_name: str) -> None:
    os.unlink(temporary_name, dir_fd=directory_descriptor)


def _write_user_config_at(directory_descriptor: int, payload: dict[str, Any]) -> None:
    _require_config_write_safety()
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = _open_temporary(directory_descriptor)
    renamed = False
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _rename_config_at(directory_descriptor, temporary_name)
        renamed = True
        os.fsync(directory_descriptor)
    except BaseException:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        if not renamed:
            with suppress(OSError):
                _unlink_config_at(directory_descriptor, temporary_name)
        raise


def _update_user_config(data_dir: str | Path, **changes: object) -> dict[str, Any]:
    """Atomically merge reviewed choices into the one user configuration file."""

    _require_config_write_safety()
    directory_descriptor = _open_config_directory(data_dir, create=True)
    lock_descriptor = -1
    locked = False
    primary_error: BaseException | None = None
    try:
        if os.name == "posix":
            os.fchmod(directory_descriptor, 0o700)
        lock_descriptor = _open_config_lock(directory_descriptor)
        _lock_exclusive(lock_descriptor)
        locked = True
        payload = _read_user_config_at(directory_descriptor)
        if payload is None:
            payload = {"schema_version": 1}
        payload.update(changes)
        _write_user_config_at(directory_descriptor, payload)
        return payload
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        cleanup_error: BaseException | None = None
        if locked:
            try:
                _unlock(lock_descriptor)
            except BaseException as exc:
                cleanup_error = exc
        if lock_descriptor >= 0:
            try:
                os.close(lock_descriptor)
            except BaseException as exc:
                if cleanup_error is None:
                    cleanup_error = exc
        try:
            os.close(directory_descriptor)
        except BaseException as exc:
            if cleanup_error is None:
                cleanup_error = exc
        if primary_error is None and cleanup_error is not None:
            raise cleanup_error


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
