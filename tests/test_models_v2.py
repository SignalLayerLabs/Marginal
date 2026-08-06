from __future__ import annotations

import pytest

from marginal.models import Decision, TokenUsage
from marginal.modes import ExecutionMode


def test_token_usage_calculates_total_when_omitted() -> None:
    usage = TokenUsage(input_tokens=10, cached_input_tokens=3, output_tokens=4, reasoning_tokens=5)
    assert usage.total_tokens == 22


def test_token_usage_rejects_inconsistent_total() -> None:
    with pytest.raises(ValueError, match="total_tokens"):
        TokenUsage(input_tokens=10, output_tokens=2, total_tokens=11)


def test_token_usage_rejects_boolean_counters() -> None:
    with pytest.raises(TypeError, match="input_tokens"):
        TokenUsage(input_tokens=True)  # type: ignore[arg-type]


def test_decision_defaults_preserve_v01_behavior() -> None:
    decision = Decision(True, "approved")
    assert decision.allowed is True
    assert decision.recommended is True
    assert decision.mode == "enforce"
    assert decision.reason_code == "UNSPECIFIED"


def test_execution_mode_parses_case_insensitively() -> None:
    assert ExecutionMode.parse("SHADOW") is ExecutionMode.SHADOW
    assert ExecutionMode.parse(ExecutionMode.RECOMMEND) is ExecutionMode.RECOMMEND


def test_execution_mode_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="execution mode"):
        ExecutionMode.parse("observe-only")


def test_common_token_usage_extractor_preserves_breakdown() -> None:
    from marginal.adapters import extract_common_token_usage

    usage = extract_common_token_usage(
        {
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 40,
                "output_tokens": 20,
                "reasoning_tokens": 10,
                "total_tokens": 130,
            }
        }
    )
    assert usage.input_tokens == 60
    assert usage.cached_input_tokens == 40
    assert usage.output_tokens == 20
    assert usage.reasoning_tokens == 10
    assert usage.total_tokens == 130


def test_common_token_usage_handles_reasoning_as_output_subset() -> None:
    from marginal.adapters import extract_common_token_usage

    usage = extract_common_token_usage(
        {
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 40,
                "output_tokens": 30,
                "reasoning_tokens": 10,
                "total_tokens": 130,
            }
        }
    )

    assert usage.input_tokens == 60
    assert usage.cached_input_tokens == 40
    assert usage.output_tokens == 20
    assert usage.reasoning_tokens == 10
    assert usage.total_tokens == 130


def test_common_token_usage_without_total_treats_output_detail_reasoning_as_subset() -> None:
    from marginal.adapters import extract_common_token_usage

    usage = extract_common_token_usage(
        {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 30,
                "output_tokens_details": {"reasoning_tokens": 10},
            }
        }
    )

    assert usage.input_tokens == 100
    assert usage.output_tokens == 20
    assert usage.reasoning_tokens == 10
    assert usage.total_tokens == 130
