"""Entry point for kuma-push-agent."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import types

from kuma_push_agent import __version__
from kuma_push_agent.config import load_config
from kuma_push_agent.logging_setup import get_logger, setup_logging
from kuma_push_agent.scheduler import AgentScheduler
from kuma_push_agent.ssh_pool import get_pool


def main() -> None:
    """Parse arguments, load config, start scheduler, and wait for shutdown."""
    parser = argparse.ArgumentParser(
        description="kuma-push-agent: push monitoring agent for Uptime Kuma"
    )
    parser.add_argument(
        "--config",
        default="config.yml",
        metavar="PATH",
        help="Path to YAML config file (default: config.yml)",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        metavar="LEVEL",
        help="Log level: DEBUG, INFO, WARNING, ERROR (overrides LOG_LEVEL env var)",
    )
    args = parser.parse_args()

    log_level = args.log_level or os.environ.get("LOG_LEVEL", "INFO")
    setup_logging(log_level)
    logger = get_logger("kuma_push_agent.main")

    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected config error: {exc}", file=sys.stderr)
        sys.exit(1)

    logger.info(
        "kuma-push-agent v%s starting with %d check(s)",
        __version__,
        len(config.checks),
    )

    stop_event = threading.Event()

    def _shutdown(signum: int, _frame: types.FrameType | None) -> None:
        logger.info("Received signal %d, shutting down…", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    scheduler = AgentScheduler(config)
    scheduler.start()

    try:
        stop_event.wait()
    finally:
        logger.info("Stopping scheduler…")
        scheduler.stop()
        logger.info("Closing SSH pool…")
        get_pool().close_all()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
