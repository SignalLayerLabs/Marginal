"""Descriptor-relative owner-only storage shared by Commons modules."""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from secrets import token_hex as _token_hex

from marginal.governance_ledger import (
    _lock_exclusive,
    _open_parent_directory,
    _unlock,
    _write_all,
)

_OWNER_ONLY_MASK = 0o077


def _validate_directory(descriptor: int) -> None:
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("Commons storage path must be a directory")
    if os.name == "posix" and stat.S_IMODE(metadata.st_mode) & _OWNER_ONLY_MASK:
        raise PermissionError("Commons storage directory must have owner-only permissions")


def _open_lock(directory_descriptor: int, name: str) -> int:
    try:
        descriptor = os.open(
            name,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_descriptor,
        )
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError("Commons storage lock must not be a symbolic link") from exc
        raise
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Commons storage lock must be a regular file")
        if os.name == "posix" and stat.S_IMODE(metadata.st_mode) & _OWNER_ONLY_MASK:
            raise PermissionError("Commons storage lock must have owner-only permissions")
        return descriptor
    except BaseException:
        with suppress(BaseException):
            os.close(descriptor)
        raise


@contextmanager
def locked_directory(path: Path, *, create: bool, lock_name: str) -> Iterator[int]:
    """Hold one nofollow directory descriptor and an interprocess lock."""

    directory_descriptor = -1
    for _ in range(16):
        try:
            directory_descriptor = _open_parent_directory(path / ".anchor", create_parents=create)
        except FileExistsError:
            continue
        break
    if directory_descriptor < 0:
        raise FileExistsError("unable to open concurrently created Commons storage")
    lock_descriptor = -1
    locked = False
    primary_error: BaseException | None = None
    try:
        _validate_directory(directory_descriptor)
        lock_descriptor = _open_lock(directory_descriptor, lock_name)
        _lock_exclusive(lock_descriptor)
        locked = True
        yield directory_descriptor
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


def _validate_regular_owner_only(descriptor: int, *, label: str) -> os.stat_result:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file")
    if os.name == "posix" and stat.S_IMODE(metadata.st_mode) & _OWNER_ONLY_MASK:
        raise PermissionError(f"{label} must have owner-only permissions")
    return metadata


def read_bounded_at(
    directory_descriptor: int,
    name: str,
    *,
    maximum_bytes: int,
    label: str,
) -> tuple[bytes, os.stat_result]:
    """Read an owner-only regular leaf without following it or exceeding a bound."""

    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_descriptor,
        )
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError(f"{label} must not be a symbolic link") from exc
        raise
    try:
        metadata = _validate_regular_owner_only(descriptor, label=label)
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum_bytes:
            raise ValueError(f"{label} is too large")
        return raw, metadata
    finally:
        os.close(descriptor)


def validate_leaf_for_replace(directory_descriptor: int, name: str, *, label: str) -> None:
    """Reject an existing unsafe target before an atomic replacement."""

    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_descriptor,
        )
    except FileNotFoundError:
        return
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError(f"{label} must not be a symbolic link") from exc
        raise
    try:
        _validate_regular_owner_only(descriptor, label=label)
    finally:
        os.close(descriptor)


def atomic_replace_at(
    directory_descriptor: int,
    name: str,
    data: bytes,
    *,
    temporary_prefix: str,
    label: str,
) -> None:
    """Write completely, fsync, and descriptor-relatively replace one safe leaf."""

    if os.rename not in os.supports_dir_fd or os.unlink not in os.supports_dir_fd:
        raise OSError("descriptor-relative Commons storage operations are unavailable")
    validate_leaf_for_replace(directory_descriptor, name, label=label)
    descriptor = -1
    temporary_name = ""
    for _ in range(16):
        temporary_name = f"{temporary_prefix}{_token_hex(12)}.tmp"
        try:
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_descriptor,
            )
        except FileExistsError:
            continue
        break
    if descriptor < 0:
        raise FileExistsError("unable to allocate a private Commons temporary file")
    renamed = False
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, data)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.rename(
            temporary_name,
            name,
            src_dir_fd=directory_descriptor,
            dst_dir_fd=directory_descriptor,
        )
        renamed = True
        os.fsync(directory_descriptor)
    except BaseException:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        if not renamed:
            with suppress(OSError):
                os.unlink(temporary_name, dir_fd=directory_descriptor)
        raise


def atomic_create_at(
    directory_descriptor: int,
    name: str,
    data: bytes,
    *,
    temporary_prefix: str,
    label: str,
) -> os.stat_result:
    """Publish a complete private file atomically without overwriting a collision."""

    if os.link not in os.supports_dir_fd or os.unlink not in os.supports_dir_fd:
        raise OSError("descriptor-relative Commons create operations are unavailable")
    descriptor = -1
    temporary_name = ""
    for _ in range(16):
        temporary_name = f"{temporary_prefix}{_token_hex(12)}.tmp"
        try:
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_descriptor,
            )
        except FileExistsError:
            continue
        break
    if descriptor < 0:
        raise FileExistsError("unable to allocate a private Commons temporary file")
    published = False
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, data)
        os.fsync(descriptor)
        metadata = _validate_regular_owner_only(descriptor, label=label)
        os.close(descriptor)
        descriptor = -1
        os.link(
            temporary_name,
            name,
            src_dir_fd=directory_descriptor,
            dst_dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        published = True
        os.unlink(temporary_name, dir_fd=directory_descriptor)
        os.fsync(directory_descriptor)
        return metadata
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        if not published:
            with suppress(OSError):
                os.unlink(temporary_name, dir_fd=directory_descriptor)
