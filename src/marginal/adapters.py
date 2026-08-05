"""Thin, provider-neutral wrappers for budgeted function and SDK calls."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, Generic, NoReturn, ParamSpec, TypeVar

from .fingerprint import fingerprint_call
from .models import Action, Allocation, Cost, Decision
from .treasury import AuthorizationRequired, Treasury

P = ParamSpec("P")
R = TypeVar("R")


class ActionDenied(RuntimeError):
    """Raised before execution when the treasury rejects an action."""

    def __init__(self, decision: Decision) -> None:
        super().__init__(decision.reason)
        self.decision = decision


UsageExtractor = Callable[[Any, Cost], Cost]
ActionFactory = Callable[[tuple[Any, ...], dict[str, Any]], Action]


def _prepare_call(
    action: Action,
    function: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Action:
    if action.fingerprint:
        return action
    return replace(
        action,
        fingerprint=fingerprint_call(action, function, args, kwargs),
    )


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


def _abort_after_error(treasury: Treasury, action: Action, error: Exception) -> NoReturn:
    try:
        treasury.abort(action, reason=f"{type(error).__name__}: {error}")
    except Exception as abort_error:
        raise error from abort_error
    raise error


def budgeted_call(
    treasury: Treasury,
    function: Callable[..., R],
    *args: Any,
    action: Action,
    usage_extractor: UsageExtractor | None = None,
    **kwargs: Any,
) -> R:
    """Authorize, execute, and settle a callable.

    The callable is never invoked when authorization fails. Callable failures release the
    reservation. Usage extraction receives both the result and estimated cost so fields
    not observable from a provider response can be preserved explicitly.
    """

    prepared = _prepare_call(action, function, tuple(args), kwargs)
    decision = treasury.authorize(prepared)
    if not decision.allowed:
        raise ActionDenied(decision)

    try:
        result = function(*args, **kwargs)
    except Exception as exc:
        _abort_after_error(treasury, prepared, exc)
    return _settle_result(treasury, prepared, result, usage_extractor)


async def async_budgeted_call(
    treasury: Treasury,
    function: Callable[..., Awaitable[R]],
    *args: Any,
    action: Action,
    usage_extractor: UsageExtractor | None = None,
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
        _abort_after_error(treasury, prepared, exc)
    return _settle_result(treasury, prepared, result, usage_extractor)


def funded_call(
    treasury: Treasury,
    allocation: Allocation,
    function: Callable[..., R],
    *args: Any,
    usage_extractor: UsageExtractor | None = None,
    **kwargs: Any,
) -> R:
    """Execute and settle an action already reserved by :meth:`Treasury.fund_best`."""

    action = _require_funded(treasury, allocation)
    try:
        result = function(*args, **kwargs)
    except Exception as exc:
        _abort_after_error(treasury, action, exc)
    return _settle_result(treasury, action, result, usage_extractor)


async def async_funded_call(
    treasury: Treasury,
    allocation: Allocation,
    function: Callable[..., Awaitable[R]],
    *args: Any,
    usage_extractor: UsageExtractor | None = None,
    **kwargs: Any,
) -> R:
    """Async equivalent of :func:`funded_call`."""

    action = _require_funded(treasury, allocation)
    try:
        result = await function(*args, **kwargs)
    except Exception as exc:
        _abort_after_error(treasury, action, exc)
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
    ) -> None:
        self.treasury = treasury
        self.function = function
        self.action_factory = action_factory
        self.usage_extractor = usage_extractor

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        action = self.action_factory(tuple(args), dict(kwargs))
        return budgeted_call(
            self.treasury,
            self.function,
            *args,
            action=action,
            usage_extractor=self.usage_extractor,
            **kwargs,
        )


def extract_common_llm_usage(result: Any, estimated_cost: Cost) -> Cost:
    """Read common token fields while preserving cost dimensions not in the response."""

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
