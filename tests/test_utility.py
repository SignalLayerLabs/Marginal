from __future__ import annotations

from marginal.receipts import GovernanceCost
from marginal.utility import MarginalUtilityEstimate, UtilityVector


def _cost(*, tokens: int = 10) -> GovernanceCost:
    return GovernanceCost(
        wall_clock_ms=10.0,
        cpu_ms=None,
        memory_peak_bytes=None,
        storage_bytes=0,
        tokens=tokens,
        model_calls=1,
        additional_tool_calls=0,
    )


def test_utility_comparison_keeps_verified_correctness_ahead_of_lower_compute() -> None:
    """Catches selecting a cheaper action when its correctness evidence is weaker."""

    verified = UtilityVector(
        verified_correctness=1.0,
        task_completion=0.4,
        safety_risk=0.3,
        latency_ms=100.0,
        tokens=100,
        monetary_cost=1.0,
        governance_overhead=10.0,
    )
    cheaper_unknown = UtilityVector(
        verified_correctness=None,
        task_completion=1.0,
        safety_risk=0.0,
        latency_ms=1.0,
        tokens=1,
        monetary_cost=0.0,
        governance_overhead=0.0,
    )

    assert verified.compare(cheaper_unknown) > 0
    assert cheaper_unknown.compare(verified) < 0


def test_unknown_correctness_never_becomes_a_scalar_efficiency_claim() -> None:
    """Catches reporting a token-saving ratio when verified utility is unavailable."""

    estimate = MarginalUtilityEstimate(
        expected_utility=UtilityVector(
            verified_correctness=None,
            task_completion=1.0,
            safety_risk=0.0,
            latency_ms=10.0,
            tokens=10,
            monetary_cost=0.1,
            governance_overhead=1.0,
        ),
        estimated_cost=_cost(),
        uncertainty=0.2,
        confidence=0.8,
        provenance={"evidence_root": "root-digest"},
        commensurable_cost=10.0,
    )

    scorecard = estimate.scorecard()

    assert estimate.scalar_emu() is None
    assert scorecard["scalar_emu"] is None
    assert scorecard["expected_utility"]["verified_correctness"] is None


def test_commensurable_verified_utility_reports_a_scalar_emu() -> None:
    """Catches dropping a justified EMU ratio from a fully measured comparable estimate."""

    estimate = MarginalUtilityEstimate(
        expected_utility=UtilityVector(
            verified_correctness=0.5,
            task_completion=0.6,
            safety_risk=0.2,
            latency_ms=10.0,
            tokens=10,
            monetary_cost=0.1,
            governance_overhead=1.0,
        ),
        estimated_cost=_cost(),
        uncertainty=0.2,
        confidence=0.8,
        provenance={"evidence_root": "root-digest"},
        commensurable_cost=2.0,
    )

    assert estimate.scalar_emu() == 0.25
