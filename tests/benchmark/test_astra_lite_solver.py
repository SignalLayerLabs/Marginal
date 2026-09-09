from __future__ import annotations

from pathlib import Path


def test_lite_solver_docker_context_includes_exact_runtime_closure() -> None:
    root = Path(__file__).resolve().parents[2]
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8")
    dockerfile = (root / "benchmark" / "astra" / "lite" / "Dockerfile.solver").read_text(
        encoding="utf-8"
    )

    assert "benchmark.astra.lite_lane" in dockerfile
    for path in (
        "benchmark/astra/_snapshot.py",
        "benchmark/astra/lite_lane.py",
        "benchmark/astra/lite/",
        "benchmark/astra/lite/freeze.py",
    ):
        assert f"!{path}" in dockerignore
