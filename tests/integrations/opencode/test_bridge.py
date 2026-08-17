import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from marginal.controls import ActionOutcomeStatus
from marginal.integrations.opencode.bridge import BridgeService, serve
from marginal.ledger import read_decision_ledger
from marginal.privacy import PrivacyProfile

from .conftest import SESSION_ID, RequestFactory


@pytest.fixture
def service(tmp_path: Path) -> BridgeService:
    return BridgeService(data_root=tmp_path / "data")


def _records(service: BridgeService) -> list[dict[str, object]]:
    files = sorted(service.data_root.rglob("*.jsonl"))
    assert files, "the bridge must write exactly one decision ledger per session"
    return read_decision_ledger(files[0])


def test_status_reports_an_observe_capability(service: BridgeService) -> None:
    status = service.handle("status", {})
    assert status == {"engine": "opencode", "sessions": 0, "capability_level": "observe"}


def test_a_full_lifecycle_is_recorded(service: BridgeService, requests: RequestFactory) -> None:
    service.handle("session_start", requests.session())
    assert service.handle("tool_start", requests.tool_start()) == {"allow": True}
    result = service.handle("tool_end", requests.tool_end(signals={"exit": 0}))
    assert result == {"observed": True, "outcome": "success"}
    service.handle("session_end", requests.session())
    events = [record["event"] for record in _records(service)]
    assert events[0] == "hook_session_start"
    assert "hook_decision" in events
    assert "hook_outcome" in events
    assert events[-1] == "hook_session_end"


def test_shadow_mode_always_allows(service: BridgeService, requests: RequestFactory) -> None:
    service.handle("session_start", requests.session())
    for index in range(4):
        call_id = f"call_synthetic000{index}"
        assert service.handle("tool_start", requests.tool_start(call_id)) == {"allow": True}
        service.handle("tool_end", requests.tool_end(call_id, signals={"exit": 0}))
    decisions = [r for r in _records(service) if r["event"] == "hook_decision"]
    assert decisions[0]["recommended"] is True
    assert decisions[-1]["recommended"] is False
    assert decisions[-1]["recommended_stop"] is True
    assert all(record["enforced"] is False for record in decisions)


def test_the_first_tool_call_opens_an_unannounced_session(
    service: BridgeService, requests: RequestFactory
) -> None:
    service.handle("tool_start", requests.tool_start())
    assert service.session_ids == (SESSION_ID,)


def test_a_shell_exit_code_proves_an_outcome(
    service: BridgeService, requests: RequestFactory
) -> None:
    service.handle("session_start", requests.session())
    service.handle(
        "tool_start", requests.tool_start(tool_name="bash", arguments={"command": "exit 3"})
    )
    result = service.handle(
        "tool_end",
        requests.tool_end(tool_name="bash", arguments={"command": "exit 3"}, signals={"exit": 3}),
    )
    assert result == {"observed": True, "outcome": "failure"}


def test_a_tool_without_signals_stays_unknown(
    service: BridgeService, requests: RequestFactory
) -> None:
    service.handle("session_start", requests.session())
    service.handle("tool_start", requests.tool_start())
    result = service.handle("tool_end", requests.tool_end(signals={}))
    assert result == {"observed": True, "outcome": "unknown"}
    outcomes = [r for r in _records(service) if r["event"] == "hook_outcome"]
    assert outcomes[-1]["outcome"] == "unknown"


def test_interleaved_sessions_stay_separate(
    service: BridgeService, requests: RequestFactory, workspace: Path
) -> None:
    other = {"session_id": "ses_synthetic0002", "workspace": str(workspace)}
    service.handle("session_start", requests.session())
    service.handle("session_start", other)
    service.handle("tool_start", requests.tool_start("call_a"))
    service.handle(
        "tool_start",
        {**requests.tool_start("call_b"), "session_id": "ses_synthetic0002"},
    )
    assert len(service.session_ids) == 2
    service.handle("session_end", other)
    assert service.session_ids == (SESSION_ID,)
    assert len(sorted(service.data_root.rglob("*.jsonl"))) == 2


def test_a_completion_for_an_unknown_session_is_reported(
    service: BridgeService, requests: RequestFactory
) -> None:
    assert service.handle("tool_end", requests.tool_end()) == {"observed": False}


def test_closing_an_unknown_session_is_harmless(service: BridgeService, workspace: Path) -> None:
    result = service.handle(
        "session_end", {"session_id": "ses_synthetic9999", "workspace": str(workspace)}
    )
    assert result == {"closed": False}


def test_close_all_settles_every_session(service: BridgeService, requests: RequestFactory) -> None:
    service.handle("tool_start", requests.tool_start())
    service.close_all()
    assert service.session_ids == ()
    summaries = [r for r in _records(service) if r["event"] == "hook_session_end"]
    assert summaries[-1]["summary_unknown_observations"] == 1


