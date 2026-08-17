import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from marginal.controls import ActionOutcomeStatus
from marginal.integrations.claude_code import service
from marginal.integrations.claude_code.events import parse_hook_event
from marginal.ledger import read_decision_ledger

from .conftest import SESSION_ID, PayloadFactory


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "plugin-data"


@pytest.fixture
def session(data_root: Path, payloads: PayloadFactory):  # type: ignore[no-untyped-def]
    start = parse_hook_event(payloads.session_start())
    service.start_session_service(start, data_root=data_root)  # type: ignore[arg-type]
    yield
    service.stop_session_service(SESSION_ID, data_root=data_root)


def _ledger_records(data_root: Path) -> list[dict[str, object]]:
    files = sorted(data_root.rglob("*.jsonl"))
    assert files, "the session must write exactly one decision ledger"
    return read_decision_ledger(files[0])


def test_a_full_tool_lifecycle_is_recorded(
    session: None, data_root: Path, payloads: PayloadFactory
) -> None:
    assert service.run_hook(payloads.pre_tool_use(), data_root=data_root).output is None
    assert service.run_hook(payloads.post_tool_use(), data_root=data_root).output is None
    events = [record["event"] for record in _ledger_records(data_root)]
    assert events[0] == "hook_session_start"
    assert "hook_decision" in events
    assert "authorization" in events
    assert "hook_outcome" in events
    assert "commit" in events


def test_shadow_mode_never_returns_output(
    session: None, data_root: Path, payloads: PayloadFactory
) -> None:
    for index in range(4):
        call_id = f"toolu_synthetic000{index}"
        assert service.run_hook(payloads.pre_tool_use(call_id), data_root=data_root).output is None
        assert service.run_hook(payloads.post_tool_use(call_id), data_root=data_root).output is None


def test_repeated_identical_work_is_recommended_against(
    session: None, data_root: Path, payloads: PayloadFactory
) -> None:
    for index in range(4):
        call_id = f"toolu_synthetic000{index}"
        service.run_hook(payloads.pre_tool_use(call_id), data_root=data_root)
        service.run_hook(payloads.post_tool_use(call_id), data_root=data_root)
    decisions = [
        record for record in _ledger_records(data_root) if record["event"] == "hook_decision"
    ]
    assert len(decisions) == 4
    assert decisions[0]["recommended"] is True
    assert decisions[-1]["recommended"] is False
    assert decisions[-1]["recommended_stop"] is True
    assert decisions[-1]["enforced"] is False
    assert decisions[-1]["no_progress_reason_code"] == "NO_PROGRESS_ENFORCEMENT_ELIGIBLE"


def test_measured_latency_and_outcome_source_are_recorded(
    session: None, data_root: Path, payloads: PayloadFactory
) -> None:
    service.run_hook(payloads.pre_tool_use(), data_root=data_root)
    service.run_hook(payloads.post_tool_use(duration_ms=17.0), data_root=data_root)
    failure_id = "toolu_synthetic0002"
    service.run_hook(
        payloads.pre_tool_use(failure_id, tool_name="Bash", tool_input={"command": "exit 3"}),
        data_root=data_root,
    )
    service.run_hook(payloads.post_tool_use_failure(failure_id), data_root=data_root)
    outcomes = [
        record for record in _ledger_records(data_root) if record["event"] == "hook_outcome"
    ]
    assert outcomes[0]["outcome"] == "success"
    assert outcomes[0]["outcome_source"] == "PostToolUse"
    assert outcomes[0]["duration_ms"] == 17.0
    assert outcomes[1]["outcome"] == "failure"
    assert outcomes[1]["outcome_source"] == "PostToolUseFailure"


def test_the_ledger_holds_no_paths_or_commands(
    session: None, data_root: Path, payloads: PayloadFactory, workspace: Path
) -> None:
    service.run_hook(
        payloads.pre_tool_use(tool_name="Bash", tool_input={"command": "cat /etc/passwd"}),
        data_root=data_root,
    )
    service.run_hook(
        payloads.post_tool_use(
            tool_name="Bash",
            tool_input={"command": "cat /etc/passwd"},
            tool_response={"stdout": "root:x:0:0", "stderr": ""},
        ),
        data_root=data_root,
    )
    files = sorted(data_root.rglob("*.jsonl"))
    contents = files[0].read_text(encoding="utf-8")
    assert "/etc/passwd" not in contents
    assert "root:x:0:0" not in contents
    assert str(workspace) not in contents


