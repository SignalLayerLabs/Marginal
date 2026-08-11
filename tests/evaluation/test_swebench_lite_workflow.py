from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "swebench-lite-canary.yml"


def test_workflow_is_manual_modal_only_and_compares_both_lanes() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "push:" not in text
    assert "pull_request:" not in text
    assert "default: smoke" in text
    assert "MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}" in text
    assert "MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}" in text
    assert "princeton-nlp/SWE-bench_Lite" in text
    assert "baseline_predictions.ndjson" in text
    assert "marginal_predictions.ndjson" in text
    assert text.count("--modal true") == 2
    assert "marginal public-eval" in text
    assert "actions/upload-artifact@v4" in text


def test_readme_refuses_gold_as_marginal_evidence() -> None:
    readme = (ROOT / "benchmarks" / "swebench_lite" / "README.md").read_text(encoding="utf-8")
    assert "gold patches are not MARGINAL evidence" in readme
    assert "resolved" in readme
    assert "verifier" in readme


def test_workflow_accepts_both_swebench_result_layouts() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "instance_results.jsonl" in text
    assert ".*.${RUN_ID}.json" not in text  # guard against a broken literal glob
    assert '"*.${RUN_ID}.json"' in text


def test_workflow_pins_dev_split_for_both_lanes() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count("--split dev") == 2


def test_workflow_uses_the_pinned_swebench_4_1_cli_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'python -m pip install "modal==1.5.3" "swebench==4.1.0"' in text
    assert text.count("--max_workers 10") == 2
    assert "--parallelism" not in text


def test_release_lint_scope_includes_repository_benchmark_code() -> None:
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "ruff format --check ." in release
    assert "ruff check ." in release