def test_an_unsupported_operation_is_rejected(service: BridgeService) -> None:
    with pytest.raises(ValueError):
        service.handle("enforce", {})


def test_a_payload_that_does_not_match_its_operation_is_rejected(
    service: BridgeService,
) -> None:
    with pytest.raises(ValueError):
        service.handle("tool_start", {"session_id": "ses_synthetic0001"})


def test_the_line_protocol_answers_every_request(tmp_path: Path, requests: RequestFactory) -> None:
    service = BridgeService(data_root=tmp_path / "data")
    lines = [
        json.dumps({"operation": "status", "payload": {}}),
        "not json",
        json.dumps({"operation": "enforce", "payload": {}}),
        json.dumps(["not", "an", "object"]),
        "",
        json.dumps({"operation": "tool_start", "payload": requests.tool_start()}),
    ]
    destination = io.StringIO()
    assert serve(service, source=io.StringIO("\n".join(lines) + "\n"), destination=destination) == 0
    responses = [json.loads(line) for line in destination.getvalue().splitlines()]
    assert responses[0]["ok"] is True
    assert responses[1] == {"ok": False, "error_code": "INVALID_MESSAGE"}
    assert responses[2] == {"ok": False, "error_code": "SERVICE_ERROR"}
    assert responses[3] == {"ok": False, "error_code": "INVALID_MESSAGE"}
    assert responses[4]["result"] == {"allow": True}
    assert service.session_ids == ()


def test_an_oversized_line_is_rejected(tmp_path: Path) -> None:
    service = BridgeService(data_root=tmp_path / "data")
    destination = io.StringIO()
    serve(service, source=io.StringIO("x" * 300_000 + "\n"), destination=destination)
    assert json.loads(destination.getvalue()) == {"ok": False, "error_code": "MESSAGE_TOO_LARGE"}


def test_a_strict_profile_pseudonymizes_the_session_identity(
    tmp_path: Path, requests: RequestFactory
) -> None:
    service = BridgeService(
        data_root=tmp_path / "data", privacy_profile=PrivacyProfile.SAFE_TELEMETRY
    )
    service.handle("session_start", requests.session())
    service.handle("tool_start", requests.tool_start())
    contents = sorted(service.data_root.rglob("*.jsonl"))[0].read_text(encoding="utf-8")
    assert SESSION_ID not in contents
    assert "safe_telemetry" in contents


def test_the_ledger_holds_no_arguments_or_digested_output(
    service: BridgeService, requests: RequestFactory, workspace: Path
) -> None:
    service.handle("session_start", requests.session())
    service.handle(
        "tool_start",
        requests.tool_start(tool_name="bash", arguments={"command": "cat /etc/passwd"}),
    )
    service.handle(
        "tool_end",
        requests.tool_end(
            tool_name="bash",
            arguments={"command": "cat /etc/passwd"},
            signals={"exit": 0},
        ),
    )
    contents = sorted(service.data_root.rglob("*.jsonl"))[0].read_text(encoding="utf-8")
    assert "/etc/passwd" not in contents
    assert str(workspace) not in contents


def test_the_module_entry_point_serves_stdin(tmp_path: Path, requests: RequestFactory) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "marginal.integrations.opencode.bridge",
            "--data-root",
            str(tmp_path / "data"),
        ],
        input="\n".join(
            [
                json.dumps({"operation": "session_start", "payload": requests.session()}),
                json.dumps({"operation": "tool_start", "payload": requests.tool_start()}),
                json.dumps(
                    {
                        "operation": "tool_end",
                        "payload": requests.tool_end(signals={"exit": 0}, duration_ms=8.0),
                    }
                ),
            ]
        )
        + "\n",
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src"),
            "HOME": str(tmp_path),
        },
        check=False,
    )
    assert completed.returncode == 0
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    assert all(response["ok"] is True for response in responses)
    assert responses[-1]["result"]["outcome"] == "success"
    records = read_decision_ledger(sorted((tmp_path / "data").rglob("*.jsonl"))[0])
    assert [record["event"] for record in records][-1] == "hook_session_end"


def test_an_unknown_target_is_rejected_by_the_entry_point() -> None:
    from marginal.integrations.opencode.bridge import main

    assert main(["--target", "not-a-real-engine"]) == 2


def test_outcome_classification_is_available_directly(requests: RequestFactory) -> None:
    from marginal.integrations.opencode import classify_outcome
    from marginal.integrations.opencode.events import parse_request

    request = parse_request("tool_end", requests.tool_end(signals={"exit": 0}))
    assert classify_outcome(request) is ActionOutcomeStatus.SUCCESS  # type: ignore[arg-type]
