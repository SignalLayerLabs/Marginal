from __future__ import annotations

from marginal.models import Cost, TokenUsage
from marginal.protocol import (
    AgentAction,
    AgentCapabilities,
    AgentEvent,
    AgentEventType,
    DeduplicationScope,
)


def test_agent_event_round_trip_preserves_normalized_action() -> None:
    event = AgentEvent(
        engine="codex",
        session_id="session-1",
        task_id="task-1",
        event_type=AgentEventType.ACTION_BEFORE,
        action=AgentAction(
            action_id="action-1",
            name="read file",
            kind="file_read",
            estimated_cost=Cost(tokens=100),
            token_usage=TokenUsage(input_tokens=80, output_tokens=20),
            expected_gain=0.2,
            state_hash="state-a",
            phase="diagnose",
            deduplication_scope=DeduplicationScope.ONCE_PER_STATE,
        ),
    )
    restored = AgentEvent.from_dict(event.to_dict())
    assert restored == event


def test_capabilities_report_control_level() -> None:
    observe = AgentCapabilities()
    control = AgentCapabilities(block_actions=True, stop_agent=True)
    full = AgentCapabilities(
        observe_model_usage=True,
        block_actions=True,
        modify_actions=True,
        stop_agent=True,
        control_model_turns=True,
        record_outcomes=True,
    )
    assert observe.level == "observe"
    assert control.level == "control"
    assert full.level == "full"


def test_state_scoped_action_fingerprint_changes_with_state() -> None:
    base = AgentAction(
        action_id="action",
        name="run test",
        kind="verification",
        state_hash="state-a",
        deduplication_scope="once_per_state",
    )
    changed = AgentAction(
        action_id="action",
        name="run test",
        kind="verification",
        state_hash="state-b",
        deduplication_scope="once_per_state",
    )
    assert base.core_fingerprint() != changed.core_fingerprint()


def test_agent_action_from_dict_rejects_string_booleans() -> None:
    payload = AgentAction(
        action_id="action",
        name="verify",
        kind="verification",
    ).to_dict()
    payload["is_verification"] = "false"

    try:
        AgentAction.from_dict(payload)
    except TypeError as exc:
        assert "is_verification must be a boolean" in str(exc)
    else:
        raise AssertionError("expected string boolean to be rejected")


def test_agent_action_from_dict_rejects_coerced_numeric_fields() -> None:
    payload = AgentAction(
        action_id="action",
        name="verify",
        kind="verification",
    ).to_dict()
    payload["retry_number"] = "1"

    try:
        AgentAction.from_dict(payload)
    except TypeError as exc:
        assert "retry_number must be an integer" in str(exc)
    else:
        raise AssertionError("expected string retry number to be rejected")


def test_core_decision_exposes_applied_and_recommended_directives() -> None:
    from marginal.models import Decision
    from marginal.protocol import AgentDecision, AgentDirective

    core = Decision(
        allowed=True,
        reason="shadow override",
        recommended=False,
        recommendation_reason="deny",
        reason_code="SHADOW_OVERRIDE",
        recommendation_reason_code="DENY",
        mode="shadow",
    )

    decision = AgentDecision.from_core("action", core)

    assert decision.directive is AgentDirective.ALLOW
    assert decision.recommended_directive is AgentDirective.DENY


def test_capabilities_report_support_for_protocol_directives() -> None:
    from marginal.protocol import AgentDirective

    capabilities = AgentCapabilities(block_actions=True, modify_actions=True)

    assert capabilities.supports(AgentDirective.ALLOW)
    assert capabilities.supports(AgentDirective.DENY)
    assert capabilities.supports(AgentDirective.MODIFY)
    assert not capabilities.supports(AgentDirective.STOP)


def test_agent_event_from_dict_rejects_coerced_identity_fields() -> None:
    event = AgentEvent(
        engine="codex",
        session_id="session",
        task_id="task",
        event_type="session.start",
    ).to_dict()
    event["session_id"] = 123

    try:
        AgentEvent.from_dict(event)
    except ValueError as exc:
        assert "session_id" in str(exc)
    else:
        raise AssertionError("expected non-string session_id to be rejected")


