from __future__ import annotations

from pathlib import Path

from marginal.controls import ActionOutcomeStatus
from marginal.integrations.codex.autopilot import AutopilotController
from marginal.integrations.codex.evidence import EvidenceStore
from marginal.integrations.codex.intent import UserIntent


def _rooted_store(path: Path) -> EvidenceStore:
    store = EvidenceStore(path)
    store.append({"schema_version": 1, "event": "session_start", "session_hash": "session"})
    return store


def _controller(path: Path) -> tuple[AutopilotController, EvidenceStore]:
    store = _rooted_store(path / "evidence")
    controller = AutopilotController(path / "data", repository_hash="repository", evidence=store)
    controller.grant_consent()
    return controller, store


def test_consent_is_deferred_and_persists_without_token_estimates(tmp_path: Path) -> None:
    store = _rooted_store(tmp_path / "evidence")
    first = AutopilotController(tmp_path / "data", repository_hash="repository", evidence=store)

    assert first.consent_granted is False
    assert first.summary() == {"avoided_actions": 0, "recoveries": 0, "pending_actions": 0}

    first.grant_consent()
    restarted = AutopilotController(tmp_path / "data", repository_hash="repository", evidence=store)

    assert restarted.consent_granted is True
    assert "tokens" not in restarted.summary()


def test_user_owned_install_consent_can_enable_autopilot_without_repository_config(
    tmp_path: Path,
) -> None:
    store = _rooted_store(tmp_path / "evidence")

    controller = AutopilotController(
        tmp_path / "data",
        repository_hash="repository",
        evidence=store,
        user_consent=True,
    )

    assert controller.consent_granted is True


def test_third_exact_safe_success_is_denied_only_with_a_verified_quick_receipt(
    tmp_path: Path,
) -> None:
    controller, store = _controller(tmp_path)
    for action_id in ("one", "two"):
        decision = controller.pre_action(
            action_id=action_id,
            workload_key="exact",
            eligible_family=True,
            state_hash="state",
            evidence_hash="evidence",
            intent=UserIntent(),
        )
        assert decision.allowed is True
        controller.settle_action(
            action_id,
            outcome=ActionOutcomeStatus.SUCCESS,
            state_hash="state",
            evidence_hash="evidence",
        )
        store.append(
            {
                "schema_version": 1,
                "event": "outcome",
                "action_hash": action_id,
                "outcome": "success",
            }
        )

    denied = controller.pre_action(
        action_id="three",
        workload_key="exact",
        eligible_family=True,
        state_hash="state",
        evidence_hash="evidence",
        intent=UserIntent(),
    )

    assert denied.allowed is False
    assert denied.reason_code == "NO_PROGRESS_ENFORCED"
    assert controller.summary()["avoided_actions"] == 1
    assert controller.quick_receipt is not None
    assert controller.quick_receipt.evidence_root == store.verified_governance_root().root_hash


def test_repeat_intent_changed_evidence_and_uncovered_families_pass(tmp_path: Path) -> None:
    controller, _store = _controller(tmp_path)
    for action_id in ("one", "two"):
        controller.pre_action(
            action_id=action_id,
            workload_key="exact",
            eligible_family=True,
            state_hash="state",
            evidence_hash="evidence",
            intent=UserIntent(),
        )
        controller.settle_action(
            action_id,
            outcome=ActionOutcomeStatus.SUCCESS,
            state_hash="state",
            evidence_hash="evidence",
        )

    assert controller.pre_action(
        action_id="repeat",
        workload_key="exact",
        eligible_family=True,
        state_hash="state",
        evidence_hash="evidence",
        intent=UserIntent(repeat_requested=True),
    ).allowed
    assert controller.pre_action(
        action_id="changed",
        workload_key="exact",
        eligible_family=True,
        state_hash="state-2",
        evidence_hash="evidence",
        intent=UserIntent(),
    ).allowed
    assert controller.pre_action(
        action_id="shell",
        workload_key="shell",
        eligible_family=False,
        state_hash="state",
        evidence_hash="evidence",
        intent=UserIntent(),
    ).allowed


