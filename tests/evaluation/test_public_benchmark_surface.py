from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "benchmarks" / "swebench_lite" / "evidence" / "smoke-2026-08-11-dbce533"
PUBLIC_RESULT = ROOT / "benchmarks" / "swebench_lite" / "public-benchmark.json"
SITE_RESULT = ROOT / "site" / "benchmark-data.json"


def test_public_result_is_the_verified_evidence_artifact() -> None:
    canonical = json.loads(PUBLIC_RESULT.read_text(encoding="utf-8"))
    evidence = json.loads((EVIDENCE / "public-benchmark.json").read_text(encoding="utf-8"))
    site = json.loads(SITE_RESULT.read_text(encoding="utf-8"))

    assert canonical == evidence == site
    assert canonical["tasks"] == 3
    assert canonical["benchmark"] == "public-agent-benchmark-comparison-v3"


def test_authoritative_verifier_chain_is_complete_and_digest_pinned() -> None:
    verification = json.loads((EVIDENCE / "verification.json").read_text(encoding="utf-8"))
    authoritative = verification["authoritative"]
    for lane in ("baseline", "marginal"):
        entry = authoritative[lane]
        report_path = EVIDENCE / entry["report"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
        assert digest == entry["report_sha256"]
        assert report["submitted_instances"] == 3
        assert report["completed_instances"] == 3
        assert report["error_instances"] == 0
        assert report["incomplete_ids"] == []

    assert verification["modal_audit"]["status"] == "infrastructure_error_not_scored"


def test_readme_and_site_publish_the_same_exploratory_result() -> None:
    result = json.loads(PUBLIC_RESULT.read_text(encoding="utf-8"))
    baseline = result["baseline"]
    marginal = result["marginal"]
    savings = result["net_savings"]

    expected = {
        "resolved": f"{baseline['resolved']}/{baseline['tasks']} → "
        f"{marginal['resolved']}/{marginal['tasks']}",
        "tokens": f"{savings['tokens_percent']:.2f}% fewer",
        "tool_calls": f"{savings['tool_calls_percent']:.2f}% fewer",
        "governance_latency": f"{result['governance']['latency_ms'] / 1000:.2f} s",
        "status": str(result["intervention"]["status"]),
    }

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    site = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    for key, value in expected.items():
        marker = f'data-benchmark-metric="{key}">{value}'
        assert marker in site
        assert value in readme

    required_disclosure = "Exploratory 3-task smoke, one paired run per task"
    assert required_disclosure in readme
    assert required_disclosure in site
    assert "No deny was applied in these three agent trajectories" in readme
    assert "No deny was applied in these three agent trajectories" in site