def test_agent_event_rejects_unsupported_protocol_version() -> None:
    try:
        AgentEvent(
            engine="codex",
            session_id="session",
            task_id="task",
            event_type="session.start",
            protocol_version="9.0",
        )
    except ValueError as exc:
        assert "protocol_version" in str(exc)
    else:
        raise AssertionError("expected unsupported protocol version to be rejected")


def test_agent_decision_to_dict_serializes_immutable_replacement() -> None:
    from marginal.protocol import AgentDecision

    decision = AgentDecision(
        action_id="action",
        allowed=True,
        recommended=True,
        reason="approved",
        reason_code="APPROVED",
        recommendation_reason="approved",
        recommendation_reason_code="APPROVED",
        mode="shadow",
        replacement={"scope": "lines"},
    )

    payload = decision.to_dict()

    assert payload["replacement"] == {"scope": "lines"}


def test_agent_action_fingerprint_rejects_non_json_metadata() -> None:
    action = AgentAction(
        action_id="action",
        name="read",
        kind="file_read",
        metadata={"opaque": object()},
    )

    try:
        action.core_fingerprint()
    except TypeError as exc:
        assert "JSON serializable" in str(exc)
    else:
        raise AssertionError("expected non-JSON metadata to be rejected")


def test_agent_decision_rejects_invalid_numeric_fields() -> None:
    from marginal.protocol import AgentDecision

    try:
        AgentDecision(
            action_id="action",
            allowed=True,
            recommended=True,
            reason="approved",
            reason_code="APPROVED",
            recommendation_reason="approved",
            recommendation_reason_code="APPROVED",
            mode="shadow",
            confidence=2.0,
        )
    except ValueError as exc:
        assert "confidence" in str(exc)
    else:
        raise AssertionError("expected invalid confidence to be rejected")


def test_agent_decision_round_trip_preserves_directives_and_replacement() -> None:
    from marginal.protocol import AgentDecision, AgentDirective

    original = AgentDecision(
        action_id="action",
        allowed=True,
        recommended=False,
        reason="shadow override",
        reason_code="SHADOW_OVERRIDE",
        recommendation_reason="deny",
        recommendation_reason_code="LOW_VALUE",
        mode="shadow",
        directive=AgentDirective.MODIFY,
        recommended_directive=AgentDirective.DENY,
        replacement={"scope": "lines"},
        expected_gain=0.1,
        confidence=0.8,
    )

    restored = AgentDecision.from_dict(original.to_dict())

    assert restored == original


def test_agent_capabilities_round_trip_rejects_string_booleans() -> None:
    original = AgentCapabilities(block_actions=True, record_outcomes=True)
    restored = AgentCapabilities.from_dict(original.to_dict())
    assert restored == original

    payload = original.to_dict()
    payload["block_actions"] = "true"
    try:
        AgentCapabilities.from_dict(payload)
    except TypeError as exc:
        assert "block_actions" in str(exc)
    else:
        raise AssertionError("expected string capability boolean to be rejected")


def test_agent_capabilities_rejects_inconsistent_derived_level() -> None:
    payload = AgentCapabilities(block_actions=True).to_dict()
    payload["level"] = "full"

    try:
        AgentCapabilities.from_dict(payload)
    except ValueError as exc:
        assert "level" in str(exc)
    else:
        raise AssertionError("expected inconsistent capability level to be rejected")


def test_agent_event_from_dict_does_not_treat_empty_action_as_missing() -> None:
    payload = AgentEvent(
        engine="codex",
        session_id="session",
        task_id="task",
        event_type="action.before",
    ).to_dict()
    payload["action"] = {}

    try:
        AgentEvent.from_dict(payload)
    except (KeyError, TypeError, ValueError):
        pass
    else:
        raise AssertionError("expected an empty action object to be rejected")
