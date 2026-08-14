from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from marginal import governance_ledger
from marginal.canonical import canonical_bytes, canonical_hash
from marginal.cli import main
from marginal.governance_ledger import GovernanceLedger


def test_append_writes_contiguous_hash_linked_canonical_records(tmp_path: Path) -> None:
    """Removing sequence or linkage binding must invalidate this observable chain."""

    path = tmp_path / "governance.jsonl"
    ledger = GovernanceLedger(path)

    first_hash = ledger.append({"kind": "receipt", "value": 1})
    second_hash = ledger.append({"kind": "outcome", "value": 2})

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [record["sequence"] for record in records] == [1, 2]
    assert records[0]["previous_hash"] is None
    assert records[1]["previous_hash"] == first_hash
    assert records[0]["record_hash"] == first_hash
    assert records[1]["record_hash"] == second_hash
    report = ledger.verify(expected_root=second_hash)
    assert report.valid is True
    assert report.records == 2
    assert report.root_hash == second_hash


def _write_records(path: Path, records: list[dict[str, object]]) -> None:
    path.write_bytes(b"".join(canonical_bytes(record) + b"\n" for record in records))


def _rehashed(record: dict[str, object]) -> dict[str, object]:
    record["record_hash"] = canonical_hash(
        {key: value for key, value in record.items() if key != "record_hash"}
    )
    return record


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda records: records[1].update({"payload": {"kind": "outcome", "value": 99}}),
            "PAYLOAD_HASH_MISMATCH",
        ),
        (
            lambda records: _rehashed(records[1].update({"previous_hash": "0" * 64}) or records[1]),
            "PREVIOUS_HASH_MISMATCH",
        ),
        (
            lambda records: records[1].update({"record_hash": "0" * 64}),
            "RECORD_HASH_MISMATCH",
        ),
    ],
)
def test_verify_fails_closed_for_hash_chain_corruption(
    tmp_path: Path, mutation, expected_code: str
) -> None:
    """A changed payload, link, or envelope hash must never verify as evidence."""

    path = tmp_path / "governance.jsonl"
    ledger = GovernanceLedger(path)
    ledger.append({"kind": "receipt", "value": 1})
    ledger.append({"kind": "outcome", "value": 2})
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    mutation(records)
    _write_records(path, records)

    report = ledger.verify()

    assert report.valid is False
    assert report.records == 1
    assert report.first_invalid_sequence == 2
    assert report.error_codes == (expected_code,)


def test_verify_detects_deleted_middle_record_and_expected_root_mismatch(tmp_path: Path) -> None:
    """Dropping evidence or pointing at another root must fail closed."""

    path = tmp_path / "governance.jsonl"
    ledger = GovernanceLedger(path)
    ledger.append({"kind": "first"})
    ledger.append({"kind": "second"})
    root = ledger.append({"kind": "third"})
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    _write_records(path, [records[0], records[2]])

    missing = ledger.verify()
    assert missing.valid is False
    assert missing.first_invalid_sequence == 2
    assert missing.error_codes == ("SEQUENCE_GAP",)

    _write_records(path, records)
    mismatch = ledger.verify(expected_root="0" * 64)
    assert mismatch.valid is False
    assert mismatch.root_hash == root
    assert mismatch.error_codes == ("EXPECTED_ROOT_MISMATCH",)


def test_verify_rejects_incompatible_schema_and_noncanonical_lines(tmp_path: Path) -> None:
    """Schema drift and noncanonical encodings are not attested records."""

    path = tmp_path / "governance.jsonl"
    ledger = GovernanceLedger(path)
    ledger.append({"kind": "receipt"})
    record = json.loads(path.read_text(encoding="utf-8"))
    record["schema_version"] = "4.0"
    _write_records(path, [_rehashed(record)])
    assert ledger.verify().error_codes == ("UNSUPPORTED_SCHEMA",)

    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert ledger.verify().error_codes == ("NONCANONICAL_LINE",)


def test_append_rejects_unsafe_or_non_json_payloads(tmp_path: Path) -> None:
    """Attestations never stringify arbitrary objects or persist raw private fields."""

    ledger = GovernanceLedger(tmp_path / "governance.jsonl")

    with pytest.raises(TypeError, match="canonical JSON"):
        ledger.append({"evidence": object()})
    with pytest.raises(ValueError, match="private field"):
        ledger.append({"raw_prompt": "do not persist"})
    with pytest.raises(ValueError, match="private field"):
        ledger.append({"rawPrompt": "do not persist"})


def test_governance_ledger_uses_owner_only_permissions_and_refuses_unsafe_paths(
    tmp_path: Path,
) -> None:
    """A public, linked, or non-regular target cannot become governance evidence."""

    path = tmp_path / "governance.jsonl"
    GovernanceLedger(path).append({"kind": "receipt"})
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0
    link = tmp_path / "linked.jsonl"
    try:
        link.symlink_to(path)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable")
    with pytest.raises(ValueError, match="symbolic link"):
        GovernanceLedger(link)
    with pytest.raises(ValueError, match="regular file"):
        GovernanceLedger(tmp_path)


