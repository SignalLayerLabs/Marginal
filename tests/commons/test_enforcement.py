from __future__ import annotations

import json
from pathlib import Path

import pytest

from marginal.diagnostics import status_report


@pytest.mark.parametrize("lifecycle", ["candidate", "supported", "validated", "promoted"])
def test_commons_lifecycle_state_has_no_local_enforcement_authority(
    tmp_path: Path, lifecycle: str
) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    commons = tmp_path / "data" / "commons"
    commons.mkdir(parents=True)
    (commons / "status.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "mode": "read_only",
                "endpoint": "https://marginal-ingress.signallayerlabs.workers.dev",
                "model_namespace": "openai/gpt-5.6-sol",
                "sharing_allowed": False,
                "safe_queue_count": 0,
                "last_sync_status": "ok",
                "cache_revision": 1,
                "lifecycle": lifecycle,
                "count": 1000,
            }
        ),
        encoding="utf-8",
    )

    payload = status_report(data_root=tmp_path / "data", workspace=workspace).to_dict()

    assert payload["authority"]["current"] == "L0"
    assert payload["authority"]["eligible"] == "L0"
    assert payload["trust"]["components"]["covered_actions"] == 0
    assert payload["trust"]["components"]["completed_sessions"] == 0
