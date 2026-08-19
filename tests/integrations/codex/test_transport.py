from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from marginal.integrations.codex.transport import (
    MAX_MESSAGE_BYTES,
    SessionServer,
    connection_filename,
    request_session,
)


@contextmanager
def _server(
    tmp_path: Path, *, token: str = "expected-token-000000000000"
) -> Iterator[SessionServer]:
    server = SessionServer(
        data_root=tmp_path,
        session_id="session-1",
        token=token,
        handler=lambda operation, payload: {"operation": operation, "payload": payload},
    )
    server.start()
    try:
        yield server
    finally:
        server.stop()


def test_wrong_token_is_rejected_without_echoing_it(tmp_path: Path) -> None:
    bad_credential = "wrong-secret"
    with _server(tmp_path) as server:
        response = request_session(
            server.connection,
            operation="status",
            payload={},
            token=bad_credential,
        )

    assert response["ok"] is False
    assert response["error_code"] == "AUTH_FAILED"
    assert bad_credential not in str(response)


def test_authenticated_bounded_request_round_trips(tmp_path: Path) -> None:
    with _server(tmp_path) as server:
        response = request_session(
            server.connection,
            operation="status",
            payload={"safe": True},
        )

    assert response == {
        "ok": True,
        "result": {"operation": "status", "payload": {"safe": True}},
    }


def test_oversized_request_is_rejected_client_side(tmp_path: Path) -> None:
    with _server(tmp_path) as server:
        response = request_session(
            server.connection,
            operation="status",
            payload={"value": "x" * MAX_MESSAGE_BYTES},
        )

    assert response["error_code"] == "MESSAGE_TOO_LARGE"


def test_connection_file_is_user_private(tmp_path: Path) -> None:
    with _server(tmp_path) as server:
        assert server.connection.connection_file.stat().st_mode & 0o077 == 0
        assert server.connection.connection_file.name == connection_filename("session-1")
        assert "session-1" not in server.connection.connection_file.name
