"""Shared CalDAV state: one HTTP client per account, the calendar list per account and a short read cache.

Why: every request used to build a new ``DAVClient`` and repeat principal discovery, ``calendars()``,
``get_supported_components()`` and the colour lookup per calendar before the one REPORT that matters.
On a real hub that was 1.3-2 s per call and ``/api/today`` needed several of them.

- ``client_for``: one ``DAVClient`` (one ``requests`` session with its connection pool) per account. The
  session is safe to share between threads for plain requests; the table is bounded (LRU).
- ``calendars``: calendars of an account with name, colour and supported components, cached for
  ``CALENDAR_TTL`` seconds. The entries keep the calendar's URL as listed: the caldav library rewrites
  ``calendar.url`` to ``host:443`` after a request, so compare with ``_normalize_url`` only.
- ``read_get`` / ``read_put``: results of event/task reads for ``READ_TTL`` seconds, keyed by account and
  user. Dropped by ``clear_reads`` on every write (connector writes and, as a safety net, every changing
  HTTP request, see ``app.main``).

Accounts are identified by a hash of URL, user and password, so a changed account never sees old data.
"""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.config import settings

CALENDAR_TTL = 300
READ_TTL = 45
MAX_ACCOUNTS = 32
MAX_READS = 500

_lock = threading.RLock()
_clients: "OrderedDict[str, Any]" = OrderedDict()
_calendars: Dict[str, Tuple[float, List["CalInfo"]]] = {}
_reads: Dict[Any, Tuple[float, Any]] = {}
_listing_locks: Dict[str, threading.Lock] = {}  # one listing at a time per account: parallel readers share it
stats = {"calendar_listings": 0, "client_builds": 0, "read_hits": 0, "read_misses": 0}


def account_key(url: Any, username: Any, password: Any) -> str:
    return sha256(json.dumps([str(url), str(username), str(password)]).encode()).hexdigest()[:24]


def client_for(url: str, username: str, password: str):
    """The account's shared ``DAVClient``."""
    import caldav

    key = account_key(url, username, password)
    with _lock:
        client = _clients.get(key)
        if client is not None:
            _clients.move_to_end(key)
            return client
        client = caldav.DAVClient(url=url, username=username, password=password, ssl_verify_cert=settings.verify_tls)
        stats["client_builds"] += 1
        _clients[key] = client
        while len(_clients) > MAX_ACCOUNTS:
            _clients.popitem(last=False)
        return client


@dataclass
class CalInfo:
    """A calendar of an account. Name, colour and components are looked up once and remembered."""

    cal: Any
    url: str  # as listed, before any request rewrote it
    _memo: Dict[str, Any] = field(default_factory=dict)
    _lock: Any = field(default_factory=threading.Lock, repr=False)

    def _once(self, key: str, fn: Callable[[], Any]) -> Any:
        with self._lock:
            if key not in self._memo:
                self._memo[key] = fn()
            return self._memo[key]

    @property
    def name(self) -> Optional[str]:
        return self._once("name", lambda: _safe(lambda: str(self.cal.name)))

    @property
    def color(self) -> Optional[str]:
        from app.connectors.caldav_connector import calendar_color

        return self._once("color", lambda: calendar_color(self.cal))

    @property
    def components(self) -> Optional[List[str]]:
        """Upper-case component names, or None when the server could not tell."""
        with self._lock:
            if "components" not in self._memo:
                found = _safe(lambda: [str(c).upper() for c in self.cal.get_supported_components()])
                if found is None:
                    return None  # a failed lookup is retried on the next request, never remembered
                self._memo["components"] = found
            return self._memo["components"]

    def supports(self, component: str) -> Optional[bool]:
        comps = self.components
        return None if comps is None else component in comps


def calendars(url: str, username: str, password: str, refresh: bool = False) -> List[CalInfo]:
    """Calendars of the account (cached). Raises what the server raises; errors are never cached."""
    key = account_key(url, username, password)
    with _lock:
        gate = _listing_locks.setdefault(key, threading.Lock())
    with gate:
        with _lock:
            hit = _calendars.get(key)
            if hit and hit[0] > time.monotonic() and not refresh:
                return list(hit[1])
        client = client_for(url, username, password)
        infos = [CalInfo(cal=c, url=str(c.url)) for c in client.principal().calendars()]
        stats["calendar_listings"] += 1
        with _lock:
            _calendars[key] = (time.monotonic() + CALENDAR_TTL, infos)
        return list(infos)


def invalidate_account(url: Any = None, username: Any = None, password: Any = None) -> None:
    """Forget client and calendar list (all accounts without arguments)."""
    with _lock:
        if url is None:
            _clients.clear()
            _calendars.clear()
            return
        key = account_key(url, username, password)
        _clients.pop(key, None)
        _calendars.pop(key, None)


# --- short read cache ---


def read_get(key: Any) -> Optional[Any]:
    with _lock:
        hit = _reads.get(key)
        if hit and hit[0] > time.monotonic():
            stats["read_hits"] += 1
            return deepcopy(hit[1])
        _reads.pop(key, None)
        stats["read_misses"] += 1
    return None


def read_put(key: Any, value: Any, ttl: float = READ_TTL) -> None:
    with _lock:
        if len(_reads) >= MAX_READS:
            now = time.monotonic()
            for k in [k for k, (exp, _) in _reads.items() if exp <= now] or list(_reads)[:50]:
                _reads.pop(k, None)
        _reads[key] = (time.monotonic() + ttl, deepcopy(value))


def clear_reads() -> None:
    with _lock:
        _reads.clear()


def reset() -> None:
    """Forget everything (tests)."""
    with _lock:
        _clients.clear()
        _calendars.clear()
        _reads.clear()
        _listing_locks.clear()
        for k in stats:
            stats[k] = 0


def _safe(fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None
