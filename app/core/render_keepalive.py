"""Render-only keepalive support.

The task is opt-in and accepts only Render-owned HTTPS hosts. This keeps an
accidental environment-variable copy from making other deployments ping an
arbitrary URL.
"""

import asyncio
import logging
from urllib.parse import urlsplit, urlunsplit

import httpx


logger = logging.getLogger(__name__)


def resolve_render_keepalive_url(
    configured_url: str,
    render_external_url: str,
) -> str | None:
    """Return a safe Render health URL, or None when the target is invalid."""
    candidate = (configured_url or render_external_url).strip()
    if not candidate:
        return None

    parsed = urlsplit(candidate)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not hostname.endswith(".onrender.com"):
        return None

    path = parsed.path.rstrip("/")
    if not path:
        path = "/health"

    return urlunsplit(("https", parsed.netloc, path, parsed.query, ""))


async def run_render_keepalive(url: str, interval_seconds: int) -> None:
    """Ping the Render health route periodically until application shutdown."""
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                response = await client.get(url)
                if response.is_success:
                    logger.info("Render keepalive health check succeeded")
                else:
                    logger.warning(
                        "Render keepalive health check returned HTTP %s",
                        response.status_code,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Render keepalive health check failed: %s", exc)
