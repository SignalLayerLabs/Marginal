from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from scripts import build_commons_release as builder
from tests.commons_signing import (
    RELEASE_PRIVATE,
    ROOT_PRIVATE,
    b64url,
    canonical,
    pack_bytes,
    public_bytes,
    signed_download,
)

REPOSITORY = Path(__file__).resolve().parents[2]
NAMESPACE = "openai/gpt-5.6-sol"


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)
    return _git(repo, "rev-parse", "HEAD")


def _atom(*, count: object = 7) -> dict[str, object]:
    return {
        "record_type": "decision",
        "action_kind": "test",
        "cost_bucket": "low",
        "gain_bucket": "high",
        "recommendation": "allow",
        "applied_decision": "allow",
        "reason_code": "APPROVED",
        "outcome_class": "not_applicable",
        "count": count,
        "minimum_group_size": 5,
    }


@pytest.fixture
def commons_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "commons-data"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    registry = json.loads((REPOSITORY / "models" / "canonical-model-registry-v1.json").read_text())
    _write(repo / "models" / "canonical-model-registry-v1.json", registry)
    _write(repo / "models" / "registry-v1.json", registry)
    _commit(repo, "initial release data")
    return repo


@pytest.fixture(autouse=True)
def trusted_test_contracts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    trusted = tmp_path / "trusted-marginal"
    (trusted / "contracts").mkdir(parents=True)
    (trusted / "models").mkdir(parents=True)
    (trusted / "schemas").mkdir(parents=True)
    for relative in (
        "models/canonical-model-registry-v1.json",
        "schemas/commons-pack-v1.json",
    ):
        target = trusted / relative
        target.write_bytes((REPOSITORY / relative).read_bytes())
    certificate = {
        "schema_version": "1.0",
        "algorithm": "ed25519",
        "key_id": "test-release",
        "public_key": b64url(public_bytes(RELEASE_PRIVATE)),
        "not_before_revision": 1,
        "not_after_revision": 2_147_483_647,
    }
    root = {
        "schema_version": "1.0",
        "algorithm": "ed25519",
        "key_id": "test-root",
        "public_key": b64url(public_bytes(ROOT_PRIVATE)),
    }
    certificate_signature = {
        "schema_version": "1.0",
        "algorithm": "ed25519",
        "key_id": "test-root",
        "signature": b64url(ROOT_PRIVATE.sign(canonical(certificate))),
    }
    _write(trusted / "contracts" / "commons-root-key-v1.json", root)
    _write(trusted / "contracts" / "commons-release-key-v1.json", certificate)
    _write(
        trusted / "contracts" / "commons-release-key-v1.sig.json",
        certificate_signature,
    )
    monkeypatch.setattr(builder, "_TRUSTED_ROOT", trusted)
    seed = RELEASE_PRIVATE.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    monkeypatch.setenv("COMMONS_RELEASE_PRIVATE_KEY_B64URL", b64url(seed))
    return trusted


def _build(repo: Path, output: Path, revision: str = "HEAD") -> builder.ReleaseArtifacts:
    return builder.build_release(repo, source_revision=revision, output_dir=output)


