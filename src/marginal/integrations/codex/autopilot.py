"""Receipt-bound, fail-open quick Autopilot state for Codex."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from marginal.controls import ActionOutcomeStatus

from .evidence import EvidenceStore
from .intent import UserIntent


@dataclass(frozen=True, slots=True)
class QuickReceipt:
    """The first-session L3 attestation, anchored to a verified v3 prefix."""

    evidence_root: str
    ledger_records: int


@dataclass(frozen=True, slots=True)
class AutopilotDecision:
    allowed: bool
    reason_code: str


@dataclass(frozen=True, slots=True)
class _Pending:
    workload_key: str
    eligible_family: bool


class AutopilotController:
    """Persist only derived repeat state; uncertain inputs always pass through."""

    def __init__(
        self,
        data_root: str | Path,
        *,
        repository_hash: str,
        evidence: EvidenceStore,
        identity_fingerprint: str = "",
        user_consent: bool = False,
    ) -> None:
        if not isinstance(user_consent, bool):
            raise TypeError("user_consent must be a bool")
        self._root = Path(data_root).resolve() / "autopilot"
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            self._root.chmod(0o700)
        self._path = self._root / f"{repository_hash}.json"
        self._evidence = evidence
        self._pending: dict[str, _Pending] = {}
        self._integrity_valid = True
        self._user_consent = user_consent
        self._state = self._load(repository_hash, identity_fingerprint)

    @property
    def consent_granted(self) -> bool:
        return bool(self._user_consent or self._state["consent"])

    @property
    def enforcement_active(self) -> bool:
        receipt = self.quick_receipt
        return bool(
            self._integrity_valid
            and self._state["active"]
            and receipt is not None
            and self._evidence.verifies_governance_prefix(
                root_hash=receipt.evidence_root, records=receipt.ledger_records
            )
        )

    @property
    def quick_receipt(self) -> QuickReceipt | None:
        value = self._state.get("quick_receipt")
        if not isinstance(value, dict):
            return None
        root = value.get("evidence_root")
        records = value.get("ledger_records")
        if not isinstance(root, str) or isinstance(records, bool) or not isinstance(records, int):
            return None
        return QuickReceipt(root, records)

    def grant_consent(self) -> None:
        """Record the one-time opt-in; no hook starts enforcement without it."""

        self._state["consent"] = True
        self._persist()

    def revoke(self, reason: str = "AUTOPILOT_REVOKED") -> None:
        """Demote immediately while preserving the opt-in and audit counters."""

        self._state["active"] = False
        self._state["demotion_reason"] = reason
        self._state["last_denial"] = None
        self._persist()

    def pre_action(
        self,
        *,
        action_id: str,
        workload_key: str,
        eligible_family: bool,
        state_hash: str,
        evidence_hash: str,
        intent: UserIntent,
    ) -> AutopilotDecision:
        self._validate_inputs(action_id, workload_key, state_hash, evidence_hash, intent)
        marker = {
            "workload_key": workload_key,
            "state_hash": state_hash,
            "evidence_hash": evidence_hash,
        }
        last_denial = self._state.get("last_denial")
        if last_denial is not None and last_denial != marker:
            self._state["last_denial"] = None
            self._persist()
        if eligible_family and self._is_immediate_recovery(marker):
            self._state["recoveries"] += 1
            self.revoke("RECOVERY")
            self._pending[action_id] = _Pending(workload_key, True)
            return AutopilotDecision(True, "RECOVERY")
        if eligible_family and self._has_pending_workload(workload_key):
            self._reserve(action_id, workload_key, True)
            return AutopilotDecision(True, "PENDING_WORKLOAD")
        if not eligible_family or intent.repeat_requested or intent.force_run:
            self._reserve(action_id, workload_key, eligible_family)
            return AutopilotDecision(
                True, "USER_REQUESTED_REPEAT" if intent.repeat_requested else "PASS_THROUGH"
            )
        if not self.consent_granted or not self._integrity_valid:
            self._reserve(action_id, workload_key, True)
            return AutopilotDecision(True, "INSUFFICIENT_TRUST")
        history = self._state["histories"].get(workload_key)
        exact_repeat = (
            isinstance(history, dict)
            and history.get("state_hash") == state_hash
            and history.get("evidence_hash") == evidence_hash
            and history.get("successes") == 2
        )
        if not exact_repeat:
            self._reserve(action_id, workload_key, True)
            return AutopilotDecision(True, "PASS_THROUGH")
        if not self._ensure_quick_receipt():
            self._reserve(action_id, workload_key, True)
            return AutopilotDecision(True, "INSUFFICIENT_EVIDENCE")
        self._state["active"] = True
        self._state["avoided_actions"] += 1
        self._state["last_denial"] = marker
        self._persist()
        return AutopilotDecision(False, "NO_PROGRESS_ENFORCED")

    def settle_action(
        self,
        action_id: str,
        *,
        outcome: ActionOutcomeStatus,
        state_hash: str,
        evidence_hash: str,
    ) -> None:
        pending = self._pending.pop(action_id, None)
        if pending is None:
            return
        if not pending.eligible_family:
            return
        if outcome is not ActionOutcomeStatus.SUCCESS or not state_hash or not evidence_hash:
            self._state["histories"].pop(pending.workload_key, None)
            self._state["quick_receipt"] = None
            self._state["last_denial"] = None
            self.revoke(
                "OUTCOME_UNOBSERVABLE"
                if outcome is ActionOutcomeStatus.UNKNOWN
                else "OUTCOME_FAILURE"
            )
            return
        previous = self._state["histories"].get(pending.workload_key)
        same = (
            isinstance(previous, dict)
            and previous.get("state_hash") == state_hash
            and previous.get("evidence_hash") == evidence_hash
        )
        successes = min(2, int(previous.get("successes", 0)) + 1) if same else 1
        self._state["histories"][pending.workload_key] = {
            "state_hash": state_hash,
            "evidence_hash": evidence_hash,
            "successes": successes,
        }
        try:
            self._evidence.append(
                {
                    "schema_version": 1,
                    "event": "autopilot_observation",
                    "action_hash": action_id,
                    "semantic_key": pending.workload_key,
                    "state_hash": state_hash,
                    "evidence_hash": evidence_hash,
                    "outcome": outcome.value,
                }
            )
        except (OSError, ValueError):
            self._integrity_valid = False
            self.revoke("EVIDENCE_INTEGRITY_FAILURE")
            return
        self._persist()

    def summary(self) -> dict[str, int]:
        return {
            "avoided_actions": int(self._state["avoided_actions"]),
            "recoveries": int(self._state["recoveries"]),
            "pending_actions": len(self._pending),
        }

    def _ensure_quick_receipt(self) -> bool:
        existing = self.quick_receipt
        if existing is not None and self._evidence.verifies_governance_prefix(
            root_hash=existing.evidence_root, records=existing.ledger_records
        ):
            return True
        report = self._evidence.verified_governance_root()
        if not report.valid or report.root_hash is None or report.records < 1:
            self.revoke("EVIDENCE_INTEGRITY_FAILURE")
            return False
        self._state["quick_receipt"] = asdict(QuickReceipt(report.root_hash, report.records))
        self._persist()
        return True

    def _is_immediate_recovery(self, marker: dict[str, str]) -> bool:
        return self._state.get("last_denial") == marker and self.enforcement_active

    def _reserve(self, action_id: str, workload_key: str, eligible_family: bool) -> None:
        if eligible_family:
            self._pending[action_id] = _Pending(workload_key, True)

    def _has_pending_workload(self, workload_key: str) -> bool:
        return any(pending.workload_key == workload_key for pending in self._pending.values())

    @staticmethod
    def _validate_inputs(
        action_id: str, workload_key: str, state_hash: str, evidence_hash: str, intent: UserIntent
    ) -> None:
        if not all(
            isinstance(value, str) and value for value in (action_id, workload_key, state_hash)
        ):
            raise ValueError("action identity and state must be non-empty strings")
        if not isinstance(evidence_hash, str) or not isinstance(intent, UserIntent):
            raise TypeError("evidence_hash must be a string and intent must be UserIntent")

    def _load(self, repository_hash: str, identity_fingerprint: str) -> dict[str, Any]:
        default: dict[str, Any] = {
            "schema_version": 1,
            "repository_hash": repository_hash,
            "identity_fingerprint": identity_fingerprint,
            "consent": False,
            "active": False,
            "histories": {},
            "quick_receipt": None,
            "last_denial": None,
            "avoided_actions": 0,
            "recoveries": 0,
            "demotion_reason": "DEFERRED_CONSENT",
        }
        if not self._path.exists():
            return default
        try:
            loaded = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or loaded.get("repository_hash") != repository_hash:
                raise ValueError("invalid Autopilot state")
            for key in default:
                if key not in loaded:
                    raise ValueError("incomplete Autopilot state")
            if identity_fingerprint and loaded["identity_fingerprint"] != identity_fingerprint:
                self._integrity_valid = False
                loaded["identity_fingerprint"] = identity_fingerprint
                loaded["active"] = False
                loaded["quick_receipt"] = None
                loaded["last_denial"] = None
                loaded["demotion_reason"] = "IDENTITY_DRIFT"
            return loaded
        except (OSError, ValueError, json.JSONDecodeError):
            self._integrity_valid = False
            return default

    def _persist(self) -> None:
        temporary = self._path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        try:
            os.write(
                descriptor,
                (json.dumps(self._state, sort_keys=True, separators=(",", ":")) + "\n").encode(),
            )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, self._path)
        if os.name == "posix":
            self._path.chmod(0o600)
