"""Idempotente Anlage für die Offline-Warteschlange der App (#32).

Die App schickt beim ersten Versuch und bei jeder späteren Wiederholung denselben
`Idempotency-Key`. Kam der erste Versuch an, nur die Antwort nicht zurück, liefert eine
Wiederholung die gespeicherte Antwort, statt Artikel/Aufgabe doppelt anzulegen.
Nur erfolgreiche Ergebnisse werden gemerkt (24 h, im Speicher); Fehler darf man erneut versuchen.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from fastapi import HTTPException

TTL = 24 * 3600
MAX_ENTRIES = 5000
_KEY = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

_results: Dict[Tuple[int, str, str], Tuple[float, Any]] = {}
_locks: Dict[Tuple[int, str, str], asyncio.Lock] = {}


def _prune(now: float) -> None:
    if len(_results) < MAX_ENTRIES:
        return
    for k in [k for k, (at, _) in _results.items() if now - at > TTL] or list(_results)[: MAX_ENTRIES // 10]:
        _results.pop(k, None)
        _locks.pop(k, None)


async def run(user_id: int, scope: str, key: Optional[str], action: Callable[[], Awaitable[Any]]) -> Any:
    if key is None:
        return await action()
    if not _KEY.match(key):
        raise HTTPException(422, "Ungültiger Idempotency-Key")
    ident = (user_id, scope, key)
    lock = _locks.setdefault(ident, asyncio.Lock())
    async with lock:  # gleichzeitige Wiederholungen warten auf den ersten Versuch
        now = time.monotonic()
        hit = _results.get(ident)
        if hit and now - hit[0] < TTL:
            return hit[1]
        result = await action()
        _prune(now)
        _results[ident] = (now, result)
        return result


def clear() -> None:
    _results.clear()
    _locks.clear()
