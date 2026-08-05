"""Hierarchical resource budgets for agent actions."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Action, Cost, Decision


class BudgetExceeded(RuntimeError):
    """Raised when a proposed or committed action exceeds a budget."""


class BudgetOverrun(BudgetExceeded):
    """Raised after actual usage is accounted when it exceeds the reserved estimate."""


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    """Hard limits and reserves for one treasury."""

    max_tokens: int | None = None
    max_usd: float | None = None
    max_latency_ms: int | None = None
    max_risk: float | None = None
    verification_reserve_tokens: int = 0
    verification_reserve_usd: float = 0.0

    def __post_init__(self) -> None:
        integer_fields = (
            ("max_tokens", self.max_tokens),
            ("max_latency_ms", self.max_latency_ms),
            ("verification_reserve_tokens", self.verification_reserve_tokens),
        )
        for name, value in integer_fields:
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise TypeError(f"{name} must be an integer")

        numeric_fields = (
            ("max_usd", self.max_usd),
            ("max_risk", self.max_risk),
            ("verification_reserve_usd", self.verification_reserve_usd),
        )
        for name, value in numeric_fields:
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise TypeError(f"{name} must be a number")
            if value is not None and not math.isfinite(float(value)):
                raise ValueError("budget values must be finite")

        values = (
            self.max_tokens,
            self.max_usd,
            self.max_latency_ms,
            self.max_risk,
            self.verification_reserve_tokens,
            self.verification_reserve_usd,
        )
        if any(value is not None and value < 0 for value in values):
            raise ValueError("budget values must be non-negative")
        if self.max_tokens is None and self.verification_reserve_tokens > 0:
            raise ValueError("verification token reserve requires max_tokens")
        if self.max_usd is None and self.verification_reserve_usd > 0:
            raise ValueError("verification USD reserve requires max_usd")
        if self.max_tokens is not None and self.verification_reserve_tokens > self.max_tokens:
            raise ValueError("verification token reserve exceeds token budget")
        if self.max_usd is not None and self.verification_reserve_usd > self.max_usd:
            raise ValueError("verification USD reserve exceeds USD budget")


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    tokens: int = 0
    usd: float = 0.0
    latency_ms: int = 0
    risk: float = 0.0

    def plus(self, cost: Cost) -> "BudgetUsage":
        return BudgetUsage(
            tokens=self.tokens + cost.tokens,
            usd=self.usd + cost.usd,
            latency_ms=self.latency_ms + cost.latency_ms,
            risk=self.risk + cost.risk,
        )


class BudgetLedger:
    """Track committed usage and pending reservations for one budget."""

    def __init__(self, limits: BudgetLimits) -> None:
        self.limits = limits
        self._usage = BudgetUsage()
        self._regular_usage = BudgetUsage()
        self._reservations: dict[str, Action] = {}

    @property
    def usage(self) -> BudgetUsage:
        """Return committed usage only."""

        return self._usage

    @property
    def reserved_usage(self) -> BudgetUsage:
        """Return resources reserved by approved but unsettled actions."""

        return self._sum_reservations(regular_only=False)

    def can_afford(
        self,
        action: Action,
        *,
        replacing_fingerprint: str | None = None,
    ) -> Decision:
        """Check an action against committed usage plus pending reservations."""

        reserved = self._sum_reservations(
            regular_only=False,
            excluding_fingerprint=replacing_fingerprint,
        )
        regular_reserved = self._sum_reservations(
            regular_only=True,
            excluding_fingerprint=replacing_fingerprint,
        )
        projected = self._usage.plus(
            Cost(
                tokens=reserved.tokens + action.cost.tokens,
                usd=reserved.usd + action.cost.usd,
                latency_ms=reserved.latency_ms + action.cost.latency_ms,
                risk=reserved.risk + action.cost.risk,
            )
        )
        limits = self.limits

        if limits.max_tokens is not None:
            if projected.tokens > limits.max_tokens:
                return Decision(False, "token budget exceeded")
            if not action.is_verification:
                regular_tokens = (
                    self._regular_usage.tokens + regular_reserved.tokens + action.cost.tokens
                )
                regular_limit = limits.max_tokens - limits.verification_reserve_tokens
                if regular_tokens > regular_limit:
                    return Decision(False, "verification reserve would be breached")

        if limits.max_usd is not None:
            if projected.usd > limits.max_usd + 1e-12:
                return Decision(False, "USD budget exceeded")
            if not action.is_verification:
                regular_usd = self._regular_usage.usd + regular_reserved.usd + action.cost.usd
                regular_limit = limits.max_usd - limits.verification_reserve_usd
                if regular_usd > regular_limit + 1e-12:
                    return Decision(False, "verification reserve would be breached")

        if limits.max_latency_ms is not None and projected.latency_ms > limits.max_latency_ms:
            return Decision(False, "latency budget exceeded")

        if limits.max_risk is not None and projected.risk > limits.max_risk + 1e-12:
            return Decision(False, "risk budget exceeded")

        return Decision(True, "within budget")

    def reserve(self, action: Action) -> None:
        """Reserve an approved estimate without increasing committed usage."""

        if not action.fingerprint:
            raise ValueError("reserved actions require a fingerprint")
        if action.fingerprint in self._reservations:
            raise BudgetExceeded("duplicate budget reservation")
        decision = self.can_afford(action)
        if not decision.allowed:
            raise BudgetExceeded(decision.reason)
        self._reservations[action.fingerprint] = action

    def release(self, fingerprint: str) -> None:
        """Release a pending reservation if it exists."""

        self._reservations.pop(fingerprint, None)

    def commit(self, action: Action) -> BudgetUsage:
        """Commit an action without an existing reservation."""

        decision = self.can_afford(action)
        if not decision.allowed:
            raise BudgetExceeded(decision.reason)
        self._record(action)
        return self._usage

    def settle(self, action: Action, *, reservation_fingerprint: str) -> Decision:
        """Replace a reservation with actual usage and always account for the spend.

        The returned decision reports whether actual usage remained within the budget. An
        overrun is still recorded because the external action has already executed.
        """

        decision = self.can_afford(action, replacing_fingerprint=reservation_fingerprint)
        self.release(reservation_fingerprint)
        self._record(action)
        return decision

    def _record(self, action: Action) -> None:
        self._usage = self._usage.plus(action.cost)
        if not action.is_verification:
            self._regular_usage = self._regular_usage.plus(action.cost)

    def _sum_reservations(
        self,
        *,
        regular_only: bool,
        excluding_fingerprint: str | None = None,
    ) -> BudgetUsage:
        total = BudgetUsage()
        for fingerprint, action in self._reservations.items():
            if fingerprint == excluding_fingerprint:
                continue
            if regular_only and action.is_verification:
                continue
            total = total.plus(action.cost)
        return total
