"""Off-policy replay of versioned MARGINAL decision evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .budget import BudgetLedger, BudgetLimits
from .ledger import read_decision_ledger
from .models import Action, Cost
from .policy import MarginalPolicy


@dataclass(frozen=True, slots=True)
class ReplayResult:
    policy_name: str
    policy_version: str
    actions: int
    recorded_allowed: int
    replayed_allowed: int
    agreements: int
    disagreements: int
    estimated_considered_tokens: int
    estimated_selected_tokens: int
    estimated_avoided_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": {"name": self.policy_name, "version": self.policy_version},
            "actions": self.actions,
            "recorded_allowed": self.recorded_allowed,
            "replayed_allowed": self.replayed_allowed,
            "agreements": self.agreements,
            "disagreements": self.disagreements,
            "estimated_considered_tokens": self.estimated_considered_tokens,
            "estimated_selected_tokens": self.estimated_selected_tokens,
            "estimated_avoided_tokens": self.estimated_avoided_tokens,
            "causal_interpretation": False,
        }


def replay_ledger(
    path: str | Path,
    policy: MarginalPolicy,
    limits: BudgetLimits | None = None,
) -> ReplayResult:
    """Re-evaluate authorization events using estimated costs.

    Replay describes what a policy would have recommended over recorded actions. It does not
    simulate missing task trajectories, infer outcome quality, or prove causal savings.
    """

    records = read_decision_ledger(path)
    ledger = BudgetLedger(limits or BudgetLimits())
    actions = 0
    recorded_allowed = 0
    replayed_allowed = 0
    agreements = 0
    considered_tokens = 0
    selected_tokens = 0

    for record in records:
        if record.get("event") != "authorization":
            continue
        action_payload = record.get("action")
        decision_payload = record.get("decision")
        if not isinstance(action_payload, dict) or not isinstance(decision_payload, dict):
            raise ValueError("authorization records require action and decision objects")
        try:
            cost_payload = action_payload.get("cost", {})
            action = Action(
                name=action_payload["name"],
                kind=action_payload["kind"],
                cost=Cost(**dict(cost_payload)),
                expected_gain=action_payload.get("expected_gain"),
                current_success_probability=action_payload.get("current_success_probability", 0.0),
                is_verification=action_payload.get("is_verification", False),
                fingerprint=action_payload.get("fingerprint"),
                metadata=dict(action_payload.get("metadata", {})),
            )
        except (KeyError, TypeError, ValueError) as exc:
            sequence = record.get("sequence", "unknown")
            raise ValueError(f"malformed authorization record at sequence {sequence}") from exc
        actions += 1
        considered_tokens += action.cost.tokens
        recorded_value = decision_payload.get("recommended", decision_payload.get("allowed"))
        if not isinstance(recorded_value, bool):
            raise ValueError("recorded recommended decision must be a boolean")
        recorded = recorded_value
        recorded_allowed += int(recorded)
        replayed = policy.evaluate(action, ledger)
        replayed_allowed += int(replayed.allowed)
        agreements += int(recorded == replayed.allowed)
        if replayed.allowed:
            ledger.commit(action)
            selected_tokens += action.cost.tokens
            if action.fingerprint:
                policy.mark_executed(action.fingerprint)

    if actions == 0:
        raise ValueError("decision ledger contains no authorization events")
    return ReplayResult(
        policy_name=policy.identity.name,
        policy_version=policy.identity.version,
        actions=actions,
        recorded_allowed=recorded_allowed,
        replayed_allowed=replayed_allowed,
        agreements=agreements,
        disagreements=actions - agreements,
        estimated_considered_tokens=considered_tokens,
        estimated_selected_tokens=selected_tokens,
        estimated_avoided_tokens=considered_tokens - selected_tokens,
    )


def render_replay_report(result: ReplayResult) -> str:
    return "\n".join(
        [
            "# MARGINAL policy replay",
            "",
            (
                "This is an off-policy diagnostic based on recorded proposed actions and "
                "estimated costs. It is **not causal proof** of token savings or preserved quality."
            ),
            "",
            f"Policy: **{result.policy_name}@{result.policy_version}**",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Actions replayed | {result.actions} |",
            f"| Recorded recommendations allowed | {result.recorded_allowed} |",
            f"| Replayed recommendations allowed | {result.replayed_allowed} |",
            f"| Agreements | {result.agreements} |",
            f"| Disagreements | {result.disagreements} |",
            f"| Estimated considered tokens | {result.estimated_considered_tokens:,} |",
            f"| Estimated selected tokens | {result.estimated_selected_tokens:,} |",
            f"| Estimated avoided tokens | {result.estimated_avoided_tokens:,} |",
            "",
        ]
    )
