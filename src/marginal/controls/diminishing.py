"""State-aware diminishing-return detection for repeated agent actions.

The detector is intentionally provider neutral. It does not special-case a model, tool,
or file type. A repeat only becomes less valuable when the same semantic action is proposed
against the same observable state without new evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..models import Action


@dataclass(frozen=True, slots=True)
class DiminishingReturnConfig:
    """Conservative controls for state-aware repetition."""

    gain_decay: float = 0.5
    max_same_state_repeats: int = 2

    def __post_init__(self) -> None:
        if isinstance(self.gain_decay, bool) or not isinstance(self.gain_decay, (int, float)):
            raise TypeError("gain_decay must be a number")
        decay = float(self.gain_decay)
        if not math.isfinite(decay) or not 0.0 < decay <= 1.0:
            raise ValueError("gain_decay must be finite and in (0, 1]")
        if isinstance(self.max_same_state_repeats, bool) or not isinstance(
            self.max_same_state_repeats, int
        ):
            raise TypeError("max_same_state_repeats must be an integer")
        if self.max_same_state_repeats < 1:
            raise ValueError("max_same_state_repeats must be at least 1")
        object.__setattr__(self, "gain_decay", decay)


@dataclass(frozen=True, slots=True)
class DiminishingReturnSignal:
    """Explain how prior same-state executions affect the next action."""

    semantic_key: str
    same_state_repeats: int
    gain_multiplier: float
    should_stop: bool
    reason_code: str
    reason: str


@dataclass(slots=True)
class _Observation:
    state_hash: str
    evidence_hash: str
    executions_in_state: int


class DiminishingReturnDetector:
    """Track repeated semantic work without confusing proposal with execution.

    ``evaluate`` is pure: it never advances history. Call ``observe`` only after an action
    actually executes successfully. Missing state information fails open because MARGINAL
    should not invent certainty it cannot observe.
    """

    def __init__(self, config: DiminishingReturnConfig | None = None) -> None:
        self.config = config or DiminishingReturnConfig()
        self._observations: dict[str, _Observation] = {}

    def evaluate(self, action: Action) -> DiminishingReturnSignal:
        semantic_key = self._semantic_key(action)
        state_hash = self._metadata_text(action, "state_hash")
        evidence_hash = self._metadata_text(action, "evidence_hash")

        if not state_hash:
            return DiminishingReturnSignal(
                semantic_key=semantic_key,
                same_state_repeats=0,
                gain_multiplier=1.0,
                should_stop=False,
                reason_code="DIMINISHING_RETURN_UNOBSERVABLE",
                reason="state is not observable; repetition control fails open",
            )

        previous = self._observations.get(semantic_key)
        if (
            previous is None
            or previous.state_hash != state_hash
            or (
                evidence_hash
                and (not previous.evidence_hash or previous.evidence_hash != evidence_hash)
            )
        ):
            repeats = 0
        else:
            repeats = previous.executions_in_state

        multiplier = self.config.gain_decay**repeats
        should_stop = repeats >= self.config.max_same_state_repeats
        if should_stop:
            return DiminishingReturnSignal(
                semantic_key=semantic_key,
                same_state_repeats=repeats,
                gain_multiplier=multiplier,
                should_stop=True,
                reason_code="DIMINISHING_RETURN_REJECTED",
                reason=(
                    "same semantic action has already executed "
                    f"{repeats} time(s) against unchanged state without new evidence"
                ),
            )
        if repeats:
            return DiminishingReturnSignal(
                semantic_key=semantic_key,
                same_state_repeats=repeats,
                gain_multiplier=multiplier,
                should_stop=False,
                reason_code="DIMINISHING_RETURN_DISCOUNTED",
                reason=(
                    f"same-state repetition detected; expected gain discounted by {multiplier:.3f}"
                ),
            )
        return DiminishingReturnSignal(
            semantic_key=semantic_key,
            same_state_repeats=0,
            gain_multiplier=1.0,
            should_stop=False,
            reason_code="DIMINISHING_RETURN_CLEAR",
            reason="new state or new evidence; no repetition penalty",
        )

    def observe(self, action: Action) -> None:
        """Record one action only after the caller confirms it executed."""

        semantic_key = self._semantic_key(action)
        state_hash = self._metadata_text(action, "state_hash")
        evidence_hash = self._metadata_text(action, "evidence_hash")
        if not state_hash:
            return

        previous = self._observations.get(semantic_key)
        same_state = previous is not None and previous.state_hash == state_hash
        same_evidence = previous is not None and (
            (not evidence_hash and not previous.evidence_hash)
            or evidence_hash == previous.evidence_hash
        )
        executions = (
            previous.executions_in_state + 1
            if previous is not None and same_state and same_evidence
            else 1
        )
        self._observations[semantic_key] = _Observation(
            state_hash=state_hash,
            evidence_hash=evidence_hash,
            executions_in_state=executions,
        )

    def reset(self) -> None:
        self._observations.clear()

    @staticmethod
    def _metadata_text(action: Action, key: str) -> str:
        value = action.metadata.get(key, "")
        return value.strip() if isinstance(value, str) else str(value).strip() if value else ""

    @classmethod
    def _semantic_key(cls, action: Action) -> str:
        explicit = cls._metadata_text(action, "marginal_semantic_key")
        if explicit:
            return explicit
        phase = cls._metadata_text(action, "phase")
        return "|".join((action.kind.strip().lower(), action.name.strip().lower(), phase.lower()))
