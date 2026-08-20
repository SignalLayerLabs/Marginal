"""Construct the Shadow Mode runtime one hook session governs itself with.

Adapters built on ``hookkit`` observe. They declare no control capability, so the
core refuses to run them in a blocking mode, and the Decision Ledger is the only
place their evidence lands.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from marginal import BudgetLimits, Treasury
from marginal.ledger import DecisionLedgerContext, JsonlDecisionLedger
from marginal.privacy import PrivacyProfile
from marginal.protocol import AgentCapabilities
from marginal.runtime import UniversalRuntime

OBSERVE_CAPABILITIES = AgentCapabilities()
"""Honest capability declaration for a hook adapter that only observes.

These hook surfaces expose no per-tool token usage, no model-turn control, and no
verifier outcomes, so every capability flag stays false and
``AgentCapabilities.level`` reports ``observe``.
"""


def session_hash(session_id: str) -> str:
    """Return a stable pseudonym for one engine session identifier."""

    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id must be a non-empty string")
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def workspace_hash(workspace: str | Path) -> str:
    """Return a stable pseudonym for one workspace path."""

    resolved = str(Path(workspace))
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ObserveSession:
    """A Shadow Mode runtime plus the ledger its evidence is written to."""

    runtime: UniversalRuntime
    ledger: JsonlDecisionLedger
    ledger_path: Path
    session_hash: str
    workspace_hash: str

    def record(self, event: dict[str, object]) -> None:
        """Append one governance evidence record, failing open on ledger errors."""

        try:
            self.ledger.emit(event)
        except Exception:  # pragma: no cover - evidence must never break a hook
            return


def build_observe_session(
    *,
    engine: str,
    session_id: str,
    workspace: str | Path,
    data_root: str | Path,
    privacy_profile: PrivacyProfile | str = PrivacyProfile.LOCAL_FULL,
    privacy_key_path: str | Path | None = None,
) -> ObserveSession:
    """Build a Shadow Mode ``UniversalRuntime`` writing to a local Decision Ledger.

    The default profile is ``LOCAL_FULL`` because the ledger stays inside the
    engine's own plugin data directory on the user's machine. Choose
    ``SAFE_TELEMETRY`` when the ledger may cross a trust boundary.
    """

    if not isinstance(engine, str) or not engine.strip():
        raise ValueError("engine must be a non-empty string")
    pseudonym = session_hash(session_id)
    task_id = workspace_hash(workspace)
    root = Path(data_root).resolve()
    ledger_path = root / "ledger" / task_id / f"{pseudonym}.jsonl"
    ledger = JsonlDecisionLedger(
        ledger_path,
        context=DecisionLedgerContext(
            run_id=pseudonym,
            task_id=task_id,
            engine=engine,
        ),
        privacy_profile=privacy_profile,
        privacy_key_path=privacy_key_path,
    )
    treasury = Treasury(BudgetLimits(), trace_sink=ledger, mode="shadow")
    runtime = UniversalRuntime(
        treasury,
        engine=engine,
        session_id=session_id,
        task_id=task_id,
        capabilities=OBSERVE_CAPABILITIES,
    )
    return ObserveSession(
        runtime=runtime,
        ledger=ledger,
        ledger_path=ledger_path,
        session_hash=pseudonym,
        workspace_hash=task_id,
    )
