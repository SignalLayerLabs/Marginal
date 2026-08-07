from __future__ import annotations

from marginal import Action, Cost, DiminishingReturnConfig, DiminishingReturnDetector


def _action(*, state: str, evidence: str = "", fingerprint: str = "a") -> Action:
    return Action(
        name="verify the same file",
        kind="verification",
        cost=Cost(tokens=100),
        expected_gain=0.4,
        fingerprint=fingerprint,
        metadata={
            "phase": "verify",
            "state_hash": state,
            "evidence_hash": evidence,
            "marginal_semantic_key": "verify:file:README.md",
        },
    )


def test_diminishing_returns_discount_same_state_then_stop() -> None:
    detector = DiminishingReturnDetector(
        DiminishingReturnConfig(gain_decay=0.5, max_same_state_repeats=2)
    )

    first = detector.evaluate(_action(state="s1"))
    assert first.gain_multiplier == 1.0
    assert first.should_stop is False
    detector.observe(_action(state="s1"))

    second = detector.evaluate(_action(state="s1", fingerprint="b"))
    assert second.same_state_repeats == 1
    assert second.gain_multiplier == 0.5
    assert second.should_stop is False
    detector.observe(_action(state="s1", fingerprint="b"))

    third = detector.evaluate(_action(state="s1", fingerprint="c"))
    assert third.same_state_repeats == 2
    assert third.gain_multiplier == 0.25
    assert third.should_stop is True
    assert third.reason_code == "DIMINISHING_RETURN_REJECTED"


def test_new_state_resets_repetition_pressure() -> None:
    detector = DiminishingReturnDetector()
    detector.observe(_action(state="s1"))

    signal = detector.evaluate(_action(state="s2", fingerprint="b"))

    assert signal.same_state_repeats == 0
    assert signal.gain_multiplier == 1.0
    assert signal.should_stop is False


def test_new_evidence_resets_repetition_pressure() -> None:
    detector = DiminishingReturnDetector()
    detector.observe(_action(state="s1", evidence="e1"))

    signal = detector.evaluate(_action(state="s1", evidence="e2", fingerprint="b"))

    assert signal.same_state_repeats == 0
    assert signal.gain_multiplier == 1.0


def test_missing_state_fails_open() -> None:
    detector = DiminishingReturnDetector()

    signal = detector.evaluate(_action(state=""))

    assert signal.should_stop is False
    assert signal.gain_multiplier == 1.0
    assert signal.reason_code == "DIMINISHING_RETURN_UNOBSERVABLE"
