from __future__ import annotations

import pytest

from marginal import GovernanceTracker


def test_governance_tracker_separates_self_cost_from_agent_cost() -> None:
    tracker = GovernanceTracker()
    tracker.record_decision(latency_ms=1.25)
    tracker.record_external_overhead(tokens=120, usd=0.002, latency_ms=50)

    summary = tracker.summary()

    assert summary["decisions"] == 1
    assert summary["external_tokens"] == 120
    assert summary["external_usd"] == 0.002
    assert summary["total_latency_ms"] == 51.25


def test_false_stop_rate_requires_explicit_reviews() -> None:
    tracker = GovernanceTracker()
    assert tracker.summary()["false_stop_rate"] is None

    tracker.record_stop_review(would_have_helped=False)
    tracker.record_stop_review(would_have_helped=True)

    assert tracker.summary()["reviewed_stops"] == 2
    assert tracker.summary()["false_stops"] == 1
    assert tracker.summary()["false_stop_rate"] == 0.5


def test_governance_tracker_rejects_invalid_overhead() -> None:
    tracker = GovernanceTracker()
    with pytest.raises(ValueError):
        tracker.record_external_overhead(tokens=-1)
