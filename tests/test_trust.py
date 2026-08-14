from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from marginal.authority import AuthorityLevel
from marginal.governance_ledger import LedgerVerificationReport
from marginal.trust import TrustContext, TrustEngine, TrustEvidence

ROOT = Path(__file__).resolve().parents[1]
LEDGER_ROOT = "a" * 64
LEDGER_VERIFICATION = LedgerVerificationReport(True, 3, LEDGER_ROOT, None, ())
NOW = datetime(2026, 8, 14, 12, tzinfo=timezone.utc)


def _context() -> TrustContext:
    return TrustContext(
        repository="repo-identity",
        agent="agent-identity",
        model="model-identity",
        task_class="local-tool",
        policy_version="policy-1",
    )


def _evidence(**changes: object) -> TrustEvidence:
    values: dict[str, object] = {
        "observed": 25,
        "evaluable": 20,
        "covered": 19,
        "coverable": 20,
        "beneficial": 18,
        "neutral": 1,
        "harmful": 1,
        "indeterminate": 0,
        "governance_tax_ratio": 0.05,
        "mean_regret": 0.05,
        "integrity_valid": True,
        "last_observed_at": NOW.isoformat(),
        "evidence_ledger_root": LEDGER_ROOT,
        "ledger_verification": LEDGER_VERIFICATION,
    }
    values.update(changes)
    return TrustEvidence(**values)  # type: ignore[arg-type]


def _engine() -> TrustEngine:
    return TrustEngine(now=NOW)


def test_minimum_evaluable_samples_is_a_promotion_blocker() -> None:
    """Catches promotion when the evaluated evidence window is too small."""

    snapshot = _engine().evaluate(
        _context(),
        _evidence(evaluable=19, beneficial=17, neutral=1, harmful=1),
        AuthorityLevel.OBSERVE,
        capabilities=4,
    )

    assert snapshot.authority == AuthorityLevel.OBSERVE
    assert "minimum_evaluable_samples" in snapshot.blockers
    assert snapshot.components["evaluable"] == 19


def test_unclassified_evaluable_outcomes_block_promotion() -> None:
    """Catches promotion when an evaluable intervention has no outcome classification."""

    snapshot = _engine().evaluate(
        _context(),
        _evidence(beneficial=17, neutral=1, harmful=1, indeterminate=0),
        AuthorityLevel.OBSERVE,
        capabilities=4,
    )

    assert snapshot.authority == AuthorityLevel.OBSERVE
    assert "unclassified_outcomes" in snapshot.blockers
    assert snapshot.components["unclassified_outcomes"] == 1


def test_coverage_harm_regret_and_tax_are_separate_transparent_blockers() -> None:
    """Catches hiding independent safety failures inside an opaque trust score."""

    snapshot = _engine().evaluate(
        _context(),
        _evidence(
            covered=18,
            beneficial=17,
            harmful=2,
            mean_regret=0.11,
            governance_tax_ratio=0.11,
        ),
        AuthorityLevel.OBSERVE,
        capabilities=4,
    )

    assert snapshot.authority == AuthorityLevel.OBSERVE
    assert set(snapshot.blockers) >= {
        "insufficient_coverage",
        "harm_rate_too_high",
        "mean_regret_too_high",
        "governance_tax_too_high",
    }
    assert snapshot.components["coverage"] == 0.9
    assert snapshot.components["harm_rate"] == 0.1


def test_capability_ceiling_and_hysteresis_allow_only_one_promotion_step() -> None:
    """Catches authority bypassing an adapter ceiling or jumping directly to tool denial."""

    first = _engine().evaluate(_context(), _evidence(), AuthorityLevel.OBSERVE, capabilities=3)
    second = _engine().evaluate(_context(), _evidence(), AuthorityLevel.ADVISE, capabilities=3)
    capped = _engine().evaluate(
        _context(), _evidence(), AuthorityLevel.SOFT_INTERVENE, capabilities=2
    )

    assert first.authority == AuthorityLevel.ADVISE
    assert second.authority == AuthorityLevel.SOFT_INTERVENE
    assert capped.authority == AuthorityLevel.SOFT_INTERVENE
    assert "capability_ceiling" in capped.blockers


def test_soft_evidence_decay_steps_down_exactly_one_level_without_flapping() -> None:
    """Catches a non-critical quality drop resetting authority or oscillating it upward."""

    snapshot = _engine().evaluate(
        _context(), _evidence(governance_tax_ratio=0.21), AuthorityLevel.TOOL_GATE, capabilities=4
    )

    assert snapshot.authority == AuthorityLevel.SOFT_INTERVENE
    assert "governance_tax_too_high" in snapshot.blockers
    assert snapshot.transition_receipt is not None
    assert snapshot.transition_receipt.previous == AuthorityLevel.TOOL_GATE


