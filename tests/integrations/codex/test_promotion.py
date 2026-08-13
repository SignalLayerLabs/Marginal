from __future__ import annotations

import json

from marginal.integrations.codex.promotion import (
    CoverageSummary,
    PromotionCriteria,
    PromotionIdentity,
    PromotionReceipt,
    activate_enforcement,
    enforcement_is_active,
    evaluate_promotion,
    read_promotion_receipt,
    write_promotion_receipt,
)


def _identity(*, policy_hash: str = "policy") -> PromotionIdentity:
    return PromotionIdentity(
        repository_hash="repository",
        codex_version="0.147.0",
        plugin_version="0.3.0",
        adapter_version="1",
        policy_hash=policy_hash,
        hook_hash="hooks",
    )


def _summary(**overrides: object) -> CoverageSummary:
    defaults: dict[str, object] = {
        "covered_actions": 100,
        "coverable_actions": 100,
        "completed_sessions": 5,
        "reviewed_candidates": 5,
        "false_stops": 0,
        "integration_failures": 0,
        "pending_actions": 0,
        "unknown_enforceable_outcomes": 0,
        "decision_latencies_ms": (1.0, 2.0, 3.0),
        "enforceable_outcomes_observable": True,
    }
    defaults.update(overrides)
    return CoverageSummary(**defaults)  # type: ignore[arg-type]


def test_default_gate_requires_minimum_actions() -> None:
    receipt = evaluate_promotion(
        _summary(covered_actions=99, coverable_actions=100),
        PromotionCriteria(),
        identity=_identity(),
    )

    assert receipt.is_ready is False
    assert "MINIMUM_ACTIONS" in receipt.blocking_reasons


def test_all_default_thresholds_produce_ready_receipt() -> None:
    receipt = evaluate_promotion(_summary(), PromotionCriteria(), identity=_identity())

    assert receipt.is_ready is True
    assert receipt.blocking_reasons == ()
    assert receipt.coverage_ratio == 1.0
    assert receipt.p95_latency_ms == 3.0


def test_each_safety_failure_blocks_promotion() -> None:
    cases = {
        "MINIMUM_SESSIONS": {"completed_sessions": 4},
        "COVERAGE": {"covered_actions": 98},
        "MINIMUM_REVIEWS": {"reviewed_candidates": 4},
        "FALSE_STOPS": {"false_stops": 1},
        "INTEGRATION_FAILURES": {"integration_failures": 1},
        "PENDING_ACTIONS": {"pending_actions": 1},
        "LATENCY": {"decision_latencies_ms": (76.0,)},
        "OUTCOME_UNOBSERVABLE": {"enforceable_outcomes_observable": False},
        "UNKNOWN_ENFORCEABLE_OUTCOMES": {"unknown_enforceable_outcomes": 1},
        "UNREVIEWED_CANDIDATES": {
            "intervention_candidates": 6,
            "reviewed_candidates": 5,
        },
    }
    for reason, overrides in cases.items():
        receipt = evaluate_promotion(
            _summary(**overrides), PromotionCriteria(), identity=_identity()
        )
        assert reason in receipt.blocking_reasons


def test_policy_change_invalidates_ready_receipt() -> None:
    receipt = evaluate_promotion(_summary(), PromotionCriteria(), identity=_identity())

    assert receipt.valid_for(_identity(policy_hash="new")) is False


def test_receipt_round_trip_is_hash_verifiable() -> None:
    receipt = evaluate_promotion(_summary(), PromotionCriteria(), identity=_identity())

    restored = PromotionReceipt.from_dict(receipt.to_dict())

    assert restored == receipt
    assert restored.verify_hash()


def test_active_enforcement_requires_ready_matching_receipt(tmp_path) -> None:
    identity = _identity()
    receipt = evaluate_promotion(_summary(), PromotionCriteria(), identity=identity)
    write_promotion_receipt(tmp_path, receipt)

    activate_enforcement(tmp_path, receipt)

    assert enforcement_is_active(tmp_path, identity=identity) is True
    assert read_promotion_receipt(tmp_path, identity.repository_hash) == receipt


def test_identity_drift_automatically_demotes_receipt(tmp_path) -> None:
    identity = _identity()
    receipt = evaluate_promotion(_summary(), PromotionCriteria(), identity=identity)
    write_promotion_receipt(tmp_path, receipt)
    activate_enforcement(tmp_path, receipt)

    assert (
        enforcement_is_active(
            tmp_path,
            identity=_identity(policy_hash="changed"),
        )
        is False
    )
    state = json.loads((tmp_path / "repositories" / f"{identity.repository_hash}.json").read_text())
    assert state["mode"] == "shadow"
    assert state["reason"] == "IDENTITY_DRIFT"


def test_evidence_drift_automatically_demotes_receipt(tmp_path) -> None:
    identity = _identity()
    receipt = evaluate_promotion(_summary(), PromotionCriteria(), identity=identity)
    write_promotion_receipt(tmp_path, receipt)
    activate_enforcement(tmp_path, receipt)

    assert (
        enforcement_is_active(
            tmp_path,
            identity=identity,
            summary=_summary(integration_failures=1),
        )
        is False
    )
    state = json.loads((tmp_path / "repositories" / f"{identity.repository_hash}.json").read_text())
    assert state["mode"] == "shadow"
    assert state["reason"] == "EVIDENCE_DRIFT"
