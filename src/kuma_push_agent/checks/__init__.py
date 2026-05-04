"""Check registry and factory for kuma-push-agent."""

from __future__ import annotations

from kuma_push_agent.checks.base import BaseCheck, CheckResult
from kuma_push_agent.checks.mariadb_via_ssh import MariaDBViaSSHCheck
from kuma_push_agent.config import CheckConfig

__all__ = ["BaseCheck", "CheckResult", "build_check"]


def build_check(cfg: CheckConfig) -> BaseCheck:
    """Instantiate the correct :class:`BaseCheck` subclass for *cfg*."""
    if cfg.type == "mariadb_via_ssh":
        return MariaDBViaSSHCheck(cfg)
    raise ValueError(f"Unknown check type: {cfg.type!r}")
