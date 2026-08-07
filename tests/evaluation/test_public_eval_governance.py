from __future__ import annotations

from marginal.public_eval import RunRecord, compare_runs, render_public_report


def test_public_eval_reports_gross_and_net_savings() -> None:
    baseline = {"task": RunRecord(instance_id="task", resolved=True, tokens=1000, usd=1.0)}
    marginal = {
        "task": RunRecord(
            instance_id="task",
            resolved=True,
            tokens=700,
            usd=0.7,
            governance_tokens=200,
            governance_usd=0.2,
            repeated_calls=1,
        )
    }

    result = compare_runs(baseline, marginal, bootstrap_samples=20)

    assert result["gross_savings"]["tokens_percent"] == 30.0
    assert result["net_savings"]["tokens_percent"] == 10.0
    assert result["savings"]["tokens_percent"] == 10.0
    assert result["intervention"]["status"] == "supported"
    assert "Governance tax" in render_public_report(result)


def test_governance_tax_can_make_pass_through_the_correct_result() -> None:
    baseline = {"task": RunRecord(instance_id="task", resolved=True, tokens=1000)}
    marginal = {
        "task": RunRecord(
            instance_id="task",
            resolved=True,
            tokens=850,
            governance_tokens=200,
        )
    }

    result = compare_runs(baseline, marginal, bootstrap_samples=20)

    assert result["gross_savings"]["tokens_percent"] == 15.0
    assert result["net_savings"]["tokens_percent"] == -5.0
    assert result["intervention"]["status"] == "pass_through"
    assert result["intervention"]["graceful_irrelevance"] is True


def test_reviewed_false_stop_can_fail_the_intervention_gate() -> None:
    baseline = {"task": RunRecord(instance_id="task", resolved=True, tokens=1000)}
    marginal = {
        "task": RunRecord(
            instance_id="task",
            resolved=True,
            tokens=500,
            reviewed_stops=1,
            false_stops=1,
        )
    }

    result = compare_runs(baseline, marginal, bootstrap_samples=20)

    assert result["quality"]["false_stop_rate"] == 1.0
    assert result["intervention"]["status"] == "false_stop_risk"
