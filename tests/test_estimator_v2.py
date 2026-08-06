from __future__ import annotations

import pytest

from marginal import Action, Cost
from marginal.estimator import EstimatorIdentity, ValueEstimator
from marginal.registry import EstimatorRegistry


def test_explicit_gain_returns_confident_versioned_estimate() -> None:
    estimator = ValueEstimator(name="reference", version="2.1.0")
    estimate = estimator.estimate_detail(
        Action(name="verify", kind="verification", cost=Cost(), expected_gain=0.2)
    )
    assert estimate.expected_gain == pytest.approx(0.2)
    assert estimate.confidence == 1.0
    assert estimate.uncertainty == 0.0
    assert estimate.provenance == "action.expected_gain"
    assert estimate.estimator.name == "reference"
    assert estimate.estimator.version == "2.1.0"


def test_contextual_observations_are_preferred_over_kind_average() -> None:
    estimator = ValueEstimator(context_fields=("engine", "phase"))
    generic = Action(name="generic", kind="research")
    codex = Action(
        name="codex research",
        kind="research",
        metadata={"engine": "codex", "phase": "diagnose"},
    )
    estimator.observe("research", 0.1)
    estimator.observe_action(codex, 0.5)
    assert estimator.estimate(generic) == pytest.approx(0.3)
    assert estimator.estimate(codex) == pytest.approx(0.5)


def test_historical_estimate_reports_sample_metadata() -> None:
    estimator = ValueEstimator()
    action = Action(name="search", kind="research")
    estimator.observe_action(action, 0.1)
    estimator.observe_action(action, 0.3)
    estimate = estimator.estimate_detail(action)
    assert estimate.expected_gain == pytest.approx(0.2)
    assert estimate.sample_size == 2
    assert estimate.confidence > 0
    assert estimate.uncertainty > 0
    assert estimate.provenance.startswith("historical:")


def test_estimator_identity_hash_is_stable_for_same_configuration() -> None:
    first = ValueEstimator(default_gain=0.1, context_fields=("engine",))
    second = ValueEstimator(default_gain=0.1, context_fields=("engine",))
    assert first.identity == second.identity
    assert first.identity.config_hash


def test_registry_resolves_name_and_version_and_rejects_duplicates() -> None:
    registry = EstimatorRegistry()
    estimator = ValueEstimator(name="historical", version="2.0.0")
    registry.register(estimator)
    assert registry.resolve("historical", "2.0.0") is estimator
    with pytest.raises(ValueError, match="already registered"):
        registry.register(estimator)


def test_estimator_identity_requires_nonempty_version() -> None:
    with pytest.raises(ValueError, match="version"):
        EstimatorIdentity(name="historical", version="", config_hash="abc")


def test_estimator_identity_rejects_non_string_training_fingerprint() -> None:
    with pytest.raises(TypeError, match="training_data_fingerprint"):
        EstimatorIdentity(
            name="historical",
            version="2.0.0",
            config_hash="abc",
            training_data_fingerprint=123,  # type: ignore[arg-type]
        )


def test_value_estimate_rejects_non_string_provenance() -> None:
    from marginal.estimator import ValueEstimate

    with pytest.raises(TypeError, match="provenance"):
        ValueEstimate(
            expected_gain=0.1,
            uncertainty=0.0,
            confidence=1.0,
            sample_size=1,
            provenance=123,  # type: ignore[arg-type]
            estimator=EstimatorIdentity(
                name="historical",
                version="2.0.0",
                config_hash="abc",
            ),
        )


def test_estimator_rejects_non_string_identity_fields() -> None:
    with pytest.raises(TypeError, match="name"):
        ValueEstimator(name=123)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="version"):
        ValueEstimator(version=123)  # type: ignore[arg-type]


def test_estimator_rejects_invalid_context_fields_container() -> None:
    with pytest.raises(TypeError, match="context_fields"):
        ValueEstimator(context_fields="engine")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unique"):
        ValueEstimator(context_fields=("engine", "engine"))


def test_contextual_action_observation_also_updates_kind_fallback() -> None:
    estimator = ValueEstimator(context_fields=("engine",))
    contextual = Action(
        name="search in codex",
        kind="research",
        metadata={"engine": "codex"},
    )

    estimator.observe_action(contextual, 0.4)

    assert estimator.estimate(Action(name="generic search", kind="research")) == pytest.approx(0.4)


def test_estimator_identity_tracks_observation_state_reproducibly() -> None:
    first = ValueEstimator(name="historical", version="2.0.0")
    second = ValueEstimator(name="historical", version="2.0.0")
    initial = first.identity

    first.observe("research", 0.2)
    second.observe("research", 0.2)

    assert first.identity.training_data_fingerprint
    assert first.identity.training_data_fingerprint != initial.training_data_fingerprint
    assert first.identity == second.identity
