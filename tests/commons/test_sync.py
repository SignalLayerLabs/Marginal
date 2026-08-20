from __future__ import annotations

import hashlib
import json
from pathlib import Path

import marginal.commons as commons
from marginal.commons.cache import CommonsCache
from marginal.commons.client import CommonsAck, CommonsHTTPError, CommonsProtocolError
from marginal.commons.config import CommonsConfig, CommonsMode
from marginal.commons.evidence import (
    ActionKind,
    AggregateReasonCode,
    CommonsEvidenceAtom,
    DecisionClass,
    OutcomeClass,
    RecordType,
    ValueBucket,
)
from marginal.commons.outbox import CommonsOutbox, OutboxEntry
from marginal.commons.sync import SyncFailure, synchronize_commons

MODEL_NAMESPACE = "openai/gpt-5.6-sol"
SOURCE_COMMIT = "a" * 40


def _pack_bytes() -> bytes:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "source_commit": SOURCE_COMMIT,
        "commons_revision": 1,
        "compatibility": {"evidence_envelope_schema_version": "1.0"},
        "models": {
            MODEL_NAMESPACE: {"aggregates": []},
            "openai/gpt-5.6-terra": {"aggregates": []},
            "openai/gpt-5.6-luna": {"aggregates": []},
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["integrity"] = {"sha256": hashlib.sha256(canonical).hexdigest()}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


class _RecordingClient:
    def __init__(self, *, pack: bytes | Exception, submit: CommonsAck | Exception) -> None:
        self.pack = pack
        self.submit_result = submit
        self.download_calls = 0
        self.submitted: list[OutboxEntry] = []

    def download(self) -> bytes:
        self.download_calls += 1
        if isinstance(self.pack, Exception):
            raise self.pack
        return self.pack

    def submit(self, entry: OutboxEntry) -> CommonsAck:
        self.submitted.append(entry)
        if isinstance(self.submit_result, Exception):
            raise self.submit_result
        return self.submit_result


def _atom() -> CommonsEvidenceAtom:
    return CommonsEvidenceAtom(
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


def _components(tmp_path: Path) -> tuple[CommonsCache, CommonsOutbox]:
    return (
        CommonsCache(
            tmp_path,
            model_namespace=MODEL_NAMESPACE,
            expected_source_commit=SOURCE_COMMIT,
        ),
        CommonsOutbox(tmp_path),
    )


def test_task_five_interfaces_are_available_from_the_commons_package() -> None:
    assert commons.CommonsCache is CommonsCache
    assert commons.CommonsOutbox is CommonsOutbox
    assert commons.synchronize_commons is synchronize_commons


def test_local_only_makes_zero_network_calls_and_does_not_enqueue(tmp_path: Path) -> None:
    cache, outbox = _components(tmp_path)
    client = _RecordingClient(
        pack=AssertionError("download must not run"),
        submit=AssertionError("submit must not run"),
    )

    result = synchronize_commons(
        CommonsConfig(CommonsMode.LOCAL_ONLY),
        cache=cache,
        outbox=outbox,
        client=client,
        model_namespace=MODEL_NAMESPACE,
        atoms=(_atom(),),
    )

    assert result.network_calls == 0
    assert result.failures == ()
    assert client.download_calls == 0
    assert client.submitted == []
    assert not outbox.queue_path.exists()


def test_read_only_downloads_but_never_enqueues_or_submits(tmp_path: Path) -> None:
    cache, outbox = _components(tmp_path)
    client = _RecordingClient(pack=_pack_bytes(), submit=AssertionError("submit must not run"))

    result = synchronize_commons(
        CommonsConfig(CommonsMode.READ_ONLY),
        cache=cache,
        outbox=outbox,
        client=client,
        model_namespace=MODEL_NAMESPACE,
        atoms=(_atom(),),
    )

    assert result.network_calls == 1
    assert result.cache_refreshed is True
    assert result.submitted == 0
    assert not outbox.queue_path.exists()


def test_contributor_without_new_or_queued_evidence_only_downloads(tmp_path: Path) -> None:
    cache, outbox = _components(tmp_path)
    client = _RecordingClient(pack=_pack_bytes(), submit=AssertionError("submit must not run"))

    result = synchronize_commons(
        CommonsConfig(CommonsMode.CONTRIBUTOR),
        cache=cache,
        outbox=outbox,
        client=client,
        model_namespace=MODEL_NAMESPACE,
        atoms=(),
    )

    assert result.network_calls == 1
    assert result.submitted == 0
    assert client.submitted == []


def test_contributor_ack_deletes_queued_evidence(tmp_path: Path) -> None:
    cache, outbox = _components(tmp_path)
    client = _RecordingClient(pack=_pack_bytes(), submit=CommonsAck(True, False))

    result = synchronize_commons(
        CommonsConfig(CommonsMode.CONTRIBUTOR),
        cache=cache,
        outbox=outbox,
        client=client,
        model_namespace=MODEL_NAMESPACE,
        atoms=(_atom(),),
    )

    assert result.acked == 1
    assert result.submitted == 1
    assert outbox.pending(limit=8).entries == ()


def test_4xx_quarantines_but_5xx_and_protocol_failures_retain_for_retry(tmp_path: Path) -> None:
    for status, expected_quarantined, expected_retained in ((422, 1, 0), (503, 0, 1)):
        case = tmp_path / str(status)
        cache, outbox = _components(case)
        outbox.enqueue(model_namespace=MODEL_NAMESPACE, atoms=(_atom(),))
        client = _RecordingClient(pack=_pack_bytes(), submit=CommonsHTTPError(status=status))

        result = synchronize_commons(
            CommonsConfig(CommonsMode.CONTRIBUTOR),
            cache=cache,
            outbox=outbox,
            client=client,
        )

        assert result.quarantined == expected_quarantined
        assert result.retained == expected_retained
        assert len(outbox.pending(limit=8).entries) == expected_retained

    protocol_case = tmp_path / "protocol"
    cache, outbox = _components(protocol_case)
    outbox.enqueue(model_namespace=MODEL_NAMESPACE, atoms=(_atom(),))
    result = synchronize_commons(
        CommonsConfig(CommonsMode.CONTRIBUTOR),
        cache=cache,
        outbox=outbox,
        client=_RecordingClient(
            pack=_pack_bytes(), submit=CommonsProtocolError("invalid Commons response")
        ),
    )
    assert result.retained == 1
    assert SyncFailure.SUBMIT_PROTOCOL in result.failures


def test_sync_is_bounded_and_download_failure_does_not_block_outbox_retry(tmp_path: Path) -> None:
    cache, outbox = _components(tmp_path)
    for _ in range(3):
        outbox.enqueue(model_namespace=MODEL_NAMESPACE, atoms=(_atom(),))
    client = _RecordingClient(
        pack=TimeoutError("privacy-canary-network-detail"),
        submit=CommonsAck(True, False),
    )

    result = synchronize_commons(
        CommonsConfig(CommonsMode.CONTRIBUTOR),
        cache=cache,
        outbox=outbox,
        client=client,
        max_submissions=2,
    )

    assert result.network_calls == 3
    assert result.acked == 2
    assert len(outbox.pending(limit=8).entries) == 1
    assert result.failures == (SyncFailure.DOWNLOAD_TRANSPORT,)
    assert "privacy-canary" not in repr(result)
