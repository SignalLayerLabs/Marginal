"""Closed parsing and verification for signed MARGINAL Commons releases."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from importlib import resources
from typing import Any

from .ed25519 import verify_ed25519

_ROOT_RESOURCE = "commons-root-key-v1.json"
_MAX_ROOT_BYTES = 4096
_MAX_ENVELOPE_BYTES = 64 * 1024
_MAX_REVISION = 2_147_483_647
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+\Z")


class CommonsTrustError(ValueError):
    """A signed Commons artifact failed its closed trust contract."""


@dataclass(frozen=True, slots=True)
class ReleaseCertificate:
    """Verified release-key identity and its permitted Commons revision interval."""

    key_id: str
    public_key: bytes
    not_before_revision: int
    not_after_revision: int


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CommonsTrustError("invalid signed Commons artifact")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise CommonsTrustError("invalid signed Commons artifact")


def _load_closed_json(raw: bytes, *, maximum_bytes: int) -> object:
    if not isinstance(raw, bytes) or not raw or len(raw) > maximum_bytes:
        raise CommonsTrustError("invalid signed Commons artifact")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        CommonsTrustError,
        RecursionError,
        MemoryError,
        OverflowError,
    ):
        raise CommonsTrustError("invalid signed Commons artifact") from None


def _exact_mapping(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise CommonsTrustError("invalid signed Commons artifact")
    return value


def decode_base64url_strict(value: object, *, expected_length: int) -> bytes:
    """Decode one canonical unpadded base64url string of an exact byte length."""

    if (
        not isinstance(value, str)
        or not _BASE64URL.fullmatch(value)
        or "=" in value
        or len(value) % 4 == 1
    ):
        raise CommonsTrustError("invalid signed Commons artifact")
    try:
        decoded = base64.b64decode(value + "=" * ((-len(value)) % 4), altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        raise CommonsTrustError("invalid signed Commons artifact") from None
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if decoded.__len__() != expected_length or canonical != value:
        raise CommonsTrustError("invalid signed Commons artifact")
    return decoded


def _algorithm_header(value: dict[str, Any]) -> tuple[str, str]:
    schema_version = value["schema_version"]
    algorithm = value["algorithm"]
    key_id = value["key_id"]
    if (
        schema_version != "1.0"
        or algorithm != "ed25519"
        or not isinstance(key_id, str)
        or not key_id
        or len(key_id) > 128
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", key_id)
    ):
        raise CommonsTrustError("invalid signed Commons artifact")
    return algorithm, key_id


def _positive_revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= _MAX_REVISION:
        raise CommonsTrustError("invalid signed Commons artifact")
    return value


def _canonical_certificate(certificate: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            certificate,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError, MemoryError, OverflowError):
        raise CommonsTrustError("invalid signed Commons artifact") from None


def _parse_root(root_document: bytes) -> tuple[str, bytes]:
    root = _exact_mapping(
        _load_closed_json(root_document, maximum_bytes=_MAX_ROOT_BYTES),
        {"schema_version", "algorithm", "key_id", "public_key"},
    )
    _root_algorithm, root_key_id = _algorithm_header(root)
    return root_key_id, decode_base64url_strict(root["public_key"], expected_length=32)


def _parse_certificate(certificate_value: object) -> tuple[dict[str, Any], ReleaseCertificate]:
    certificate = _exact_mapping(
        certificate_value,
        {
            "schema_version",
            "algorithm",
            "key_id",
            "public_key",
            "not_before_revision",
            "not_after_revision",
        },
    )
    _certificate_algorithm, certificate_key_id = _algorithm_header(certificate)
    public_key = decode_base64url_strict(certificate["public_key"], expected_length=32)
    not_before = _positive_revision(certificate["not_before_revision"])
    not_after = _positive_revision(certificate["not_after_revision"])
    if not_before > not_after:
        raise CommonsTrustError("invalid signed Commons artifact")
    return certificate, ReleaseCertificate(certificate_key_id, public_key, not_before, not_after)


def _verify_certificate_signature(
    certificate: dict[str, Any],
    certificate_signature_value: object,
    *,
    root_key_id: str,
    root_public_key: bytes,
) -> None:
    certificate_signature = _exact_mapping(
        certificate_signature_value,
        {"schema_version", "algorithm", "key_id", "signature"},
    )
    _signature_algorithm, signature_key_id = _algorithm_header(certificate_signature)
    if signature_key_id != root_key_id:
        raise CommonsTrustError("invalid signed Commons artifact")
    root_signature = decode_base64url_strict(certificate_signature["signature"], expected_length=64)
    if not verify_ed25519(root_public_key, _canonical_certificate(certificate), root_signature):
        raise CommonsTrustError("invalid signed Commons artifact")


def verify_release_certificate_with_root(
    certificate_document: bytes,
    certificate_signature_document: bytes,
    root_document: bytes,
) -> ReleaseCertificate:
    """Verify a closed standalone release certificate against a public root document."""

    root_key_id, root_public_key = _parse_root(root_document)
    certificate, parsed = _parse_certificate(
        _load_closed_json(certificate_document, maximum_bytes=_MAX_ROOT_BYTES)
    )
    certificate_signature = _load_closed_json(
        certificate_signature_document, maximum_bytes=_MAX_ROOT_BYTES
    )
    _verify_certificate_signature(
        certificate,
        certificate_signature,
        root_key_id=root_key_id,
        root_public_key=root_public_key,
    )
    return parsed


def verify_signed_pack_with_root(
    pack: bytes, envelope_bytes: bytes, root_document: bytes
) -> ReleaseCertificate:
    """Verify a detached pack signature through an explicitly supplied public root document."""

    if not isinstance(pack, bytes):
        raise CommonsTrustError("invalid signed Commons artifact")
    root_key_id, root_public_key = _parse_root(root_document)

    envelope = _exact_mapping(
        _load_closed_json(envelope_bytes, maximum_bytes=_MAX_ENVELOPE_BYTES),
        {
            "schema_version",
            "algorithm",
            "key_id",
            "certificate",
            "certificate_signature",
            "signature",
        },
    )
    _envelope_algorithm, envelope_key_id = _algorithm_header(envelope)
    certificate, parsed_certificate = _parse_certificate(envelope["certificate"])
    if envelope_key_id != parsed_certificate.key_id:
        raise CommonsTrustError("invalid signed Commons artifact")
    _verify_certificate_signature(
        certificate,
        envelope["certificate_signature"],
        root_key_id=root_key_id,
        root_public_key=root_public_key,
    )

    pack_signature = decode_base64url_strict(envelope["signature"], expected_length=64)
    if not verify_ed25519(parsed_certificate.public_key, pack, pack_signature):
        raise CommonsTrustError("invalid signed Commons artifact")
    return parsed_certificate


def verify_signed_pack(pack: bytes, envelope_bytes: bytes) -> ReleaseCertificate:
    """Verify a detached Commons pack using MARGINAL's packaged public root anchor."""

    try:
        root_document = resources.files("marginal.commons").joinpath(_ROOT_RESOURCE).read_bytes()
    except (FileNotFoundError, OSError):
        raise CommonsTrustError("invalid signed Commons artifact") from None
    return verify_signed_pack_with_root(pack, envelope_bytes, root_document)


__all__ = [
    "CommonsTrustError",
    "ReleaseCertificate",
    "decode_base64url_strict",
    "verify_release_certificate_with_root",
    "verify_signed_pack",
    "verify_signed_pack_with_root",
]
