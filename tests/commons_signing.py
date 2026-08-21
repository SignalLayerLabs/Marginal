from __future__ import annotations

import base64
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from marginal.commons.client import CommonsPackDownload

ROOT_PRIVATE = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
RELEASE_PRIVATE = Ed25519PrivateKey.from_private_bytes(bytes(range(32, 64)))
MODEL_NAMESPACES = (
    "openai/gpt-5.6-luna",
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
)


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def public_bytes(private: Ed25519PrivateKey) -> bytes:
    return private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def root_document() -> bytes:
    return canonical(
        {
            "schema_version": "1.0",
            "algorithm": "ed25519",
            "key_id": "test-root",
            "public_key": b64url(public_bytes(ROOT_PRIVATE)),
        }
    )


def pack_bytes(
    *,
    revision: int = 1,
    source_commit: str = "a" * 40,
    models: dict[str, list[dict[str, object]]] | None = None,
    compatibility: str = "1.0",
    extra: tuple[str, object] | None = None,
) -> bytes:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "source_commit": source_commit,
        "commons_revision": revision,
        "compatibility": {"evidence_envelope_schema_version": compatibility},
        "models": {
            namespace: {"aggregates": (models or {}).get(namespace, [])}
            for namespace in MODEL_NAMESPACES
        },
    }
    if extra is not None:
        payload[extra[0]] = extra[1]
    payload["integrity"] = {"sha256": hashlib.sha256(canonical(payload)).hexdigest()}
    return canonical(payload)


def signed_download(
    pack: bytes,
    *,
    not_before_revision: int = 1,
    not_after_revision: int = 2_147_483_647,
    release_private: Ed25519PrivateKey = RELEASE_PRIVATE,
) -> CommonsPackDownload:
    certificate = {
        "schema_version": "1.0",
        "algorithm": "ed25519",
        "key_id": "test-release",
        "public_key": b64url(public_bytes(release_private)),
        "not_before_revision": not_before_revision,
        "not_after_revision": not_after_revision,
    }
    envelope = {
        "schema_version": "1.0",
        "algorithm": "ed25519",
        "key_id": "test-release",
        "certificate": certificate,
        "certificate_signature": {
            "schema_version": "1.0",
            "algorithm": "ed25519",
            "key_id": "test-root",
            "signature": b64url(ROOT_PRIVATE.sign(canonical(certificate))),
        },
        "signature": b64url(release_private.sign(pack)),
    }
    return CommonsPackDownload(pack=pack, signature=canonical(envelope))
