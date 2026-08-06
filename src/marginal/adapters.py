"""Thin, provider-neutral wrappers for budgeted function and SDK calls."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, Generic, NoReturn, ParamSpec, TypeVar

from .fingerprint import fingerprint_call
from .models import Action, Allocation, Cost, Decision, TokenUsage
from .treasury import AuthorizationRequired, Treasury

P = ParamSpec("P")
R = TypeVar("R")


class ActionDenied(RuntimeError):
    """Raised before execution when the treasury rejects an action."""

    def __init__(self, decision: Decision) -> None:
        super().__init__(decision.reason)
        self.decision = decision


UsageExtractor = Callable[[Any, Cost], Cost]
FailureUsageExtractor = Callable[[Exception, Cost], Cost | None]
ActionFactory = Callable[[tuple[Any, ...], dict[str, Any]], Action]


def _prepare_call(
    action: Action,
    function: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Action:
    if action.fingerprint:
        return action
    return replace(action, fingerprint=fingerprint_call(action, function, args, kwargs))


def _settle_result(
    treasury: Treasury,
    action: Action,
    result: R,
    usage_extractor: UsageExtractor | None,
) -> R:
    committed = action
    if usage_extractor is not None:
        try:
            actual_cost = usage_extractor(result, action.cost)
            if not isinstance(actual_cost, Cost):
                raise TypeError("usage_extractor must return Cost")
        except Exception:
            treasury.commit(action)
            raise
        committed = replace(action, cost=actual_cost)
    treasury.commit(committed)
    return result


def _require_funded(treasury: Treasury, allocation: Allocation) -> Action:
    action = allocation.action
    if not allocation.decision.allowed or not treasury.is_authorized(action):
        raise AuthorizationRequired("action must be authorized before funded execution")
    return action


def _handle_execution_error(
    treasury: Treasury,
    action: Action,
    error: Exception,
    failure_usage_extractor: FailureUsageExtractor | None,
) -> NoReturn:
    reason = f"{type(error).__name__}: {error}"
    if failure_usage_extractor is None:
        try:
            treasury.abort(action, reason=reason)
        except Exception as abort_error:
            raise error from abort_error
        raise error

    try:
        actual_cost = failure_usage_extractor(error, action.cost)
        if actual_cost is not None and not isinstance(actual_cost, Cost):
            raise TypeError("failure_usage_extractor must return Cost or None")
    except Exception as extraction_error:
        try:
            treasury.settle_failure(
                action,
                action.cost,
                reason=f"{reason}; usage extraction failed conservatively",
            )
        except Exception as settlement_error:
            raise error from settlement_error
        raise error from extraction_error

    try:
        if actual_cost is None:
            treasury.abort(action, reason=reason)
        else:
            treasury.settle_failure(action, actual_cost, reason=reason)
    except Exception as settlement_error:
        raise error from settlement_error
    raise error


def budgeted_call(
    treasury: Treasury,
    function: Callable[..., R],
    *args: Any,
    action: Action,
    usage_extractor: UsageExtractor | None = None,
    failure_usage_extractor: FailureUsageExtractor | None = None,
    **kwargs: Any,
) -> R:
    """Authorize, execute, and settle a synchronous callable."""

    prepared = _prepare_call(action, function, tuple(args), kwargs)
    decision = treasury.authorize(prepared)
    if not decision.allowed:
        raise ActionDenied(decision)
    try:
        result = function(*args, **kwargs)
    except Exception as exc:
        _handle_execution_error(treasury, prepared, exc, failure_usage_extractor)
    return _settle_result(treasury, prepared, result, usage_extractor)


async def async_budgeted_call(
    treasury: Treasury,
    function: Callable[..., Awaitable[R]],
    *args: Any,
    action: Action,
    usage_extractor: UsageExtractor | None = None,
    failure_usage_extractor: FailureUsageExtractor | None = None,
    **kwargs: Any,
) -> R:
    """Async equivalent of :func:`budgeted_call`."""

    prepared = _prepare_call(action, function, tuple(args), kwargs)
    decision = treasury.authorize(prepared)
    if not decision.allowed:
        raise ActionDenied(decision)
    try:
        result = await function(*args, **kwargs)
    except Exception as exc:
        _handle_execution_error(treasury, prepared, exc, failure_usage_extractor)
    return _settle_result(treasury, prepared, result, usage_extractor)


def funded_call(
    treasury: Treasury,
    allocation: Allocation,
    function: Callable[..., R],
    *args: Any,
    usage_extractor: UsageExtractor | None = None,
    failure_usage_extractor: FailureUsageExtractor | None = None,
    **kwargs: Any,
) -> R:
    """Execute and settle an action reserved by :meth:`Treasury.fund_best`."""

    action = _require_funded(treasury, allocation)
    try:
        result = function(*args, **kwargs)
    except Exception as exc:
        _handle_execution_error(treasury, action, exc, failure_usage_extractor)
    return _settle_result(treasury, action, result, usage_extractor)


async def async_funded_call(
    treasury: Treasury,
    allocation: Allocation,
    function: Callable[..., Awaitable[R]],
    *args: Any,
    usage_extractor: UsageExtractor | None = None,
    failure_usage_extractor: FailureUsageExtractor | None = None,
    **kwargs: Any,
) -> R:
    """Async equivalent of :func:`funded_call`."""

    action = _require_funded(treasury, allocation)
    try:
        result = await function(*args, **kwargs)
    except Exception as exc:
        _handle_execution_error(treasury, action, exc, failure_usage_extractor)
    return _settle_result(treasury, action, result, usage_extractor)


class BudgetedCallable(Generic[P, R]):
    """Reusable callable wrapper that creates one action per invocation."""

    def __init__(
        self,
        treasury: Treasury,
        function: Callable[P, R],
        *,
        action_factory: ActionFactory,
        usage_extractor: UsageExtractor | None = None,
        failure_usage_extractor: FailureUsageExtractor | None = None,
    ) -> None:
        self.treasury = treasury
        self.function = function
        self.action_factory = action_factory
        self.usage_extractor = usage_extractor
        self.failure_usage_extractor = failure_usage_extractor

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        action = self.action_factory(tuple(args), dict(kwargs))
        return budgeted_call(
            self.treasury,
            self.function,
            *args,
            action=action,
            usage_extractor=self.usage_extractor,
            failure_usage_extractor=self.failure_usage_extractor,
            **kwargs,
        )


def extract_common_token_usage(result: Any) -> TokenUsage:
    """Read a normalized token breakdown from common provider response shapes.

    Common provider ``input_tokens`` counters usually include cached input. When a cached
    counter is present, this function reports uncached input in ``input_tokens`` and cached
    input separately so the four components remain additive.
    """

    usage = getattr(result, "usage", None)
    if usage is None and isinstance(result, dict):
        usage = result.get("usage")
    if usage is None:
        raise ValueError("response does not expose usage information")

    def read(*names: str) -> int | None:
        for name in names:
            if isinstance(usage, dict) and name in usage:
                value = usage[name]
            else:
                value = getattr(usage, name, None)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("usage token fields must be integers")
            if value < 0:
                raise ValueError("usage token fields must be non-negative")
            return value
        return None

    raw_input = read("input_tokens", "prompt_tokens") or 0
    cached = read("cached_input_tokens", "cached_tokens") or 0
    raw_output = read("output_tokens", "completion_tokens") or 0
    reasoning = read("reasoning_tokens") or 0
    reasoning_is_output_subset = False

    details = None
    if isinstance(usage, dict):
        details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details")
    else:
        details = getattr(usage, "input_tokens_details", None) or getattr(
            usage, "prompt_tokens_details", None
        )
    if details is not None and cached == 0:
        if isinstance(details, dict):
            detail_cached = details.get("cached_tokens")
        else:
            detail_cached = getattr(details, "cached_tokens", None)
        if detail_cached is not None:
            if isinstance(detail_cached, bool) or not isinstance(detail_cached, int):
                raise TypeError("usage token fields must be integers")
            if detail_cached < 0:
                raise ValueError("usage token fields must be non-negative")
            cached = detail_cached

    output_details = None
    if isinstance(usage, dict):
        output_details = usage.get("output_tokens_details") or usage.get(
            "completion_tokens_details"
        )
    else:
        output_details = getattr(usage, "output_tokens_details", None) or getattr(
            usage, "completion_tokens_details", None
        )
    if output_details is not None and reasoning == 0:
        if isinstance(output_details, dict):
            detail_reasoning = output_details.get("reasoning_tokens")
        else:
            detail_reasoning = getattr(output_details, "reasoning_tokens", None)
        if detail_reasoning is not None:
            if isinstance(detail_reasoning, bool) or not isinstance(detail_reasoning, int):
                raise TypeError("usage token fields must be integers")
            if detail_reasoning < 0:
                raise ValueError("usage token fields must be non-negative")
            reasoning = detail_reasoning
            reasoning_is_output_subset = True

    if cached > raw_input:
        raise ValueError("cached input tokens cannot exceed total input tokens")
    uncached_input = raw_input - cached
    declared_total = read("total_tokens")

    if declared_total is None:
        if reasoning_is_output_subset:
            if reasoning > raw_output:
                raise ValueError("reasoning tokens cannot exceed total output tokens")
            output = raw_output - reasoning
        else:
            output = raw_output
        calculated = uncached_input + cached + output + reasoning
    elif declared_total == raw_input + raw_output:
        if reasoning > raw_output:
            raise ValueError("reasoning tokens cannot exceed total output tokens")
        output = raw_output - reasoning
        calculated = declared_total
    elif declared_total == raw_input + raw_output + reasoning:
        output = raw_output
        calculated = declared_total
    else:
        raise ValueError("total_tokens is inconsistent with the normalized token breakdown")

    if calculated == 0 and declared_total is None:
        raise ValueError("usage does not expose recognized token fields")
    return TokenUsage(
        input_tokens=uncached_input,
        cached_input_tokens=cached,
        output_tokens=output,
        reasoning_tokens=reasoning,
        total_tokens=calculated,
    )


def extract_common_llm_usage(result: Any, estimated_cost: Cost) -> Cost:
    """Read common total token fields while preserving unobserved dimensions."""

    usage = getattr(result, "usage", None)
    if usage is None and isinstance(result, dict):
        usage = result.get("usage")
    if usage is None:
        raise ValueError("response does not expose usage information")

    def read(*names: str) -> int | None:
        for name in names:
            if isinstance(usage, dict) and name in usage:
                value = usage[name]
            else:
                value = getattr(usage, name, None)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("usage token fields must be integers")
            if value < 0:
                raise ValueError("usage token fields must be non-negative")
            return value
        return None

    total = read("total_tokens")
    if total is None:
        input_tokens = read("input_tokens", "prompt_tokens")
        output_tokens = read("output_tokens", "completion_tokens")
        if input_tokens is None and output_tokens is None:
            raise ValueError("usage does not expose recognized token fields")
        total = (input_tokens or 0) + (output_tokens or 0)
    return Cost(
        tokens=total,
        usd=estimated_cost.usd,
        latency_ms=estimated_cost.latency_ms,
        risk=estimated_cost.risk,
    )
