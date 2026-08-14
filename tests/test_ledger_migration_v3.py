from __future__ import annotations

import os
from pathlib import Path

import pytest

from marginal import governance_ledger
from marginal.cli import main
from marginal.governance_ledger import GovernanceLedger, migrate_v2_to_v3
from marginal.ledger import DecisionLedgerContext, JsonlDecisionLedger


def test_migration_is_deterministic_preserves_v2_source_and_verifies_root(tmp_path: Path) -> None:
    """Changing migration order, timestamps, or source data must change this chain."""

    source = tmp_path / "decision-v2.jsonl"
    legacy = JsonlDecisionLedger(source, context=DecisionLedgerContext(run_id="run"))
    legacy.emit({"event": "custom", "evidence": {"kind": "first"}})
    legacy.emit({"event": "custom", "evidence": {"kind": "second"}})
    original = source.read_bytes()

    first_destination = tmp_path / "first-v3.jsonl"
    second_destination = tmp_path / "second-v3.jsonl"
    first = migrate_v2_to_v3(source, first_destination)
    second = migrate_v2_to_v3(source, second_destination)

    assert source.read_bytes() == original
    assert first.valid is True
    assert first.records == 2
    assert first.root_hash is not None
    assert second.root_hash == first.root_hash
    assert second_destination.read_bytes() == first_destination.read_bytes()
    assert GovernanceLedger(first_destination).verify(expected_root=first.root_hash).valid is True


def test_migration_rejects_unsafe_v2_records_without_creating_destination(tmp_path: Path) -> None:
    """A legacy raw prompt is never copied into the governance-ledger v3."""

    source = tmp_path / "unsafe-v2.jsonl"
    JsonlDecisionLedger(source, context=DecisionLedgerContext(run_id="run")).emit(
        {"event": "custom", "raw_prompt": "credential-bearing request"}
    )
    destination = tmp_path / "unsafe-v3.jsonl"

    with pytest.raises(ValueError, match="private field"):
        migrate_v2_to_v3(source, destination)

    assert not destination.exists()


def test_migration_never_overwrites_existing_destination(tmp_path: Path) -> None:
    """A pre-existing v3 file remains authoritative during a migration attempt."""

    source = tmp_path / "decision-v2.jsonl"
    JsonlDecisionLedger(source, context=DecisionLedgerContext(run_id="run")).emit(
        {"event": "custom"}
    )
    destination = tmp_path / "existing-v3.jsonl"
    destination.write_text("authoritative", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        migrate_v2_to_v3(source, destination)

    assert destination.read_text(encoding="utf-8") == "authoritative"


def test_cli_ledger_migrate_reports_verified_record_count_and_root(tmp_path: Path, capsys) -> None:
    """The migration command reports the verified destination rather than a blind copy."""

    source = tmp_path / "decision-v2.jsonl"
    JsonlDecisionLedger(source, context=DecisionLedgerContext(run_id="run")).emit(
        {"event": "custom"}
    )
    destination = tmp_path / "decision-v3.jsonl"

    assert main(["ledger-migrate", str(source), str(destination)]) == 0

    output = capsys.readouterr().out
    report = GovernanceLedger(destination).verify()
    assert report.valid is True
    assert f"migrated 1 records to {destination}; root {report.root_hash}" in output


def test_migration_and_quarantine_reject_symlinked_destination_parent(tmp_path: Path) -> None:
    """Derived v3 evidence never escapes through a symlinked output directory."""

    source = tmp_path / "decision-v2.jsonl"
    JsonlDecisionLedger(source, context=DecisionLedgerContext(run_id="run")).emit(
        {"event": "custom"}
    )
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(ValueError, match="parent"):
        migrate_v2_to_v3(source, link / "migrated.jsonl")

    corrupt = tmp_path / "corrupt.jsonl"
    ledger = GovernanceLedger(corrupt)
    ledger.append({"kind": "receipt"})
    corrupt.write_text('{"invalid":true}\n', encoding="utf-8")
    from marginal.governance_ledger import quarantine_invalid_records

    with pytest.raises(ValueError, match="parent"):
        quarantine_invalid_records(corrupt, link / "quarantine")
    assert not (target / "migrated.jsonl").exists()
    assert not (target / "quarantine").exists()


def test_migration_opens_the_v2_source_relative_to_a_secure_directory_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The legacy reader cannot reopen a name after the source parent is validated."""

    source = tmp_path / "decision-v2.jsonl"
    JsonlDecisionLedger(source, context=DecisionLedgerContext(run_id="run")).emit(
        {"event": "custom"}
    )
    destination = tmp_path / "decision-v3.jsonl"
    calls: list[tuple[object, int | None]] = []
    original_open = os.open

    def recording_open(
        name: object, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        calls.append((name, dir_fd))
        if dir_fd is None:
            return original_open(name, flags, mode)
        return original_open(name, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(governance_ledger.os, "open", recording_open)

    assert migrate_v2_to_v3(source, destination).valid is True
    assert any(name == source.name and directory_fd is not None for name, directory_fd in calls)
