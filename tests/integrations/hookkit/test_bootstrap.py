from pathlib import Path

import pytest

from marginal import BudgetLimits, Treasury
from marginal.integrations.hookkit.bootstrap import (
    OBSERVE_CAPABILITIES,
    build_observe_session,
    session_hash,
    workspace_hash,
)
from marginal.ledger import read_decision_ledger
from marginal.privacy import PrivacyProfile
from marginal.runtime import UniversalRuntime


def test_observe_capabilities_declare_no_control() -> None:
    assert OBSERVE_CAPABILITIES.level == "observe"
    assert OBSERVE_CAPABILITIES.block_actions is False
    assert OBSERVE_CAPABILITIES.observe_model_usage is False
    assert OBSERVE_CAPABILITIES.record_outcomes is False


def test_an_observe_adapter_cannot_be_run_in_an_enforcing_mode() -> None:
    with pytest.raises(ValueError):
        UniversalRuntime(
            Treasury(BudgetLimits(), mode="enforce"),
            engine="test-engine",
            session_id="session-1",
            task_id="task-1",
            capabilities=OBSERVE_CAPABILITIES,
        )


def test_identifiers_are_pseudonymized(tmp_path: Path) -> None:
    assert len(session_hash("session-1")) == 64
    assert session_hash("session-1") != "session-1"
    assert workspace_hash(tmp_path) == workspace_hash(tmp_path)
    with pytest.raises(ValueError):
        session_hash("")


def test_the_session_writes_a_pseudonymous_local_ledger(tmp_path: Path) -> None:
    session = build_observe_session(
        engine="test-engine",
        session_id="session-1",
        workspace=tmp_path / "workspace",
        data_root=tmp_path / "data",
    )
    assert session.runtime.treasury.mode.value == "shadow"
    assert session.ledger_path.name == f"{session_hash('session-1')}.jsonl"
    assert "session-1" not in str(session.ledger_path)
    session.record({"event": "hook_session_start"})
    records = read_decision_ledger(session.ledger_path)
    assert [record["event"] for record in records] == ["hook_session_start"]
    assert records[0]["engine"] == "test-engine"
    assert records[0]["run_id"] == session.session_hash


def test_recording_fails_open_on_an_invalid_event(tmp_path: Path) -> None:
    session = build_observe_session(
        engine="test-engine",
        session_id="session-1",
        workspace=tmp_path / "workspace",
        data_root=tmp_path / "data",
    )
    session.record({"event": ""})
    session.record({"event": "hook_decision", "engine": "spoofed"})
    assert not session.ledger_path.exists() or read_decision_ledger(session.ledger_path) == []


def test_a_strict_privacy_profile_is_selectable(tmp_path: Path) -> None:
    session = build_observe_session(
        engine="test-engine",
        session_id="session-1",
        workspace=tmp_path / "workspace",
        data_root=tmp_path / "data",
        privacy_profile=PrivacyProfile.SAFE_TELEMETRY,
        privacy_key_path=tmp_path / "key",
    )
    session.record({"event": "hook_session_start"})
    records = read_decision_ledger(session.ledger_path)
    assert records[0]["privacy_profile"] == PrivacyProfile.SAFE_TELEMETRY.value


def test_an_empty_engine_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_observe_session(
            engine=" ",
            session_id="session-1",
            workspace=tmp_path,
            data_root=tmp_path / "data",
        )
