#!/usr/bin/env python3
"""Build and independently verify a signed Commons release from immutable Git data."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

_SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_SCRIPT_ROOT / "src"))

from marginal.commons.cache import _parse_pack  # noqa: E402
from marginal.commons.trust import (  # noqa: E402
    CommonsTrustError,
    decode_base64url_strict,
    verify_release_certificate_with_root,
    verify_signed_pack_with_root,
)

MAX_SOURCE_BYTES = 2 * 1024 * 1024
_MAX_RELEASE_BYTES = 3 * 1024 * 1024
_TRUSTED_ROOT = _SCRIPT_ROOT
_PRIVATE_KEY_ENV = "COMMONS_RELEASE_PRIVATE_KEY_B64URL"
_PACK_NAME = "commons-pack-v1.json"
_SIGNATURE_NAME = "commons-pack-v1.sig.json"


class CommonsReleaseError(ValueError):
    """Untrusted input or signing configuration cannot produce a release."""


@dataclass(frozen=True, slots=True)
class ReleaseArtifacts:
    pack: Path
    signature: Path


@dataclass(frozen=True, slots=True)
class VerifiedRelease:
    revision: int
    source_commit: str


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError, MemoryError, OverflowError):
        raise CommonsReleaseError("release data is not canonical JSON") from None


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CommonsReleaseError("release input contains a duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise CommonsReleaseError("release input is invalid JSON")


def _json_bytes(raw: bytes, *, label: str) -> object:
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        raise CommonsReleaseError(f"{label} is too large or empty")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except CommonsReleaseError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        MemoryError,
        OverflowError,
    ):
        raise CommonsReleaseError(f"{label} is invalid JSON") from None


def _mapping(value: object, *, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise CommonsReleaseError(f"{label} has unknown or missing fields")
    return value


def _git_environment() -> dict[str, str]:
    environment = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.defpath,
    }
    return environment


class _GitSnapshot:
    def __init__(self, repository: Path, revision: str) -> None:
        self.repository = repository.resolve()
        if not self.repository.is_dir():
            raise CommonsReleaseError("Commons repository is unavailable")
        resolved = self._run("rev-parse", "--verify", f"{revision}^{{commit}}").decode().strip()
        if len(resolved) != 40 or any(
            character not in "0123456789abcdef" for character in resolved
        ):
            raise CommonsReleaseError("Commons revision is not a commit")
        self.requested_commit = resolved

    def _run(self, *arguments: str) -> bytes:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repository), *arguments],
                check=False,
                capture_output=True,
                env=_git_environment(),
            )
        except OSError:
            raise CommonsReleaseError("Commons Git snapshot is unavailable") from None
        if result.returncode != 0:
            raise CommonsReleaseError("Commons Git snapshot is unavailable")
        return result.stdout

    def _entry(self, commit: str, path: str) -> tuple[str, str, str] | None:
        raw = self._run("ls-tree", "-z", commit, "--", path)
        if not raw:
            return None
        entries = raw.rstrip(b"\0").split(b"\0")
        if len(entries) != 1:
            raise CommonsReleaseError(f"invalid Git entry for {path}")
        metadata, separator, listed_path = entries[0].partition(b"\t")
        if not separator or listed_path.decode("utf-8", "strict") != path:
            raise CommonsReleaseError(f"invalid Git entry for {path}")
        try:
            mode, kind, object_id = metadata.decode("ascii").split(" ")
        except ValueError:
            raise CommonsReleaseError(f"invalid Git entry for {path}") from None
        return mode, kind, object_id

    def read(self, commit: str, path: str, *, required: bool) -> bytes | None:
        entry = self._entry(commit, path)
        if entry is None:
            if required:
                raise CommonsReleaseError(f"missing release input: {path}")
            return None
        mode, kind, object_id = entry
        if mode == "120000":
            raise CommonsReleaseError(f"symlink release input: {path}")
        if mode != "100644" or kind != "blob":
            raise CommonsReleaseError(f"non-regular Git release input: {path}")
        size_raw = self._run("cat-file", "-s", object_id)
        try:
            size = int(size_raw)
        except ValueError:
            raise CommonsReleaseError(f"invalid Git entry for {path}") from None
        if size < 1 or size > MAX_SOURCE_BYTES:
            raise CommonsReleaseError(f"release input is too large: {path}")
        content = self._run("cat-file", "blob", object_id)
        if len(content) != size:
            raise CommonsReleaseError(f"invalid Git blob for {path}")
        return content

    def listed_paths(self, commit: str, *roots: str) -> tuple[str, ...]:
        raw = self._run("ls-tree", "-r", "-z", "--name-only", commit, "--", *roots)
        if not raw:
            return ()
        try:
            return tuple(item.decode("utf-8") for item in raw.rstrip(b"\0").split(b"\0"))
        except UnicodeDecodeError:
            raise CommonsReleaseError("release tree contains an invalid path") from None

    def release_history(self, paths: tuple[str, ...]) -> tuple[str, ...]:
        raw = self._run("rev-list", "--reverse", self.requested_commit, "--", *paths)
        commits = tuple(raw.decode("ascii").splitlines())
        if not commits:
            raise CommonsReleaseError("Commons release input history is empty")
        if any(len(commit) != 40 for commit in commits):
            raise CommonsReleaseError("Commons release input history is invalid")
        return commits


def _trusted_bytes(relative: str) -> bytes:
    path = _TRUSTED_ROOT / relative
    try:
        raw = path.read_bytes()
    except OSError:
        raise CommonsReleaseError("trusted MARGINAL release contract is unavailable") from None
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        raise CommonsReleaseError("trusted MARGINAL release contract is invalid")
    return raw


def _trusted_registry() -> tuple[dict[str, Any], tuple[str, ...]]:
    registry = _mapping(
        _json_bytes(
            _trusted_bytes("models/canonical-model-registry-v1.json"),
            label="trusted model registry",
        ),
        keys={"schema_version", "models"},
        label="trusted model registry",
    )
    models = registry["models"]
    if registry["schema_version"] != "1.0" or not isinstance(models, dict) or not models:
        raise CommonsReleaseError("trusted model registry is invalid")
    namespaces = tuple(sorted(models.values()))
    if not all(isinstance(value, str) and value for value in namespaces) or len(
        set(namespaces)
    ) != len(namespaces):
        raise CommonsReleaseError("trusted model registry is invalid")
    return registry, namespaces


def _aggregate_contract() -> tuple[set[str], dict[str, dict[str, Any]]]:
    schema = _mapping(
        _json_bytes(_trusted_bytes("schemas/commons-pack-v1.json"), label="trusted pack schema"),
        keys={
            "$schema",
            "$id",
            "title",
            "type",
            "required",
            "properties",
            "additionalProperties",
            "unevaluatedProperties",
            "$defs",
        },
        label="trusted pack schema",
    )
    definitions = schema["$defs"]
    if not isinstance(definitions, dict) or not isinstance(definitions.get("aggregate"), dict):
        raise CommonsReleaseError("trusted pack schema is invalid")
    aggregate = definitions["aggregate"]
    required = aggregate.get("required")
    properties = aggregate.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        raise CommonsReleaseError("trusted pack schema is invalid")
    atom_fields = set(required) - {"lifecycle"}
    if set(properties) != set(required):
        raise CommonsReleaseError("trusted pack schema is invalid")
    return atom_fields, properties


def _parse_atom(
    value: object, *, atom_fields: set[str], properties: dict[str, dict[str, Any]]
) -> dict[str, object]:
    atom = _mapping(value, keys=atom_fields, label="aggregate atom")
    result: dict[str, object] = {}
    for field in sorted(atom_fields):
        candidate = atom[field]
        specification = properties[field]
        if "enum" in specification:
            allowed = specification["enum"]
            if not isinstance(candidate, str) or candidate not in allowed:
                raise CommonsReleaseError(f"aggregate {field} is invalid")
        else:
            minimum = specification.get("minimum")
            maximum = specification.get("maximum")
            if (
                isinstance(candidate, bool)
                or not isinstance(candidate, int)
                or not isinstance(minimum, int)
                or not isinstance(maximum, int)
                or not minimum <= candidate <= maximum
            ):
                raise CommonsReleaseError(f"aggregate {field} count is invalid")
        result[field] = candidate
    return result


def _identity(atom: dict[str, object]) -> tuple[object, ...]:
    return tuple(atom[field] for field in sorted(set(atom) - {"count"}))


def _parse_aggregate_document(
    raw: bytes,
    *,
    namespace: str,
    atom_fields: set[str],
    properties: dict[str, dict[str, Any]],
) -> list[dict[str, object]]:
    document = _mapping(
        _json_bytes(raw, label="aggregate document"),
        keys={"schema_version", "model_namespace", "atoms"},
        label="aggregate document",
    )
    if document["schema_version"] != "1.0":
        raise CommonsReleaseError("aggregate schema version is invalid")
    if document["model_namespace"] != namespace:
        raise CommonsReleaseError("aggregate namespace does not match its path")
    atoms = document["atoms"]
    if not isinstance(atoms, list) or not atoms or len(atoms) > 10_000:
        raise CommonsReleaseError("aggregate atoms are invalid")
    parsed = [_parse_atom(item, atom_fields=atom_fields, properties=properties) for item in atoms]
    identities = [_identity(atom) for atom in parsed]
    if len(set(identities)) != len(identities):
        raise CommonsReleaseError("duplicate aggregate dimensions")
    return parsed


def _parse_lifecycle_artifacts(
    raw: bytes | None,
    *,
    namespaces: tuple[str, ...],
    atom_fields: set[str],
    properties: dict[str, dict[str, Any]],
) -> dict[str, dict[str, set[tuple[object, ...]]]]:
    if raw is None:
        return {}
    document = _mapping(
        _json_bytes(raw, label="lifecycle artifacts"),
        keys={"schema_version", "models"},
        label="lifecycle artifacts",
    )
    if document["schema_version"] != "1.0":
        raise CommonsReleaseError("lifecycle artifacts schema version is invalid")
    models = document["models"]
    if not isinstance(models, dict) or set(models) != set(namespaces):
        raise CommonsReleaseError("lifecycle artifact registry is invalid")
    identity_fields = atom_fields - {"count"}
    result: dict[str, dict[str, set[tuple[object, ...]]]] = {}
    for namespace, lifecycle_value in models.items():
        lifecycle = _mapping(
            lifecycle_value,
            keys={"supported", "validated", "promoted"},
            label="lifecycle artifact",
        )
        result[namespace] = {}
        for label in ("supported", "validated", "promoted"):
            values = lifecycle[label]
            if not isinstance(values, list) or len(values) > 10_000:
                raise CommonsReleaseError("lifecycle artifact list is invalid")
            identities: list[tuple[object, ...]] = []
            for value in values:
                identity_value = _mapping(
                    value, keys=identity_fields, label="lifecycle aggregate identity"
                )
                atom = _parse_atom(
                    {**identity_value, "count": 1},
                    atom_fields=atom_fields,
                    properties=properties,
                )
                identities.append(_identity(atom))
            if len(set(identities)) != len(identities):
                raise CommonsReleaseError("duplicate lifecycle aggregate identity")
            result[namespace][label] = set(identities)
    return result


def _lifecycle(
    namespace: str,
    atom: dict[str, object],
    artifacts: dict[str, dict[str, set[tuple[object, ...]]]],
) -> str:
    identity = _identity(atom)
    state = "candidate"
    namespace_artifacts = artifacts.get(namespace, {})
    for next_state in ("supported", "validated", "promoted"):
        if identity not in namespace_artifacts.get(next_state, set()):
            break
        state = next_state
    return state


def _release_inputs(namespaces: tuple[str, ...]) -> tuple[str, ...]:
    return (
        "models/canonical-model-registry-v1.json",
        "models/registry-v1.json",
        *(f"models/{namespace}/aggregates.json" for namespace in namespaces),
        "validation/artifacts-v1.json",
    )


def _reject_unknown_release_data(snapshot: _GitSnapshot, *, allowed: tuple[str, ...]) -> None:
    allowed_set = set(allowed)
    for path in snapshot.listed_paths(snapshot.requested_commit, "models", "validation"):
        if path.endswith(".json") and path not in allowed_set:
            label = "lifecycle" if path.startswith("validation/") else "model registry"
            raise CommonsReleaseError(f"unreviewed {label} release input")


def _compile_pack(repository: Path, *, source_revision: str) -> bytes:
    trusted_registry, namespaces = _trusted_registry()
    atom_fields, properties = _aggregate_contract()
    inputs = _release_inputs(namespaces)
    snapshot = _GitSnapshot(repository, source_revision)
    _reject_unknown_release_data(snapshot, allowed=inputs)
    history = snapshot.release_history(inputs)
    source_commit = history[-1]
    canonical_registry_raw = snapshot.read(
        source_commit, "models/canonical-model-registry-v1.json", required=True
    )
    registry_raw = snapshot.read(source_commit, "models/registry-v1.json", required=True)
    assert canonical_registry_raw is not None and registry_raw is not None
    canonical_registry = _json_bytes(canonical_registry_raw, label="Commons canonical registry")
    registry = _json_bytes(registry_raw, label="Commons registry")
    if canonical_registry != trusted_registry or registry != trusted_registry:
        raise CommonsReleaseError("Commons model registry drifted from MARGINAL")
    lifecycle_raw = snapshot.read(source_commit, "validation/artifacts-v1.json", required=False)
    artifacts = _parse_lifecycle_artifacts(
        lifecycle_raw,
        namespaces=namespaces,
        atom_fields=atom_fields,
        properties=properties,
    )
    models: dict[str, dict[str, list[dict[str, object]]]] = {}
    for namespace in namespaces:
        raw = snapshot.read(source_commit, f"models/{namespace}/aggregates.json", required=False)
        aggregates: list[dict[str, object]] = []
        if raw is not None:
            for atom in _parse_aggregate_document(
                raw,
                namespace=namespace,
                atom_fields=atom_fields,
                properties=properties,
            ):
                aggregates.append({**atom, "lifecycle": _lifecycle(namespace, atom, artifacts)})
            aggregates.sort(key=_canonical)
        models[namespace] = {"aggregates": aggregates}
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "source_commit": source_commit,
        "commons_revision": len(history),
        "compatibility": {"evidence_envelope_schema_version": "1.0"},
        "models": models,
    }
    payload["integrity"] = {"sha256": hashlib.sha256(_canonical(payload)).hexdigest()}
    return _canonical(payload)


def _load_signing_material() -> tuple[Ed25519PrivateKey, dict[str, Any], dict[str, Any], bytes]:
    root_document = _trusted_bytes("contracts/commons-root-key-v1.json")
    certificate_document = _trusted_bytes("contracts/commons-release-key-v1.json")
    certificate_signature_document = _trusted_bytes("contracts/commons-release-key-v1.sig.json")
    try:
        verified = verify_release_certificate_with_root(
            certificate_document, certificate_signature_document, root_document
        )
        encoded_seed = os.environ.get(_PRIVATE_KEY_ENV)
        seed = decode_base64url_strict(encoded_seed, expected_length=32)
        private_key = Ed25519PrivateKey.from_private_bytes(seed)
        derived_public = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    except (CommonsTrustError, TypeError, ValueError):
        raise CommonsReleaseError("release private key or public trust chain is invalid") from None
    if not hmac.compare_digest(derived_public, verified.public_key):
        raise CommonsReleaseError("release private key does not match public certificate")
    certificate = _mapping(
        _json_bytes(certificate_document, label="release certificate"),
        keys={
            "schema_version",
            "algorithm",
            "key_id",
            "public_key",
            "not_before_revision",
            "not_after_revision",
        },
        label="release certificate",
    )
    certificate_signature = _mapping(
        _json_bytes(certificate_signature_document, label="certificate signature"),
        keys={"schema_version", "algorithm", "key_id", "signature"},
        label="certificate signature",
    )
    return private_key, certificate, certificate_signature, root_document


def _write_release(output_dir: Path, pack: bytes, signature: bytes) -> ReleaseArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    pack_path = output_dir / _PACK_NAME
    signature_path = output_dir / _SIGNATURE_NAME
    pack_path.write_bytes(pack)
    signature_path.write_bytes(signature)
    return ReleaseArtifacts(pack=pack_path, signature=signature_path)


def build_release(
    commons_repository: str | Path,
    *,
    source_revision: str,
    output_dir: str | Path,
) -> ReleaseArtifacts:
    """Build, sign, independently verify, and write one deterministic release pair."""

    private_key, certificate, certificate_signature, root_document = _load_signing_material()
    pack = _compile_pack(Path(commons_repository), source_revision=source_revision)
    envelope = {
        "schema_version": "1.0",
        "algorithm": "ed25519",
        "key_id": certificate["key_id"],
        "certificate": certificate,
        "certificate_signature": certificate_signature,
        "signature": base64.urlsafe_b64encode(private_key.sign(pack)).rstrip(b"=").decode("ascii"),
    }
    signature = _canonical(envelope)
    try:
        verified_certificate = verify_signed_pack_with_root(pack, signature, root_document)
        parsed_pack = _parse_pack(pack)
    except (CommonsTrustError, ValueError, RecursionError, MemoryError, OverflowError):
        raise CommonsReleaseError("built release failed strict verification") from None
    revision = parsed_pack["commons_revision"]
    if (
        not verified_certificate.not_before_revision
        <= revision
        <= verified_certificate.not_after_revision
    ):
        raise CommonsReleaseError("built release revision is outside its certificate")
    _independent_crypto_verify(pack, signature, root_document)
    return _write_release(Path(output_dir), pack, signature)


def _independent_crypto_verify(pack: bytes, signature: bytes, root_document: bytes) -> None:
    try:
        envelope = _mapping(
            _json_bytes(signature, label="detached signature"),
            keys={
                "schema_version",
                "algorithm",
                "key_id",
                "certificate",
                "certificate_signature",
                "signature",
            },
            label="detached signature",
        )
        certificate = envelope["certificate"]
        certificate_signature = envelope["certificate_signature"]
        assert isinstance(certificate, dict) and isinstance(certificate_signature, dict)
        root = _json_bytes(root_document, label="root key")
        assert isinstance(root, dict)
        root_public = decode_base64url_strict(root["public_key"], expected_length=32)
        release_public = decode_base64url_strict(certificate["public_key"], expected_length=32)
        root_signature = decode_base64url_strict(
            certificate_signature["signature"], expected_length=64
        )
        pack_signature = decode_base64url_strict(envelope["signature"], expected_length=64)
        Ed25519PublicKey.from_public_bytes(root_public).verify(
            root_signature, _canonical(certificate)
        )
        Ed25519PublicKey.from_public_bytes(release_public).verify(pack_signature, pack)
    except (
        AssertionError,
        KeyError,
        TypeError,
        ValueError,
        InvalidSignature,
        CommonsTrustError,
    ):
        raise CommonsReleaseError("release failed independent signature verification") from None


def verify_release_artifacts(pack_path: str | Path, signature_path: str | Path) -> VerifiedRelease:
    """Independently verify existing candidate files against MARGINAL's public root."""

    try:
        pack = Path(pack_path).read_bytes()
        signature = Path(signature_path).read_bytes()
    except OSError:
        raise CommonsReleaseError("release artifact is unavailable") from None
    if (
        not pack
        or len(pack) > _MAX_RELEASE_BYTES
        or not signature
        or len(signature) > MAX_SOURCE_BYTES
    ):
        raise CommonsReleaseError("release artifact is invalid")
    root_document = _trusted_bytes("contracts/commons-root-key-v1.json")
    try:
        certificate = verify_signed_pack_with_root(pack, signature, root_document)
        parsed = _parse_pack(pack)
    except (CommonsTrustError, ValueError, RecursionError, MemoryError, OverflowError):
        raise CommonsReleaseError("release artifact failed strict verification") from None
    revision = parsed["commons_revision"]
    if not certificate.not_before_revision <= revision <= certificate.not_after_revision:
        raise CommonsReleaseError("release artifact revision is outside its certificate")
    _independent_crypto_verify(pack, signature, root_document)
    return VerifiedRelease(revision=revision, source_commit=parsed["source_commit"])