def test_builder_never_executes_untrusted_commons_code(commons_repo: Path, tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    script = commons_repo / "tooling" / "build_pack.py"
    script.parent.mkdir()
    script.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n")
    _commit(commons_repo, "malicious tooling")

    _build(commons_repo, tmp_path / "out")

    assert not marker.exists()


def test_symlink_git_input_is_rejected(commons_repo: Path, tmp_path: Path) -> None:
    registry = commons_repo / "models" / "registry-v1.json"
    registry.unlink()
    registry.symlink_to("canonical-model-registry-v1.json")
    _commit(commons_repo, "symlink registry")

    with pytest.raises(builder.CommonsReleaseError, match="symlink"):
        _build(commons_repo, tmp_path / "out")


def test_worktree_mutation_cannot_alter_claimed_snapshot(
    commons_repo: Path, tmp_path: Path
) -> None:
    claimed = _git(commons_repo, "rev-parse", "HEAD")
    aggregate = commons_repo / "models" / NAMESPACE / "aggregates.json"
    _write(
        aggregate,
        {"schema_version": "1.0", "model_namespace": NAMESPACE, "atoms": [_atom()]},
    )

    artifacts = _build(commons_repo, tmp_path / "out", claimed)
    pack = json.loads(artifacts.pack.read_bytes())

    assert pack["models"][NAMESPACE]["aggregates"] == []
    assert pack["source_commit"] == claimed


def test_docs_only_commit_produces_identical_signed_release(
    commons_repo: Path, tmp_path: Path
) -> None:
    first = _build(commons_repo, tmp_path / "first")
    (commons_repo / "README.md").write_text("documentation only\n")
    _commit(commons_repo, "docs only")

    second = _build(commons_repo, tmp_path / "second")

    assert first.pack.read_bytes() == second.pack.read_bytes()
    assert first.signature.read_bytes() == second.signature.read_bytes()


def test_changed_aggregate_advances_revision_and_source_commit(
    commons_repo: Path, tmp_path: Path
) -> None:
    first = _build(commons_repo, tmp_path / "first")
    aggregate = commons_repo / "models" / NAMESPACE / "aggregates.json"
    _write(
        aggregate,
        {"schema_version": "1.0", "model_namespace": NAMESPACE, "atoms": [_atom()]},
    )
    changed_commit = _commit(commons_repo, "aggregate")

    second = _build(commons_repo, tmp_path / "second")
    first_pack = json.loads(first.pack.read_bytes())
    second_pack = json.loads(second.pack.read_bytes())

    assert second_pack["commons_revision"] == first_pack["commons_revision"] + 1
    assert second_pack["source_commit"] == changed_commit


def test_changed_lifecycle_source_advances_revision(commons_repo: Path, tmp_path: Path) -> None:
    aggregate = commons_repo / "models" / NAMESPACE / "aggregates.json"
    _write(
        aggregate,
        {"schema_version": "1.0", "model_namespace": NAMESPACE, "atoms": [_atom()]},
    )
    _commit(commons_repo, "aggregate")
    first = _build(commons_repo, tmp_path / "first")
    identity = {key: value for key, value in _atom().items() if key != "count"}
    namespaces = json.loads(
        (REPOSITORY / "models" / "canonical-model-registry-v1.json").read_text()
    )["models"].values()
    lifecycle = {
        "schema_version": "1.0",
        "models": {
            namespace: {
                "supported": [identity] if namespace == NAMESPACE else [],
                "validated": [],
                "promoted": [],
            }
            for namespace in namespaces
        },
    }
    _write(commons_repo / "validation" / "artifacts-v1.json", lifecycle)
    lifecycle_commit = _commit(commons_repo, "lifecycle")

    second = _build(commons_repo, tmp_path / "second")
    first_pack = json.loads(first.pack.read_bytes())
    second_pack = json.loads(second.pack.read_bytes())

    assert second_pack["commons_revision"] == first_pack["commons_revision"] + 1
    assert second_pack["source_commit"] == lifecycle_commit
    assert second_pack["models"][NAMESPACE]["aggregates"][0]["lifecycle"] == "supported"


def test_deterministic_repeated_build_is_byte_identical(commons_repo: Path, tmp_path: Path) -> None:
    first = _build(commons_repo, tmp_path / "first")
    second = _build(commons_repo, tmp_path / "second")
    assert first.pack.read_bytes() == second.pack.read_bytes()
    assert first.signature.read_bytes() == second.signature.read_bytes()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update({"unknown": "free text"}), "unknown"),
        (lambda value: value["atoms"][0].update({"count": 0}), "count"),
        (
            lambda value: value.update({"model_namespace": "openai/gpt-5.6-terra"}),
            "namespace",
        ),
        (lambda value: value["atoms"].append(dict(value["atoms"][0])), "duplicate"),
    ],
)
def test_poisoned_aggregate_data_is_rejected(
    commons_repo: Path, tmp_path: Path, mutation: object, message: str
) -> None:
    value = {"schema_version": "1.0", "model_namespace": NAMESPACE, "atoms": [_atom()]}
    mutation(value)  # type: ignore[operator]
    _write(commons_repo / "models" / NAMESPACE / "aggregates.json", value)
    _commit(commons_repo, "poison")

    with pytest.raises(builder.CommonsReleaseError, match=message):
        _build(commons_repo, tmp_path / "out")


def test_duplicate_json_keys_and_recursive_or_oversized_input_are_rejected(
    commons_repo: Path, tmp_path: Path
) -> None:
    aggregate = commons_repo / "models" / NAMESPACE / "aggregates.json"
    aggregate.parent.mkdir(parents=True)
    aggregate.write_bytes(
        b'{"schema_version":"1.0","schema_version":"1.0",'
        b'"model_namespace":"openai/gpt-5.6-sol","atoms":[]}'
    )
    _commit(commons_repo, "duplicate json")
    with pytest.raises(builder.CommonsReleaseError, match="duplicate"):
        _build(commons_repo, tmp_path / "duplicate")

    aggregate.write_bytes(b"[" * 2_000 + b"]" * 2_000)
    _commit(commons_repo, "recursive json")
    with pytest.raises(builder.CommonsReleaseError):
        _build(commons_repo, tmp_path / "recursive")

    aggregate.write_bytes(b" " * (builder.MAX_SOURCE_BYTES + 1))
    _commit(commons_repo, "oversized json")
    with pytest.raises(builder.CommonsReleaseError, match="large"):
        _build(commons_repo, tmp_path / "oversized")