def test_immediate_identical_retry_recovers_once_and_demotes(tmp_path: Path) -> None:
    controller, _store = _controller(tmp_path)
    for action_id in ("one", "two"):
        controller.pre_action(
            action_id=action_id,
            workload_key="exact",
            eligible_family=True,
            state_hash="state",
            evidence_hash="evidence",
            intent=UserIntent(),
        )
        controller.settle_action(
            action_id,
            outcome=ActionOutcomeStatus.SUCCESS,
            state_hash="state",
            evidence_hash="evidence",
        )
    assert not controller.pre_action(
        action_id="three",
        workload_key="exact",
        eligible_family=True,
        state_hash="state",
        evidence_hash="evidence",
        intent=UserIntent(),
    ).allowed

    recovery = controller.pre_action(
        action_id="four",
        workload_key="exact",
        eligible_family=True,
        state_hash="state",
        evidence_hash="evidence",
        intent=UserIntent(),
    )

    assert recovery.allowed is True
    assert recovery.reason_code == "RECOVERY"
    assert controller.enforcement_active is False
    assert controller.summary()["recoveries"] == 1


def test_failures_and_unknowns_demote_but_unrelated_pending_workloads_do_not(
    tmp_path: Path,
) -> None:
    controller, _store = _controller(tmp_path)
    controller.pre_action(
        action_id="read",
        workload_key="read",
        eligible_family=True,
        state_hash="state",
        evidence_hash="evidence",
        intent=UserIntent(),
    )
    controller.pre_action(
        action_id="other",
        workload_key="other",
        eligible_family=True,
        state_hash="state",
        evidence_hash="evidence",
        intent=UserIntent(),
    )
    controller.settle_action(
        "read", outcome=ActionOutcomeStatus.SUCCESS, state_hash="state", evidence_hash="evidence"
    )

    assert controller.summary()["pending_actions"] == 1
    controller.settle_action(
        "other", outcome=ActionOutcomeStatus.UNKNOWN, state_hash="state", evidence_hash="evidence"
    )

    assert controller.enforcement_active is False


def test_same_workload_pending_repeat_bypasses_a_denial_until_settled(tmp_path: Path) -> None:
    controller, _store = _controller(tmp_path)
    for action_id in ("one", "two"):
        controller.pre_action(
            action_id=action_id,
            workload_key="exact",
            eligible_family=True,
            state_hash="state",
            evidence_hash="evidence",
            intent=UserIntent(),
        )
        controller.settle_action(
            action_id,
            outcome=ActionOutcomeStatus.SUCCESS,
            state_hash="state",
            evidence_hash="evidence",
        )

    pending = controller.pre_action(
        action_id="requested",
        workload_key="exact",
        eligible_family=True,
        state_hash="state",
        evidence_hash="evidence",
        intent=UserIntent(repeat_requested=True),
    )
    concurrent = controller.pre_action(
        action_id="concurrent",
        workload_key="exact",
        eligible_family=True,
        state_hash="state",
        evidence_hash="evidence",
        intent=UserIntent(),
    )

    assert pending.allowed is True
    assert concurrent.allowed is True
    assert concurrent.reason_code == "PENDING_WORKLOAD"


def test_failed_workload_clears_its_history_and_quick_receipt(tmp_path: Path) -> None:
    controller, _store = _controller(tmp_path)
    for action_id in ("one", "two"):
        controller.pre_action(
            action_id=action_id,
            workload_key="exact",
            eligible_family=True,
            state_hash="state",
            evidence_hash="evidence",
            intent=UserIntent(),
        )
        controller.settle_action(
            action_id,
            outcome=ActionOutcomeStatus.SUCCESS,
            state_hash="state",
            evidence_hash="evidence",
        )
    assert not controller.pre_action(
        action_id="denied",
        workload_key="exact",
        eligible_family=True,
        state_hash="state",
        evidence_hash="evidence",
        intent=UserIntent(),
    ).allowed
    controller.pre_action(
        action_id="forced",
        workload_key="exact",
        eligible_family=True,
        state_hash="state",
        evidence_hash="evidence",
        intent=UserIntent(force_run=True),
    )
    controller.settle_action(
        "forced",
        outcome=ActionOutcomeStatus.FAILURE,
        state_hash="state",
        evidence_hash="evidence",
    )

    assert controller.quick_receipt is None
    assert controller.pre_action(
        action_id="again",
        workload_key="exact",
        eligible_family=True,
        state_hash="state",
        evidence_hash="evidence",
        intent=UserIntent(),
    ).allowed
