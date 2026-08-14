"""Schema-versioned decision evidence for MARGINAL learning loops."""

from __future__ import annotations

import json
import os
import stat
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO, cast

from .outcomes import Outcome
from .privacy import (
    LocalPseudonymizer,
    PrivacyProfile,
    aggregate_ledger_records,
    load_or_create_privacy_key,
    sanitize_ledger_record,
    validate_safe_telemetry_record,
)

LEDGER_SCHEMA_VERSION = "2.0"


@dataclass(frozen=True, slots=True)
class DecisionLedgerContext:
    """Stable correlation fields applied to every ledger event."""

    run_id: str
    task_id: str = ""
    trajectory_id: str = ""
    engine: str = ""
    model: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        for name in ("task_id", "trajectory_id", "engine", "model"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be a string")

    def to_dict(self) -> dict[str, str]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "trajectory_id": self.trajectory_id,
            "engine": self.engine,
            "model": self.model,
        }


class JsonlDecisionLedger:
    """Append-only JSONL ledger with explicit schema and correlation identity."""

    _RESERVED_FIELDS = frozenset(
        {
            "schema_version",
            "event_id",
            "sequence",
            "timestamp",
            "run_id",
            "task_id",
            "trajectory_id",
            "engine",
            "model",
            "privacy_profile",
        }
    )

    def __init__(
        self,
        path: str | Path,
        *,
        context: DecisionLedgerContext,
        privacy_profile: PrivacyProfile | str = PrivacyProfile.LOCAL_FULL,
        privacy_key: bytes | None = None,
        privacy_key_path: str | Path | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _validate_append_target(self.path)
        self.context = context
        self.privacy_profile = PrivacyProfile.parse(privacy_profile)
        if self.privacy_profile is PrivacyProfile.AGGREGATE_EXPORT:
            raise ValueError(
                "aggregate_export is not an operational ledger profile; use export_decision_ledger"
            )
        if privacy_key is not None and privacy_key_path is not None:
            raise ValueError("provide privacy_key or privacy_key_path, not both")
        self.privacy_key_path: Path | None = None
        self._pseudonymizer: LocalPseudonymizer | None = None
        if self.privacy_profile is PrivacyProfile.SAFE_TELEMETRY:
            if privacy_key is None:
                selected_path = (
                    Path(privacy_key_path)
                    if privacy_key_path is not None
                    else self.path.with_name(f".{self.path.name}.privacy.key")
                )
                privacy_key = load_or_create_privacy_key(selected_path)
                self.privacy_key_path = selected_path
            self._pseudonymizer = LocalPseudonymizer(privacy_key)
        elif privacy_key is not None or privacy_key_path is not None:
            raise ValueError("privacy keys are only valid with safe_telemetry")
        self._lock = threading.Lock()
        self._sequence = self._existing_sequence()

    def emit(self, event: Mapping[str, Any]) -> None:
        if not isinstance(event, Mapping):
            raise TypeError("ledger events must be mappings")
        event_name = event.get("event")
        if not isinstance(event_name, str) or not event_name.strip():
            raise ValueError("ledger events require a non-empty event name")
        reserved = self._RESERVED_FIELDS.intersection(event)
        if reserved:
            names = ", ".join(sorted(reserved))
            raise ValueError(f"event cannot override reserved ledger fields: {names}")
        if event_name == "outcome" and self.context.task_id:
            outcome = event.get("outcome")
            if not isinstance(outcome, Mapping):
                raise ValueError("outcome events require an outcome object")
            if outcome.get("task_id") != self.context.task_id:
                raise ValueError("outcome task_id does not match the decision ledger context")
        with self._lock:
            next_sequence = self._sequence + 1
            full_record = {
                "schema_version": LEDGER_SCHEMA_VERSION,
                "privacy_profile": self.privacy_profile.value,
                "event_id": str(uuid.uuid4()),
                "sequence": next_sequence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **self.context.to_dict(),
                **dict(event),
            }
            record = sanitize_ledger_record(
                full_record,
                profile=self.privacy_profile,
                pseudonymizer=self._pseudonymizer,
            )
            encoded = json.dumps(
                record,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            with _open_owner_only_text(self.path, append=True) as stream:
                stream.write(encoded + "\n")
                stream.flush()
            self._sequence = next_sequence

    def record_outcome(self, outcome: Outcome) -> None:
        if not isinstance(outcome, Outcome):
            raise TypeError("outcome must be Outcome")
        self.emit({"event": "outcome", "outcome": outcome.to_dict()})

    def _existing_sequence(self) -> int:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return 0
        records = read_decision_ledger(self.path)
        return int(records[-1]["sequence"])


def read_decision_ledger(path: str | Path) -> list[dict[str, Any]]:
    """Load and structurally validate a MARGINAL v2 decision ledger."""

    ledger_path = Path(path)
    with _open_readonly_text(ledger_path) as stream:
        return _read_decision_ledger_stream(stream)


def _read_decision_ledger_stream(stream: TextIO) -> list[dict[str, Any]]:
    """Validate v2 ledger data from an already-secured text stream."""

    records: list[dict[str, Any]] = []
    previous_sequence = 0
    for line_number, raw in enumerate(stream, start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid ledger JSON on line {line_number}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"ledger record on line {line_number} must be an object")
        if record.get("schema_version") != LEDGER_SCHEMA_VERSION:
            raise ValueError(f"unsupported ledger schema on line {line_number}")
        try:
            privacy_profile = PrivacyProfile.parse(record.get("privacy_profile", "local_full"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"unsupported privacy profile on line {line_number}") from exc
        if privacy_profile is PrivacyProfile.SAFE_TELEMETRY:
            try:
                validate_safe_telemetry_record(record)
            except ValueError as exc:
                raise ValueError(f"invalid safe telemetry on line {line_number}: {exc}") from exc
        for field_name in ("event_id", "timestamp", "run_id", "event"):
            value = record.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"ledger {field_name} missing or invalid on line {line_number}")
        for field_name in ("task_id", "trajectory_id", "engine", "model"):
            value = record.get(field_name, "")
            if not isinstance(value, str):
                raise ValueError(f"ledger {field_name} must be a string on line {line_number}")
        try:
            datetime.fromisoformat(record["timestamp"])
        except ValueError as exc:
            raise ValueError(f"ledger timestamp invalid on line {line_number}") from exc
        sequence = record.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise ValueError(f"invalid ledger sequence on line {line_number}")
        if sequence <= previous_sequence:
            raise ValueError(f"ledger sequence is not strictly increasing on line {line_number}")
        previous_sequence = sequence
        records.append(record)
    if not records:
        raise ValueError("decision ledger is empty")
    return records


def export_decision_ledger(
    source: str | Path,
    destination: str | Path,
    *,
    privacy_profile: PrivacyProfile | str,
    privacy_key: bytes | None = None,
    privacy_key_path: str | Path | None = None,
    minimum_group_size: int = 5,
) -> int:
    """Export a ledger with strict safe telemetry or grouped aggregate privacy."""

    selected = PrivacyProfile.parse(privacy_profile)
    if selected is PrivacyProfile.LOCAL_FULL:
        raise ValueError("ledger export requires safe_telemetry or aggregate_export")
    if privacy_key is not None and privacy_key_path is not None:
        raise ValueError("provide privacy_key or privacy_key_path, not both")

    source_path = Path(source)
    destination_path = Path(destination)
    if destination_path.exists():
        raise FileExistsError(f"destination already exists: {destination_path}")
    records = read_decision_ledger(source_path)

    if selected is PrivacyProfile.AGGREGATE_EXPORT:
        if privacy_key is not None or privacy_key_path is not None:
            raise ValueError("aggregate_export does not use a pseudonymization key")
        exported = aggregate_ledger_records(records, minimum_group_size=minimum_group_size)
    else:
        if privacy_key is None:
            selected_key_path = (
                Path(privacy_key_path)
                if privacy_key_path is not None
                else destination_path.with_name(f".{destination_path.name}.privacy.key")
            )
            privacy_key = load_or_create_privacy_key(selected_key_path)
        pseudonymizer = LocalPseudonymizer(privacy_key)
        exported = [
            sanitize_ledger_record(
                record,
                profile=PrivacyProfile.SAFE_TELEMETRY,
                pseudonymizer=pseudonymizer,
            )
            for record in records
        ]

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        stream = _open_owner_only_text(destination_path, exclusive=True)
        created = True
        with stream:
            for record in exported:
                stream.write(
                    json.dumps(
                        record,
                        sort_keys=True,
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                    + "\n"
                )
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if created:
            destination_path.unlink(missing_ok=True)
        raise
    return len(exported)


def _validate_append_target(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("decision ledger path must not be a symbolic link")
    if not path.exists():
        return
    details = path.stat()
    if not stat.S_ISREG(details.st_mode):
        raise ValueError("decision ledger path must be a regular file")
    if os.name != "nt" and details.st_mode & 0o077:
        raise PermissionError("decision ledger file must not be accessible by group or others")


def _open_readonly_text(path: Path) -> TextIO:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("decision ledger path must be a regular file")
        return os.fdopen(descriptor, "r", encoding="utf-8")
    except Exception:
        os.close(descriptor)
        raise


def _open_owner_only_text(path: Path, *, append: bool = False, exclusive: bool = False) -> TextIO:
    flags = os.O_WRONLY | os.O_CREAT
    mode = "w"
    if append:
        flags |= os.O_APPEND
        mode = "a"
    if exclusive:
        flags |= os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("decision ledger path must be a regular file")
        if os.name != "nt" and details.st_mode & 0o077:
            raise PermissionError("decision ledger file must not be accessible by group or others")
        return cast(TextIO, os.fdopen(descriptor, mode, encoding="utf-8"))
    except Exception:
        os.close(descriptor)
        raise


def summarize_decision_ledger(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize applied and recommended behavior without inferring causality."""

    authorizations = [record for record in records if record.get("event") == "authorization"]
    outcomes = [record for record in records if record.get("event") == "outcome"]
    commits = [
        record for record in records if record.get("event") in {"commit", "failure_settlement"}
    ]
    recommended_allowed = 0
    applied_allowed = 0
    overrides = 0
    for record in authorizations:
        decision = record.get("decision", {})
        if decision.get("recommended") is True:
            recommended_allowed += 1
        if decision.get("allowed") is True:
            applied_allowed += 1
        if decision.get("allowed") is True and decision.get("recommended") is False:
            overrides += 1
    last_usage = commits[-1].get("usage", {}) if commits else {}
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "events": len(records),
        "authorizations": len(authorizations),
        "recommended_allowed": recommended_allowed,
        "applied_allowed": applied_allowed,
        "nonblocking_overrides": overrides,
        "commits": len(commits),
        "outcomes": len(outcomes),
        "usage": last_usage,
        "run_ids": sorted({str(record.get("run_id", "")) for record in records}),
        "privacy_profiles": sorted(
            {str(record.get("privacy_profile", "local_full")) for record in records}
        ),
    }