def test_registry_drift_and_extra_lifecycle_artifacts_are_rejected(
    commons_repo: Path, tmp_path: Path
) -> None:
    registry = json.loads((commons_repo / "models" / "registry-v1.json").read_text())
    registry["models"]["custom"] = "custom/model"
    _write(commons_repo / "models" / "registry-v1.json", registry)
    _commit(commons_repo, "registry drift")
    with pytest.raises(builder.CommonsReleaseError, match="registry"):
        _build(commons_repo, tmp_path / "registry")

    _write(
        commons_repo / "models" / "registry-v1.json",
        json.loads((REPOSITORY / "models" / "canonical-model-registry-v1.json").read_text()),
    )
    _write(commons_repo / "validation" / "unreviewed-lifecycle.json", {})
    _commit(commons_repo, "extra lifecycle artifact")
    with pytest.raises(builder.CommonsReleaseError, match="lifecycle"):
        _build(commons_repo, tmp_path / "lifecycle")

    (commons_repo / "validation" / "unreviewed-lifecycle.json").unlink()
    marker = tmp_path / "validation-code-executed"
    (commons_repo / "validation" / "lifecycle.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n"
    )
    _commit(commons_repo, "untrusted validation code")

    _build(commons_repo, tmp_path / "untrusted-validation-code")

    assert not marker.exists()


def test_private_key_public_certificate_mismatch_fails_before_writing(
    commons_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "COMMONS_RELEASE_PRIVATE_KEY_B64URL",
        b64url(bytes(reversed(range(32)))),
    )
    output = tmp_path / "out"

    with pytest.raises(builder.CommonsReleaseError, match="does not match") as captured:
        _build(commons_repo, output)

    assert not output.exists()
    assert "COMMONS_RELEASE_PRIVATE_KEY_B64URL" not in str(captured.value)


def test_private_key_must_be_strict_unpadded_base64url_from_environment(
    commons_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COMMONS_RELEASE_PRIVATE_KEY_B64URL", b64url(bytes(range(32))) + "=")
    with pytest.raises(builder.CommonsReleaseError, match="private key"):
        _build(commons_repo, tmp_path / "out")


def test_built_release_is_independently_verified(commons_repo: Path, tmp_path: Path) -> None:
    artifacts = _build(commons_repo, tmp_path / "out")
    verified = builder.verify_release_artifacts(artifacts.pack, artifacts.signature)
    assert verified.revision == 1


def test_production_comparison_is_idempotent_and_anti_rollback(
    commons_repo: Path, tmp_path: Path
) -> None:
    current = _build(commons_repo, tmp_path / "current")
    assert (
        builder.release_required(current.pack, current.signature, current.pack, current.signature)
        is False
    )
    aggregate = commons_repo / "models" / NAMESPACE / "aggregates.json"
    _write(
        aggregate,
        {"schema_version": "1.0", "model_namespace": NAMESPACE, "atoms": [_atom()]},
    )
    _commit(commons_repo, "aggregate")
    candidate = _build(commons_repo, tmp_path / "candidate")
    assert (
        builder.release_required(
            candidate.pack, candidate.signature, current.pack, current.signature
        )
        is True
    )
    with pytest.raises(builder.CommonsReleaseError, match="rollback"):
        builder.release_required(
            current.pack, current.signature, candidate.pack, candidate.signature
        )


def test_production_comparison_fails_closed_for_equivocation_or_invalid_current(
    commons_repo: Path, tmp_path: Path
) -> None:
    candidate = _build(commons_repo, tmp_path / "candidate")
    parsed = json.loads(candidate.pack.read_bytes())
    conflicting_pack = pack_bytes(
        revision=parsed["commons_revision"],
        source_commit=parsed["source_commit"],
        models={NAMESPACE: [{**_atom(), "lifecycle": "candidate"}]},
    )
    conflict = signed_download(conflicting_pack)
    conflict_pack_path = tmp_path / "conflict-pack.json"
    conflict_signature_path = tmp_path / "conflict-signature.json"
    conflict_pack_path.write_bytes(conflict.pack)
    conflict_signature_path.write_bytes(conflict.signature)

    with pytest.raises(builder.CommonsReleaseError, match="equivocation"):
        builder.release_required(
            conflict_pack_path,
            conflict_signature_path,
            candidate.pack,
            candidate.signature,
        )

    invalid_signature = tmp_path / "invalid-signature.json"
    invalid_signature.write_bytes(candidate.signature.read_bytes() + b" ")
    with pytest.raises(builder.CommonsReleaseError):
        builder.release_required(
            candidate.pack,
            candidate.signature,
            candidate.pack,
            invalid_signature,
        )
