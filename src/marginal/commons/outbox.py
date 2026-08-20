"""Durable owner-only queue for closed Commons evidence envelopes."""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._storage import atomic_create_at, locked_directory, read_bounded_at
from .evidence import (
    ActionKind,
    AggregateReasonCode,
    CommonsEvidenceAtom,
    DecisionClass,
    OutcomeClass,
    RecordType,
    ValueBucket,
)
from .identity import is_canonical_namespace

_MAX_QUEUE_BYTES = 512 * 1024
_MAX_ATOMS = 1_000
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


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
    envelope: dict[str, object]
    device: int
    inode: int

    def body(self) -> bytes:
        """Serialize only the closed wire envelope, excluding local metadata."""

        return (
            json.dumps(self.envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class OutboxScan:
    """Bounded valid entries plus the count of malformed leaves quarantined."""

    entries: tuple[OutboxEntry, ...]
    quarantined: int = 0


def _atom_from_mapping(raw: object) -> CommonsEvidenceAtom:
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
    try:
        return CommonsEvidenceAtom(
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
    parsed = [_atom_from_mapping(atom).to_dict() for atom in atoms]
    return {"schema_version": "1.0", "model_namespace": namespace, "atoms": parsed}


def _parse_queue_record(raw: bytes, *, name: str, device: int, inode: int) -> OutboxEntry:
    try:
        payload: Any = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("queued Commons record is malformed") from exc
    if not isinstance(payload, dict) or set(payload) != {"retry_token", "envelope"}:
        raise ValueError("queued Commons record has an invalid shape")
    retry_token = payload["retry_token"]
    if not isinstance(retry_token, str) or _TOKEN_PATTERN.fullmatch(retry_token) is None:
        raise ValueError("queued Commons retry token is invalid")
    envelope = _validate_envelope(payload["envelope"])
    return OutboxEntry(name, retry_token, envelope, device, inode)


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
        model_namespace: str,
        atoms: tuple[CommonsEvidenceAtom, ...],
    ) -> OutboxEntry | None:
        """Atomically queue nonempty typed evidence with one random retry token."""

        if not is_canonical_namespace(model_namespace) or not atoms:
            return None
        if len(atoms) > _MAX_ATOMS or not all(
            isinstance(atom, CommonsEvidenceAtom) for atom in atoms
        ):
            return None
        envelope: dict[str, object] = {
            "schema_version": "1.0",
            "model_namespace": model_namespace,
            "atoms": [atom.to_dict() for atom in atoms],
        }
        retry_token = secrets.token_urlsafe(32)
        record = {"envelope": envelope, "retry_token": retry_token}
        encoded = (
            json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        ).encode("utf-8")
        if len(encoded) > _MAX_QUEUE_BYTES:
            return None
        with locked_directory(self.queue_path, create=True, lock_name=".outbox.lock") as directory:
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
                return OutboxEntry(
                    name=name,
                    retry_token=retry_token,
                    envelope=envelope,
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
                    except (OSError, ValueError):
                        quarantined += int(self._quarantine_name(directory, name))
                        continue
                    if len(entries) < limit:
                        entries.append(entry)
                return OutboxScan(tuple(entries), quarantined)
        except FileNotFoundError:
            return OutboxScan(())

    def _matches(self, directory: int, entry: OutboxEntry) -> bool:
        try:
            _, metadata = read_bounded_at(
                directory,
                entry.name,
                maximum_bytes=_MAX_QUEUE_BYTES,
                label="Commons outbox entry",
            )
        except (FileNotFoundError, OSError, ValueError):
            return False
        return (metadata.st_dev, metadata.st_ino) == (entry.device, entry.inode)

    def ack(self, entry: OutboxEntry) -> bool:
        """Delete only the exact inode whose valid envelope received an ACK."""

        if not isinstance(entry, OutboxEntry):
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

        if not isinstance(entry, OutboxEntry):
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
