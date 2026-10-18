# Plugins

Everything beyond the core (Today, reminders, own meal plan, notifications, accounts) is a **plugin**. The shipped ones live in `backend/app/plugins/builtin/`:

| Plugin | Capability | Per-person access |
|---|---|---|
| Nextcloud (CalDAV) | tasks, calendar | own Nextcloud account and app password |
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

- **Capabilities** decide which areas the app shows: `tasks`, `calendar`, `shopping`, `meal_source`, `meal_planning`, `documents`, `books`, `media_requests`, `weather`, `push_ntfy`. Several task providers can be active side by side. For the other areas, the first active plugin wins.
- **Settings** are read only through `get_setting(KEY)`: admin entry > core setting > environment. Fields with `secret=True` are stored encrypted and never sent back to the app.
- **Active** means all required settings are set and the id is not in `PLUGINS_DISABLED`. Override `is_configured()` if your plugin works with per-person accounts instead.
- **Fail softly.** Lists from external systems use `{status: ok | unavailable | not_configured, error, items}`. An external system that is down must never break the app.
- **Personal data only with personal access.** If data belongs to a person (documents, tasks, requests), each person connects their own account. There is no shared admin login that reads everyone's data.
- **Roles:** protect write endpoints with `require_min_role(ROLE_CHILD | ROLE_PARTNER | ROLE_ADMIN)` from `app.core.security`. Guests mostly read: see the role table in [security](security.md).
- **Notifications:** call `await notify(user_id, title, body, category=…, data={"route": "/…"})` from `app.services.notify`. Quiet hours and channels are handled for you.
- **Database tables** need an Alembic migration. Prefer a key-value or JSON column in your own table over changing core tables.
- **Tests:** mock the external system (`respx` for httpx), never call real services in tests.

## Install a plugin

Build a small image on top of your Familienhub image (`docker compose build` tags it `familienhub:local`):

```dockerfile
FROM familienhub:local
RUN pip install --no-cache-dir familienhub-plugin-grocy==0.1.0
```

Then point `docker-compose.yml` at that image and restart. The plugin appears under *Plugins & access*, where you enter its settings.

## Share a plugin

- Publish the package on GitHub (and optionally PyPI) as `familienhub-plugin-<name>`, with the topic `familienhub-plugin`.
- In the README, state the capabilities, the settings and what data the plugin reads.
- If it reads personal data, say whose credentials it uses.
- A plugin can only extend the server. If it needs its own screens in the app, open an issue first: app screens are part of the main repository.

A catalogue for one-click installation is on the [roadmap](roadmap.md) as an open idea (plugin and theme store).
