from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from marginal.commons.client import (
    CommonsClient,
    CommonsHTTPError,
    CommonsProtocolError,
    CommonsTransportError,
)
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
from marginal.commons.outbox import CommonsOutbox, OutboxEntry


class _Handler(BaseHTTPRequestHandler):
    requests: ClassVar[list[dict[str, object]]] = []
    response_status: ClassVar[int] = 200
    response_body: ClassVar[bytes] = b"{}"
    response_delay: ClassVar[float] = 0.0
    trickle_delay: ClassVar[float] = 0.0

    def _write_body(self) -> None:
        time.sleep(type(self).response_delay)
        try:
            if type(self).trickle_delay:
                for byte in type(self).response_body:
                    time.sleep(type(self).trickle_delay)
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
            else:
                self.wfile.write(type(self).response_body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self) -> None:
        type(self).requests.append(
            {"method": "GET", "path": self.path, "headers": dict(self.headers)}
        )
        self.send_response(type(self).response_status)
        self.send_header("Content-Length", str(len(type(self).response_body)))
        self.end_headers()
        self._write_body()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).requests.append(
            {"method": "POST", "path": self.path, "headers": dict(self.headers), "body": body}
        )
        self.send_response(type(self).response_status)
        self.send_header("Content-Length", str(len(type(self).response_body)))
        self.end_headers()
        self._write_body()

    def log_message(self, _format: str, *_args: object) -> None:
        return


@contextmanager
def _server(
    *,
    status: int = 200,
    body: bytes = b"{}",
    delay: float = 0.0,
    trickle_delay: float = 0.0,
) -> Iterator[str]:
    _Handler.requests = []
    _Handler.response_status = status
    _Handler.response_body = body
    _Handler.response_delay = delay
    _Handler.trickle_delay = trickle_delay
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _entry(tmp_path: Path) -> OutboxEntry:
    identity = resolve_canonical_model(provider="openai", model="gpt-5.6-sol")
    assert identity is not None
    atom = CommonsEvidenceAtom(
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
    entry = CommonsOutbox(tmp_path).enqueue(
        batch=CommonsEvidenceBatch(identity=identity, atoms=(atom,))
    )
    assert entry is not None
    return entry


def test_download_uses_only_the_fixed_pack_path_without_query_or_tracking_headers() -> None:
    with _server(body=b"pack") as origin:
        client = CommonsClient(pack_origin=origin, ingress_origin=origin)

        assert client.download() == b"pack"

    request = _Handler.requests[0]
    assert request["path"] == "/dist/commons-pack-v1.json"
    headers = {key.lower(): value for key, value in request["headers"].items()}
    assert "cookie" not in headers
    assert "referer" not in headers
    assert "x-request-id" not in headers


def test_submit_sends_only_the_closed_envelope_and_retry_header(tmp_path: Path) -> None:
    response = json.dumps({"accepted": True, "duplicate": False}).encode()
    with _server(body=response) as origin:
        entry = _entry(tmp_path)
        ack = CommonsClient(pack_origin=origin, ingress_origin=origin).submit(entry)

    assert ack.accepted is True
    assert ack.duplicate is False
    request = _Handler.requests[0]
    assert request["path"] == "/v1/evidence"
    assert json.loads(request["body"]) == entry.envelope
    assert request["headers"]["Idempotency-Key"] == entry.retry_token
    assert entry.retry_token.encode() not in request["body"]


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b'{"accepted":true}',
        b'{"accepted":true,"duplicate":false,"extra":true}',
        b'{"accepted":1,"duplicate":false}',
        b'{"accepted":true,"duplicate":true,"duplicate":false}',
    ],
)
def test_submit_requires_the_exact_ack_shape(tmp_path: Path, body: bytes) -> None:
    with (
        _server(body=body) as origin,
        pytest.raises(CommonsProtocolError, match="invalid Commons response"),
    ):
        CommonsClient(pack_origin=origin, ingress_origin=origin).submit(_entry(tmp_path))


def test_invalid_response_errors_do_not_retain_raw_body_details(tmp_path: Path) -> None:
    with (
        _server(body=b"privacy-canary-not-json") as origin,
        pytest.raises(CommonsProtocolError) as captured,
    ):
        CommonsClient(pack_origin=origin, ingress_origin=origin).submit(_entry(tmp_path))

    assert "privacy-canary" not in str(captured.value)
    assert captured.value.__cause__ is None


def test_recursive_ack_is_a_redacted_protocol_failure(tmp_path: Path) -> None:
    body = ("[" * 2_000 + "]" * 2_000).encode()
    with (
        _server(body=body) as origin,
        pytest.raises(CommonsProtocolError, match="invalid Commons response"),
    ):
        CommonsClient(pack_origin=origin, ingress_origin=origin).submit(_entry(tmp_path))


def test_read_timeout_is_separate_and_redacted() -> None:
    with (
        _server(body=b"late", delay=0.1) as origin,
        pytest.raises(CommonsTransportError, match="Commons transport failed") as captured,
    ):
        CommonsClient(
            pack_origin=origin,
            ingress_origin=origin,
            connect_timeout=1.0,
            read_timeout=0.01,
        ).download()

    assert "timed out" not in str(captured.value).lower()


def test_slow_trickle_hits_one_monotonic_request_deadline() -> None:
    with _server(body=b"slow-body", trickle_delay=0.04) as origin:
        started = time.monotonic()
        with pytest.raises(CommonsTransportError, match="Commons transport failed"):
            CommonsClient(
                pack_origin=origin,
                ingress_origin=origin,
                connect_timeout=1.0,
                read_timeout=0.2,
                request_timeout=0.12,
            ).download()
        elapsed = time.monotonic() - started

    assert elapsed < 0.3


@pytest.mark.parametrize("status", [422, 503])
def test_non_2xx_status_is_classified_before_oversized_body_validation(
    tmp_path: Path, status: int
) -> None:
    with (
        _server(status=status, body=b"x" * 65) as origin,
        pytest.raises(CommonsHTTPError) as captured,
    ):
        CommonsClient(
            pack_origin=origin,
            ingress_origin=origin,
            max_response_bytes=64,
        ).submit(_entry(tmp_path))

    assert captured.value.status == status


def test_client_bounds_response_bytes_and_reports_only_status_category(tmp_path: Path) -> None:
    with _server(body=b"x" * 65) as origin:
        client = CommonsClient(pack_origin=origin, ingress_origin=origin, max_response_bytes=64)
        with pytest.raises(CommonsProtocolError, match="invalid Commons response"):
            client.download()

    with (
        _server(status=503, body=b"privacy-canary-secret-error") as origin,
        pytest.raises(CommonsHTTPError) as captured,
    ):
        CommonsClient(pack_origin=origin, ingress_origin=origin).submit(_entry(tmp_path))
    assert captured.value.status == 503
    assert "privacy-canary" not in str(captured.value)


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.test",
        "https://example.test/base",
        "https://example.test?tracking=yes",
        "https://user:secret@example.test",
        "ftp://example.test",
    ],
)
def test_client_rejects_origins_that_could_change_fixed_request_targets(origin: str) -> None:
    with pytest.raises(ValueError, match="origin"):
        CommonsClient(pack_origin=origin, ingress_origin="https://example.test")
