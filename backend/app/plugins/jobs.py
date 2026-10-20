"""Scheduled jobs of plugins (``Plugin.schedule_minutes`` and ``Plugin.scheduled``).

Called from the hub's scheduler loop once a minute. A job runs for an active plugin when its interval has
passed, never twice at the same time for one plugin, with a timeout, and in its own task: a slow or broken
job neither blocks the loop nor the other plugins. The time of the last run is kept in memory only, so every
plugin runs once soon after a restart.
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

from app.core.logging_config import get_logger
from app.plugins.base import Plugin
from app.plugins.hooks import SCHEDULED_TIMEOUT

logger = get_logger("plugins.jobs")

MIN_MINUTES = 5

_last_run: Dict[str, float] = {}
_running: Dict[str, "asyncio.Task"] = {}


def reset() -> None:
    """Forget last runs and running jobs (tests)."""
    _last_run.clear()
    _running.clear()


def interval_seconds(plugin: Plugin) -> Optional[float]:
    """Seconds between two runs, or None when the plugin has no (valid) schedule."""
    minutes = getattr(plugin, "schedule_minutes", None)
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or minutes <= 0:
        return None
    return max(float(minutes), MIN_MINUTES) * 60


def has_job(plugin: Plugin) -> bool:
    return type(plugin).scheduled is not Plugin.scheduled and interval_seconds(plugin) is not None


async def _run(plugin: Plugin) -> None:
    from app.core.database import SessionLocal

    started = time.monotonic()
    try:
        with SessionLocal() as db:
            await asyncio.wait_for(plugin.scheduled(db), SCHEDULED_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("Plugin %s: scheduled job stopped after %ss", plugin.id, SCHEDULED_TIMEOUT)
    except asyncio.CancelledError:  # pragma: no cover - shutdown
        raise
    except Exception as exc:  # noqa: BLE001 - a plugin job must never stop the scheduler
        logger.warning("Plugin %s: scheduled job failed: %s", plugin.id, type(exc).__name__)
    else:
        logger.debug("Plugin %s: scheduled job done in %.1fs", plugin.id, time.monotonic() - started)
    finally:
        _running.pop(plugin.id, None)


async def run_due(wait: bool = False) -> List[str]:
    """Starts the jobs that are due; returns the ids of the plugins started. With ``wait`` it returns after
    they finished (tests); the scheduler loop does not wait."""
    from app.plugins.registry import plugin_registry

    now = time.monotonic()
    started: List[str] = []
    tasks = []
    for plugin in plugin_registry.all():
        try:
            if not (plugin.active and has_job(plugin)) or plugin.id in _running:
                continue
        except Exception as exc:  # noqa: BLE001 - e.g. a broken is_configured()
            logger.warning("Plugin %s: job check failed: %s", plugin.id, type(exc).__name__)
            continue
        last = _last_run.get(plugin.id)
        if last is not None and now - last < interval_seconds(plugin):
            continue
        _last_run[plugin.id] = now
        task = asyncio.create_task(_run(plugin))
        _running[plugin.id] = task
        tasks.append(task)
        started.append(plugin.id)
    if wait and tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    return started
