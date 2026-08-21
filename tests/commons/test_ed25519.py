from __future__ import annotations

import pytest

from marginal.commons.ed25519 import verify_ed25519

# RFC 8032, section 7.1, test vector 1 (empty message).
RFC8032_PUBLIC_KEY = bytes.fromhex(
    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
)
RFC8032_SIGNATURE = bytes.fromhex(
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)
GROUP_ORDER = 2**252 + 27742317777372353535851937790883648493
FIELD_PRIME = 2**255 - 19


def test_rfc8032_valid_vector() -> None:
    assert verify_ed25519(RFC8032_PUBLIC_KEY, b"", RFC8032_SIGNATURE) is True


def test_tampered_rfc8032_signature_is_rejected() -> None:
    tampered = RFC8032_SIGNATURE[:-1] + bytes([RFC8032_SIGNATURE[-1] ^ 1])
    assert verify_ed25519(RFC8032_PUBLIC_KEY, b"", tampered) is False


@pytest.mark.parametrize(
    ("public_key", "signature"),
    [
        (RFC8032_PUBLIC_KEY[:-1], RFC8032_SIGNATURE),
        (RFC8032_PUBLIC_KEY, RFC8032_SIGNATURE[:-1]),
        (RFC8032_PUBLIC_KEY + b"\0", RFC8032_SIGNATURE),
        (RFC8032_PUBLIC_KEY, RFC8032_SIGNATURE + b"\0"),
    ],
)
def test_wrong_key_or_signature_length_is_rejected(public_key: bytes, signature: bytes) -> None:
    assert verify_ed25519(public_key, b"", signature) is False


def test_noncanonical_public_point_encoding_is_rejected() -> None:
    encoded_y_equal_to_p = FIELD_PRIME.to_bytes(32, "little")
    assert verify_ed25519(encoded_y_equal_to_p, b"", RFC8032_SIGNATURE) is False


def test_malformed_public_point_is_rejected() -> None:
    # y=2 has no corresponding x on Edwards25519.
    malformed = (2).to_bytes(32, "little")
    assert verify_ed25519(malformed, b"", RFC8032_SIGNATURE) is False


def test_small_order_public_key_is_rejected() -> None:
    identity = (1).to_bytes(32, "little")
    assert verify_ed25519(identity, b"", RFC8032_SIGNATURE) is False


def test_invalid_subgroup_public_key_is_rejected() -> None:
    # Add the order-2 point (0, -1) to the RFC public point. This remains a valid,
    # non-small-order curve point but is outside the prime-order subgroup.
    encoded_y = int.from_bytes(RFC8032_PUBLIC_KEY, "little")
    y = encoded_y & ((1 << 255) - 1)
    invalid_subgroup_y = (-y) % FIELD_PRIME
    invalid_subgroup = invalid_subgroup_y.to_bytes(32, "little")
    invalid_subgroup = invalid_subgroup[:-1] + bytes(
        [invalid_subgroup[-1] | (RFC8032_PUBLIC_KEY[-1] & 0x80)]
    )
    assert verify_ed25519(invalid_subgroup, b"", RFC8032_SIGNATURE) is False


def test_malformed_r_is_rejected() -> None:
    malformed_r = FIELD_PRIME.to_bytes(32, "little")
    assert verify_ed25519(RFC8032_PUBLIC_KEY, b"", malformed_r + RFC8032_SIGNATURE[32:]) is False


def test_small_order_r_is_rejected() -> None:
    identity_r = (1).to_bytes(32, "little")
    assert verify_ed25519(RFC8032_PUBLIC_KEY, b"", identity_r + RFC8032_SIGNATURE[32:]) is False


def test_s_at_or_above_group_order_is_rejected() -> None:
    signature = RFC8032_SIGNATURE[:32] + GROUP_ORDER.to_bytes(32, "little")
    assert verify_ed25519(RFC8032_PUBLIC_KEY, b"", signature) is False


def test_tampered_message_is_rejected() -> None:
    assert verify_ed25519(RFC8032_PUBLIC_KEY, b"tampered", RFC8032_SIGNATURE) is False
