from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, replace
from pathlib import Path

import pytest

import marginal.integrations.codex.service as service_module
from marginal.commons.config import CommonsMode, configure_commons_mode
from marginal.commons.outbox import CommonsOutbox
from marginal.integrations.codex.events import SessionEvent
from marginal.integrations.codex.evidence import (
    EvidenceStore,
    summarize_evidence,
    summarize_verified_evidence,
)
from marginal.integrations.codex.identity import current_promotion_identity
from marginal.integrations.codex.promotion import (
    CoverageSummary,
    PromotionCriteria,
    activate_enforcement,
    evaluate_promotion,
    write_promotion_receipt,
)
from marginal.integrations.codex.service import (
    _bootstrap_event_payload,
    _bootstrap_path,
    read_mode,
    run_hook,
    start_session_service,
    stop_session_service,
)
from marginal.integrations.codex.transport import connection_filename, request_session


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repository(path: Path) -> Path:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(path, "add", "tracked.txt")
    _git(path, "commit", "-qm", "initial")
    return path


def _start(workspace: Path) -> SessionEvent:
    return SessionEvent(
        session_id="session-1",
        cwd=str(workspace),
        hook_event_name="SessionStart",
        model="gpt-5.6-sol",
        permission_mode="default",
        source="startup",
    )


def _seed_ready_evidence(store: EvidenceStore) -> None:
    for session_index in range(5):
        session_hash = f"session-{session_index}"
        store.append({"schema_version": 1, "event": "session_start", "session_hash": session_hash})
        for action_index in range(20):
            ordinal = session_index * 20 + action_index
            action_hash = f"action-{ordinal}"
            store.append(
                {
                    "schema_version": 1,
                    "event": "decision",
                    "session_hash": session_hash,
                    "action_hash": action_hash,
                    "latency_ms": 1.0,
                    "covered": True,
                    "coverable": True,
                    "recommended_stop": ordinal < 5,
                    "reviewed": False,
                    "false_stop": False,
                    "pending": True,
                }
            )
            store.append(
                {
                    "schema_version": 1,
                    "event": "outcome",
                    "session_hash": session_hash,
                    "action_hash": action_hash,
                    "outcome": "success",
                    "pending": False,
                }
            )
            if ordinal < 5:
                store.append(
                    {
                        "schema_version": 1,
                        "event": "review",
                        "session_hash": session_hash,
                        "action_hash": action_hash,
                        "reviewed": True,
                        "false_stop": False,
                    }
                )
        store.append({"schema_version": 1, "event": "session_end", "session_hash": session_hash})


