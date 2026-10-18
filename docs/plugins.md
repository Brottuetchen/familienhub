# Plugins

Familienhub is organised in **areas** (tasks, shopping, calendar, meal planning, documents …). Every area takes its data from **sources**, and every source is a plugin:

- **The hub's own sources** (`hub_tasks`, `hub_shopping`, `hub_calendar`) store data in the hub database. They work without any external service and serve an area whenever nothing else does.
- **Connected services** replace or add to them: several task sources run side by side, calendar sources are merged, and the shopping list has one source.
- **Admins choose** under *Administration → Sources per area* (or in the setup wizard). This is stored as `TASKS_SOURCES`, `CALENDAR_SOURCES` and `SHOPPING_SOURCE`. Without a choice, all active sources are used, or the first active one for single-source areas.

The shipped plugins live in `backend/app/plugins/builtin/`:

| Plugin | Capability | Per-person access |
|---|---|---|
| Tasks / shopping list / family calendar in the hub | tasks, shopping, calendar | – (stored in the hub) |
| CalDAV (Nextcloud, iCloud, Radicale …) | tasks, calendar | own CalDAV account and app password |
| Mealie | meal_planning, meal_source, shopping: search and plan recipes, household meal plan in the week, shopping list | – (household API token) |
| Calendar subscriptions (ICS) | calendar (read-only): school holidays, waste collection, clubs | – (admin adds calendars as a list, each link checked before saving) |
| Habitica | tasks (dailies, habits, rewards) | own Habitica user ID and API key |
| Home Assistant | shopping list, house tiles, Cookidoo meal plan (read) | – (shared, admin chooses entities) |
| Cookidoo | search recipes, plan them, ingredients to the list | – |
| Paperless-ngx | documents, deadlines as reminders | own API token |
| Shelfarr | request e-books and audiobooks | mapped by username |
| Seerr | request movies and shows | own Seerr user (via Jellyfin login) |
| ntfy | push channel, see [ntfy](ntfy.md) | own secret topic |
| Weather (Open-Meteo) | weather on Today | – |

Admins switch plugins on and off and enter credentials under **More → Administration → Plugins & access**. The change applies without a restart, secrets are stored encrypted, and *Test connection* checks reachability. Alternatively, set the same keys as environment variables in `.env`.

## Write a plugin

A plugin is a normal Python package that exposes a `Plugin` object through an entry point.

```python
# familienhub_grocy/plugin.py
from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.plugins import Plugin, Setting, get_setting

router = APIRouter(prefix="/api/grocy", tags=["grocy"])


@router.get("/stock")
async def stock(user=Depends(get_current_user)):
    if not get_setting("GROCY_URL"):
        return {"status": "not_configured", "error": None, "items": []}
    ...  # call Grocy; on failure return {"status": "unavailable", "error": "…", "items": []}


class GrocyPlugin(Plugin):
    def __init__(self):
        super().__init__(
            id="grocy",                                  # unique, lowercase
            name="Grocy",
            version="0.1.0",
            description="Stock and shopping from Grocy",
            capabilities=frozenset({"shopping"}),
            settings=(
                Setting("GROCY_URL", "Address (reachable from the hub)"),
                Setting("GROCY_API_KEY", "API key", secret=True),
            ),
        )

    def routers(self):
        return [router]
```

```toml
# pyproject.toml
[project]
name = "familienhub-plugin-grocy"
version = "0.1.0"
dependencies = ["httpx"]

[project.entry-points."familienhub.plugins"]
grocy = "familienhub_grocy.plugin:GrocyPlugin"
```

At start-up the hub loads every entry point in the group `familienhub.plugins` (`backend/app/plugins/registry.py`). A plugin that fails to load is skipped and logged; the hub keeps running.

### Rules

