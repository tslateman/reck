"""Check function protocol and registry for the review pipeline."""

from __future__ import annotations

from typing import Protocol

from reck.events import AgentResult, CheckResult


class CheckFn(Protocol):
    def __call__(self, result: AgentResult, criteria: dict) -> CheckResult: ...


class CheckRegistry:
    """Maps check type names (matching YAML keys) to CheckFn instances."""

    def __init__(self) -> None:
        self._checks: dict[str, CheckFn] = {}

    def register(self, type_name: str, fn: CheckFn) -> None:
        self._checks[type_name] = fn

    def get(self, type_name: str) -> CheckFn:
        if type_name not in self._checks:
            raise KeyError(f"Unknown check type: {type_name!r}")
        return self._checks[type_name]

    def __contains__(self, type_name: str) -> bool:
        return type_name in self._checks
