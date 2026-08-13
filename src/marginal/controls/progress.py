"""Provider-neutral evidence-invariant progress detection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActionOutcomeStatus(str, Enum):
    """What an adapter can prove about a completed action."""

    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, value: ActionOutcomeStatus | str) -> ActionOutcomeStatus:
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            raise ValueError(f"unknown action outcome status: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class NoProgressConfig:
    """Threshold for repeated completions with identical state and evidence."""

    max_same_evidence_completions: int = 2

    def __post_init__(self) -> None:
        value = self.max_same_evidence_completions
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("max_same_evidence_completions must be an integer")
        if value < 1:
            raise ValueError("max_same_evidence_completions must be at least 1")


@dataclass(frozen=True, slots=True)
class NoProgressSignal:
    """Explain whether unchanged completion evidence warrants a stop recommendation."""

    semantic_key: str
    same_evidence_completions: int
    should_recommend_stop: bool
    enforcement_eligible: bool
    reason_code: str
    reason: str


@dataclass(slots=True)
class _ProgressObservation:
    state_hash: str
    evidence_hash: str
    completions: int
    all_successful: bool


class NoProgressDetector:
    """Track evidence-invariant completions without equating completion with success."""

    def __init__(self, config: NoProgressConfig | None = None) -> None:
        self.config = config or NoProgressConfig()
        self._observations: dict[str, _ProgressObservation] = {}

    def evaluate(
        self,
        semantic_key: str,
        state_hash: str,
        evidence_hash: str,
    ) -> NoProgressSignal:
        semantic_key = _required_or_empty(semantic_key, "semantic_key")
        state_hash = _required_or_empty(state_hash, "state_hash")
        evidence_hash = _required_or_empty(evidence_hash, "evidence_hash")
        if not semantic_key or not state_hash or not evidence_hash:
            return NoProgressSignal(
                semantic_key=semantic_key,
                same_evidence_completions=0,
                should_recommend_stop=False,
                enforcement_eligible=False,
                reason_code="NO_PROGRESS_UNOBSERVABLE",
                reason="semantic identity, state, or completion evidence is unavailable",
            )

        previous = self._observations.get(semantic_key)
        same_observation = (
            previous is not None
            and previous.state_hash == state_hash
            and previous.evidence_hash == evidence_hash
        )
        if not same_observation or previous is None:
            return NoProgressSignal(
                semantic_key=semantic_key,
                same_evidence_completions=0,
                should_recommend_stop=False,
                enforcement_eligible=False,
                reason_code="NO_PROGRESS_CLEAR",
                reason="state or completion evidence changed",
            )

        completions = previous.completions
        should_stop = completions >= self.config.max_same_evidence_completions
        enforcement_eligible = should_stop and previous.all_successful
        if enforcement_eligible:
            reason_code = "NO_PROGRESS_ENFORCEMENT_ELIGIBLE"
            reason = "successful completions repeated without state or evidence change"
        elif should_stop:
            reason_code = "NO_PROGRESS_RECOMMENDED_UNKNOWN"
            reason = "completions repeated without progress, but success is not proven"
        else:
            reason_code = "NO_PROGRESS_OBSERVED"
            reason = "unchanged completion evidence remains below the stop threshold"
        return NoProgressSignal(
            semantic_key=semantic_key,
            same_evidence_completions=completions,
            should_recommend_stop=should_stop,
            enforcement_eligible=enforcement_eligible,
            reason_code=reason_code,
            reason=reason,
        )

    def observe(
        self,
        semantic_key: str,
        state_hash: str,
        evidence_hash: str,
        outcome: ActionOutcomeStatus | str,
    ) -> None:
        semantic_key = _required_or_empty(semantic_key, "semantic_key")
        state_hash = _required_or_empty(state_hash, "state_hash")
        evidence_hash = _required_or_empty(evidence_hash, "evidence_hash")
        normalized_outcome = ActionOutcomeStatus.parse(outcome)
        if not semantic_key or not state_hash or not evidence_hash:
            return

        previous = self._observations.get(semantic_key)
        same_observation = (
            previous is not None
            and previous.state_hash == state_hash
            and previous.evidence_hash == evidence_hash
        )
        completions = previous.completions + 1 if same_observation and previous else 1
        all_successful = normalized_outcome is ActionOutcomeStatus.SUCCESS
        if same_observation and previous is not None:
            all_successful = previous.all_successful and all_successful
        self._observations[semantic_key] = _ProgressObservation(
            state_hash=state_hash,
            evidence_hash=evidence_hash,
            completions=completions,
            all_successful=all_successful,
        )

    def reset(self) -> None:
        self._observations.clear()


def _required_or_empty(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value.strip()