def test_demotion_requires_a_clean_recovery_window_before_repromotion() -> None:
    """Catches L3 to L2 decay immediately flapping back to L3 at the promotion boundary."""

    engine = _engine()
    demoted = engine.evaluate(
        _context(), _evidence(governance_tax_ratio=0.21), AuthorityLevel.TOOL_GATE, capabilities=4
    )
    recovered = engine.evaluate(_context(), _evidence(), demoted.authority, capabilities=4)

    assert demoted.authority == AuthorityLevel.SOFT_INTERVENE
    assert recovered.authority == AuthorityLevel.SOFT_INTERVENE
    assert "recovery_hysteresis" in recovered.blockers


def test_promotion_and_demotion_quality_thresholds_are_asymmetric() -> None:
    """Catches a marginal tax increase immediately revoking an already-earned authority level."""

    snapshot = _engine().evaluate(
        _context(), _evidence(governance_tax_ratio=0.11), AuthorityLevel.TOOL_GATE, capabilities=4
    )

    assert snapshot.authority == AuthorityLevel.TOOL_GATE
    assert "governance_tax_too_high" in snapshot.blockers


def test_unverified_ledger_root_cannot_support_a_promotion() -> None:
    """Catches issuing a receipt from a digest that a ledger verifier did not validate."""

    snapshot = _engine().evaluate(
        _context(),
        _evidence(ledger_verification=LedgerVerificationReport(False, 3, LEDGER_ROOT, 3, ("BAD",))),
        AuthorityLevel.OBSERVE,
        capabilities=4,
    )

    assert snapshot.authority == AuthorityLevel.OBSERVE
    assert "unverified_evidence_ledger_root" in snapshot.blockers


def test_integrity_and_capability_drift_reset_directly_to_observation() -> None:
    """Catches retaining enforcement authority after critical evidence or adapter failure."""

    integrity = _engine().evaluate(
        _context(), _evidence(integrity_valid=False), AuthorityLevel.TOOL_GATE, capabilities=4
    )
    capability = _engine().evaluate(
        _context(), _evidence(), AuthorityLevel.TOOL_GATE, capabilities=2
    )

    assert integrity.authority == AuthorityLevel.OBSERVE
    assert "integrity_failure" in integrity.blockers
    assert capability.authority == AuthorityLevel.OBSERVE
    assert "capability_drift" in capability.blockers


def test_identity_shifts_reset_and_large_repository_shift_decays_one_level() -> None:
    """Catches reusing authority across a changed model, policy, or repository distribution."""

    model = _engine().evaluate(
        _context(), _evidence(), AuthorityLevel.TOOL_GATE, capabilities=4, shift_reasons=("model",)
    )
    policy = _engine().evaluate(
        _context(), _evidence(), AuthorityLevel.TOOL_GATE, capabilities=4, shift_reasons=("policy",)
    )
    repository = _engine().evaluate(
        _context(),
        _evidence(),
        AuthorityLevel.TOOL_GATE,
        capabilities=4,
        shift_reasons=("large_repository",),
    )

    assert model.authority == AuthorityLevel.OBSERVE
    assert policy.authority == AuthorityLevel.OBSERVE
    assert repository.authority == AuthorityLevel.SOFT_INTERVENE
    assert "distribution_shift" in repository.blockers


def test_inactivity_is_soft_decay_and_snapshot_matches_the_published_schema() -> None:
    """Catches stale evidence retaining a gate and schema drift in the diagnostic payload."""

    snapshot = _engine().evaluate(
        _context(),
        _evidence(last_observed_at=(NOW - timedelta(days=31)).isoformat()),
        AuthorityLevel.SOFT_INTERVENE,
        capabilities=4,
    )

    assert snapshot.authority == AuthorityLevel.ADVISE
    assert "inactivity" in snapshot.blockers
    schema = json.loads((ROOT / "schemas" / "trust-snapshot-v1.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(snapshot.payload())


def test_future_observation_outside_clock_skew_tolerance_softly_demotes() -> None:
    """Catches future-dated evidence retaining or increasing enforcement authority."""

    snapshot = _engine().evaluate(
        _context(),
        _evidence(last_observed_at=(NOW + timedelta(minutes=6)).isoformat()),
        AuthorityLevel.TOOL_GATE,
        capabilities=4,
    )

    assert snapshot.authority == AuthorityLevel.SOFT_INTERVENE
    assert "future_observation" in snapshot.blockers
