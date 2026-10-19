"""The auth dependency must not block the event loop (pool deadlock, 2026-10-19)."""
import asyncio
import inspect

from app.core.security import get_current_user


def test_get_current_user_runs_in_thread_pool():
    # async def would run its blocking DB checkout on the event loop: with the pool exhausted the
    # whole server froze, because no other request could finish and return its connection.
    assert not inspect.iscoroutinefunction(get_current_user)
    assert not asyncio.iscoroutinefunction(get_current_user)
