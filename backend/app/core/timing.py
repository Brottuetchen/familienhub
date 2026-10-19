"""Per-source timing and time limits (#71): regressions show up in the log, slow sources never block a screen."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Optional

SLOW_SECONDS = 1.5


async def timed(name: str, make: Callable[[], Awaitable[Any]], *, timeout: float, default: Any,
                logger: Optional[logging.Logger] = None, on_timeout: Optional[Callable[[], Any]] = None) -> Any:
    """Run ``make()`` and log its duration (debug; warning above ``SLOW_SECONDS``).

    After ``timeout`` seconds the source is given up: its ``default`` (or ``on_timeout()``) is returned
    instead and a warning is logged. Other exceptions propagate; the sources handle their own failures.
    """
    log = logger or logging.getLogger("hermes.timing")
    started = time.monotonic()
    try:
        return await asyncio.wait_for(make(), timeout)
    except asyncio.TimeoutError:
        log.warning("source %s gave up after %.1f s", name, timeout)
        return on_timeout() if on_timeout else default
    finally:
        took = time.monotonic() - started
        (log.warning if took > SLOW_SECONDS else log.debug)("source %s took %.0f ms", name, took * 1000)
