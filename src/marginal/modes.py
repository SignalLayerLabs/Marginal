"""Execution modes for MARGINAL authorization decisions."""

from __future__ import annotations

from enum import Enum


class ExecutionMode(str, Enum):
    """Control whether MARGINAL enforces or only records recommendations."""

    SHADOW = "shadow"
    RECOMMEND = "recommend"
    ENFORCE = "enforce"

    @classmethod
    def parse(cls, value: ExecutionMode | str) -> ExecutionMode:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError("execution mode must be a string or ExecutionMode")
        normalized = value.strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            choices = ", ".join(mode.value for mode in cls)
            raise ValueError(f"unknown execution mode {value!r}; choose one of: {choices}") from exc

    @property
    def is_blocking(self) -> bool:
        return self is self.ENFORCE
