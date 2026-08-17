import pytest

from marginal.controls import ActionOutcomeStatus
from marginal.integrations.hookkit.outcomes import (
    classify_structured_result,
    completion_evidence_hash,
)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"exit_code": 0}, ActionOutcomeStatus.SUCCESS),
        ({"exit_code": 3}, ActionOutcomeStatus.FAILURE),
        ({"metadata": {"exit": 0}}, ActionOutcomeStatus.SUCCESS),
        ({"metadata": {"exit": 3}}, ActionOutcomeStatus.FAILURE),
        ({"success": True}, ActionOutcomeStatus.SUCCESS),
        ({"is_error": True}, ActionOutcomeStatus.FAILURE),
        ({"status": "passed"}, ActionOutcomeStatus.SUCCESS),
        ({"outcome": "failed"}, ActionOutcomeStatus.FAILURE),
    ],
)
def test_structured_signals_are_classified(
    result: dict[str, object], expected: ActionOutcomeStatus
) -> None:
    assert classify_structured_result(result) is expected


@pytest.mark.parametrize(
    "result",
    [
        "completed successfully",
        {"output": "tests passed"},
        {"exit_code": 0, "success": False},
        {"metadata": {"exit": 0}, "status": "failed"},
        {"exit_code": True},
        None,
        [],
    ],
)
def test_unprovable_results_stay_unknown(result: object) -> None:
    assert classify_structured_result(result) is ActionOutcomeStatus.UNKNOWN


def test_evidence_hash_is_stable_and_content_sensitive() -> None:
    first = completion_evidence_hash({"type": "text", "content": "hello"})
    assert first == completion_evidence_hash({"content": "hello", "type": "text"})
    assert first != completion_evidence_hash({"type": "text", "content": "hello world"})
    assert len(first) == 64


def test_evidence_hash_is_empty_when_unavailable() -> None:
    assert completion_evidence_hash(None) == ""
    assert completion_evidence_hash({"handle": object()}) == ""
