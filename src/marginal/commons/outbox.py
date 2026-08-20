"""Durable owner-only queue for closed Commons evidence envelopes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ._storage import atomic_create_at, locked_directory, read_bounded_at
from .evidence import (
    ActionKind,
    AggregateReasonCode,
    CommonsEvidenceAtom,
    CommonsEvidenceBatch,
    DecisionClass,
    OutcomeClass,
    RecordType,
    ValueBucket,
)
from .identity import is_canonical_namespace, resolve_canonical_namespace

_MAX_QUEUE_BYTES = 512 * 1024
_MAX_ATOMS = 1_000
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_ENTRY_NAME_PATTERN = re.compile(r"^queue-[0-9a-f]{32}\.json$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("queued Commons record contains a duplicate field")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class OutboxEntry:
    """One validated queued envelope plus local-only retry metadata."""

    name: str
    retry_token: str
    body_bytes: bytes
    canonical_record: bytes
    record_sha256: str
    device: int
    inode: int
    export_receipt: str | None = None

    def body(self) -> bytes:
        """Serialize only the closed wire envelope, excluding local metadata."""

        return self.body_bytes

    @property
    def envelope(self) -> dict[str, object]:
        """Return a fresh mapping decoded from immutable canonical body bytes."""

        return cast(dict[str, object], json.loads(self.body_bytes.decode("utf-8")))

    @property
    def model_namespace(self) -> str:
        """Return the exact model namespace bound into canonical body bytes."""

        return cast(str, self.envelope["model_namespace"])


@dataclass(frozen=True, slots=True)
class OutboxScan:
    """Bounded valid entries plus the count of malformed leaves quarantined."""

    entries: tuple[OutboxEntry, ...]
    quarantined: int = 0


def _atom_from_mapping(raw: object, *, model_namespace: str) -> CommonsEvidenceAtom:
    expected = {
        "record_type",
        "action_kind",
        "cost_bucket",
        "gain_bucket",
        "recommendation",
        "applied_decision",
        "reason_code",
        "outcome_class",
        "count",
        "minimum_group_size",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("queued Commons atom has an invalid shape")
    identity = resolve_canonical_namespace(model_namespace)
    if identity is None:
        raise ValueError("queued Commons atom has an invalid model")
    try:
        return CommonsEvidenceAtom(
            model_identity=identity,
            record_type=RecordType(raw["record_type"]),
            action_kind=ActionKind(raw["action_kind"]),
            cost_bucket=ValueBucket(raw["cost_bucket"]),
            gain_bucket=ValueBucket(raw["gain_bucket"]),
            recommendation=DecisionClass(raw["recommendation"]),
            applied_decision=DecisionClass(raw["applied_decision"]),
            reason_code=AggregateReasonCode(raw["reason_code"]),
            outcome_class=OutcomeClass(raw["outcome_class"]),
            count=raw["count"],
            minimum_group_size=raw["minimum_group_size"],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("queued Commons atom has an invalid value") from exc


def _validate_envelope(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "model_namespace", "atoms"}:
        raise ValueError("queued Commons envelope has an invalid shape")
    namespace = raw["model_namespace"]
    atoms = raw["atoms"]
    if raw["schema_version"] != "1.0" or not is_canonical_namespace(namespace):
        raise ValueError("queued Commons envelope is incompatible")
    if not isinstance(atoms, list) or not 1 <= len(atoms) <= _MAX_ATOMS:
        raise ValueError("queued Commons envelope must contain bounded evidence")
    assert isinstance(namespace, str)
    parsed = [_atom_from_mapping(atom, model_namespace=namespace).to_dict() for atom in atoms]
    return {"schema_version": "1.0", "model_namespace": namespace, "atoms": parsed}


def _parse_queue_record(raw: bytes, *, name: str, device: int, inode: int) -> OutboxEntry:
    if _ENTRY_NAME_PATTERN.fullmatch(name) is None:
        raise ValueError("queued Commons record name is invalid")
    try:
        payload: Any = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("queued Commons record is malformed") from exc
    if not isinstance(payload, dict) or set(payload) not in (
        {"retry_token", "envelope"},
        {"retry_token", "envelope", "export_receipt"},
    ):
        raise ValueError("queued Commons record has an invalid shape")
    retry_token = payload["retry_token"]
    if not isinstance(retry_token, str) or _TOKEN_PATTERN.fullmatch(retry_token) is None:
        raise ValueError("queued Commons retry token is invalid")
    export_receipt = payload.get("export_receipt")
    if export_receipt is not None and (
        not isinstance(export_receipt, str) or _DIGEST_PATTERN.fullmatch(export_receipt) is None
    ):
        raise ValueError("queued Commons export receipt is invalid")
    envelope = _validate_envelope(payload["envelope"])
    body_bytes = (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")
    canonical_record = (
        json.dumps(
            {
                "envelope": envelope,
                "retry_token": retry_token,
                **({"export_receipt": export_receipt} if export_receipt is not None else {}),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    return OutboxEntry(
        name=name,
        retry_token=retry_token,
        body_bytes=body_bytes,
        canonical_record=canonical_record,
        record_sha256=hashlib.sha256(canonical_record).hexdigest(),
        device=device,
        inode=inode,
        export_receipt=export_receipt,
    )


def _entry_boundary_valid(entry: object) -> bool:
    if not isinstance(entry, OutboxEntry):
        return False
    if (
        _ENTRY_NAME_PATTERN.fullmatch(entry.name) is None
        or _TOKEN_PATTERN.fullmatch(entry.retry_token) is None
        or not isinstance(entry.body_bytes, bytes)
        or not isinstance(entry.canonical_record, bytes)
        or _DIGEST_PATTERN.fullmatch(entry.record_sha256) is None
        or hashlib.sha256(entry.canonical_record).hexdigest() != entry.record_sha256
        or len(entry.canonical_record) > _MAX_QUEUE_BYTES
    ):
        return False
    try:
        rebound = _parse_queue_record(
            entry.canonical_record,
            name=entry.name,
            device=entry.device,
            inode=entry.inode,
        )
    except (UnicodeDecodeError, ValueError, RecursionError, MemoryError, OverflowError):
        return False
    return rebound == entry


class CommonsOutbox:
    """Queue, recover, acknowledge, and quarantine exact evidence files."""

    def __init__(self, data_dir: str | Path) -> None:
        root = Path(data_dir)
        if ".." in root.parts:
            raise ValueError("Commons outbox path must not contain traversal")
        absolute = root if root.is_absolute() else Path.cwd() / root
        base = absolute / "commons" / "outbox"
        self.queue_path = base / "queue"
        self.quarantine_path = base / "quarantine"

    def enqueue(
        self,
        *,
        batch: CommonsEvidenceBatch,
        export_receipt: str | None = None,
    ) -> OutboxEntry | None:
        """Atomically queue nonempty typed evidence with one random retry token."""

        if not isinstance(batch, CommonsEvidenceBatch) or not batch.atoms:
            return None
        if len(batch.atoms) > _MAX_ATOMS:
            return None
        if export_receipt is not None and _DIGEST_PATTERN.fullmatch(export_receipt) is None:
            raise ValueError("Commons export receipt is invalid")
        envelope: dict[str, object] = {
            "schema_version": "1.0",
            "model_namespace": batch.model_namespace,
            "atoms": [atom.to_dict() for atom in batch.atoms],
        }
        retry_token = secrets.token_urlsafe(32)
        encoded = (
            json.dumps(
                {
                    "envelope": envelope,
                    "retry_token": retry_token,
                    **({"export_receipt": export_receipt} if export_receipt is not None else {}),
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
        if len(encoded) > _MAX_QUEUE_BYTES:
            return None
        with locked_directory(self.queue_path, create=True, lock_name=".outbox.lock") as directory:
            if export_receipt is not None:
                for existing_name in os.listdir(directory):
                    if existing_name.startswith("."):
                        continue
                    try:
                        raw, metadata = read_bounded_at(
                            directory,
                            existing_name,
                            maximum_bytes=_MAX_QUEUE_BYTES,
                            label="Commons outbox entry",
                        )
                        existing = _parse_queue_record(
                            raw,
                            name=existing_name,
                            device=metadata.st_dev,
                            inode=metadata.st_ino,
                        )
                    except (OSError, ValueError):
                        continue
                    if existing.export_receipt == export_receipt:
                        return existing
            for _ in range(16):
                name = f"queue-{secrets.token_hex(16)}.json"
                try:
                    metadata = atomic_create_at(
                        directory,
                        name,
                        encoded,
                        temporary_prefix=".outbox-",
                        label="Commons outbox entry",
                    )
                except FileExistsError:
                    continue
                return _parse_queue_record(
                    encoded,
                    name=name,
                    device=metadata.st_dev,
                    inode=metadata.st_ino,
                )
        raise FileExistsError("unable to allocate a unique Commons outbox entry")

    def _quarantine_name(self, queue_descriptor: int, name: str) -> bool:
        with locked_directory(
            self.quarantine_path, create=True, lock_name=".quarantine.lock"
        ) as quarantine_descriptor:
            for _ in range(16):
                target = f"quarantine-{secrets.token_hex(16)}.json"
                try:
                    os.stat(target, dir_fd=quarantine_descriptor, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    continue
                try:
                    os.rename(
                        name,
                        target,
                        src_dir_fd=queue_descriptor,
                        dst_dir_fd=quarantine_descriptor,
                    )
                except FileNotFoundError:
                    return False
                os.fsync(queue_descriptor)
                os.fsync(quarantine_descriptor)
                return True
        raise FileExistsError("unable to allocate a Commons quarantine entry")

    def pending(self, *, limit: int = 8) -> OutboxScan:
        """Return bounded valid work and quarantine malformed leaves during the scan."""

        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 1_000:
            raise ValueError("Commons outbox scan limit must be between 1 and 1000")
        try:
            context = locked_directory(self.queue_path, create=False, lock_name=".outbox.lock")
            with context as directory:
                entries: list[OutboxEntry] = []
                quarantined = 0
                names = sorted(
                    name
                    for name in os.listdir(directory)
                    if isinstance(name, str) and not name.startswith(".")
                )
                for name in names[: limit * 4 + 16]:
                    try:
                        raw, metadata = read_bounded_at(
                            directory,
                            name,
                            maximum_bytes=_MAX_QUEUE_BYTES,
                            label="Commons outbox entry",
                        )
                        entry = _parse_queue_record(
                            raw, name=name, device=metadata.st_dev, inode=metadata.st_ino
                        )
                    except (OSError, ValueError, RecursionError, MemoryError, OverflowError):
                        quarantined += int(self._quarantine_name(directory, name))
                        continue
                    if len(entries) < limit:
                        entries.append(entry)
                return OutboxScan(tuple(entries), quarantined)
        except FileNotFoundError:
            return OutboxScan(())

    def _matches(self, directory: int, entry: OutboxEntry) -> bool:
        if not _entry_boundary_valid(entry):
            return False
        try:
            raw, metadata = read_bounded_at(
                directory,
                entry.name,
                maximum_bytes=_MAX_QUEUE_BYTES,
                label="Commons outbox entry",
            )
            rebound = _parse_queue_record(
                raw,
                name=entry.name,
                device=metadata.st_dev,
                inode=metadata.st_ino,
            )
        except (
            FileNotFoundError,
            OSError,
            ValueError,
            RecursionError,
            MemoryError,
            OverflowError,
        ):
            return False
        return rebound == entry

    def ack(self, entry: OutboxEntry) -> bool:
        """Delete only the exact inode whose valid envelope received an ACK."""

        if not _entry_boundary_valid(entry):
            return False
        try:
            with locked_directory(
                self.queue_path, create=False, lock_name=".outbox.lock"
            ) as directory:
                if not self._matches(directory, entry):
                    return False
                os.unlink(entry.name, dir_fd=directory)
                os.fsync(directory)
                return True
        except FileNotFoundError:
            return False

    def quarantine(self, entry: OutboxEntry) -> bool:
        """Move only the exact inode to the owner-only quarantine directory."""

        if not _entry_boundary_valid(entry):
            return False
        try:
            with locked_directory(
                self.queue_path, create=False, lock_name=".outbox.lock"
            ) as directory:
                if not self._matches(directory, entry):
                    return False
                return self._quarantine_name(directory, entry.name)
        except FileNotFoundError:
            return False
