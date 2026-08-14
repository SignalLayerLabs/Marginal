"""Progressive enforcement levels and hash-bound authority transitions."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum
from types import MappingProxyType

from .canonical import canonical_hash
from .governance_ledger import LedgerVerificationReport

AUTHORITY_TRANSITION_SCHEMA_VERSION = "1.0"
_HEX = frozenset("0123456789abcdef")


class AuthorityLevel(IntEnum):
    """Increasing power to alter an agent's execution."""

    OBSERVE = 0
    ADVISE = 1
    SOFT_INTERVENE = 2
    TOOL_GATE = 3
    COMPUTE_GOVERN = 4


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _sha256(value: str, name: str) -> str:
    _required_text(value, name)
    if len(value) != 64 or any(character not in _HEX for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class AuthorityTransitionReceipt:
    """An immutable transition attestation anchored to the evidence-ledger root."""

    schema_version: str
    context: Mapping[str, str]
    previous: AuthorityLevel
    current: AuthorityLevel
    evidence_ledger_root: str
    ledger_verification: LedgerVerificationReport
    blockers: tuple[str, ...]
    receipt_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != AUTHORITY_TRANSITION_SCHEMA_VERSION:
            raise ValueError("unsupported authority transition schema version")
        if not isinstance(self.context, Mapping):
            raise TypeError("context must be a mapping")
        normalized_context: dict[str, str] = {}
        for key, value in self.context.items():
            normalized_context[_required_text(key, "context key")] = _required_text(
                value, f"context[{key!r}]"
            )
        object.__setattr__(self, "context", MappingProxyType(normalized_context))
        if not isinstance(self.previous, AuthorityLevel) or not isinstance(
            self.current, AuthorityLevel
        ):
            raise TypeError("previous and current must be AuthorityLevel")
        _sha256(self.evidence_ledger_root, "evidence_ledger_root")
        if not isinstance(self.ledger_verification, LedgerVerificationReport):
            raise TypeError("ledger_verification must be LedgerVerificationReport")
        if (
            not self.ledger_verification.valid
            or self.ledger_verification.root_hash != self.evidence_ledger_root
        ):
            raise ValueError("ledger_verification must validate evidence_ledger_root")
        if not isinstance(self.blockers, tuple) or not all(
            isinstance(item, str) and item for item in self.blockers
        ):
            raise TypeError("blockers must be a tuple of non-empty strings")
        if not isinstance(self.receipt_hash, str):
            raise TypeError("receipt_hash must be a string")

    def payload(self) -> dict[str, object]:
        """Return the canonical fields committed by ``receipt_hash``."""

        return {
            "schema_version": self.schema_version,
            "context": dict(self.context),
            "previous": int(self.previous),
            "current": int(self.current),
            "evidence_ledger_root": self.evidence_ledger_root,
            "ledger_records": self.ledger_verification.records,
            "blockers": list(self.blockers),
        }


def transition_receipt_hash(receipt: AuthorityTransitionReceipt) -> str:
    """Hash a transition without trusting arbitrary object representations."""

    if not isinstance(receipt, AuthorityTransitionReceipt):
        raise TypeError("receipt must be AuthorityTransitionReceipt")
    return canonical_hash(receipt.payload())


def verify_transition_receipt(receipt: AuthorityTransitionReceipt) -> bool:
    """Return whether a receipt still binds its exact canonical transition payload."""

    if not isinstance(receipt, AuthorityTransitionReceipt):
        return False
    if len(receipt.receipt_hash) != 64 or any(char not in _HEX for char in receipt.receipt_hash):
        return False
    return hmac.compare_digest(receipt.receipt_hash, transition_receipt_hash(receipt))
