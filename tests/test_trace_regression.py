from __future__ import annotations

import json

from marginal import Action, BudgetLimits, Cost, Treasury
from marginal.policy import MarginalPolicy, PolicyConfig
from marginal.trace import JsonlTraceSink


def test_jsonl_trace_writes_authorization_and_commit_events(tmp_path) -> None:
    path = tmp_path / "trace.jsonl"
    treasury = Treasury(
        BudgetLimits(max_tokens=1_000),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
        trace_sink=JsonlTraceSink(path),
    )
    action = Action(name="run tests", kind="verification", cost=Cost(tokens=10), expected_gain=0.2)
    treasury.authorize(action)
    treasury.commit(action)
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert [event["event"] for event in events] == ["authorization", "commit"]
    assert events[1]["usage"]["tokens"] == 10
