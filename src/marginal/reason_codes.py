"""Versioned, privacy-safe governance reason codes."""

from enum import Enum

REASON_CODE_VERSION = "1.0"


class ReasonCode(str, Enum):
    """Stable codes for evidence-based autonomy decisions."""

    APPROVAL = "approval"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INSUFFICIENT_TRUST = "insufficient_trust"
    REPEATED_ACTION = "repeated_action"
    NO_PROGRESS = "no_progress"
    USER_REQUESTED_REPEAT = "user_requested_repeat"
    CONTROL_PLANE_BYPASS = "control_plane_bypass"
    POLICY_REVOKED = "policy_revoked"
    DISTRIBUTION_SHIFT = "distribution_shift"
    INTEGRITY_FAILURE = "integrity_failure"
    RECOVERY = "recovery"
    OUTCOME_UNKNOWN = "outcome_unknown"
