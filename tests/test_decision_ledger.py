from __future__ import annotations

import json
from pathlib import Path

import pytest

from marginal import Action, BudgetLimits, Cost, MarginalPolicy, PolicyConfig, Treasury
from marginal.ledger import DecisionLedgerContext, JsonlDecisionLedger, read_decision_ledger
from marginal.outcomes import Outcome


def test_ledger_enriches_events_with_versioned_context_and_sequence(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    context = DecisionLedgerContext(
        run_id="run-1",
        task_id="task-1",
        trajectory_id="trajectory-1",
        engine="codex",
        model="gpt-test",
    )
    ledger = JsonlDecisionLedger(path, context=context)
    treasury = Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
        trace_sink=ledger,
        mode="shadow",
    )
    action = Action(name="read", kind="file_read", cost=Cost(tokens=10), expected_gain=0.2)
    treasury.authorize(action)
    treasury.commit(action)
    treasury.record_outcome(Outcome(task_id="task-1", reward=1.0, resolved=True, verifier="pytest"))

    records = read_decision_ledger(path)
    assert [record["sequence"] for record in records] == [1, 2, 3]
    assert all(record["schema_version"] == "2.0" for record in records)
    assert all(record["run_id"] == "run-1" for record in records)
    assert records[0]["policy"]["version"] == "2.0.0"
    assert records[0]["estimator"]["version"] == "2.0.0"
    assert records[-1]["event"] == "outcome"


def test_ledger_does_not_add_prompt_or_output_fields(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = JsonlDecisionLedger(path, context=DecisionLedgerContext(run_id="run"))
    ledger.emit({"event": "custom", "safe": "metadata"})
    record = json.loads(path.read_text(encoding="utf-8"))
    assert "prompt" not in record
    assert "output" not in record


def test_reader_rejects_non_monotonic_sequence(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema_version": "2.0",
                        "event_id": "event-1",
                        "sequence": 2,
                        "timestamp": "2026-08-06T00:00:00+00:00",
                        "run_id": "run",
                        "event": "a",
                    }
                ),
                json.dumps(
                    {
                        "schema_version": "2.0",
                        "event_id": "event-2",
                        "sequence": 1,
                        "timestamp": "2026-08-06T00:00:01+00:00",
                        "run_id": "run",
                        "event": "b",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sequence"):
        read_decision_ledger(path)


def test_outcome_validates_reward_and_immutable_mappings() -> None:
    outcome = Outcome(task_id="task", reward=0.5, evidence={"suite": "unit"})
    assert outcome.evidence["suite"] == "unit"
    with pytest.raises(TypeError):
        outcome.evidence["suite"] = "full"  # type: ignore[index]
    with pytest.raises(ValueError, match="finite"):
        Outcome(task_id="task", reward=float("nan"))


def test_treasury_outcome_event_keeps_policy_and_estimator_identity(tmp_path) -> None:
    from marginal import BudgetLimits, MarginalPolicy, Outcome, PolicyConfig, Treasury

    ledger = JsonlDecisionLedger(
        tmp_path / "ledger.jsonl",
        context=DecisionLedgerContext(run_id="run-identity", task_id="task"),
    )
    treasury = Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=1.0)),
        trace_sink=ledger,
    )

    treasury.record_outcome(Outcome(task_id="task", resolved=True, reward=1.0))

    record = read_decision_ledger(tmp_path / "ledger.jsonl")[0]
    assert record["event"] == "outcome"
    assert record["policy"]["name"] == "marginal-reference"
    assert record["estimator"]["name"] == "historical-mean"


def test_ledger_rejects_reserved_envelope_field_overrides(tmp_path) -> None:
    ledger = JsonlDecisionLedger(
        tmp_path / "ledger.jsonl",
        context=DecisionLedgerContext(run_id="trusted-run"),
    )

    with pytest.raises(ValueError, match="reserved ledger fields"):
        ledger.emit({"event": "custom", "run_id": "spoofed-run"})


def test_ledger_serialization_failure_does_not_advance_sequence(tmp_path) -> None:
    ledger = JsonlDecisionLedger(
        tmp_path / "ledger.jsonl",
        context=DecisionLedgerContext(run_id="run"),
    )

    with pytest.raises(TypeError):
        ledger.emit({"event": "bad", "unsafe": object()})

    ledger.emit({"event": "good"})
    records = read_decision_ledger(tmp_path / "ledger.jsonl")
    assert records[0]["sequence"] == 1


def test_outcome_rejects_non_string_verifier_and_trajectory() -> None:
    with pytest.raises(TypeError, match="verifier"):
        Outcome(task_id="task", reward=1.0, verifier=123)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="trajectory_id"):
        Outcome(task_id="task", reward=1.0, trajectory_id=123)  # type: ignore[arg-type]