def release_required(
    candidate_pack: str | Path,
    candidate_signature: str | Path,
    current_pack: str | Path,
    current_signature: str | Path,
) -> bool:
    """Fail closed on rollback/equivocation and report whether a newer release is required."""

    candidate = verify_release_artifacts(candidate_pack, candidate_signature)
    current = verify_release_artifacts(current_pack, current_signature)
    if candidate.revision < current.revision:
        raise CommonsReleaseError("candidate release would cause production rollback")
    try:
        candidate_bytes = (
            Path(candidate_pack).read_bytes(),
            Path(candidate_signature).read_bytes(),
        )
        current_bytes = (
            Path(current_pack).read_bytes(),
            Path(current_signature).read_bytes(),
        )
    except OSError:
        raise CommonsReleaseError("release artifact is unavailable") from None
    if candidate.revision == current.revision:
        if candidate_bytes == current_bytes:
            return False
        raise CommonsReleaseError("candidate release conflicts with production equivocation guard")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commons-repo", type=Path)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--verify-pack", type=Path)
    parser.add_argument("--verify-signature", type=Path)
    parser.add_argument("--current-pack", type=Path)
    parser.add_argument("--current-signature", type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.verify_pack is not None or arguments.verify_signature is not None:
            if arguments.verify_pack is None or arguments.verify_signature is None:
                raise CommonsReleaseError("both release verification paths are required")
            if arguments.current_pack is not None or arguments.current_signature is not None:
                if arguments.current_pack is None or arguments.current_signature is None:
                    raise CommonsReleaseError("both current production paths are required")
                required = release_required(
                    arguments.verify_pack,
                    arguments.verify_signature,
                    arguments.current_pack,
                    arguments.current_signature,
                )
                print(f"deploy={'true' if required else 'false'}")
            else:
                verify_release_artifacts(arguments.verify_pack, arguments.verify_signature)
        else:
            if arguments.commons_repo is None or arguments.output_dir is None:
                raise CommonsReleaseError("Commons repository and output directory are required")
            build_release(
                arguments.commons_repo,
                source_revision=arguments.revision,
                output_dir=arguments.output_dir,
            )
    except CommonsReleaseError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
