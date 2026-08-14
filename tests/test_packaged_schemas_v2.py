from __future__ import annotations

import json
from pathlib import Path

import marginal

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "aggregate-export-v1.json",
    "agent-capabilities-v1.json",
    "agent-decision-v1.json",
    "agent-event-v1.json",
    "decision-ledger-v2.json",
    "decision-receipt-v1.json",
    "governance-ledger-v3.json",
    "outcome-v1.json",
    "progress-evidence-v1.json",
    "safe-telemetry-v1.json",
    "token-usage-v2.json",
    "trust-snapshot-v1.json",
}


def test_public_schema_api_lists_and_loads_all_contracts() -> None:
    assert set(marginal.available_schemas()) == EXPECTED
    for name in EXPECTED:
        payload = marginal.load_schema(name)
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert payload == json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def test_schema_api_rejects_unknown_or_unsafe_names() -> None:
    for name in ("missing.json", "../pyproject.toml", "/etc/passwd"):
        try:
            marginal.load_schema(name)
        except (KeyError, ValueError):
            pass
        else:
            raise AssertionError(f"expected schema lookup to reject {name!r}")
