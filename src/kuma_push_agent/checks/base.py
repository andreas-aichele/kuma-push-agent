"""Base classes and result type for all checks."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    """Result returned by every check implementation."""

    ok: bool
    message: str
    duration_ms: int = field(default=0)


class BaseCheck(abc.ABC):
    """Abstract base for all check implementations."""

    @abc.abstractmethod
    def run(self) -> CheckResult:
        """Execute the check and return a result."""