- **Capabilities** decide which areas the app shows: `tasks`, `calendar`, `shopping`, `meal_source`, `meal_planning`, `documents`, `books`, `media_requests`, `weather`, `push_ntfy`. Recipe sources (`meal_planning`) appear in the app as "Recipe from <name>" through `/api/recipe-sources` (`backend/app/routers/recipe_sources.py`); a new source adds its service there. Several task providers can be active side by side. For the other areas, the first active plugin wins.
- **Settings** are read only through `get_setting(KEY)`: admin entry > core setting > environment. Fields with `secret=True` are stored encrypted and never sent back to the app.
- **Active** means all required settings are set and the id is not in `PLUGINS_DISABLED`. Override `is_configured()` if your plugin works with per-person accounts instead.
- **Fail softly.** Lists from external systems use `{status: ok | unavailable | not_configured, error, items}`. An external system that is down must never break the app.
- **Personal data only with personal access.** If data belongs to a person (documents, tasks, requests), each person connects their own account. There is no shared admin login that reads everyone's data.
- **Roles:** protect write endpoints with `require_min_role(ROLE_CHILD | ROLE_PARTNER | ROLE_ADMIN)` from `app.core.security`. Guests mostly read: see the role table in [security](security.md).
- **Notifications:** call `await notify(user_id, title, body, category=…, data={"route": "/…"})` from `app.services.notify`. Quiet hours and channels are handled for you.
- **Database tables** need an Alembic migration. Prefer a key-value or JSON column in your own table over changing core tables.
- **Tests:** mock the external system (`respx` for httpx), never call real services in tests.

## Tasks: where a task lands

`POST /api/tasks?provider=auto` (what the app sends) routes by recipient; an explicit `provider=` keeps the old behaviour for older clients.

- **Preferred task place** per person: their explicit choice (profile, `PUT /api/tasks/me/place`), else derived from the connected accounts in this order: CalDAV (Nextcloud) account, Habitica account (native writes released), the hub itself. `GET /api/tasks/me/place` returns `place`, `explicit`, `auto` and the options. A stale choice (account removed) is ignored.
- **Task for another person** is written with the **recipient's own connector and stored credentials**, never the creator's account. If she has no usable account for her place, or the provider errors, the task is stored in the hub (`placed.fallback: true`). A Habitica error leaves that account's write lock in place (see the Habitica contract), the task is then kept in the hub; a duplicate is possible if Habitica did create it.
- **Family tasks and household rotation** go to the family list of the first source of the area that can hold one (`family_tasks=True` on the plugin; sources per area apply), else the hub.
- **Own tasks** go to the creator's preferred place. Native Habitica types (habit, daily, reward) are still created in the Habitica account screen.
- **"Von mir"** reads the `task_assignments` records (creator, recipient, provider, remote id, title, status). Open/done is read on each request through the recipient's connector and fails soft (`stale: true`, last known status). Tasks deleted by the recipient drop out. The creator never sees anything else from the recipient's lists. Hub tasks are listed natively, other providers appear as read-only items (`provider: "assigned"`, `via`).
- Providers without a creator field (Habitica) get a "Von <name>" line in the notes.

## Install a plugin

Build a small image on top of the Familienhub image: `ghcr.io/brottuetchen/familienhub:latest`, or `familienhub:local` if you build from source (`docker compose -f docker-compose.yml -f docker-compose.dev.yml build` tags it that way):

```dockerfile
FROM ghcr.io/brottuetchen/familienhub:latest
RUN pip install --no-cache-dir familienhub-plugin-grocy==0.1.0
```

Then point `docker-compose.yml` at that image and restart. The plugin appears under *Plugins & access*, where you enter its settings.

## Share a plugin

- Publish the package on GitHub (and optionally PyPI) as `familienhub-plugin-<name>`, with the topic `familienhub-plugin`.
- In the README, state the capabilities, the settings and what data the plugin reads.
- If it reads personal data, say whose credentials it uses.
- A plugin can only extend the server. If it needs its own screens in the app, open an issue first: app screens are part of the main repository.

A catalogue for one-click installation is on the [roadmap](roadmap.md) as an open idea (plugin and theme store).
