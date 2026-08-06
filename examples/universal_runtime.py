"""Minimal engine-neutral adapter lifecycle."""

from marginal import (
    AgentAction,
    AgentCapabilities,
    BudgetLimits,
    Cost,
    Treasury,
    UniversalRuntime,
    build_policy,
)

treasury = Treasury(BudgetLimits(max_tokens=10_000), policy=build_policy("balanced"), mode="shadow")
runtime = UniversalRuntime(
    treasury,
    engine="example-engine",
    session_id="session-1",
    task_id="task-1",
    capabilities=AgentCapabilities(block_actions=True, record_outcomes=True),
)

action = AgentAction(
    action_id="read-1",
    name="read a large file",
    kind="file_read",
    estimated_cost=Cost(tokens=4_000),
    expected_gain=0.04,
    state_hash="workspace-v1",
    phase="diagnose",
    deduplication_scope="once_per_state",
)

decision = runtime.before_action(action)
print(decision.to_dict())
if decision.allowed:
    runtime.after_action(action.action_id, actual_cost=Cost(tokens=3_600))
