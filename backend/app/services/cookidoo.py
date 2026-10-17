"""Cookidoo-Zugang über cookidoo-api (Rezeptsuche, Wochenplan, Zutaten).

Eine angemeldete Sitzung wird wiederverwendet. Läuft sie ab, meldet sich der Dienst einmal neu an.
Fehler kommen als ``CookidooUnavailable`` mit Klartext an, nie als rohe Ausnahme bis in die App.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.core.logging_config import get_logger
from app.plugins.base import get_setting

logger = get_logger("service.cookidoo")

try:  # Abmelde-/Ablauf-Fehler der Bibliothek → neu anmelden
    from cookidoo_api import CookidooAuthException

    AUTH_ERRORS: tuple = (CookidooAuthException,)
except ImportError:  # pragma: no cover – Bibliothek fehlt (Python < 3.12)
    AUTH_ERRORS = ()


class CookidooUnavailable(Exception):
    pass


def plugin_active() -> bool:
    """Plugin eingerichtet und nicht abgeschaltet (PLUGINS_DISABLED)."""
    from app.plugins.registry import plugin_registry

    plugin = plugin_registry.get("cookidoo")
    return bool(plugin and plugin.active)


def config() -> Optional[Dict[str, str]]:
    email, password = get_setting("COOKIDOO_EMAIL"), get_setting("COOKIDOO_PASSWORD")
    if not email or not password:
        return None
    return {
        "email": str(email).strip(),
        "password": str(password),
        "country": str(get_setting("COOKIDOO_COUNTRY") or "de").strip().lower(),
        "language": str(get_setting("COOKIDOO_LANGUAGE") or "de-DE").strip(),
    }


async def _default_factory(cfg: Dict[str, str]):
    import aiohttp
    from cookidoo_api import Cookidoo, CookidooConfig, get_localization_options

    options = await get_localization_options(country=cfg["country"], language=cfg["language"])
    if not options:
        raise CookidooUnavailable(f"Cookidoo kennt Land/Sprache {cfg['country']}/{cfg['language']} nicht")
    session = aiohttp.ClientSession()
    return Cookidoo(session, cfg=CookidooConfig(localization=options[0], email=cfg["email"], password=cfg["password"]))


def minutes(total_time: Any) -> Optional[int]:
    """Cookidoo liefert Sekunden, mal als Zahl, mal als Text („4200.0“)."""
    try:
        return round(float(total_time) / 60) or None
    except (TypeError, ValueError):
        return None


class CookidooService:
    def __init__(self, factory: Callable[[Dict[str, str]], Awaitable[Any]] = _default_factory):
        self._factory = factory
        self._client = None
        self._cfg: Optional[Dict[str, str]] = None
        self._lock = asyncio.Lock()

    def reset(self) -> None:
        self._client, self._cfg = None, None

    @property
    def configured(self) -> bool:
        return config() is not None

    async def _login(self, cfg: Dict[str, str]):
        old = self._client
        client = await self._factory(cfg)
        await client.login()
        self._client, self._cfg = client, cfg
        session = getattr(old, "_session", None)  # aiohttp-Sitzung der alten Anmeldung schließen
        if old is not None and old is not client and session is not None:
            try:
                await session.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Alte Cookidoo-Sitzung nicht geschlossen: %s", exc)
        return client

    async def call(self, fn: Callable[[Any], Awaitable[Any]]) -> Any:
        cfg = config()
        if cfg is None:
            raise CookidooUnavailable("Cookidoo ist nicht eingerichtet")
        if not plugin_active():
            raise CookidooUnavailable("Cookidoo ist deaktiviert")
        try:
            async with self._lock:
                client = self._client if self._client is not None and self._cfg == cfg else await self._login(cfg)
            try:
                return await fn(client)
            except AUTH_ERRORS:
                async with self._lock:
                    client = await self._login(cfg)
                return await fn(client)
        except CookidooUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 – Cookidoo-Fehler sanft weitergeben
            logger.warning("Cookidoo-Aufruf fehlgeschlagen: %s", exc)
            raise CookidooUnavailable(f"Cookidoo nicht erreichbar: {exc}") from exc

    # ── Bausteine ──────────────────────────────────────────────────────────

    async def search(self, query: str, page: int = 0) -> Dict[str, Any]:
        result = await self.call(lambda c: c.search_recipes(query, page=page or None))
        items = [{"id": r.id, "name": r.name, "image": r.image, "thumbnail": r.thumbnail, "url": r.url}
                 for r in result.recipes]
        return {"items": items, "total": result.total}

    async def plan_between(self, start: date, end: date) -> Dict[str, List[Dict[str, Any]]]:
        """Geplante Rezepte je Tag (ISO-Datum) im Zeitraum, Grenzen eingeschlossen."""
        weeks, day = [], start - timedelta(days=start.weekday())
        while day <= end:
            weeks.append(day)
            day += timedelta(days=7)
        out: Dict[str, List[Dict[str, Any]]] = {}
        for monday in weeks:
            for d in await self.call(lambda c, m=monday: c.get_recipes_in_calendar_week(m)):
                if not (start.isoformat() <= d.id <= end.isoformat()):
                    continue
                out[d.id] = [{
                    "title": r.name, "source": "cookidoo", "cookidoo_id": r.id, "minutes": minutes(r.total_time),
                    "image": r.thumbnail or r.image, "url": r.url,
                } for r in d.recipes]
        return out

    async def add(self, day: date, recipe_id: str) -> None:
        await self.call(lambda c: c.add_recipes_to_calendar(day, [recipe_id]))

    async def remove(self, day: date, recipe_id: str) -> None:
        await self.call(lambda c: c.remove_recipe_from_calendar(day, recipe_id))

    async def recipe(self, recipe_id: str) -> Dict[str, Any]:
        r = await self.call(lambda c: c.get_recipe_details(recipe_id))
        return {
            "id": r.id, "name": r.name, "image": r.image, "url": r.url, "minutes": minutes(r.total_time),
            "servings": r.serving_size, "difficulty": r.difficulty,
            "ingredients": [" ".join(p for p in (i.description, i.name) if p) for i in r.ingredients],
        }

    async def ingredients_to_shopping(self, recipe_ids: List[str]) -> int:
        items = await self.call(lambda c: c.add_ingredient_items_for_recipes(recipe_ids))
        return len(items or [])


cookidoo_service = CookidooService()
