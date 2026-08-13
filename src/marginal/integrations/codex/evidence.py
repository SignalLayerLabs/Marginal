"""Bounded, local-only evidence storage for Codex governance receipts."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_ALLOWED_EVIDENCE_FIELDS = {
    "schema_version",
    "event",
    "session_hash",
    "action_hash",
    "semantic_key",
    "state_hash",
    "evidence_hash",
    "outcome",
    "reason_code",
    "latency_ms",
    "covered",
    "coverable",
    "recommended_stop",
    "reviewed",
    "false_stop",
    "integration_failure",
    "pending",
    "timestamp",
}
_FORBIDDEN_FIELDS = {
    "auth",
    "command",
    "credential",
    "prompt",
    "source",
    "tool_input",
    "tool_response",
    "transcript",
}


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("evidence must be canonical JSON") from exc


class EvidenceStore:
    """Append redacted JSONL records and atomically persist small checkpoints."""

    def __init__(self, root: str | Path, *, max_record_bytes: int = 16_384) -> None:
        if isinstance(max_record_bytes, bool) or not isinstance(max_record_bytes, int):
            raise TypeError("max_record_bytes must be an integer")
        if max_record_bytes < 128:
            raise ValueError("max_record_bytes must be at least 128")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            self.root.chmod(0o700)
        self.path = self.root / "evidence.jsonl"
        self.checkpoint_path = self.root / "checkpoint.json"
        self.max_record_bytes = max_record_bytes

    def append(self, record: Mapping[str, Any]) -> None:
        if not isinstance(record, Mapping):
            raise TypeError("evidence record must be a mapping")
        fields = set(record)
        forbidden = fields & _FORBIDDEN_FIELDS
        if forbidden:
            raise ValueError(f"forbidden evidence field: {sorted(forbidden)[0]}")
        unsupported = fields - _ALLOWED_EVIDENCE_FIELDS
        if unsupported:
            raise ValueError(f"unsupported evidence field: {sorted(unsupported)[0]}")
        serialized = _canonical_bytes(record)
        if len(serialized) > self.max_record_bytes:
            raise ValueError("evidence record is too large")
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, serialized + b"\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if os.name == "posix":
            self.path.chmod(0o600)

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("evidence record must decode to an object")
                records.append(value)
        return records

    def write_checkpoint(self, checkpoint: Mapping[str, Any]) -> None:
        if not isinstance(checkpoint, Mapping):
            raise TypeError("checkpoint must be a mapping")
        serialized = _canonical_bytes(checkpoint)
        if len(serialized) > self.max_record_bytes:
            raise ValueError("checkpoint is too large")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".checkpoint-", suffix=".tmp", dir=self.root
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            os.write(descriptor, serialized + b"\n")
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, self.checkpoint_path)
            if os.name == "posix":
                self.checkpoint_path.chmod(0o600)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)

    def read_checkpoint(self) -> dict[str, Any] | None:
        if not self.checkpoint_path.exists():
            return None
        value = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("checkpoint must decode to an object")
        return value

