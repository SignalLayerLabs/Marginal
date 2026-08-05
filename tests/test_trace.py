from __future__ import annotations

import json

from marginal import Action, BudgetLimits, Cost, Treasury
from marginal.policy import MarginalPolicy, PolicyConfig
from marginal.trace import JsonlTraceSink


def test_jsonl_trace_writes_authorization_and_commit_events(tmp_path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    sink = JsonlTraceSink(trace_path)
    policy = MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0))
    treasury = Treasury(BudgetLimits(max_tokens=1_000), policy=policy, trace_sink=sink)
    action = Action(name="run tests", kind="verification", cost=Cost(tokens=10), expected_gain=0.2)

    treasury.authorize(action)
    treasury.commit(action)

    events = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert [event["event"] for event in events] == ["authorization", "commit"]
    assert events[0]["action"]["name"] == "run tests"
    assert events[0]["decision"]["allowed"] is True
    assert events[1]["usage"]["tokens"] == 10
