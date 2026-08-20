from __future__ import annotations

import dataclasses
import hashlib
import json
import multiprocessing
import os
import re
import stat
import threading
from pathlib import Path

import pytest

from marginal.commons.evidence import (
    ActionKind,
    AggregateReasonCode,
    CommonsEvidenceAtom,
    CommonsEvidenceBatch,
    DecisionClass,
    OutcomeClass,
    RecordType,
    ValueBucket,
)
from marginal.commons.identity import resolve_canonical_model
from marginal.commons.outbox import CommonsOutbox

MODEL_NAMESPACE = "openai/gpt-5.6-sol"


def _atom(model: str = "gpt-5.6-sol") -> CommonsEvidenceAtom:
    identity = resolve_canonical_model(provider="openai", model=model)
    assert identity is not None
    return CommonsEvidenceAtom(
        model_identity=identity,
        record_type=RecordType.DECISION,
        action_kind=ActionKind.TEST,
        cost_bucket=ValueBucket.LOW,
        gain_bucket=ValueBucket.HIGH,
        recommendation=DecisionClass.ALLOW,
        applied_decision=DecisionClass.ALLOW,
        reason_code=AggregateReasonCode.APPROVED,
        outcome_class=OutcomeClass.NOT_APPLICABLE,
        count=7,
        minimum_group_size=5,
    )


def _batch(model: str = "gpt-5.6-sol") -> CommonsEvidenceBatch:
    identity = resolve_canonical_model(provider="openai", model=model)
    assert identity is not None
    return CommonsEvidenceBatch(identity=identity, atoms=(_atom(model),))


def _enqueue_child(data_dir: str, results: multiprocessing.Queue[str]) -> None:
    entry = CommonsOutbox(data_dir).enqueue(batch=_batch())
    results.put(entry.name if entry is not None else "")


def test_enqueue_is_private_atomic_and_keeps_retry_identity_outside_evidence(
    tmp_path: Path,
) -> None:
    outbox = CommonsOutbox(tmp_path)

    entry = outbox.enqueue(batch=_batch())

    assert entry is not None
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", entry.retry_token)
    assert "retry" not in json.dumps(entry.envelope, sort_keys=True).lower()
    persisted = (outbox.queue_path / entry.name).read_bytes()
    raw = json.loads(persisted)
    assert raw == {"envelope": entry.envelope, "retry_token": entry.retry_token}
    assert entry.canonical_record == persisted
    assert entry.record_sha256 == hashlib.sha256(entry.canonical_record).hexdigest()
    assert json.loads(entry.body_bytes) == entry.envelope
    assert stat.S_IMODE((outbox.queue_path / entry.name).stat().st_mode) == 0o600
    assert stat.S_IMODE(outbox.queue_path.stat().st_mode) == 0o700


def test_restart_recovers_the_same_one_time_retry_token_and_ack_deletes_exact_entry(
    tmp_path: Path,
) -> None:
    first = CommonsOutbox(tmp_path)
    queued = first.enqueue(batch=_batch())
    assert queued is not None

    restarted = CommonsOutbox(tmp_path)
    pending = restarted.pending(limit=8)

    assert len(pending.entries) == 1
    assert pending.entries[0].retry_token == queued.retry_token
    assert restarted.ack(pending.entries[0]) is True
    assert restarted.pending(limit=8).entries == ()


def test_empty_or_unregistered_evidence_is_never_queued(tmp_path: Path) -> None:
    outbox = CommonsOutbox(tmp_path)

    empty = CommonsEvidenceBatch(identity=_batch().identity, atoms=())
    assert outbox.enqueue(batch=empty) is None
    assert not outbox.queue_path.exists()


def test_pending_quarantines_malformed_files_without_following_symlinks(tmp_path: Path) -> None:
    outbox = CommonsOutbox(tmp_path)
    queued = outbox.enqueue(batch=_batch())
    assert queued is not None
    malformed = outbox.queue_path / "queue-malformed.json"
    malformed.write_text('{"retry_token":"privacy-canary"}', encoding="utf-8")
    malformed.chmod(0o600)
    outside = tmp_path / "outside"
    outside.write_text("do-not-read", encoding="utf-8")
    symlink = outbox.queue_path / "queue-symlink.json"
    symlink.symlink_to(outside)

    scan = outbox.pending(limit=8)

    assert [entry.name for entry in scan.entries] == [queued.name]
    assert scan.quarantined == 2
    assert outside.read_text(encoding="utf-8") == "do-not-read"
    assert not malformed.exists()
    assert not symlink.exists()
    assert (
        len([path for path in outbox.quarantine_path.iterdir() if not path.name.startswith(".")])
        == 2
    )


def test_pending_quarantines_duplicate_json_fields_instead_of_accepting_last_value(
    tmp_path: Path,
) -> None:
    outbox = CommonsOutbox(tmp_path)
    queued = outbox.enqueue(batch=_batch())
    assert queued is not None
    path = outbox.queue_path / queued.name
    raw = path.read_text(encoding="utf-8")
    attacked = raw.replace(
        '"schema_version":"1.0"',
        '"schema_version":"2.0","schema_version":"1.0"',
    )
    path.write_text(attacked, encoding="utf-8")
    path.chmod(0o600)

    scan = outbox.pending(limit=8)

    assert scan.entries == ()
    assert scan.quarantined == 1


