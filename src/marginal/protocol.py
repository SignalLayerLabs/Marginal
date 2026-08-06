"""Universal, engine-neutral protocol values for AI development agents."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from .models import Action, Cost, Decision, TokenUsage
from .modes import ExecutionMode

PROTOCOL_VERSION = "1.0"


class AgentEventType(str, Enum):
    SESSION_START = "session.start"
    SESSION_END = "session.end"
    ACTION_BEFORE = "action.before"
    ACTION_AFTER = "action.after"
    ACTION_FAILED = "action.failed"
    OUTCOME = "outcome"

    @classmethod
    def parse(cls, value: AgentEventType | str) -> AgentEventType:
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value))
        except ValueError as exc:
            raise ValueError(f"unknown agent event type: {value}") from exc


class AgentDirective(str, Enum):
    """Action requested from an engine adapter by the universal protocol."""

    ALLOW = "allow"
    DENY = "deny"
    MODIFY = "modify"
    DEFER = "defer"
    REUSE = "reuse"
    STOP = "stop"
    FORCE_VERIFY = "force_verify"

    @classmethod
    def parse(cls, value: AgentDirective | str) -> AgentDirective:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError("agent directive must be a string or AgentDirective")
        normalized = value.strip().lower().replace("-", "_")
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"unknown agent directive: {value}") from exc


class DeduplicationScope(str, Enum):
    EXACT = "exact"
    ONCE_PER_STATE = "once_per_state"
    ONCE_PER_PHASE = "once_per_phase"
    ALLOW_RETRY = "allow_retry"

    @classmethod
    def parse(cls, value: DeduplicationScope | str) -> DeduplicationScope:
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().lower().replace("-", "_")
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"unknown deduplication scope: {value}") from exc


@dataclass(frozen=True, slots=True)
class AgentCapabilities:
    """Capabilities negotiated by an engine adapter."""

    observe_model_usage: bool = False
    block_actions: bool = False
    modify_actions: bool = False
    stop_agent: bool = False
    control_model_turns: bool = False
    record_outcomes: bool = False

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be a boolean")

    @property
    def level(self) -> str:
        if all(asdict(self).values()):
            return "full"
        control_capabilities = (
            self.block_actions,
            self.modify_actions,
            self.stop_agent,
            self.control_model_turns,
        )
        if any(control_capabilities):
            return "control"
        return "observe"

    def supports(self, directive: AgentDirective | str) -> bool:
        selected = AgentDirective.parse(directive)
        if selected is AgentDirective.ALLOW:
            return True
        if selected is AgentDirective.DENY:
            return self.block_actions
        if selected is AgentDirective.MODIFY:
            return self.modify_actions
        if selected is AgentDirective.STOP:
            return self.stop_agent
        if selected is AgentDirective.FORCE_VERIFY:
            return self.block_actions
        return self.block_actions

    def to_dict(self) -> dict[str, bool | str]:
        return {**asdict(self), "level": self.level}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AgentCapabilities:
        if not isinstance(payload, Mapping):
            raise TypeError("capability payload must be a mapping")
        fields = (
            "observe_model_usage",
            "block_actions",
            "modify_actions",
            "stop_agent",
            "control_model_turns",
            "record_outcomes",
        )
        values: dict[str, bool] = {}
        for name in fields:
            value = payload.get(name, False)
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be a boolean")
            values[name] = value
        capabilities = cls(
            observe_model_usage=values["observe_model_usage"],
            block_actions=values["block_actions"],
            modify_actions=values["modify_actions"],
            stop_agent=values["stop_agent"],
            control_model_turns=values["control_model_turns"],
            record_outcomes=values["record_outcomes"],
        )
        declared_level = payload.get("level")
        if declared_level is not None and declared_level != capabilities.level:
            raise ValueError(
                f"declared capability level {declared_level!r} does not match "
                f"derived level {capabilities.level!r}"
            )
        return capabilities


@dataclass(frozen=True, slots=True)
class AgentAction:
    """Normalized action proposed by an external agent runtime."""

    action_id: str
    name: str
    kind: str
    estimated_cost: Cost = field(default_factory=Cost)
    token_usage: TokenUsage | None = None
    expected_gain: float | None = None
    current_success_probability: float = 0.0
    is_verification: bool = False
    state_hash: str = ""
    phase: str = ""
    retry_number: int = 0
    deduplication_scope: DeduplicationScope | str = DeduplicationScope.EXACT
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("action_id", "name", "kind"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.estimated_cost, Cost):
            raise TypeError("estimated_cost must be Cost")
        if not isinstance(self.is_verification, bool):
            raise TypeError("is_verification must be a boolean")
        for field_name in ("state_hash", "phase"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string")
        if self.token_usage is not None and not isinstance(self.token_usage, TokenUsage):
            raise TypeError("token_usage must be TokenUsage or None")
        if self.expected_gain is not None:
            if isinstance(self.expected_gain, bool) or not isinstance(
                self.expected_gain, (int, float)
            ):
                raise TypeError("expected_gain must be a number")
            gain = float(self.expected_gain)
            if not math.isfinite(gain) or not 0.0 <= gain <= 1.0:
                raise ValueError("expected_gain must be finite and between 0 and 1")
            object.__setattr__(self, "expected_gain", gain)
        probability = self.current_success_probability
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise TypeError("current_success_probability must be a number")
        normalized_probability = float(probability)
        if not math.isfinite(normalized_probability) or not 0.0 <= normalized_probability <= 1.0:
            raise ValueError("current_success_probability must be finite and between 0 and 1")
        object.__setattr__(self, "current_success_probability", normalized_probability)
        if isinstance(self.retry_number, bool) or not isinstance(self.retry_number, int):
            raise TypeError("retry_number must be an integer")
        if self.retry_number < 0:
            raise ValueError("retry_number must be non-negative")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        object.__setattr__(
            self, "deduplication_scope", DeduplicationScope.parse(self.deduplication_scope)
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def core_fingerprint(self) -> str:
        payload: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "is_verification": self.is_verification,
            "metadata": dict(self.metadata),
        }
        scope = DeduplicationScope.parse(self.deduplication_scope)
        if scope is DeduplicationScope.ONCE_PER_STATE:
            payload["state_hash"] = self.state_hash
        elif scope is DeduplicationScope.ONCE_PER_PHASE:
            payload["phase"] = self.phase
        elif scope is DeduplicationScope.ALLOW_RETRY:
            payload["retry_number"] = self.retry_number
        try:
            canonical = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise TypeError("agent action fingerprint metadata must be JSON serializable") from exc
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_core_action(self, *, engine: str) -> Action:
        metadata = {
            **dict(self.metadata),
            "engine": engine,
            "phase": self.phase,
            "state_hash": self.state_hash,
            "retry_number": self.retry_number,
            "deduplication_scope": DeduplicationScope.parse(self.deduplication_scope).value,
            "agent_action_id": self.action_id,
        }
        if self.token_usage is not None:
            metadata["token_usage"] = asdict(self.token_usage)
        return Action(
            name=self.name,
            kind=self.kind,
            cost=self.estimated_cost,
            expected_gain=self.expected_gain,
            current_success_probability=self.current_success_probability,
            is_verification=self.is_verification,
            fingerprint=self.core_fingerprint(),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "name": self.name,
            "kind": self.kind,
            "estimated_cost": asdict(self.estimated_cost),
            "token_usage": asdict(self.token_usage) if self.token_usage else None,
            "expected_gain": self.expected_gain,
            "current_success_probability": self.current_success_probability,
            "is_verification": self.is_verification,
            "state_hash": self.state_hash,
            "phase": self.phase,
            "retry_number": self.retry_number,
            "deduplication_scope": DeduplicationScope.parse(self.deduplication_scope).value,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AgentAction:
        cost_payload = payload.get("estimated_cost", {})
        token_payload = payload.get("token_usage")
        return cls(
            action_id=payload["action_id"],
            name=payload["name"],
            kind=payload["kind"],
            estimated_cost=Cost(**dict(cost_payload)),
            token_usage=TokenUsage(**dict(token_payload)) if token_payload else None,
            expected_gain=payload.get("expected_gain"),
            current_success_probability=payload.get("current_success_probability", 0.0),
            is_verification=payload.get("is_verification", False),
            state_hash=payload.get("state_hash", ""),
            phase=payload.get("phase", ""),
            retry_number=payload.get("retry_number", 0),
            deduplication_scope=payload.get("deduplication_scope", "exact"),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class AgentDecision:
    """Normalized decision returned to an engine adapter."""

    action_id: str
    allowed: bool
    recommended: bool
    reason: str
    reason_code: str
    recommendation_reason: str
    recommendation_reason_code: str
    mode: str
    directive: AgentDirective | str = AgentDirective.ALLOW
    recommended_directive: AgentDirective | str = AgentDirective.ALLOW
    replacement: Mapping[str, Any] = field(default_factory=dict)
    score: float = 0.0
    expected_gain: float = 0.0
    estimated_cost_value: float = 0.0
    uncertainty: float = 0.0
    confidence: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "action_id",
            "reason",
            "reason_code",
            "recommendation_reason",
            "recommendation_reason_code",
            "mode",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.allowed, bool) or not isinstance(self.recommended, bool):
            raise TypeError("allowed and recommended must be booleans")
        object.__setattr__(self, "mode", ExecutionMode.parse(self.mode).value)
        for name, value in (
            ("score", self.score),
            ("expected_gain", self.expected_gain),
            ("estimated_cost_value", self.estimated_cost_value),
            ("uncertainty", self.uncertainty),
            ("confidence", self.confidence),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, float(value))
        if not 0.0 <= self.expected_gain <= 1.0:
            raise ValueError("expected_gain must be between 0 and 1")
        if self.uncertainty < 0.0:
            raise ValueError("uncertainty must be non-negative")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        object.__setattr__(self, "directive", AgentDirective.parse(self.directive))
        object.__setattr__(
            self,
            "recommended_directive",
            AgentDirective.parse(self.recommended_directive),
        )
        if not isinstance(self.replacement, Mapping):
            raise TypeError("replacement must be a mapping")
        object.__setattr__(self, "replacement", MappingProxyType(dict(self.replacement)))

    @classmethod
    def from_core(cls, action_id: str, decision: Decision) -> AgentDecision:
        return cls(
            action_id=action_id,
            allowed=decision.allowed,
            recommended=bool(decision.recommended),
            reason=decision.reason,
            reason_code=decision.reason_code,
            recommendation_reason=decision.recommendation_reason or decision.reason,
            recommendation_reason_code=(
                decision.recommendation_reason_code or decision.reason_code
            ),
            mode=decision.mode,
            directive=(AgentDirective.ALLOW if decision.allowed else AgentDirective.DENY),
            recommended_directive=(
                AgentDirective.ALLOW if decision.recommended else AgentDirective.DENY
            ),
            score=decision.score,
            expected_gain=decision.expected_gain,
            estimated_cost_value=decision.estimated_cost_value,
            uncertainty=decision.uncertainty,
            confidence=decision.confidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "allowed": self.allowed,
            "recommended": self.recommended,
            "reason": self.reason,
            "reason_code": self.reason_code,
            "recommendation_reason": self.recommendation_reason,
            "recommendation_reason_code": self.recommendation_reason_code,
            "mode": self.mode,
            "directive": AgentDirective.parse(self.directive).value,
            "recommended_directive": AgentDirective.parse(self.recommended_directive).value,
            "replacement": dict(self.replacement),
            "score": self.score,
            "expected_gain": self.expected_gain,
            "estimated_cost_value": self.estimated_cost_value,
            "uncertainty": self.uncertainty,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AgentDecision:
        if not isinstance(payload, Mapping):
            raise TypeError("decision payload must be a mapping")
        replacement = payload.get("replacement", {})
        if not isinstance(replacement, Mapping):
            raise TypeError("replacement must be a mapping")
        return cls(
            action_id=payload["action_id"],
            allowed=payload["allowed"],
            recommended=payload["recommended"],
            reason=payload["reason"],
            reason_code=payload["reason_code"],
            recommendation_reason=payload["recommendation_reason"],
            recommendation_reason_code=payload["recommendation_reason_code"],
            mode=payload["mode"],
            directive=payload.get("directive", "allow"),
            recommended_directive=payload.get("recommended_directive", "allow"),
            replacement=dict(replacement),
            score=payload.get("score", 0.0),
            expected_gain=payload.get("expected_gain", 0.0),
            estimated_cost_value=payload.get("estimated_cost_value", 0.0),
            uncertainty=payload.get("uncertainty", 0.0),
            confidence=payload.get("confidence", 0.0),
        )


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """One normalized lifecycle event emitted by an engine adapter."""

    engine: str
    session_id: str
    task_id: str
    event_type: AgentEventType | str
    action: AgentAction | None = None
    protocol_version: str = PROTOCOL_VERSION
    state: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("engine", "session_id", "task_id", "protocol_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError(
                f"unsupported protocol_version {self.protocol_version!r}; "
                f"expected {PROTOCOL_VERSION!r}"
            )
        object.__setattr__(self, "event_type", AgentEventType.parse(self.event_type))
        if self.action is not None and not isinstance(self.action, AgentAction):
            raise TypeError("action must be AgentAction or None")
        if not isinstance(self.state, Mapping) or not isinstance(self.metadata, Mapping):
            raise TypeError("state and metadata must be mappings")
        object.__setattr__(self, "state", MappingProxyType(dict(self.state)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "engine": self.engine,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "event_type": AgentEventType.parse(self.event_type).value,
            "action": self.action.to_dict() if self.action else None,
            "state": dict(self.state),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AgentEvent:
        action_payload = payload.get("action")
        if action_payload is not None and not isinstance(action_payload, Mapping):
            raise TypeError("action payload must be a mapping or None")
        return cls(
            protocol_version=payload.get("protocol_version", PROTOCOL_VERSION),
            engine=payload["engine"],
            session_id=payload["session_id"],
            task_id=payload["task_id"],
            event_type=payload["event_type"],
            action=(AgentAction.from_dict(action_payload) if action_payload is not None else None),
            state=dict(payload.get("state", {})),
            metadata=dict(payload.get("metadata", {})),
        )