def test_quarantine_preserves_source_and_copies_only_invalid_suffix(tmp_path: Path) -> None:
    """Quarantine records corruption explicitly without deleting evidence."""

    from marginal.governance_ledger import quarantine_invalid_records

    source = tmp_path / "governance.jsonl"
    ledger = GovernanceLedger(source)
    ledger.append({"kind": "first"})
    ledger.append({"kind": "second"})
    original = source.read_bytes()
    records = [json.loads(line) for line in original.splitlines()]
    records[1]["payload"] = {"kind": "tampered"}
    _write_records(source, records)
    corrupt_source = source.read_bytes()

    quarantine = quarantine_invalid_records(source, tmp_path / "quarantine")

    assert source.read_bytes() == corrupt_source
    assert (quarantine / "invalid-records.jsonl").read_bytes() == canonical_bytes(
        records[1]
    ) + b"\n"
    report = json.loads((quarantine / "report.json").read_text(encoding="utf-8"))
    assert report["first_invalid_sequence"] == 2
    assert report["error_codes"] == ["PAYLOAD_HASH_MISMATCH"]
    if os.name != "nt":
        assert quarantine.stat().st_mode & 0o077 == 0


def test_cli_verify_has_stable_json_success_and_integrity_error(tmp_path: Path, capsys) -> None:
    """CLI consumers receive typed verification reports for valid and invalid chains."""

    path = tmp_path / "governance.jsonl"
    root = GovernanceLedger(path).append({"kind": "receipt"})

    assert main(["verify", str(path), "--expected-root", root, "--json"]) == 0
    valid = json.loads(capsys.readouterr().out)
    assert valid == {
        "error_codes": [],
        "first_invalid_sequence": None,
        "records": 1,
        "root_hash": root,
        "valid": True,
    }

    path.write_text('{"corrupted":true}\n', encoding="utf-8")
    assert main(["verify", str(path), "--json"]) == 1
    invalid = json.loads(capsys.readouterr().out)
    assert invalid["valid"] is False
    assert invalid["error_codes"] == ["INVALID_RECORD"]


def test_append_rejects_traversal_and_symlinked_parent_before_creating_directories(
    tmp_path: Path,
) -> None:
    """A ledger path is an absolute, lexical path below no symlinked component."""

    traversing = tmp_path / "untrusted" / ".." / "ledger.jsonl"
    with pytest.raises(ValueError, match="traversal"):
        GovernanceLedger(traversing)
    assert not (tmp_path / "untrusted").exists()

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable")
    with pytest.raises(ValueError, match="parent"):
        GovernanceLedger(link / "ledger.jsonl").append({"kind": "receipt"})
    assert not (target / "ledger.jsonl").exists()


def test_verify_rejects_unsafe_path_without_creating_missing_parent(tmp_path: Path) -> None:
    """Verification is read-only even when an attacker supplies a missing path."""

    path = tmp_path / "missing-parent" / "ledger.jsonl"

    report = GovernanceLedger(path).verify()

    assert report.valid is False
    assert report.error_codes == ("IO_ERROR",)
    assert not path.parent.exists()


def test_verify_rejects_non_integer_sequence_and_naive_timestamp(tmp_path: Path) -> None:
    """The chain enforces the schema's integer and RFC3339-style core envelope fields."""

    path = tmp_path / "governance.jsonl"
    GovernanceLedger(path).append({"kind": "receipt"})
    record = json.loads(path.read_text(encoding="utf-8"))
    record["sequence"] = 1.0
    _write_records(path, [_rehashed(record)])
    assert GovernanceLedger(path).verify().error_codes == ("INVALID_RECORD",)

    record["sequence"] = 1
    record["timestamp"] = "2026-08-14T00:00:00"
    _write_records(path, [_rehashed(record)])
    assert GovernanceLedger(path).verify().error_codes == ("INVALID_TIMESTAMP",)


def test_cli_verify_serializes_constructor_path_errors(tmp_path: Path, capsys) -> None:
    """Unsafe verify input returns the same structured failure shape as bad evidence."""

    assert main(["verify", str(tmp_path), "--json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "error_codes": ["IO_ERROR"],
        "first_invalid_sequence": None,
        "records": 0,
        "root_hash": None,
        "valid": False,
    }


def test_append_and_verify_open_the_leaf_relative_to_a_nofollow_directory_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parent validation cannot be invalidated between traversal and leaf open."""

    path = tmp_path / "parents" / "governance.jsonl"
    calls: list[tuple[object, int | None]] = []
    original_open = os.open

    def recording_open(
        name: object, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        calls.append((name, dir_fd))
        if dir_fd is None:
            return original_open(name, flags, mode)
        return original_open(name, flags, mode, dir_fd=dir_fd)

    # Preserve real system behavior while recording the descriptor boundary contract.
    monkeypatch.setattr(governance_ledger.os, "open", recording_open)

    ledger = GovernanceLedger(path)
    ledger.append({"kind": "receipt"})
    ledger.verify()

    assert any(name == path.name and directory_fd is not None for name, directory_fd in calls)


def test_append_fails_closed_without_directory_fd_safety_primitives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No platform is advertised as race-safe when nofollow directory walks are unavailable."""

    monkeypatch.setattr(governance_ledger.os, "O_DIRECTORY", 0)

    with pytest.raises(OSError, match="directory descriptor"):
        GovernanceLedger(tmp_path / "governance.jsonl").append({"kind": "receipt"})