def test_reader_rejects_missing_required_envelope_fields(tmp_path: Path) -> None:
    path = tmp_path / "missing-envelope.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "sequence": 1,
                "event": "authorization",
                "run_id": "run",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="event_id"):
        read_decision_ledger(path)


def test_ledger_rejects_outcome_for_different_context_task(tmp_path: Path) -> None:
    ledger = JsonlDecisionLedger(
        tmp_path / "ledger.jsonl",
        context=DecisionLedgerContext(run_id="run", task_id="task-a"),
    )

    with pytest.raises(ValueError, match="task_id"):
        ledger.emit(
            {
                "event": "outcome",
                "outcome": Outcome(task_id="task-b", reward=1.0).to_dict(),
            }
        )


def test_outcome_trace_failure_does_not_increment_summary_count() -> None:
    class FailingTrace:
        def emit(self, event) -> None:
            del event
            raise OSError("ledger unavailable")

    treasury = Treasury(BudgetLimits(), trace_sink=FailingTrace())

    with pytest.raises(OSError, match="ledger unavailable"):
        treasury.record_outcome(Outcome(task_id="task", reward=1.0))

    assert treasury.summary()["outcomes"] == 0


def test_safe_telemetry_ledger_sanitizes_all_treasury_events(tmp_path: Path) -> None:
    from marginal import PrivacyProfile

    path = tmp_path / "safe-ledger.jsonl"
    ledger = JsonlDecisionLedger(
        path,
        context=DecisionLedgerContext(
            run_id="customer-acme-contract-2026",
            task_id="customer-acme-contract-2026",
            trajectory_id="secret-trajectory",
            engine="codex",
            model="internal-legal-model",
        ),
        privacy_profile=PrivacyProfile.SAFE_TELEMETRY,
        privacy_key=b"k" * 32,
    )
    treasury = Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
        trace_sink=ledger,
        mode="shadow",
    )
    action = Action(
        name="review termination clause",
        kind="verification",
        cost=Cost(tokens=10),
        expected_gain=0.2,
        metadata={"repository": "secret-merger-project"},
    )
    treasury.authorize(action)
    treasury.commit(action)
    treasury.record_outcome(
        Outcome(
            task_id="customer-acme-contract-2026",
            reward=1.0,
            resolved=True,
            verifier="internal legal verifier",
            trajectory_id="secret-trajectory",
            evidence={"repository": "secret-merger-project"},
        )
    )

    records = read_decision_ledger(path)
    encoded = json.dumps(records, sort_keys=True)
    assert all(record["privacy_profile"] == "safe_telemetry" for record in records)
    assert records[0]["run_id"].startswith("psn_")
    assert records[-1]["outcome"]["task_id"] == records[-1]["task_id"]
    assert records[-1]["outcome"]["trajectory_id"] == records[-1]["trajectory_id"]
    for secret in (
        "customer-acme",
        "secret-trajectory",
        "internal-legal-model",
        "termination clause",
        "secret-merger-project",
        "internal legal verifier",
    ):
        assert secret not in encoded


def test_safe_telemetry_ledger_creates_a_local_key_file(tmp_path: Path) -> None:
    path = tmp_path / "safe-ledger.jsonl"
    key_path = tmp_path / "keys" / "ledger.key"
    ledger = JsonlDecisionLedger(
        path,
        context=DecisionLedgerContext(run_id="run"),
        privacy_profile="safe_telemetry",
        privacy_key_path=key_path,
    )
    ledger.emit({"event": "custom"})
    assert key_path.is_file()
    assert len(key_path.read_bytes()) == 32


def test_aggregate_export_cannot_be_used_as_an_operational_ledger_profile(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="aggregate_export"):
        JsonlDecisionLedger(
            tmp_path / "ledger.jsonl",
            context=DecisionLedgerContext(run_id="run"),
            privacy_profile="aggregate_export",
        )


def test_ledger_rejects_privacy_profile_override(tmp_path: Path) -> None:
    ledger = JsonlDecisionLedger(
        tmp_path / "ledger.jsonl",
        context=DecisionLedgerContext(run_id="run"),
    )
    with pytest.raises(ValueError, match="reserved ledger fields"):
        ledger.emit({"event": "custom", "privacy_profile": "safe_telemetry"})


def test_ledger_summary_reports_privacy_profiles(tmp_path: Path) -> None:
    from marginal import summarize_decision_ledger

    path = tmp_path / "safe.jsonl"
    ledger = JsonlDecisionLedger(
        path,
        context=DecisionLedgerContext(run_id="run"),
        privacy_profile="safe_telemetry",
        privacy_key=b"k" * 32,
    )
    ledger.emit({"event": "custom"})
    summary = summarize_decision_ledger(read_decision_ledger(path))
    assert summary["privacy_profiles"] == ["safe_telemetry"]


