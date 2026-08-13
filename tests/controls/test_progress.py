from __future__ import annotations

import pytest

from marginal.controls import (
    ActionOutcomeStatus,
    NoProgressConfig,
    NoProgressDetector,
)


def test_unknown_completions_can_recommend_but_never_enforce() -> None:
    detector = NoProgressDetector(NoProgressConfig(max_same_evidence_completions=2))
    detector.observe("semantic", "state", "evidence", ActionOutcomeStatus.UNKNOWN)
    detector.observe("semantic", "state", "evidence", ActionOutcomeStatus.UNKNOWN)

    signal = detector.evaluate("semantic", "state", "evidence")

    assert signal.same_evidence_completions == 2
    assert signal.should_recommend_stop is True
    assert signal.enforcement_eligible is False
    assert signal.reason_code == "NO_PROGRESS_RECOMMENDED_UNKNOWN"


def test_same_successful_evidence_can_be_enforcement_eligible() -> None:
    detector = NoProgressDetector(NoProgressConfig(max_same_evidence_completions=2))
    detector.observe("semantic", "state", "evidence", ActionOutcomeStatus.SUCCESS)
    detector.observe("semantic", "state", "evidence", ActionOutcomeStatus.SUCCESS)

    signal = detector.evaluate("semantic", "state", "evidence")

    assert signal.should_recommend_stop is True
    assert signal.enforcement_eligible is True
    assert signal.reason_code == "NO_PROGRESS_ENFORCEMENT_ELIGIBLE"


def test_one_unknown_completion_keeps_later_sequence_out_of_enforcement() -> None:
    detector = NoProgressDetector(NoProgressConfig(max_same_evidence_completions=2))
    detector.observe("semantic", "state", "evidence", ActionOutcomeStatus.UNKNOWN)
    detector.observe("semantic", "state", "evidence", ActionOutcomeStatus.SUCCESS)

    signal = detector.evaluate("semantic", "state", "evidence")

    assert signal.should_recommend_stop is True
    assert signal.enforcement_eligible is False


@pytest.mark.parametrize("missing", ["semantic", "state", "evidence"])
def test_missing_identity_fails_open(missing: str) -> None:
    values = {"semantic": "semantic", "state": "state", "evidence": "evidence"}
    values[missing] = ""
    detector = NoProgressDetector(NoProgressConfig(max_same_evidence_completions=1))
    detector.observe(
        values["semantic"],
        values["state"],
        values["evidence"],
        ActionOutcomeStatus.SUCCESS,
    )

    signal = detector.evaluate(values["semantic"], values["state"], values["evidence"])

    assert signal.same_evidence_completions == 0
    assert signal.should_recommend_stop is False
    assert signal.enforcement_eligible is False
    assert signal.reason_code == "NO_PROGRESS_UNOBSERVABLE"


def test_state_or_evidence_change_resets_pressure() -> None:
    detector = NoProgressDetector(NoProgressConfig(max_same_evidence_completions=1))
    detector.observe("semantic", "state-1", "evidence-1", ActionOutcomeStatus.SUCCESS)

    new_state = detector.evaluate("semantic", "state-2", "evidence-1")
    new_evidence = detector.evaluate("semantic", "state-1", "evidence-2")

    assert new_state.same_evidence_completions == 0
    assert new_evidence.same_evidence_completions == 0
    assert new_state.should_recommend_stop is False
    assert new_evidence.should_recommend_stop is False


def test_evaluate_does_not_advance_history() -> None:
    detector = NoProgressDetector(NoProgressConfig(max_same_evidence_completions=2))
    detector.observe("semantic", "state", "evidence", ActionOutcomeStatus.SUCCESS)

    first = detector.evaluate("semantic", "state", "evidence")
    second = detector.evaluate("semantic", "state", "evidence")

    assert first == second
    assert second.same_evidence_completions == 1


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_completion_threshold_must_be_a_positive_integer(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        NoProgressConfig(max_same_evidence_completions=value)  # type: ignore[arg-type]


def test_outcome_status_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="unknown action outcome status"):
        ActionOutcomeStatus.parse("completed")