def test_a_strict_profile_pseudonymizes_the_session_identity(
    monkeypatch: pytest.MonkeyPatch, data_root: Path, payloads: PayloadFactory
) -> None:
    monkeypatch.setenv("MARGINAL_PRIVACY_PROFILE", "safe_telemetry")
    start = parse_hook_event(payloads.session_start())
    service.start_session_service(start, data_root=data_root)  # type: ignore[arg-type]
    try:
        service.run_hook(payloads.pre_tool_use(), data_root=data_root)
        service.run_hook(payloads.post_tool_use(), data_root=data_root)
    finally:
        service.stop_session_service(SESSION_ID, data_root=data_root)
    contents = sorted(data_root.rglob("*.jsonl"))[0].read_text(encoding="utf-8")
    assert SESSION_ID not in contents
    assert "safe_telemetry" in contents


def test_an_unknown_privacy_profile_falls_back_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARGINAL_PRIVACY_PROFILE", "not-a-profile")
    assert service.selected_privacy_profile().value == "local_full"
    monkeypatch.setenv("MARGINAL_PRIVACY_PROFILE", "safe_telemetry")
    assert service.selected_privacy_profile().value == "safe_telemetry"


def test_the_session_end_summary_is_recorded(data_root: Path, payloads: PayloadFactory) -> None:
    start = parse_hook_event(payloads.session_start())
    service.start_session_service(start, data_root=data_root)  # type: ignore[arg-type]
    service.run_hook(payloads.pre_tool_use(), data_root=data_root)
    service.run_hook(payloads.session_end(), data_root=data_root)
    summaries = [
        record for record in _ledger_records(data_root) if record["event"] == "hook_session_end"
    ]
    assert len(summaries) == 1
    assert summaries[0]["summary_pending_actions"] == 0
    assert summaries[0]["summary_unknown_observations"] == 1


def test_a_hook_without_a_service_fails_open(data_root: Path, payloads: PayloadFactory) -> None:
    result = service.run_hook(payloads.pre_tool_use(), data_root=data_root)
    assert result.exit_code == 0
    assert result.output is None
    assert result.warning_code == "SERVICE_UNAVAILABLE"


def test_an_unparsable_payload_fails_open(data_root: Path) -> None:
    result = service.run_hook({"hook_event_name": "Nonsense"}, data_root=data_root)
    assert result.exit_code == 0
    assert result.warning_code == "INTEGRATION_ERROR"


def test_a_completion_without_a_proposal_fails_open(
    session: None, data_root: Path, payloads: PayloadFactory
) -> None:
    result = service.run_hook(payloads.post_tool_use("toolu_synthetic9999"), data_root=data_root)
    assert result.exit_code == 0
    assert result.output is None
    outcomes = [
        record for record in _ledger_records(data_root) if record["event"] == "hook_outcome"
    ]
    assert outcomes[-1]["outcome"] == "unknown"


def test_stopping_an_unknown_session_is_harmless(data_root: Path) -> None:
    service.stop_session_service("synthetic-session-9999", data_root=data_root)


def test_starting_requires_session_start(payloads: PayloadFactory, data_root: Path) -> None:
    end = parse_hook_event(payloads.session_end())
    with pytest.raises(ValueError):
        service.start_session_service(end, data_root=data_root)  # type: ignore[arg-type]


def test_outcome_classification_is_available_without_a_session(
    payloads: PayloadFactory,
) -> None:
    assert service.observe_outcome(payloads.post_tool_use()) is ActionOutcomeStatus.SUCCESS
    assert service.observe_outcome(payloads.post_tool_use_failure()) is ActionOutcomeStatus.FAILURE
    with pytest.raises(ValueError):
        service.observe_outcome(payloads.pre_tool_use())


def test_the_hook_entry_point_is_silent_without_a_data_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in service.DATA_ROOT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    assert service.hook_main([]) == 0


def test_the_hook_entry_point_reads_stdin_and_exits_zero(
    session: None, data_root: Path, payloads: PayloadFactory
) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "marginal.integrations.claude_code.service"],
        input=json.dumps(payloads.pre_tool_use()),
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "CLAUDE_PLUGIN_DATA": str(data_root),
            "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src"),
        },
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == ""


def test_a_spawned_service_governs_a_full_lifecycle(
    data_root: Path, payloads: PayloadFactory
) -> None:
    environment = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "CLAUDE_PLUGIN_DATA": str(data_root),
        "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src"),
    }

    def hook(payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "marginal.integrations.claude_code.service"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )

    assert hook(payloads.session_start()).returncode == 0
    assert hook(payloads.pre_tool_use()).returncode == 0
    assert hook(payloads.post_tool_use()).returncode == 0
    assert hook(payloads.session_end()).returncode == 0
    events = [record["event"] for record in _ledger_records(data_root)]
    assert "hook_decision" in events
    assert "hook_outcome" in events
    assert "hook_session_end" in events
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and list((data_root / "sessions").glob("*.json")):
        time.sleep(0.05)
    assert not list((data_root / "sessions").glob("*.json"))
