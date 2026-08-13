"""User-facing Codex integration management commands."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .evidence import EvidenceStore, summarize_evidence
from .identity import current_promotion_identity
from .installer import inspect_codex
from .promotion import (
    PromotionCriteria,
    activate_enforcement,
    demote_enforcement,
    evaluate_promotion,
    write_promotion_receipt,
)
from .service import read_mode


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
    workspace: str | Path | None = None,
    candidate: str | None = None,
    verdict: str | None = None,
    as_json: bool = False,
) -> int:
    root = Path(data_dir).resolve() if data_dir is not None else default_data_dir()
    selected_workspace = Path(workspace).resolve() if workspace is not None else Path.cwd()
    identity = current_promotion_identity(selected_workspace)
    evidence_store = EvidenceStore(root / "evidence" / identity.repository_hash)
    payload: dict[str, Any]
    if command == "status":
        state = read_mode(root, repository_hash=identity.repository_hash)
        _emit(
            {
                **state,
                "capability": "Tool Enforcement",
                "repository_hash": identity.repository_hash,
            },
            as_json=as_json,
        )
        return 0
    if command == "doctor":
        _emit(inspect_codex().to_dict(), as_json=as_json)
        return 0
    if command == "review":
        records = evidence_store.read_all()
        candidates = {
            str(record["action_hash"])
            for record in records
            if record.get("event") == "decision"
            and record.get("recommended_stop") is True
            and isinstance(record.get("action_hash"), str)
        }
        already_reviewed = {
            str(record["action_hash"])
            for record in records
            if record.get("reviewed") is True and isinstance(record.get("action_hash"), str)
        }
        if candidate is None and verdict is None:
            payload = {
                "review_command": "/hooks",
                "message": "Review hook trust, then label each redacted candidate explicitly.",
                "unreviewed_candidates": sorted(candidates - already_reviewed),
            }
            _emit(payload, as_json=as_json)
            return 0
        if candidate not in candidates or verdict not in {"helpful", "waste"}:
            _emit(
                {
                    "error_code": "INVALID_REVIEW",
                    "message": (
                        "Candidate must be identified only by its hash; "
                        "verdict is helpful or waste."
                    ),
                },
                as_json=as_json,
            )
            return 2
        if candidate in already_reviewed:
            _emit(
                {"error_code": "ALREADY_REVIEWED", "candidate": candidate},
                as_json=as_json,
            )
            return 2
        evidence_store.append(
            {
                "schema_version": 1,
                "event": "review",
                "action_hash": candidate,
                "reviewed": True,
                "false_stop": verdict == "helpful",
            }
        )
        if verdict == "helpful":
            demote_enforcement(
                root,
                repository_hash=identity.repository_hash,
                reason="FALSE_STOP_REVIEWED",
            )
            evidence_store.start_new_window(reason_code="FALSE_STOP_REVIEWED")
        payload = {
            "candidate": candidate,
            "reviewed": True,
            "false_stop": verdict == "helpful",
        }
        _emit(payload, as_json=as_json)
        return 0
    if command == "demote":
        demote_enforcement(
            root,
            repository_hash=identity.repository_hash,
            reason="EXPLICIT_USER_DEMOTION",
        )
        payload = {
            "schema_version": 1,
            "mode": "shadow",
            "capability": "Tool Enforcement",
            "reason": "Explicit user demotion",
            "repository_hash": identity.repository_hash,
        }
        _emit(payload, as_json=as_json)
        return 0
    if command == "promote":
        summary = summarize_evidence(evidence_store.read_all())
        receipt = evaluate_promotion(summary, PromotionCriteria(), identity=identity)
        write_promotion_receipt(root, receipt)
        if not receipt.is_ready:
            payload = {
                "mode": "shadow",
                "error_code": "EVIDENCE_NOT_READY",
                "blocking_reasons": list(receipt.blocking_reasons),
                "receipt_hash": receipt.receipt_hash,
            }
            _emit(payload, as_json=as_json)
            return 2
        activate_enforcement(root, receipt)
        payload = {
            "schema_version": 1,
            "mode": "enforce",
            "capability": "Tool Enforcement",
            "receipt_hash": receipt.receipt_hash,
            "reason": "Explicit promotion with a ready evidence receipt",
        }
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
