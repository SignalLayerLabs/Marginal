from __future__ import annotations

import pytest

from marginal.canonical import canonical_bytes, canonical_hash
from marginal.fingerprint import fingerprint_action
from marginal.models import Action
from marginal.policy import MarginalPolicy, PolicyConfig


def test_canonical_hash_is_stable_across_mapping_key_order() -> None:
    """Catches a serializer regression that stops sorting mapping keys."""

    first = {"z": [2, 1], "a": "café"}
    second = {"a": "café", "z": [2, 1]}

    assert canonical_bytes(first) == b'{"a":"caf\xc3\xa9","z":[2,1]}'
    assert canonical_hash(first) == canonical_hash(second)


@pytest.mark.parametrize("value", [float("nan"), {"value": float("nan")}, b"not-json"])
def test_canonical_serialization_rejects_non_json_values(value: object) -> None:
    """Catches accepting NaN or values without a JSON representation as attestation input."""

    with pytest.raises((TypeError, ValueError)):
        canonical_bytes(value)


def test_existing_fingerprint_and_policy_hashes_remain_compatible() -> None:
    """Catches a shared-hash refactor changing frozen action or policy identities."""

    action = Action(
        name="café",
        kind="tool",
        metadata={"z": 1, "a": "é"},
    )

    assert (
        fingerprint_action(action)
        == "7ca348d0e0f9734011057570463aea0ef57b7d40e793e8059ccd21b730225b84"
    )
    assert (
        MarginalPolicy(PolicyConfig(minimum_roi=1.2)).identity.config_hash
        == "c4ace16a8fffaea091fbda0757630ff52f10867f5538adcd752f1e8f866f3388"
    )
