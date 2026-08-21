"""Independent tests for the signed Commons trust chain."""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from marginal.commons.trust import (
    CommonsTrustError,
    ReleaseCertificate,
    decode_base64url_strict,
    verify_release_certificate_with_root,
    verify_signed_pack_with_root,
)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _public(private: Ed25519PrivateKey) -> bytes:
    return private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _signed_fixture(
    pack: bytes = b'{"commons_revision":7}',
) -> tuple[bytes, bytes, bytes, Ed25519PrivateKey, Ed25519PrivateKey]:
    root = Ed25519PrivateKey.generate()
    release = Ed25519PrivateKey.generate()
    certificate = {
        "schema_version": "1.0",
        "algorithm": "ed25519",
        "key_id": "release-test",
        "public_key": _b64(_public(release)),
        "not_before_revision": 1,
        "not_after_revision": 10,
    }
    root_document = _canonical(
        {
            "schema_version": "1.0",
            "algorithm": "ed25519",
            "key_id": "root-test",
            "public_key": _b64(_public(root)),
        }
    )
    envelope = {
        "schema_version": "1.0",
        "algorithm": "ed25519",
        "key_id": "release-test",
        "certificate": certificate,
        "certificate_signature": {
            "schema_version": "1.0",
            "algorithm": "ed25519",
            "key_id": "root-test",
            "signature": _b64(root.sign(_canonical(certificate))),
        },
        "signature": _b64(release.sign(pack)),
    }
    return pack, _canonical(envelope), root_document, root, release


def test_independently_signed_chain_verifies_exact_pack_bytes() -> None:
    pack, envelope, root_document, _root, _release = _signed_fixture()

    certificate = verify_signed_pack_with_root(pack, envelope, root_document)

    assert certificate == ReleaseCertificate(
        key_id="release-test",
        public_key=decode_base64url_strict(
            json.loads(envelope)["certificate"]["public_key"], expected_length=32
        ),
        not_before_revision=1,
        not_after_revision=10,
    )


def test_packaged_production_release_certificate_verifies_against_public_root() -> None:
    repository = Path(__file__).resolve().parents[2]

    certificate = verify_release_certificate_with_root(
        (repository / "contracts" / "commons-release-key-v1.json").read_bytes(),
        (repository / "contracts" / "commons-release-key-v1.sig.json").read_bytes(),
        (repository / "contracts" / "commons-root-key-v1.json").read_bytes(),
    )

    assert certificate.key_id == "commons-release-962b690a695e079d"
    assert certificate.not_before_revision == 1
    assert certificate.not_after_revision == 2_147_483_647


def test_wrong_root_is_rejected() -> None:
    pack, envelope, _root_document, _root, _release = _signed_fixture()
    wrong_root = Ed25519PrivateKey.generate()
    wrong_document = _canonical(
        {
            "schema_version": "1.0",
            "algorithm": "ed25519",
            "key_id": "root-test",
            "public_key": _b64(_public(wrong_root)),
        }
    )

    with pytest.raises(CommonsTrustError):
        verify_signed_pack_with_root(pack, envelope, wrong_document)


def test_forged_release_certificate_is_rejected() -> None:
    pack, envelope, root_document, _root, _release = _signed_fixture()
    payload = json.loads(envelope)
    payload["certificate"]["not_after_revision"] = 11

    with pytest.raises(CommonsTrustError):
        verify_signed_pack_with_root(pack, _canonical(payload), root_document)


def test_wrong_release_key_is_rejected() -> None:
    pack, envelope, root_document, root, _release = _signed_fixture()
    payload = json.loads(envelope)
    payload["certificate"]["public_key"] = _b64(_public(Ed25519PrivateKey.generate()))
    payload["certificate_signature"]["signature"] = _b64(
        root.sign(_canonical(payload["certificate"]))
    )

    with pytest.raises(CommonsTrustError):
        verify_signed_pack_with_root(pack, _canonical(payload), root_document)


def test_tampered_pack_is_rejected() -> None:
    pack, envelope, root_document, _root, _release = _signed_fixture()
    with pytest.raises(CommonsTrustError):
        verify_signed_pack_with_root(pack + b" ", envelope, root_document)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value + "=",
        lambda value: value[:-1] + "+",
        lambda value: value + "A",
    ],
)
def test_signature_base64url_is_strict_and_unpadded(mutate: object) -> None:
    pack, envelope, root_document, _root, _release = _signed_fixture()
    payload = json.loads(envelope)
    payload["signature"] = mutate(payload["signature"])  # type: ignore[operator]

    with pytest.raises(CommonsTrustError):
        verify_signed_pack_with_root(pack, _canonical(payload), root_document)


@pytest.mark.parametrize("location", ["envelope", "certificate"])
def test_closed_envelope_and_certificate_reject_extra_fields(location: str) -> None:
    pack, envelope, root_document, _root, _release = _signed_fixture()
    payload = json.loads(envelope)
    target = payload if location == "envelope" else payload["certificate"]
    target["extra"] = "not-allowed"

    with pytest.raises(CommonsTrustError):
        verify_signed_pack_with_root(pack, _canonical(payload), root_document)


def test_duplicate_json_fields_are_rejected() -> None:
    pack, envelope, root_document, _root, _release = _signed_fixture()
    duplicate = envelope[:-1] + b',"signature":"duplicate"}'
    with pytest.raises(CommonsTrustError):
        verify_signed_pack_with_root(pack, duplicate, root_document)


def test_certificate_bounds_are_positive_ordered_integers() -> None:
    pack, envelope, root_document, root, _release = _signed_fixture()
    payload = json.loads(envelope)
    for before, after in ((0, 10), (1, 0), (11, 10), (True, 10)):
        payload["certificate"]["not_before_revision"] = before
        payload["certificate"]["not_after_revision"] = after
        payload["certificate_signature"]["signature"] = _b64(
            root.sign(_canonical(payload["certificate"]))
        )
        with pytest.raises(CommonsTrustError):
            verify_signed_pack_with_root(pack, _canonical(payload), root_document)


def test_release_certificate_dataclass_is_immutable() -> None:
    certificate = ReleaseCertificate("release", b"x" * 32, 1, 2)
    with pytest.raises(AttributeError):
        replace(certificate, key_id="changed").key_id = "again"  # type: ignore[misc]
