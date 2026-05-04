"""Uptime Kuma push heartbeat client."""

from __future__ import annotations

import logging
from urllib.parse import urlencode, urlparse, urlunparse

import httpx

_logger = logging.getLogger(__name__)


def _mask_url(url: str) -> str:
    """Replace the last path segment (the push token) with *** for safe logging."""
    parsed = urlparse(url)
    path = parsed.path
    if not path or path == "/":
        return url
    slash_idx = path.rfind("/")
    if slash_idx < 0:
        return url
    masked_path = path[: slash_idx + 1] + "***"
    return urlunparse(parsed._replace(path=masked_path))


def push(
    url: str,
    status: str = "up",
    msg: str = "OK",
    ping: int = 0,
) -> None:
    """Push a heartbeat to the Uptime Kuma push endpoint.

    Never raises; all errors are logged so the agent keeps running.
    """
    params = {"status": status, "msg": msg, "ping": str(ping)}
    full_url = f"{url}?{urlencode(params)}"

    _logger.info(
        "Pushing to Uptime Kuma: %s status=%s msg=%s ping=%dms",
        _mask_url(url),
        status,
        msg,
        ping,
    )

    try:
        response = httpx.get(full_url, timeout=10.0)
        response.raise_for_status()
        _logger.debug("Uptime Kuma push OK: %s", _mask_url(url))
    except httpx.TimeoutException:
        _logger.error("Uptime Kuma push timed out: %s", _mask_url(url))
    except httpx.HTTPStatusError as exc:
        _logger.error(
            "Uptime Kuma push HTTP %d: %s",
            exc.response.status_code,
            _mask_url(url),
        )
    except httpx.RequestError as exc:
        _logger.error(
            "Uptime Kuma push request error %s: %s",
            type(exc).__name__,
            _mask_url(url),
        )
