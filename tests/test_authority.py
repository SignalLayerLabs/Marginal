from __future__ import annotations

from dataclasses import replace

import pytest

from marginal.authority import (
    AuthorityLevel,
    AuthorityTransitionReceipt,
    transition_receipt_hash,
    verify_transition_receipt,
)
from marginal.governance_ledger import LedgerVerificationReport

ROOT = "a" * 64
VERIFIED_REPORT = LedgerVerificationReport(True, 3, ROOT, None, ())


def test_authority_levels_are_ordered_from_observation_to_compute_governance() -> None:
    """Catches assigning a stronger authority below a weaker intervention."""

    assert list(AuthorityLevel) == [
        AuthorityLevel.OBSERVE,
        AuthorityLevel.ADVISE,
        AuthorityLevel.SOFT_INTERVENE,
        AuthorityLevel.TOOL_GATE,
        AuthorityLevel.COMPUTE_GOVERN,
    ]


def test_transition_receipt_binds_the_evidence_ledger_root_and_detects_tampering() -> None:
    """Catches a transition attestation that survives an edited authority or evidence root."""

    unsigned = AuthorityTransitionReceipt(
        schema_version="1.0",
        context={"repository": "repo", "agent": "agent", "model": "model"},
        previous=AuthorityLevel.ADVISE,
        current=AuthorityLevel.SOFT_INTERVENE,
        evidence_ledger_root=ROOT,
        ledger_verification=VERIFIED_REPORT,
        blockers=(),
        receipt_hash="",
    )
    receipt = replace(unsigned, receipt_hash=transition_receipt_hash(unsigned))

    assert verify_transition_receipt(receipt)
    assert not verify_transition_receipt(replace(receipt, current=AuthorityLevel.TOOL_GATE))
    with pytest.raises(ValueError, match="ledger_verification"):
        replace(receipt, evidence_ledger_root="b" * 64)


def test_transition_receipt_requires_a_valid_report_for_its_exact_ledger_root() -> None:
    """Catches treating any digest-shaped string as verified governance evidence."""

    with pytest.raises(ValueError, match="ledger_verification"):
        AuthorityTransitionReceipt(
            schema_version="1.0",
            context={"repository": "repo"},
            previous=AuthorityLevel.OBSERVE,
            current=AuthorityLevel.ADVISE,
            evidence_ledger_root=ROOT,
            ledger_verification=LedgerVerificationReport(False, 3, ROOT, 3, ("BAD",)),
            blockers=(),
            receipt_hash="",
        )
    with pytest.raises(ValueError, match="evidence_ledger_root"):
        AuthorityTransitionReceipt(
            schema_version="1.0",
            context={"repository": "repo"},
            previous=AuthorityLevel.OBSERVE,
            current=AuthorityLevel.ADVISE,
            evidence_ledger_root=ROOT,
            ledger_verification=LedgerVerificationReport(True, 3, "b" * 64, None, ()),
            blockers=(),
            receipt_hash="",
        )


@pytest.mark.parametrize("root", ["", "not-a-root", "A" * 64, "a" * 63])
def test_transition_receipt_rejects_an_invalid_evidence_ledger_root(root: str) -> None:
    """Catches emitting a transition receipt that cannot anchor a verified evidence chain."""

    with pytest.raises(ValueError, match="evidence_ledger_root"):
        AuthorityTransitionReceipt(
            schema_version="1.0",
            context={"repository": "repo"},
            previous=AuthorityLevel.OBSERVE,
            current=AuthorityLevel.ADVISE,
            evidence_ledger_root=root,
            ledger_verification=VERIFIED_REPORT,
            blockers=(),
            receipt_hash="",
        )