def test_reader_rejects_unreviewed_fields_in_safe_telemetry(tmp_path: Path) -> None:
    path = tmp_path / "safe.jsonl"
    ledger = JsonlDecisionLedger(
        path,
        context=DecisionLedgerContext(run_id="run"),
        privacy_profile="safe_telemetry",
        privacy_key=b"k" * 32,
    )
    ledger.emit({"event": "custom"})
    record = json.loads(path.read_text(encoding="utf-8"))
    record["metadata"] = {"repository": "secret-merger"}
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="safe telemetry"):
        read_decision_ledger(path)


def test_reader_rejects_malformed_safe_telemetry_pseudonyms(tmp_path: Path) -> None:
    path = tmp_path / "safe.jsonl"
    ledger = JsonlDecisionLedger(
        path,
        context=DecisionLedgerContext(run_id="run"),
        privacy_profile="safe_telemetry",
        privacy_key=b"k" * 32,
    )
    ledger.emit({"event": "custom"})
    record = json.loads(path.read_text(encoding="utf-8"))
    record["run_id"] = "customer-acme"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="safe telemetry"):
        read_decision_ledger(path)


def test_new_decision_ledger_uses_owner_only_permissions(tmp_path: Path) -> None:
    import os

    path = tmp_path / "ledger.jsonl"
    ledger = JsonlDecisionLedger(path, context=DecisionLedgerContext(run_id="run"))
    ledger.emit({"event": "custom"})

    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0


def test_existing_ledger_rejects_symlink_append_target(tmp_path: Path) -> None:
    target = tmp_path / "target.jsonl"
    JsonlDecisionLedger(target, context=DecisionLedgerContext(run_id="run")).emit(
        {"event": "custom"}
    )
    link = tmp_path / "linked.jsonl"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(ValueError, match="symbolic link"):
        JsonlDecisionLedger(link, context=DecisionLedgerContext(run_id="run"))


def test_existing_ledger_rejects_weak_permissions_before_append(tmp_path: Path) -> None:
    import os

    if os.name == "nt":
        pytest.skip("POSIX permission bits are unavailable")
    path = tmp_path / "ledger.jsonl"
    JsonlDecisionLedger(path, context=DecisionLedgerContext(run_id="run")).emit({"event": "custom"})
    path.chmod(0o644)

    with pytest.raises(PermissionError, match="group or others"):
        JsonlDecisionLedger(path, context=DecisionLedgerContext(run_id="run"))


def test_aggregate_export_uses_privacy_preserving_group_threshold(tmp_path: Path) -> None:
    from marginal import export_decision_ledger

    source = tmp_path / "source.jsonl"
    ledger = JsonlDecisionLedger(source, context=DecisionLedgerContext(run_id="run"))
    for index in range(4):
        ledger.emit(
            {
                "event": "authorization",
                "action": {
                    "name": f"secret action {index}",
                    "kind": "verification",
                    "cost": {"tokens": 100},
                },
                "decision": {
                    "allowed": True,
                    "recommended": True,
                    "reason_code": "APPROVED",
                    "expected_gain": 0.2,
                },
            }
        )

    destination = tmp_path / "aggregate.jsonl"
    assert (
        export_decision_ledger(
            source,
            destination,
            privacy_profile="aggregate_export",
        )
        == 0
    )
    assert destination.read_text(encoding="utf-8") == ""

    relaxed = tmp_path / "aggregate-relaxed.jsonl"
    assert (
        export_decision_ledger(
            source,
            relaxed,
            privacy_profile="aggregate_export",
            minimum_group_size=4,
        )
        == 1
    )
    row = json.loads(relaxed.read_text(encoding="utf-8"))
    assert row["count"] == 4
    assert row["minimum_group_size"] == 4


def test_export_never_overwrites_destination_during_exists_check_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from marginal import export_decision_ledger

    source = tmp_path / "source.jsonl"
    JsonlDecisionLedger(source, context=DecisionLedgerContext(run_id="run")).emit(
        {"event": "custom"}
    )
    destination = tmp_path / "existing.jsonl"
    destination.write_text("authoritative", encoding="utf-8")
    original_exists = Path.exists

    def hide_destination_once(path: Path) -> bool:
        return path != destination and original_exists(path)

    monkeypatch.setattr(Path, "exists", hide_destination_once)

    with pytest.raises(FileExistsError):
        export_decision_ledger(
            source,
            destination,
            privacy_profile="aggregate_export",
        )
    assert destination.read_text(encoding="utf-8") == "authoritative"
