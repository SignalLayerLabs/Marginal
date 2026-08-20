"""Closed, typed compilation of verified local evidence into Commons atoms."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from marginal.integrations.codex.evidence import EvidenceStore

from .identity import CanonicalModelIdentity, identity_is_canonical


class RecordType(str, Enum):
    DECISION = "decision"
    OUTCOME = "outcome"


class ActionKind(str, Enum):
    COMMAND = "command"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    GENERATION = "generation"
    LLM = "llm"
    MODEL_CALL = "model_call"
    REASONING = "reasoning"
    RESEARCH = "research"
    REVIEW = "review"
    SEARCH = "search"
    SUBAGENT = "subagent"
    TEST = "test"
    TOOL = "tool"
    VERIFICATION = "verification"
    UNKNOWN = "unknown"
    OTHER = "other"


class ValueBucket(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class DecisionClass(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class AggregateReasonCode(str, Enum):
    APPROVED = "APPROVED"
    BUDGET_REJECTED = "BUDGET_REJECTED"
    DENY = "DENY"
    DUPLICATE_ACTION = "DUPLICATE_ACTION"
    DUPLICATE_PENDING = "DUPLICATE_PENDING"
    EXPECTED_GAIN_REJECTED = "EXPECTED_GAIN_REJECTED"
    FUNDED = "FUNDED"
    MARGINAL_ROI_REJECTED = "MARGINAL_ROI_REJECTED"
    OTHER = "OTHER"
    PARENT_BUDGET_REJECTED = "PARENT_BUDGET_REJECTED"
    RECOMMEND_OVERRIDE = "RECOMMEND_OVERRIDE"
    SHADOW_OVERRIDE = "SHADOW_OVERRIDE"
    TARGET_REACHED = "TARGET_REACHED"
    UNSPECIFIED = "UNSPECIFIED"
    NOT_APPLICABLE = "not_applicable"


class OutcomeClass(str, Enum):
    VERIFIED_SUCCESS = "verified_success"
    VERIFIED_FAILURE = "verified_failure"
    POSITIVE_REWARD = "positive_reward"
    NON_POSITIVE_REWARD = "non_positive_reward"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class CommonsEvidenceAtom:
    """One immutable atom containing only frozen aggregate dimensions and bounded counts."""

    model_identity: CanonicalModelIdentity
    record_type: RecordType
    action_kind: ActionKind
    cost_bucket: ValueBucket
    gain_bucket: ValueBucket
    recommendation: DecisionClass
    applied_decision: DecisionClass
    reason_code: AggregateReasonCode
    outcome_class: OutcomeClass
    count: int
    minimum_group_size: int

    def __post_init__(self) -> None:
        if not identity_is_canonical(self.model_identity):
            raise ValueError("model_identity must be one exact canonical model")
        if not isinstance(self.record_type, RecordType):
            raise TypeError("record_type must be a typed Commons enum")
        if not isinstance(self.action_kind, ActionKind):
            raise TypeError("action_kind must be a typed Commons enum")
        if not isinstance(self.cost_bucket, ValueBucket):
            raise TypeError("cost_bucket must be a typed Commons enum")
        if not isinstance(self.gain_bucket, ValueBucket):
            raise TypeError("gain_bucket must be a typed Commons enum")
        if not isinstance(self.recommendation, DecisionClass):
            raise TypeError("recommendation must be a typed Commons enum")
        if not isinstance(self.applied_decision, DecisionClass):
            raise TypeError("applied_decision must be a typed Commons enum")
        if not isinstance(self.reason_code, AggregateReasonCode):
            raise TypeError("reason_code must be a typed Commons enum")
        if not isinstance(self.outcome_class, OutcomeClass):
            raise TypeError("outcome_class must be a typed Commons enum")
        for name, integer_value in (
            ("count", self.count),
            ("minimum_group_size", self.minimum_group_size),
        ):
            if isinstance(integer_value, bool) or not isinstance(integer_value, int):
                raise TypeError(f"{name} must be an integer")
            if not 1 <= integer_value <= 1_000:
                raise ValueError(f"{name} must be between 1 and 1000")

    def to_dict(self) -> dict[str, str | int]:
        return {
            "record_type": self.record_type.value,
            "action_kind": self.action_kind.value,
            "cost_bucket": self.cost_bucket.value,
            "gain_bucket": self.gain_bucket.value,
            "recommendation": self.recommendation.value,
            "applied_decision": self.applied_decision.value,
            "reason_code": self.reason_code.value,
            "outcome_class": self.outcome_class.value,
            "count": self.count,
            "minimum_group_size": self.minimum_group_size,
        }


@dataclass(frozen=True, slots=True)
class CommonsEvidenceBatch:
    """Immutable compiled atoms bound to one exact canonical model identity."""

    identity: CanonicalModelIdentity
    atoms: tuple[CommonsEvidenceAtom, ...]

    def __post_init__(self) -> None:
        if not identity_is_canonical(self.identity):
            raise ValueError("Commons evidence batch requires a canonical model identity")
        if not isinstance(self.atoms, tuple) or not all(
            isinstance(atom, CommonsEvidenceAtom) for atom in self.atoms
        ):
            raise TypeError("Commons evidence batch atoms must be an immutable typed tuple")
        if any(atom.model_identity != self.identity for atom in self.atoms):
            raise ValueError("Commons evidence batch atoms must use the same canonical model")

    @property
    def model_namespace(self) -> str:
        """Return the namespace inseparably carried by the compiled batch."""

        return self.identity.namespace


_EnumT = TypeVar("_EnumT", bound=Enum)
_DimensionKey = tuple[
    RecordType,
    ActionKind,
    ValueBucket,
    ValueBucket,
    DecisionClass,
    DecisionClass,
    AggregateReasonCode,
    OutcomeClass,
]


def _exact_enum(enum_type: type[_EnumT], value: object) -> _EnumT | None:
    if not isinstance(value, str):
        return None
    try:
        return enum_type(value)
    except ValueError:
        return None


def _decision_key(record: dict[str, object]) -> _DimensionKey | None:
    action_kind = _exact_enum(ActionKind, record.get("action_kind"))
    cost_bucket = _exact_enum(ValueBucket, record.get("cost_bucket"))
    gain_bucket = _exact_enum(ValueBucket, record.get("gain_bucket"))
    recommendation = _exact_enum(DecisionClass, record.get("recommendation"))
    applied = _exact_enum(DecisionClass, record.get("applied_decision"))
    if not isinstance(action_kind, ActionKind):
        return None
    if not isinstance(cost_bucket, ValueBucket) or not isinstance(gain_bucket, ValueBucket):
        return None
    if not isinstance(recommendation, DecisionClass) or not isinstance(applied, DecisionClass):
        return None
    reason = _exact_enum(AggregateReasonCode, record.get("reason_code"))
    if reason is None:
        reason = AggregateReasonCode.OTHER
    return (
        RecordType.DECISION,
        action_kind,
        cost_bucket,
        gain_bucket,
        recommendation,
        applied,
        reason,
        OutcomeClass.NOT_APPLICABLE,
    )


def _outcome_key(record: dict[str, object]) -> _DimensionKey | None:
    outcomes = {
        "success": OutcomeClass.VERIFIED_SUCCESS,
        "failure": OutcomeClass.VERIFIED_FAILURE,
        "unknown": OutcomeClass.UNKNOWN,
    }
    value = record.get("outcome")
    if not isinstance(value, str) or value not in outcomes:
        return None
    return (
        RecordType.OUTCOME,
        ActionKind.UNKNOWN,
        ValueBucket.UNKNOWN,
        ValueBucket.UNKNOWN,
        DecisionClass.NOT_APPLICABLE,
        DecisionClass.NOT_APPLICABLE,
        AggregateReasonCode.NOT_APPLICABLE,
        outcomes[value],
    )


def compile_verified_evidence(
    evidence_store: EvidenceStore,
    *,
    model_identity: CanonicalModelIdentity | None,
    minimum_group_size: int = 5,
    after_records: int = 0,
    through_records: int | None = None,
) -> CommonsEvidenceBatch | None:
    """Compile a verified local chain; arbitrary caller rows are never accepted."""

    if isinstance(minimum_group_size, bool) or not isinstance(minimum_group_size, int):
        raise TypeError("minimum_group_size must be an integer")
    if not 1 <= minimum_group_size <= 1_000:
        raise ValueError("minimum_group_size must be between 1 and 1000")
    if not isinstance(evidence_store, EvidenceStore):
        raise TypeError("evidence_store must be an EvidenceStore")
    if isinstance(after_records, bool) or not isinstance(after_records, int) or after_records < 0:
        raise ValueError("after_records must be a non-negative integer")
    if model_identity is None or not identity_is_canonical(model_identity):
        return None
    try:
        records, verification = evidence_store.verified_records()
    except (OSError, ValueError):
        return None
    if not verification.valid:
        return None
    end = verification.records if through_records is None else through_records
    if (
        isinstance(end, bool)
        or not isinstance(end, int)
        or not after_records <= end <= len(records)
    ):
        return None
    records = records[after_records:end]
    if after_records != 0 or through_records is not None:
        records = [
            record
            for record in records
            if record.get("model_namespace") == model_identity.namespace
        ]
    attributed_namespaces = {
        namespace
        for record in records
        if isinstance((namespace := record.get("model_namespace")), str)
    }
    if attributed_namespaces != {model_identity.namespace}:
        return None

    counter: Counter[_DimensionKey] = Counter()
    for record in records:
        if record.get("model_namespace") != model_identity.namespace:
            continue
        event = record.get("event")
        key = _decision_key(record) if event == "decision" else None
        if event == "outcome":
            key = _outcome_key(record)
        if key is not None:
            counter[key] += 1

    atoms: list[CommonsEvidenceAtom] = []
    for key, count in sorted(counter.items(), key=lambda item: tuple(v.value for v in item[0])):
        if count < minimum_group_size:
            continue
        atoms.append(
            CommonsEvidenceAtom(
                model_identity=model_identity,
                record_type=key[0],
                action_kind=key[1],
                cost_bucket=key[2],
                gain_bucket=key[3],
                recommendation=key[4],
                applied_decision=key[5],
                reason_code=key[6],
                outcome_class=key[7],
                count=min(count, 1_000),
                minimum_group_size=minimum_group_size,
            )
        )
    if not atoms:
        return None
    return CommonsEvidenceBatch(identity=model_identity, atoms=tuple(atoms))
