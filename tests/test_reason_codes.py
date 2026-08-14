from __future__ import annotations

from marginal.reason_codes import REASON_CODE_VERSION, ReasonCode


def test_reason_code_registry_has_the_documented_versioned_governance_values() -> None:
    """Catches an accidental rename, removal, or unversioned addition to governance codes."""

    assert REASON_CODE_VERSION == "1.0"
    assert {code.name: code.value for code in ReasonCode} == {
        "APPROVAL": "approval",
        "INSUFFICIENT_EVIDENCE": "insufficient_evidence",
        "INSUFFICIENT_TRUST": "insufficient_trust",
        "REPEATED_ACTION": "repeated_action",
        "NO_PROGRESS": "no_progress",
        "USER_REQUESTED_REPEAT": "user_requested_repeat",
        "CONTROL_PLANE_BYPASS": "control_plane_bypass",
        "POLICY_REVOKED": "policy_revoked",
        "DISTRIBUTION_SHIFT": "distribution_shift",
        "INTEGRITY_FAILURE": "integrity_failure",
        "RECOVERY": "recovery",
        "OUTCOME_UNKNOWN": "outcome_unknown",
    }
