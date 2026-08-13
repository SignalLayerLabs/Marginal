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
from .transport import ConnectionInfo, request_session

_MAX_SESSION_RECEIPTS = 64
_MAX_SESSION_RECEIPT_BYTES = 16_384


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


def _live_session_repository(path: Path) -> str | None:
    if path.is_symlink() or path.stat().st_size > _MAX_SESSION_RECEIPT_BYTES:
        return None
    connection = ConnectionInfo.from_file(path)
    if connection.host != "127.0.0.1" or len(connection.token.encode("utf-8")) < 16:
        return None
    response = request_session(connection, operation="status", payload={}, timeout=0.25)
    if response.get("ok") is not True:
        return None
    result = response.get("result")
    repository_hash = result.get("repository_hash") if isinstance(result, dict) else None
    return repository_hash if isinstance(repository_hash, str) else None


def _active_hook_sessions(data_dir: Path, *, repository_hash: str) -> tuple[int, int]:
    sessions_root = data_dir / "sessions"
    if not sessions_root.is_dir():
        return 0, 0
    active = 0
    stale = 0
    for index, path in enumerate(sessions_root.glob("*.json")):
        if index >= _MAX_SESSION_RECEIPTS:
            break
        try:
            session_repository = _live_session_repository(path)
        except (OSError, ValueError, KeyError):
            session_repository = None
        if session_repository is None:
            stale += 1
        elif session_repository == repository_hash:
            active += 1
    return active, stale


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
        records = evidence_store.read_all()
        summary = summarize_evidence(records)
        hooks_observed = any(
            record.get("event") in {"session_start", "decision", "outcome", "session_end"}
            for record in records
        )
        coverage_ratio = (
            summary.covered_actions / summary.coverable_actions
            if summary.coverable_actions
            else 0.0
        )
        active_hook_sessions, stale_session_receipts = _active_hook_sessions(
            root,
            repository_hash=identity.repository_hash,
        )
        hooks_active = active_hook_sessions > 0
        _emit(
            {
                **state,
                "capability": "Tool Enforcement",
                "repository_hash": identity.repository_hash,
                "hook_state": (
                    "active" if hooks_active else "observed" if hooks_observed else "not_observed"
                ),
                "hooks_observed": hooks_observed,
                "hooks_active": hooks_active,
                "active_hook_sessions": active_hook_sessions,
                "stale_session_receipts": stale_session_receipts,
                "evidence_records": len(records),
                "covered_actions": summary.covered_actions,
                "coverable_actions": summary.coverable_actions,
                "coverage_ratio": coverage_ratio,
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