def test_pending_quarantines_recursive_json_without_stopping_other_work(tmp_path: Path) -> None:
    outbox = CommonsOutbox(tmp_path)
    valid = outbox.enqueue(batch=_batch())
    assert valid is not None
    recursive = outbox.queue_path / f"queue-{'f' * 32}.json"
    recursive.write_text("[" * 2_000 + "]" * 2_000, encoding="utf-8")
    recursive.chmod(0o600)

    scan = outbox.pending(limit=8)

    assert [entry.name for entry in scan.entries] == [valid.name]
    assert scan.quarantined == 1


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO leaves are POSIX-specific")
def test_pending_rejects_a_fifo_leaf_without_blocking_for_a_writer(tmp_path: Path) -> None:
    outbox = CommonsOutbox(tmp_path)
    queued = outbox.enqueue(batch=_batch())
    assert queued is not None
    fifo = outbox.queue_path / "queue-fifo.json"
    os.mkfifo(fifo, mode=0o600)
    completed = threading.Event()

    def scan() -> None:
        outbox.pending(limit=8)
        completed.set()

    worker = threading.Thread(target=scan, daemon=True)
    worker.start()
    returned_without_writer = completed.wait(timeout=0.2)
    if not returned_without_writer:
        writer = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        os.close(writer)
        worker.join(timeout=1)

    assert returned_without_writer is True


def test_ack_refuses_a_different_inode_reusing_the_same_name(tmp_path: Path) -> None:
    outbox = CommonsOutbox(tmp_path)
    queued = outbox.enqueue(batch=_batch())
    assert queued is not None
    path = outbox.queue_path / queued.name
    path.unlink()
    path.write_text("replacement", encoding="utf-8")
    path.chmod(0o600)

    assert outbox.ack(queued) is False
    assert path.read_text(encoding="utf-8") == "replacement"


def test_ack_and_quarantine_reject_forged_traversal_names(tmp_path: Path) -> None:
    outbox = CommonsOutbox(tmp_path)
    queued = outbox.enqueue(batch=_batch())
    assert queued is not None
    victim = tmp_path / "victim.json"
    victim.write_bytes((outbox.queue_path / queued.name).read_bytes())
    victim.chmod(0o600)
    metadata = victim.stat()
    forged = dataclasses.replace(
        queued,
        name="../../../victim.json",
        device=metadata.st_dev,
        inode=metadata.st_ino,
    )

    assert outbox.ack(forged) is False
    assert outbox.quarantine(forged) is False
    assert victim.exists()


def test_transition_revalidates_canonical_content_immediately_before_delete(tmp_path: Path) -> None:
    outbox = CommonsOutbox(tmp_path)
    queued = outbox.enqueue(batch=_batch())
    assert queued is not None
    path = outbox.queue_path / queued.name
    mutated = path.read_bytes().replace(b'"action_kind":"test"', b'"action_kind":"search"')
    path.write_bytes(mutated)
    path.chmod(0o600)

    assert outbox.ack(queued) is False
    assert path.exists()


def test_transition_revalidates_bound_retry_token_and_digest(tmp_path: Path) -> None:
    outbox = CommonsOutbox(tmp_path)
    queued = outbox.enqueue(batch=_batch())
    assert queued is not None

    assert outbox.ack(dataclasses.replace(queued, retry_token="x" * 43)) is False
    assert outbox.quarantine(dataclasses.replace(queued, record_sha256="0" * 64)) is False
    assert (outbox.queue_path / queued.name).exists()


def test_enqueue_handles_random_name_collision_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outbox = CommonsOutbox(tmp_path)
    tokens = iter(["a" * 32, "a" * 32, "b" * 32])
    monkeypatch.setattr("marginal.commons.outbox.secrets.token_hex", lambda _size: next(tokens))

    first = outbox.enqueue(batch=_batch())
    second = outbox.enqueue(batch=_batch())

    assert first is not None and second is not None
    assert first.name != second.name
    assert len(outbox.pending(limit=8).entries) == 2


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions are required")
def test_outbox_rejects_weak_existing_queue_permissions(tmp_path: Path) -> None:
    queue = tmp_path / "commons" / "outbox" / "queue"
    queue.mkdir(parents=True)
    queue.chmod(0o755)

    with pytest.raises(PermissionError, match="owner-only"):
        CommonsOutbox(tmp_path).pending(limit=1)


def test_outbox_rejects_a_symlinked_queue_directory_without_writing_outside(tmp_path: Path) -> None:
    outbox = CommonsOutbox(tmp_path)
    outbox.queue_path.parent.mkdir(parents=True)
    outside = tmp_path / "outside-queue"
    outside.mkdir()
    outbox.queue_path.symlink_to(outside, target_is_directory=True)

    with pytest.raises((OSError, ValueError)):
        outbox.enqueue(batch=_batch())

    assert list(outside.iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX process locks are required")
def test_concurrent_processes_publish_complete_unique_entries(tmp_path: Path) -> None:
    context = multiprocessing.get_context("fork")
    results: multiprocessing.Queue[str] = context.Queue()
    processes = [
        context.Process(target=_enqueue_child, args=(str(tmp_path), results)) for _ in range(6)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=5)

    assert all(process.exitcode == 0 for process in processes)
    names = [results.get(timeout=1) for _ in processes]
    assert len(set(names)) == 6
    assert len(CommonsOutbox(tmp_path).pending(limit=8).entries) == 6
