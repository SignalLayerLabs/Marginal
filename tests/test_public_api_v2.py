from __future__ import annotations

import json
from pathlib import Path

import marginal


def test_v02_public_exports_and_version() -> None:
    expected = {
        "AgentAction",
        "AgentCapabilities",
        "AgentDecision",
        "AgentDirective",
        "AgentEvent",
        "DecisionLedgerContext",
        "EstimatorRegistry",
        "ExecutionMode",
        "JsonlDecisionLedger",
        "Outcome",
        "TokenUsage",
        "UniversalRuntime",
        "ValueEstimate",
    }
    assert expected.issubset(set(marginal.__all__))
    assert marginal.__version__ == "0.3.3"


def test_json_schemas_exist_and_are_valid() -> None:
    root = Path(__file__).parents[1]
    for name in [
        "agent-event-v1.json",
        "agent-decision-v1.json",
        "decision-ledger-v2.json",
        "outcome-v1.json",
    ]:
        payload = json.loads((root / "schemas" / name).read_text(encoding="utf-8"))
        assert payload["$schema"].startswith("https://json-schema.org/")
        assert payload["title"]


def test_documentation_uses_consistent_v02_terms() -> None:
    root = Path(__file__).parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")
    assert "Shadow Mode" in readme
    assert "Decision Ledger" in readme
    assert "0.2.0" in changelog
    assert "v0.2 — Learning Loop Foundation" in roadmap


def test_capability_and_token_usage_schemas_are_published() -> None:
    root = Path(__file__).parents[1]
    for name in ["agent-capabilities-v1.json", "token-usage-v2.json"]:
        payload = json.loads((root / "schemas" / name).read_text(encoding="utf-8"))
        assert payload["$schema"].startswith("https://json-schema.org/")
        assert payload["title"]


def test_privacy_public_exports_and_documentation_are_published() -> None:
    expected = {
        "FIELD_CLASSIFICATION",
        "JsonlDecisionLedger",
        "LocalPseudonymizer",
        "PrivacyClass",
        "PrivacyConfig",
        "PrivacyProfile",
        "aggregate_ledger_records",
        "classify_field",
        "export_decision_ledger",
        "generate_local_identifier",
        "load_or_create_privacy_key",
        "sanitize_ledger_record",
        "validate_safe_telemetry_record",
    }
    assert expected.issubset(set(marginal.__all__))

    root = Path(__file__).parents[1]
    privacy_doc = (root / "docs" / "privacy.md").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    security = (root / "SECURITY.md").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")

    for text in (privacy_doc, readme, security, changelog, roadmap):
        assert "SAFE_TELEMETRY" in text or "safe_telemetry" in text
        assert "AGGREGATE_EXPORT" in text or "aggregate_export" in text
    assert "pseudonymization is not anonymization" in privacy_doc.lower()
    assert (root / "examples" / "privacy_profiles.py").is_file()