def test_start_is_idempotent_and_end_removes_credentials(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _repository(workspace)
    data = tmp_path / "data"
    first = start_session_service(_start(workspace), data_root=data)
    try:
        assert start_session_service(_start(workspace), data_root=data) == first
    finally:
        stop_session_service("session-1", data_root=data)

    assert not first.connection_file.exists()


def test_bootstrap_redacts_transcript_and_hashes_session_filename(tmp_path: Path) -> None:
    event = replace(_start(tmp_path), transcript_path="/private/raw-transcript.jsonl")

    bootstrap = _bootstrap_path(tmp_path, event.session_id)
    payload = _bootstrap_event_payload(event)

    assert event.session_id not in bootstrap.name
    assert "transcript_path" not in payload
    assert "/private/raw-transcript.jsonl" not in json.dumps(payload)
    assert "source" not in payload


def test_missing_service_fails_open_and_demotes(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _repository(workspace)
    data = tmp_path / "data"
    identity = current_promotion_identity(workspace)
    summary = CoverageSummary(
        covered_actions=100,
        coverable_actions=100,
        completed_sessions=5,
        reviewed_candidates=5,
        false_stops=0,
        integration_failures=0,
        pending_actions=0,
        unknown_enforceable_outcomes=0,
        decision_latencies_ms=(1.0,),
        enforceable_outcomes_observable=True,
    )
    store = EvidenceStore(data / "evidence" / identity.repository_hash)
    store.append({"schema_version": 1, "event": "session_start", "session_hash": "seed"})
    root = store.verified_governance_root()
    receipt = evaluate_promotion(
        summary,
        PromotionCriteria(),
        identity=identity,
        evidence_root=root.root_hash,
        ledger_records=root.records,
        ledger_path=store.governance_ledger_path,
    )
    write_promotion_receipt(data, receipt)
    activate_enforcement(data, receipt, ledger_path=store.governance_ledger_path)
    pre_payload = {
        "session_id": "missing",
        "cwd": str(workspace),
        "hook_event_name": "PreToolUse",
        "model": "gpt-5.6-sol",
        "permission_mode": "default",
        "turn_id": "turn-1",
        "tool_name": "Bash",
        "tool_use_id": "call-1",
        "tool_input": {"command": "git status"},
    }

    result = run_hook(pre_payload, data_root=data)

    assert result.exit_code == 0
    assert result.output is None
    assert read_mode(data, repository_hash=identity.repository_hash)["mode"] == "shadow"
    assert result.warning_code == "SERVICE_UNAVAILABLE"
    evidence = EvidenceStore(data / "evidence" / identity.repository_hash).read_all()
    failure = next(record for record in evidence if record.get("integration_failure") is True)
    assert failure["reason_code"] == "SERVICE_UNAVAILABLE"
    assert evidence[-1]["event"] == "window_start"


def test_fail_open_survives_unavailable_evidence_storage(tmp_path: Path, monkeypatch) -> None:
    def unavailable_store(*_args, **_kwargs):
        raise OSError("read-only data root")

    monkeypatch.setattr(service_module, "_evidence_store", unavailable_store)
    payload = {
        "session_id": "missing",
        "cwd": str(tmp_path),
        "hook_event_name": "PreToolUse",
        "model": "gpt-5.6-sol",
        "permission_mode": "default",
        "turn_id": "turn-1",
        "tool_name": "Bash",
        "tool_use_id": "call-1",
        "tool_input": {"command": "git status"},
    }

    result = run_hook(payload, data_root=tmp_path / "unavailable")

    assert result.exit_code == 0
    assert result.output is None
    assert result.warning_code == "SERVICE_UNAVAILABLE"


def test_session_start_and_end_are_complete_hook_lifecycle(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _repository(workspace)
    data = tmp_path / "data"
    start_payload = json.loads(json.dumps(asdict(_start(workspace))))
    end_payload = {
        **start_payload,
        "hook_event_name": "SessionEnd",
        "source": None,
        "reason": "other",
    }

    start_result = run_hook(start_payload, data_root=data)
    end_result = run_hook(end_payload, data_root=data)

    assert start_result.exit_code == 0
    assert end_result.exit_code == 0
    assert not (data / "sessions" / connection_filename("session-1")).exists()


class _OfflineCommonsClient:
    def __init__(self) -> None:
        self.downloads = 0
        self.submissions = 0

    def download(self) -> bytes:
        self.downloads += 1
        raise TimeoutError("private network detail")

    def submit(self, _entry) -> object:
        self.submissions += 1
        raise TimeoutError("private network detail")


@pytest.mark.parametrize(
    "mode,expected_downloads",
    [
        (CommonsMode.LOCAL_ONLY, 0),
        (CommonsMode.READ_ONLY, 1),
        (CommonsMode.CONTRIBUTOR, 2),
    ],
)
def test_session_lifecycle_finalizes_locally_in_every_commons_mode_and_fails_open(
    tmp_path: Path, monkeypatch, mode: CommonsMode, expected_downloads: int
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _repository(workspace)
    data = tmp_path / "data"
    configure_commons_mode(data, mode=mode)
    client = _OfflineCommonsClient()
    monkeypatch.setattr(service_module, "_commons_client", lambda: client)

    connection = start_session_service(_start(workspace), data_root=data)
    stop_session_service("session-1", data_root=data)
    stop_session_service("session-1", data_root=data)

    identity = current_promotion_identity(workspace)
    store = EvidenceStore(data / "evidence" / identity.repository_hash)
    records = store.read_all()
    assert sum(record.get("event") == "session_end" for record in records) == 1
    checkpoint = store.read_checkpoint()
    assert checkpoint is not None
    ledger = store.verified_governance_root()
    assert checkpoint == {
        "schema_version": 1,
        "event": "session_finalized",
        "session_hash": service_module._session_hash("session-1"),
        "ledger_root": ledger.root_hash,
        "ledger_records": ledger.records,
    }
    assert client.downloads == expected_downloads
    assert connection.connection_file.exists() is False


def test_contributor_session_end_queues_model_bound_evidence_for_offline_retry(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _repository(workspace)
    data = tmp_path / "data"
    configure_commons_mode(data, mode=CommonsMode.CONTRIBUTOR)
    client = _OfflineCommonsClient()
    monkeypatch.setattr(service_module, "_commons_client", lambda: client)
    connection = start_session_service(_start(workspace), data_root=data)
    common = {
        "session_id": "session-1",
        "cwd": str(workspace),
        "model": "gpt-5.6-sol",
        "permission_mode": "default",
        "turn_id": "turn-1",
        "tool_name": "Read",
        "tool_input": {"path": str(workspace / "tracked.txt")},
    }
    for index in range(5):
        pre = {**common, "hook_event_name": "PreToolUse", "tool_use_id": f"call-{index}"}
        post = {**pre, "hook_event_name": "PostToolUse", "tool_response": {"exit_code": 0}}
        assert request_session(connection, operation="pre", payload=pre)["ok"] is True
        assert request_session(connection, operation="post", payload=post)["ok"] is True

    stop_session_service("session-1", data_root=data)

    queued = CommonsOutbox(data).pending(limit=8).entries
    assert len(queued) == 1
    assert queued[0].model_namespace == "openai/gpt-5.6-sol"
    assert client.submissions == 1
    identity = current_promotion_identity(workspace)
    records = EvidenceStore(data / "evidence" / identity.repository_hash).read_all()
    dimensions = [record for record in records if record.get("event") == "decision"]
    assert {record.get("model_namespace") for record in dimensions} == {"openai/gpt-5.6-sol"}
    assert {record.get("action_kind") for record in dimensions} == {"file_read"}


def test_contributor_exports_only_each_new_finalized_range(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _repository(workspace)
    data = tmp_path / "data"
    configure_commons_mode(data, mode=CommonsMode.CONTRIBUTOR)
    client = _OfflineCommonsClient()
    monkeypatch.setattr(service_module, "_commons_client", lambda: client)

    def run_session(session_id: str, actions: int) -> None:
        connection = start_session_service(
            replace(_start(workspace), session_id=session_id), data_root=data
        )
        for index in range(actions):
            pre = {
                "session_id": session_id,
                "cwd": str(workspace),
                "model": "gpt-5.6-sol",
                "permission_mode": "default",
                "turn_id": "turn-1",
                "tool_name": "Read",
                "tool_input": {"path": str(workspace / "tracked.txt")},
                "hook_event_name": "PreToolUse",
                "tool_use_id": f"{session_id}-call-{index}",
            }
            post = {**pre, "hook_event_name": "PostToolUse", "tool_response": {"exit_code": 0}}
            request_session(connection, operation="pre", payload=pre)
            request_session(connection, operation="post", payload=post)
        stop_session_service(session_id, data_root=data)

    run_session("session-1", 5)
    first = CommonsOutbox(data).pending(limit=8).entries
    assert len(first) == 1
    run_session("session-empty", 0)
    assert [entry.name for entry in CommonsOutbox(data).pending(limit=8).entries] == [first[0].name]
    run_session("session-2", 5)

    queued = CommonsOutbox(data).pending(limit=8).entries
    assert len(queued) == 2
    exported_counts = sorted(atom["count"] for entry in queued for atom in entry.envelope["atoms"])
    assert exported_counts == [5, 5]


def test_ambiguous_model_session_remains_local_and_never_queues(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _repository(workspace)
    data = tmp_path / "data"
    configure_commons_mode(data, mode=CommonsMode.CONTRIBUTOR)
    client = _OfflineCommonsClient()
    monkeypatch.setattr(service_module, "_commons_client", lambda: client)
    event = replace(_start(workspace), model="private/fine-tune")

    start_session_service(event, data_root=data)
    stop_session_service("session-1", data_root=data)

    assert CommonsOutbox(data).pending(limit=8).entries == ()
    assert client.submissions == 0


def test_user_prompt_submit_reaches_only_the_authenticated_session_and_is_not_persisted(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _repository(workspace)
    data = tmp_path / "data"
    start = json.loads(json.dumps(asdict(_start(workspace))))
    prompt = {
        **start,
        "hook_event_name": "UserPromptSubmit",
        "prompt": "MARGINAL_PROMPT_SECRET: esegui di nuovo",
    }
    end = {**start, "hook_event_name": "SessionEnd", "source": None, "reason": "other"}

    assert run_hook(start, data_root=data).exit_code == 0
    try:
        prompt_result = run_hook(prompt, data_root=data)
        assert prompt_result.output is None
        assert prompt_result.warning_code == ""
    finally:
        run_hook(end, data_root=data)

    persisted = "\n".join(
        path.read_text(encoding="utf-8") for path in data.rglob("*") if path.is_file()
    )
    assert "MARGINAL_PROMPT_SECRET" not in persisted
    assert "prompt_hash" not in persisted


def test_ready_repository_enforces_proven_no_progress_and_only_that(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _repository(workspace)
    data = tmp_path / "data"
    identity = current_promotion_identity(workspace)
    store = EvidenceStore(data / "evidence" / identity.repository_hash)
    _seed_ready_evidence(store)
    summary, root = summarize_verified_evidence(store)
    receipt = evaluate_promotion(
        summary,
        PromotionCriteria(),
        identity=identity,
        evidence_root=root.root_hash,
        ledger_records=root.records,
        ledger_path=store.governance_ledger_path,
    )
    write_promotion_receipt(data, receipt)
    activate_enforcement(data, receipt, ledger_path=store.governance_ledger_path)
    start_payload = json.loads(json.dumps(asdict(_start(workspace))))
    assert run_hook(start_payload, data_root=data).exit_code == 0
    try:
        common = {
            "session_id": "session-1",
            "cwd": str(workspace),
            "model": "gpt-5.6-sol",
            "permission_mode": "default",
            "turn_id": "turn-1",
            "tool_name": "Bash",
            "tool_input": {"command": "python -m pytest -q"},
        }
        for index in (1, 2):
            pre = {
                **common,
                "hook_event_name": "PreToolUse",
                "tool_use_id": f"call-{index}",
            }
            post = {
                **pre,
                "hook_event_name": "PostToolUse",
                "tool_response": {"exit_code": 0},
            }
            assert run_hook(pre, data_root=data).output is None
            assert run_hook(post, data_root=data).output is None
        third = {
            **common,
            "hook_event_name": "PreToolUse",
            "tool_use_id": "call-3",
        }

        denied = run_hook(third, data_root=data)

        assert denied.output is not None
        hook_output = denied.output["hookSpecificOutput"]
        assert hook_output["permissionDecision"] == "deny"
        assert "NO_PROGRESS_ENFORCED" in hook_output["permissionDecisionReason"]
    finally:
        stop_session_service("session-1", data_root=data)

    records = store.read_all()
    observed_summary = summarize_evidence(records)
    serialized = json.dumps(records)
    assert observed_summary.covered_actions == summary.covered_actions + 3
    assert observed_summary.coverable_actions == summary.coverable_actions + 3
    assert observed_summary.completed_sessions == summary.completed_sessions + 1
    assert "python -m pytest" not in serialized
    assert "tool_input" not in serialized
