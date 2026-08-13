"""User-facing Codex integration management commands."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .installer import inspect_codex
from .promotion import PromotionReceipt


def default_data_dir() -> Path:
    plugin_data = os.environ.get("PLUGIN_DATA")
    if plugin_data:
        return Path(plugin_data).resolve()
    return Path.home() / ".local" / "share" / "marginal" / "codex"


def _state_path(data_dir: Path) -> Path:
    return data_dir / "state.json"


def _read_state(data_dir: Path) -> dict[str, Any]:
    path = _state_path(data_dir)
    if not path.exists():
        return {
            "schema_version": 1,
            "mode": "shadow",
            "capability": "Tool Enforcement",
            "reason": "Earned Enforcement evidence not yet promoted",
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Codex state must be a JSON object")
    return payload


def _write_state(data_dir: Path, payload: dict[str, Any]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = _state_path(data_dir)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    if os.name == "posix":
        temporary.chmod(0o600)
    os.replace(temporary, path)


def _emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")


def codex_command(
    command: str,
    *,
    data_dir: str | Path | None = None,
    as_json: bool = False,
) -> int:
    root = Path(data_dir).resolve() if data_dir is not None else default_data_dir()
    if command == "status":
        _emit(_read_state(root), as_json=as_json)
        return 0
    if command == "doctor":
        _emit(inspect_codex().to_dict(), as_json=as_json)
        return 0
    if command == "review":
        payload = {
            **_read_state(root),
            "review_command": "/hooks",
            "message": "Review and trust the exact MARGINAL hook commands in Codex.",
        }
        _emit(payload, as_json=as_json)
        return 0
    if command == "demote":
        payload = {
            "schema_version": 1,
            "mode": "shadow",
            "capability": "Tool Enforcement",
            "reason": "Explicit user demotion",
        }
        _write_state(root, payload)
        _emit(payload, as_json=as_json)
        return 0
    if command == "promote":
        receipt_path = root / "promotion-receipt.json"
        if not receipt_path.exists():
            payload = {
                "mode": "shadow",
                "error_code": "EVIDENCE_NOT_READY",
                "message": "No ready Earned Enforcement receipt exists.",
            }
            _emit(payload, as_json=as_json)
            return 2
        receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt = PromotionReceipt.from_dict(receipt_payload)
        if not receipt.is_ready or not receipt.verify_hash():
            payload = {
                "mode": "shadow",
                "error_code": "EVIDENCE_NOT_READY",
                "blocking_reasons": list(receipt.blocking_reasons),
            }
            _emit(payload, as_json=as_json)
            return 2
        payload = {
            "schema_version": 1,
            "mode": "enforce",
            "capability": "Tool Enforcement",
            "receipt_hash": receipt.receipt_hash,
            "reason": "Explicit promotion with a ready evidence receipt",
        }
        _write_state(root, payload)
        _emit(payload, as_json=as_json)
        return 0
    raise ValueError(f"unsupported Codex command: {command}")


def purge_data(data_dir: str | Path, *, confirmed: bool) -> bool:
    if not confirmed:
        return False
    root = Path(data_dir).resolve()
    if root.exists():
        shutil.rmtree(root)
    return True

