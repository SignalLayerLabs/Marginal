"""Append-only, hash-chained governance evidence ledger (schema v3)."""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, canonical_hash

GOVERNANCE_LEDGER_SCHEMA_VERSION = "3.0"
_OWNER_ONLY_MASK = 0o077
_OPEN_SUPPORTS_DIRECTORY_FD = os.open in os.supports_dir_fd
_MKDIR_SUPPORTS_DIRECTORY_FD = os.mkdir in os.supports_dir_fd


@dataclass(frozen=True, slots=True)
class LedgerVerificationReport:
    """The result of verifying a governance-ledger v3 chain."""

    valid: bool
    records: int
    root_hash: str | None
    first_invalid_sequence: int | None
    error_codes: tuple[str, ...]


class GovernanceLedger:
    """A separately-versioned, append-only hash chain for governance payloads."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        _validate_file_path(self.path, allow_missing=True)

    def append(self, payload: Mapping[str, Any]) -> str:
        """Append one canonical payload and return its record hash.

        A POSIX advisory lock serializes cooperating writers. Platforms without
        that primitive fail closed instead of claiming cross-process safety.
        """

        normalized_payload = _canonical_payload(payload)
        descriptor = _open_append_descriptor(self.path)
        try:
            _lock_exclusive(descriptor)
            try:
                data = _read_descriptor(descriptor)
                report, records, _ = _verify_data(data)
                if not report.valid:
                    raise ValueError("cannot append to invalid governance ledger")
                sequence = len(records) + 1
                previous_hash = report.root_hash
                record: dict[str, Any] = {
                    "schema_version": GOVERNANCE_LEDGER_SCHEMA_VERSION,
                    "sequence": sequence,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "previous_hash": previous_hash,
                    "payload": normalized_payload,
                    "payload_hash": canonical_hash(normalized_payload),
                }
                record["record_hash"] = canonical_hash(record)
                os.lseek(descriptor, 0, os.SEEK_END)
                encoded = canonical_bytes(record) + b"\n"
                _write_all(descriptor, encoded)
                os.fsync(descriptor)
                return str(record["record_hash"])
            finally:
                _unlock(descriptor)
        finally:
            os.close(descriptor)

    def verify(self, *, expected_root: str | None = None) -> LedgerVerificationReport:
        """Verify every canonical record and optionally require a known root."""

        if expected_root is not None and not _is_hash(expected_root):
            return LedgerVerificationReport(False, 0, None, None, ("INVALID_EXPECTED_ROOT",))
        try:
            data = _read_path(self.path)
        except (OSError, ValueError) as exc:
            return LedgerVerificationReport(False, 0, None, None, (_error_code(exc),))
        report, _, _ = _verify_data(data)
        if report.valid and expected_root is not None and report.root_hash != expected_root:
            return LedgerVerificationReport(
                False,
                report.records,
                report.root_hash,
                None,
                ("EXPECTED_ROOT_MISMATCH",),
            )
        return report

    def verify_prefix(
        self,
        records: int,
        *,
        expected_root: str,
    ) -> LedgerVerificationReport:
        """Verify an immutable prefix retained by a receipt.

        A later append changes the current root, so receipts validate the exact
        prefix they were issued from rather than comparing against the live tip.
        """

        if isinstance(records, bool) or not isinstance(records, int) or records < 1:
            return LedgerVerificationReport(False, 0, None, None, ("INVALID_RECORD_RANGE",))
        if not _is_hash(expected_root):
            return LedgerVerificationReport(False, 0, None, None, ("INVALID_EXPECTED_ROOT",))
        try:
            lines = _read_path(self.path).splitlines(keepends=True)
        except (OSError, ValueError) as exc:
            return LedgerVerificationReport(False, 0, None, None, (_error_code(exc),))
        if len(lines) < records:
            return LedgerVerificationReport(False, len(lines), None, None, ("RANGE_UNAVAILABLE",))
        report, _, _ = _verify_data(b"".join(lines[:records]))
        if report.valid and report.root_hash != expected_root:
            return LedgerVerificationReport(
                False, report.records, report.root_hash, None, ("EXPECTED_ROOT_MISMATCH",)
            )
        return report

    def read_verified_payloads(self) -> tuple[LedgerVerificationReport, tuple[dict[str, Any], ...]]:
        """Return payloads only when the complete v3 chain verifies."""

        try:
            data = _read_path(self.path)
        except (OSError, ValueError) as exc:
            return LedgerVerificationReport(False, 0, None, None, (_error_code(exc),)), ()
        report, records, _ = _verify_data(data)
        if not report.valid:
            return report, ()
        return report, tuple(dict(record["payload"]) for record in records)


def migrate_v2_to_v3(source: Path, destination: Path) -> LedgerVerificationReport:
    """Deterministically convert safe v2 records into a new verified v3 chain."""

    source_path = Path(source)
    destination_path = Path(destination)
    _validate_file_path(source_path, allow_missing=False)
    _validate_parent_components(destination_path)
    if _path_exists(destination_path):
        raise FileExistsError(f"destination already exists: {destination_path}")
    _validate_file_path(destination_path, allow_missing=True)

    from .ledger import _read_decision_ledger_stream

    records = _read_decision_ledger_stream(StringIO(_read_path(source_path).decode("utf-8")))
    converted: list[dict[str, Any]] = []
    previous_hash: str | None = None
    for sequence, record in enumerate(records, start=1):
        payload = _canonical_payload(record)
        converted_record: dict[str, Any] = {
            "schema_version": GOVERNANCE_LEDGER_SCHEMA_VERSION,
            "sequence": sequence,
            "timestamp": record["timestamp"],
            "previous_hash": previous_hash,
            "payload": payload,
            "payload_hash": canonical_hash(payload),
        }
        converted_record["record_hash"] = canonical_hash(converted_record)
        previous_hash = str(converted_record["record_hash"])
        converted.append(converted_record)

    descriptor = _open_new_descriptor(destination_path)
    try:
        for record in converted:
            _write_all(descriptor, canonical_bytes(record) + b"\n")
        os.fsync(descriptor)
        data = _read_descriptor(descriptor)
    finally:
        os.close(descriptor)
    verification_report, _, _ = _verify_data(data)
    if verification_report.valid and verification_report.root_hash != previous_hash:
        return LedgerVerificationReport(
            False,
            verification_report.records,
            verification_report.root_hash,
            None,
            ("EXPECTED_ROOT_MISMATCH",),
        )
    return verification_report


def quarantine_invalid_records(source: Path, destination: Path) -> Path:
    """Copy the invalid suffix and a verification report without altering source."""

    source_path = Path(source)
    destination_path = Path(destination)
    _validate_file_path(source_path, allow_missing=False)
    _validate_parent_components(destination_path)
    if _path_exists(destination_path):
        raise FileExistsError(f"quarantine destination already exists: {destination_path}")
    data = _read_path(source_path)
    report, _, invalid_offset = _verify_data(data)
    if report.valid:
        raise ValueError("governance ledger is valid; nothing to quarantine")
    if invalid_offset is None:
        invalid_offset = 0
    quarantine_descriptor = _create_quarantine_directory(destination_path)
    try:
        _write_owner_only_at(quarantine_descriptor, "invalid-records.jsonl", data[invalid_offset:])
        _write_owner_only_at(
            quarantine_descriptor,
            "report.json",
            canonical_bytes(
                {
                    "valid": report.valid,
                    "records": report.records,
                    "root_hash": report.root_hash,
                    "first_invalid_sequence": report.first_invalid_sequence,
                    "error_codes": list(report.error_codes),
                }
            )
            + b"\n",
        )
    finally:
        os.close(quarantine_descriptor)
    return destination_path


def _canonical_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise TypeError("governance payload must be a mapping")
    normalized = _json_value(payload, "payload")
    if not isinstance(normalized, dict):
        raise TypeError("governance payload must be an object")
    return normalized


def _json_value(value: Any, name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{name} must not contain non-finite numbers")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item, name) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{name} mapping keys must be strings")
            if _private_key(key):
                raise ValueError(f"{name} must not contain private field {key!r}")
            normalized[key] = _json_value(item, name)
        return normalized
    raise TypeError(f"{name} must contain only canonical JSON values")


def _private_key(key: str) -> bool:
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    terms = {part for part in re.split(r"[^a-z0-9]+", separated.casefold()) if part}
    return bool(
        terms
        & {
            "auth",
            "authorization",
            "command",
            "commands",
            "credential",
            "credentials",
            "output",
            "outputs",
            "prompt",
            "prompts",
            "raw",
            "response",
            "responses",
            "secret",
            "secrets",
            "source",
            "sources",
            "transcript",
            "transcripts",
        }
    )


def _verify_data(
    data: bytes,
) -> tuple[LedgerVerificationReport, list[dict[str, Any]], int | None]:
    if not data:
        return LedgerVerificationReport(True, 0, None, None, ()), [], None
    records: list[dict[str, Any]] = []
    previous_hash: str | None = None
    offset = 0
    for expected_sequence, raw_line in enumerate(data.splitlines(keepends=True), start=1):
        line_offset = offset
        offset += len(raw_line)
        if not raw_line.endswith(b"\n"):
            return _invalid(
                records, previous_hash, expected_sequence, "NONCANONICAL_LINE", line_offset
            )
        raw_value = raw_line[:-1]
        try:
            value = json.loads(raw_value)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _invalid(records, previous_hash, expected_sequence, "INVALID_JSON", line_offset)
        if not isinstance(value, dict):
            return _invalid(
                records, previous_hash, expected_sequence, "INVALID_RECORD", line_offset
            )
        try:
            if canonical_bytes(value) != raw_value:
                return _invalid(
                    records, previous_hash, expected_sequence, "NONCANONICAL_LINE", line_offset
                )
            _validate_record(value, expected_sequence, previous_hash)
        except (TypeError, ValueError) as exc:
            return _invalid(
                records, previous_hash, expected_sequence, _error_code(exc), line_offset
            )
        records.append(value)
        previous_hash = str(value["record_hash"])
    return LedgerVerificationReport(True, len(records), previous_hash, None, ()), records, None


def _invalid(
    records: list[dict[str, Any]],
    root_hash: str | None,
    sequence: int,
    code: str,
    offset: int,
) -> tuple[LedgerVerificationReport, list[dict[str, Any]], int]:
    return (
        LedgerVerificationReport(False, len(records), root_hash, sequence, (code,)),
        records,
        offset,
    )


def _validate_record(record: dict[str, Any], sequence: int, previous_hash: str | None) -> None:
    expected_keys = {
        "schema_version",
        "sequence",
        "timestamp",
        "previous_hash",
        "payload",
        "payload_hash",
        "record_hash",
    }
    if set(record) != expected_keys:
        raise ValueError("INVALID_RECORD")
    if (
        type(record["schema_version"]) is not str
        or record["schema_version"] != GOVERNANCE_LEDGER_SCHEMA_VERSION
    ):
        raise ValueError("UNSUPPORTED_SCHEMA")
    if type(record["sequence"]) is not int:
        raise ValueError("INVALID_RECORD")
    if record["sequence"] != sequence:
        raise ValueError("SEQUENCE_GAP")
    if record["previous_hash"] is not None and not _is_hash(record["previous_hash"]):
        raise ValueError("INVALID_RECORD")
    if record["previous_hash"] != previous_hash:
        raise ValueError("PREVIOUS_HASH_MISMATCH")
    timestamp = record["timestamp"]
    if not isinstance(timestamp, str):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if parsed_timestamp.tzinfo is None:
        raise ValueError("INVALID_TIMESTAMP")
    payload = _canonical_payload(record["payload"])
    if payload != record["payload"]:
        raise ValueError("INVALID_PAYLOAD")
    if not _is_hash(record["payload_hash"]) or not _is_hash(record["record_hash"]):
        raise ValueError("INVALID_RECORD")
    if record["payload_hash"] != canonical_hash(payload):
        raise ValueError("PAYLOAD_HASH_MISMATCH")
    without_hash = {key: value for key, value in record.items() if key != "record_hash"}
    if record["record_hash"] != canonical_hash(without_hash):
        raise ValueError("RECORD_HASH_MISMATCH")


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _validate_parent_components(path: Path) -> None:
    """Require an absolute lexical path with no traversal or symlinked parent."""

    if not path.is_absolute():
        raise ValueError("governance ledger path must be absolute")
    if ".." in path.parts:
        raise ValueError("governance ledger path must not contain traversal components")
    current = Path(path.anchor)
    for component in path.parts[1:-1]:
        current /= component
        try:
            details = current.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(details.st_mode):
            raise ValueError("governance ledger path must not have a symbolic-link parent")
        if not stat.S_ISDIR(details.st_mode):
            raise ValueError("governance ledger path parent must be a directory")


def _path_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _validate_file_path(path: Path, *, allow_missing: bool) -> None:
    _validate_parent_components(path)
    try:
        details = path.lstat()
    except FileNotFoundError:
        if allow_missing:
            return
        raise
    if stat.S_ISLNK(details.st_mode):
        raise ValueError("governance ledger path must not be a symbolic link")
    if not stat.S_ISREG(details.st_mode):
        raise ValueError("governance ledger path must be a regular file")
    if os.name != "nt" and details.st_mode & _OWNER_ONLY_MASK:
        raise PermissionError("governance ledger file must not be accessible by group or others")


def _read_path(path: Path) -> bytes:
    _validate_file_path(path, allow_missing=False)
    descriptor = _open_leaf_descriptor(path, os.O_RDONLY, create_parents=False)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("governance ledger path must be a regular file")
        return _read_descriptor(descriptor)
    finally:
        os.close(descriptor)


def _open_append_descriptor(path: Path) -> int:
    _validate_file_path(path, allow_missing=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    descriptor = _open_leaf_descriptor(path, flags, create_parents=True)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("governance ledger path must be a regular file")
        if os.name != "nt" and details.st_mode & _OWNER_ONLY_MASK:
            raise PermissionError(
                "governance ledger file must not be accessible by group or others"
            )
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_new_descriptor(path: Path) -> int:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    descriptor = _open_leaf_descriptor(path, flags, create_parents=True)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("governance ledger path must be a regular file")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _read_descriptor(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 64 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError("write made no progress")
        offset += written


def _write_owner_only_at(directory_descriptor: int, name: str, data: bytes) -> None:
    _require_directory_fd_safety()
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_descriptor,
    )
    try:
        _write_all(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _open_leaf_descriptor(path: Path, flags: int, *, create_parents: bool) -> int:
    """Open a regular ledger leaf relative to a nofollow directory descriptor."""

    directory_descriptor = _open_parent_directory(path, create_parents=create_parents)
    try:
        return os.open(
            path.name,
            flags | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_descriptor,
        )
    finally:
        os.close(directory_descriptor)


def _create_quarantine_directory(path: Path) -> int:
    """Create and hold the quarantine directory through descriptor-relative writes."""

    directory_descriptor = _open_parent_directory(path, create_parents=True)
    try:
        os.mkdir(path.name, mode=0o700, dir_fd=directory_descriptor)
        return os.open(
            path.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=directory_descriptor,
        )
    finally:
        os.close(directory_descriptor)


def _open_parent_directory(path: Path, *, create_parents: bool) -> int:
    """Walk every parent by descriptor, rejecting swaps and symbolic links."""

    _require_directory_fd_safety()
    _validate_parent_components(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags)
    try:
        for component in path.parts[1:-1]:
            try:
                child_descriptor = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create_parents:
                    raise
                os.mkdir(component, mode=0o700, dir_fd=descriptor)
                child_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _require_directory_fd_safety() -> None:
    """Fail closed when the platform cannot safely anchor path traversal."""

    required_flags = (getattr(os, "O_DIRECTORY", 0), getattr(os, "O_NOFOLLOW", 0))
    if (
        not all(required_flags)
        or not _OPEN_SUPPORTS_DIRECTORY_FD
        or not _MKDIR_SUPPORTS_DIRECTORY_FD
    ):
        raise OSError("secure directory descriptor operations are unavailable")


def _lock_exclusive(descriptor: int) -> None:
    try:
        import fcntl
    except ImportError as exc:
        raise OSError("OS-level file locking is unavailable") from exc
    fcntl.flock(descriptor, fcntl.LOCK_EX)


def _unlock(descriptor: int) -> None:
    try:
        import fcntl
    except ImportError:
        return
    fcntl.flock(descriptor, fcntl.LOCK_UN)


def _error_code(exc: BaseException) -> str:
    message = str(exc)
    known = {
        "INVALID_RECORD",
        "UNSUPPORTED_SCHEMA",
        "SEQUENCE_GAP",
        "PREVIOUS_HASH_MISMATCH",
        "INVALID_TIMESTAMP",
        "INVALID_PAYLOAD",
        "PAYLOAD_HASH_MISMATCH",
        "RECORD_HASH_MISMATCH",
    }
    return message if message in known else "IO_ERROR"
