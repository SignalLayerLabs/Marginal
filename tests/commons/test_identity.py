from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from marginal.commons.identity import (
    CanonicalModelIdentity,
    resolve_canonical_model,
    resolve_model_attribution,
)

REVIEWED = {
    "gpt-5.6-sol": "openai/gpt-5.6-sol",
    "gpt-5.6-terra": "openai/gpt-5.6-terra",
    "gpt-5.6-luna": "openai/gpt-5.6-luna",
}


@pytest.mark.parametrize(("model", "namespace"), REVIEWED.items())
def test_exact_public_registry_match_resolves_an_immutable_identity(
    model: str, namespace: str
) -> None:
    identity = resolve_canonical_model(provider="openai", model=model)

    assert identity == CanonicalModelIdentity(
        provider="openai", model=model, namespace=namespace, registry_version="1.0"
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.model = "gpt-5.6-sol"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("OpenAI", "gpt-5.6-sol"),
        ("openai", "GPT-5.6-SOL"),
        ("openai", " gpt-5.6-sol"),
        ("openai", "gpt-5.6-sol "),
        ("openai", "gpt-5.6"),
        ("openai", "gpt-5.6-sol-latest"),
        ("openai", "gpt-5.6-sol-2026-08-21"),
        ("openai", "ft:gpt-5.6-sol:private"),
        ("openai", "private/gpt-5.6-sol"),
        ("custom", "gpt-5.6-sol"),
    ],
)
def test_unknown_private_alias_and_version_drift_remain_unresolved(
    provider: str, model: str
) -> None:
    assert resolve_canonical_model(provider=provider, model=model) is None


def test_attribution_requires_one_unambiguous_exact_model() -> None:
    expected = resolve_canonical_model(provider="openai", model="gpt-5.6-sol")

    assert resolve_model_attribution([("openai", "gpt-5.6-sol")]) == expected
    assert (
        resolve_model_attribution([("openai", "gpt-5.6-sol"), ("openai", "gpt-5.6-sol")])
        == expected
    )
    assert (
        resolve_model_attribution([("openai", "gpt-5.6-sol"), ("openai", "gpt-5.6-terra")]) is None
    )
    assert resolve_model_attribution([("openai", "gpt-5.6-sol"), ("custom", "private")]) is None
    assert resolve_model_attribution([]) is None


def test_packaged_registry_is_byte_identical_to_reviewed_root_registry() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / "models" / "canonical-model-registry-v1.json").read_bytes() == (
        root / "src" / "marginal" / "commons" / "canonical-model-registry-v1.json"
    ).read_bytes()
