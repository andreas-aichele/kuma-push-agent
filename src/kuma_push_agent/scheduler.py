"""APScheduler-based interval scheduler for check jobs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler

from kuma_push_agent.checks import build_check
from kuma_push_agent.checks.base import BaseCheck
from kuma_push_agent.config import AgentConfig, CheckConfig
from kuma_push_agent.uptime_kuma import push

_logger = logging.getLogger(__name__)


def _run_check_job(check: BaseCheck, cfg: CheckConfig) -> None:
    """Execute *check*, log the result, and push the heartbeat to Uptime Kuma."""
    _logger.debug("Running check: %s", cfg.name)
    result = check.run()
    status = "up" if result.ok else "down"
    _logger.info(
        "Check '%s': ok=%s msg=%s ping=%dms",
        cfg.name,
        result.ok,
        result.message,
        result.duration_ms,
    )
    push(cfg.uptime_kuma_push_url, status=status, msg=result.message, ping=result.duration_ms)


class AgentScheduler:
    """Manages APScheduler interval jobs — one per configured check."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._scheduler = BackgroundScheduler()

    def start(self) -> None:
        """Register all check jobs and start the background scheduler."""
        for cfg in self._config.checks:
            check = build_check(cfg)
            self._scheduler.add_job(
                _run_check_job,
                "interval",
                args=[check, cfg],
                seconds=cfg.interval_seconds,
                next_run_time=datetime.now(UTC),
                misfire_grace_time=cfg.interval_seconds,
                id=cfg.name,
                name=cfg.name,
            )
            _logger.info("Scheduled check '%s' every %ds", cfg.name, cfg.interval_seconds)

        self._scheduler.start()
        _logger.info("Scheduler started with %d job(s)", len(self._config.checks))

    def stop(self) -> None:
        """Shut down the scheduler and wait for running jobs to finish."""
        self._scheduler.shutdown(wait=True)
        _logger.info("Scheduler stopped")
