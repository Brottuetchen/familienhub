# Plugins

Familienhub is organised in **areas** (tasks, shopping, calendar, meal planning, documents …). Every area takes its data from **sources**, and every source is a plugin:

- **The hub's own sources** (`hub_tasks`, `hub_shopping`, `hub_calendar`) store data in the hub database. They work without any external service and serve an area whenever nothing else does.
- **Connected services** replace or add to them: several task sources run side by side, calendar sources are merged, and the shopping list has one source.
- **Admins choose** under *Administration → Sources per area* (or in the setup wizard). This is stored as `TASKS_SOURCES`, `CALENDAR_SOURCES` and `SHOPPING_SOURCE`. Without a choice, all active sources are used, or the first active one for single-source areas.
- **Recipe ingredients** (same screen, shopping area; `SHOPPING_RECIPE_INGREDIENTS`): `merge` (default) puts the ingredients of Cookidoo, Mealie and recipe-book recipes onto our shopping list and merges equal ingredients; `source` leaves Cookidoo/Mealie ingredients in the source's own list (Cookidoo's shopping list, where ticking off also counts in Cookidoo; Mealie's recipe import). Recipe-book recipes always go onto our list.

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

More plugins come from GitHub: admins install them with a link, see [Install a plugin from GitHub](#install-a-plugin-from-github). To write one, see [Write a plugin](#write-a-plugin) and the ready-to-copy [plugin template](../examples/plugin-template/).

## Install a plugin from GitHub

Admins install, update and remove plugins in the app, no Docker image and no restart needed. It works like installing a theme: you paste a link.

1. **More → Administration → Plugins & access → Install plugin.**
2. **Paste the link** of the plugin's repository, e.g. `https://github.com/<owner>/<repo>`. Links to a branch, tag or folder work too: `https://github.com/<owner>/<repo>/tree/<branch>/<folder>`. Only `github.com` is accepted.
3. **Review.** The hub resolves the link to one exact commit and shows the plugin's name, author, version, repository and commit, description, **the external hosts it contacts** and what it provides. Nothing has been installed yet. Plugins run inside the hub with full access, so only install plugins from sources you know and trust; you confirm that before you can continue.
4. **Fill in the settings.** The form is generated from the plugin's manifest: password fields for secrets, and checks for required values, addresses and numbers. Values you enter are stored encrypted where they are secret and are never shown again.
5. **Install.** It takes a little while (the plugin's dependencies are installed). Then the plugin is active at once, without a restart. If something goes wrong (unreachable GitHub, invalid manifest, a plugin that does not load), nothing is left behind and the app tells you why.

**Update.** *Plugins & access →* the plugin's menu *→ Check for update* checks the same link again. The app shows the old and the new version and prefills the form with the current values; only settings that are new and required need input. Existing values are kept (secrets too: leave the field empty). If the new version does not load, the old one keeps running.

**Remove.** The plugin's menu *→ Remove* switches the plugin off and removes its routes at once, deletes its files and its stored settings (including secrets). Only if a plugin shipped native extension modules (compiled code), Python keeps them in memory until the next restart, and the app says so: `docker compose restart familienhub`.

**What the installer does**, step by step:

1. `POST /api/plugins/inspect`: resolves the link to a commit SHA (GitHub API), reads `familienhub-plugin.json` at exactly that commit and validates it strictly.
2. `POST /api/plugins/install`: reads the manifest at that commit again, validates your settings, downloads the source tarball of **that commit** (max. 10 MB), unpacks it safely into `<DATA_DIR>/plugins/src/<id>-<commit>` (no links, devices, absolute or `..` paths; max. 2000 files, 50 MB unpacked), runs `pip install --target <DATA_DIR>/plugins/site/<id>` for the package, stores the settings (secrets encrypted), records the installation (repository, commit, version, manifest, who and when) and loads the plugin into the running hub.
3. At start-up the hub loads every recorded plugin again. A plugin that fails (files missing, import error) is logged and skipped; the hub keeps running and the plugin list shows the error. Installing the same commit again repairs it.

The installer only talks to `api.github.com`, `raw.githubusercontent.com` and `codeload.github.com` (https, no redirects, timeouts, size limits). The dependency step (`pip`) contacts the Python package index (`pypi.org`, `files.pythonhosted.org`) if the plugin has dependencies or a build backend that is not installed yet.

### For operators

| | |
|---|---|
| `PLUGIN_INSTALL_ENABLED` | `true` by default. `false` hides the install button and refuses inspect and install (HTTP 403). Plugins that are already installed keep loading and can still be removed. |
| `PLUGIN_PIP_ARGS` | Extra arguments for `pip`, e.g. `--index-url https://pypi.example.org/simple` for a mirror, or `--no-index --find-links /wheels` for a hub without internet access. |
| `DATA_DIR` (`/app/data`) | **Must be a persistent volume.** Installed plugins live in `<DATA_DIR>/plugins`, next to the generated `SECRET_KEY`. The default `docker-compose.yml` has it (`familienhub_data`). A compose file without that volume loses the plugin files each time the container is re-created; the database record stays, the plugin shows an error, and installing the same commit again repairs it. The container user (UID 10001) must be able to write there. The install screen warns if the data folder does not look like a volume of its own. |
| Network | The hub needs outbound https to the three GitHub hosts (and to the package index for the dependency step). |
| Reverse proxy | Installing can take a minute or more. Allow long requests for `/api/` (e.g. nginx `proxy_read_timeout 300s`; Nginx Proxy Manager: *Advanced* tab). If the connection is cut, the install may still finish: check the plugin list. |
| GitHub rate limit | Anonymous GitHub API access is limited to 60 requests per hour and IP. Inspect and install use one or two requests each. |
| Backup | Back up the data volume. It holds the plugin code and the key that decrypts stored secrets. |
| Log | Every install, update and removal is written to the log (*Administration → Log*, and the container log) with plugin, version, short commit and person. |

### Security notes

- A plugin is Python code that runs **inside the hub process**: it can read the database, all stored credentials and everything the hub can reach. The installer is **not a sandbox**. Its checks (admin only, one pinned commit, allow-listed hosts, safe unpacking, namespaced and authenticated routes, a settings namespace) prevent accidents and sloppy plugins; they cannot make untrusted code safe.
- Only admins can install, update or remove. Nothing updates by itself: an update is always an explicit action on a commit you have seen.
- The commit is pinned: what you reviewed is what is installed, even if the author pushes new code a minute later. The author's later commits never run unless an admin updates.
- Build scripts of a plugin (`setup.py`, a build backend) run during installation. They get a minimal environment without the hub's `SECRET_KEY`, database URL or other settings.
- The manifest's `hosts` list is information for the review; the hub does not enforce it.

## Write a plugin

A plugin is a small Python project in a GitHub repository. It has a manifest (`familienhub-plugin.json`) that tells the hub what the plugin is and which settings it needs, and a Python package with a `Plugin` class. Admins install it with a link, see above.

**Quick start:** copy [`examples/plugin-template/`](../examples/plugin-template/) into a new repository and follow its README. The template is a working plugin with one setting, one secret, one endpoint and tests.

### Repository layout

```
my-plugin/                        the repository (or the folder you link to)
├── familienhub-plugin.json       the manifest, in the repository root or in the linked folder
├── pyproject.toml                the Python project: name, version, dependencies, entry point
├── fh_plugin_myservice/          the package (unique name, see below)
│   ├── __init__.py
│   └── plugin.py                 the Plugin class and its router
├── tests/test_plugin.py          tests with respx
└── README.md
```

The `package` field of the manifest points to the folder with `pyproject.toml` (default: the folder of the manifest). One repository can hold several plugins in several folders, each with its own manifest.

**Package name.** Choose a unique top-level package such as `fh_plugin_<id>`. The installer refuses names that are already used by the hub, the standard library or another installed plugin.

### The manifest

`familienhub-plugin.json`, at most 64 KB. It is validated strictly: wrong types, too long values and **unknown fields are rejected**, so a typo shows up at once.

```json
{
  "id": "grocy",
  "name": {"de": "Grocy", "en": "Grocy"},
  "version": "0.1.0",
  "description": {"de": "Vorräte und Einkauf aus Grocy", "en": "Stock and shopping from Grocy"},
  "author": "Your name",
  "homepage": "https://github.com/you/familienhub-plugin-grocy",
  "license": "MIT",
  "min_hub_version": "1.0.0",
  "package": ".",
  "entry_point": "fh_plugin_grocy.plugin:GrocyPlugin",
  "settings": [
    {"key": "GROCY_URL", "label": {"de": "Adresse", "en": "Address"}, "type": "url", "required": true,
     "example": "http://grocy.lan:9283"},
    {"key": "GROCY_API_KEY", "label": "API key", "type": "password", "required": true}
  ],
  "hosts": ["grocy.lan"],
  "capabilities": ["shopping"]
}
```

| Field | | Meaning |
|---|---|---|
| `id` | required | Unique id: `^[a-z][a-z0-9_]{1,30}$`. It is also the prefix of all settings keys and of the plugin's routes. It must not be the id (or start with the id and `_`) of a built-in plugin, a capability name, or the first word of a core setting (`app`, `database`, `oidc`, `vapid`, `secret`, `hub`, `tasks`, `weather` …). Pick something distinctive. |
| `name` | required | Text, or `{"de": …, "en": …}`; at most 60 characters. |
| `version` | required | `1.2.0`, `0.3.1-beta`: starts with a digit, at most 32 characters. Raise it with every release. |
| `description` | required | Text or `{"de": …, "en": …}`; at most 500 characters. Shown in the review and the plugin list. |
| `author` | required | At most 100 characters. |
| `homepage` | optional | An `https://` address. |
| `license` | optional | e.g. an [SPDX](https://spdx.org/licenses/) id such as `MIT`. |
| `min_hub_version` | optional | The oldest hub version that works, e.g. `1.0.0`. Compared by its numbers; if the hub's own version is not a number (e.g. `dev`), the check is skipped. Installing on an older hub is refused. |
| `package` | optional | Folder with the `pyproject.toml` (or `setup.py`), relative to the manifest, default `.`. No `..`, no absolute path. |
| `entry_point` | required | `module:Class`, e.g. `fh_plugin_grocy.plugin:GrocyPlugin`. The class, or a function that returns a `Plugin`. |
| `settings` | optional | The settings the admin fills in, at most 20, see below. |
| `hosts` | optional | Host names the plugin contacts (`grocy.lan`, `api.example.org:8443`), without `https://`. Shown to the admin before installing. **Information only, the hub does not enforce it**, so keep it honest. |
| `capabilities` | optional | What the plugin provides, from the list in [Rules](#rules). The class may declare no capability that is not listed here. |

**Settings** are the form the admin sees. Each entry:

| Field | | Meaning |
|---|---|---|
| `key` | required | `^[A-Z][A-Z0-9_]{2,60}$` and **must start with the id in capitals plus `_`** (`GROCY_URL` for id `grocy`). That is how a plugin can never touch a core setting or another plugin's. |
| `label` | required | Text or `{"de": …, "en": …}`; at most 60 characters. |
| `help` | optional | Short hint under the field; text or `{"de": …, "en": …}`; at most 300 characters. |
| `type` | optional | `text` (default), `url` (must start with `http://` or `https://`), `password` (hidden input, always a secret), `number`, `bool` (a switch). |
| `secret` | optional | `true` stores the value encrypted and never shows it again. `type: password` implies it. A secret cannot have a `default`. |
| `required` | optional | Default `true`. A plugin is only *active* when all required settings have a value. A `bool` is never required. |
| `default` | optional | Prefilled and used when the admin leaves the field empty. A string, number or boolean that fits the `type`. |
| `example` | optional | Shown as "e.g. …" below the field. |

Values reach your code as strings through `get_setting("GROCY_URL")`: a `bool` is `"true"` or `"false"`, a `number` is text such as `"5"` or `"2.5"`, convert it yourself.

### The plugin class

```python
# fh_plugin_grocy/plugin.py
import httpx
from fastapi import APIRouter, Depends, Request

from app.core.i18n import request_language
from app.core.logging_config import get_logger
from app.core.security import get_current_user
from app.plugins import Plugin, Setting, get_setting

logger = get_logger("plugin.grocy")
router = APIRouter(prefix="/api/plugins/grocy", tags=["grocy"])   # always /api/plugins/<id>


@router.get("/stock")
async def stock(request: Request, user=Depends(get_current_user)):
    base = str(get_setting("GROCY_URL") or "").rstrip("/")
    if not base:
        return {"status": "not_configured", "error": None, "items": []}
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.get(f"{base}/api/stock", headers={"GROCY-API-KEY": get_setting("GROCY_API_KEY") or ""})
        r.raise_for_status()
        items = [{"name": row["product"]["name"]} for row in r.json()]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        logger.warning("Grocy not reachable")                      # never log tokens or addresses
        return {"status": "unavailable", "error": {"de": "Grocy ist nicht erreichbar", "en": "Grocy is not reachable"}[request_language(request)], "items": []}
    return {"status": "ok", "error": None, "items": items}


class GrocyPlugin(Plugin):
    def __init__(self):
        super().__init__(
            id="grocy",                                   # same as the manifest
            name="Grocy", version="0.1.0", description="Stock and shopping from Grocy",
            capabilities=frozenset({"shopping"}),         # subset of the manifest's capabilities
            settings=(Setting("GROCY_URL", "Address"),    # subset of the manifest's settings
                      Setting("GROCY_API_KEY", "API key", secret=True)),
        )

    def routers(self):
        return [router]
```

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "familienhub-plugin-grocy"
version = "0.1.0"
dependencies = []        # only what the hub does not ship

[project.entry-points."familienhub.plugins"]     # also makes the plugin installable in a custom image
grocy = "fh_plugin_grocy.plugin:GrocyPlugin"

[tool.setuptools.packages.find]
include = ["fh_plugin_grocy*"]
```

**What the hub checks when it loads your plugin.** Anything that does not fit is refused at install time with a message, and nothing stays behind:

- `Plugin.id` equals the manifest's `id`.
- Every `Setting` key the class declares is listed in the manifest; every capability the class declares is listed in the manifest. The manifest wins: name, version, description and settings (with `secret` and `required`) shown in the app come from it, not from the class.
- **Every route lives below `/api/plugins/<id>/`.** Core routes can never be shadowed.
- **Every route requires a logged-in user**, whether or not you add `Depends(get_current_user)` (do add it, you need the user). Unauthenticated webhooks are not possible in installed plugins. Check roles yourself (below).
- The module must come from your package, with a name nobody else uses.

**Dependencies.** The hub ships `fastapi`, `starlette`, `httpx`, `pydantic`, `sqlalchemy`, `cryptography` and others (`backend/requirements.txt`). Do **not** list these: the hub's versions are always used, a second copy would only be ignored. List everything else in `dependencies`; it is installed from the Python package index into the plugin's own folder. The build backend (`setuptools` in the template) is fetched from the index too. Prefer pure-Python packages; compiled ones work, but removing or updating such a plugin then needs a restart.

### Rules

- **Capabilities** decide which areas the app shows: `tasks`, `calendar`, `shopping`, `meal_source`, `meal_planning`, `documents`, `books`, `media_requests`, `weather`, `push_ntfy`. Recipe sources (`meal_planning`) appear in the app as "Recipe from <name>" through `/api/recipe-sources` (`backend/app/routers/recipe_sources.py`); a new source adds its service there. Several task providers can be active side by side. For the other areas, the first active plugin wins. A plugin without capabilities only offers its own endpoints.
- **Settings** are read only through `get_setting(KEY)`: admin entry > core setting > environment. Fields with `secret` are stored encrypted (Fernet, key derived from the hub's `SECRET_KEY`) and never sent back to the app: the app only learns *set* or *not set*.
- **Active** means all required settings are set and the id is not in `PLUGINS_DISABLED`. Override `is_configured()` if your plugin works with per-person accounts instead.
- **Fail softly.** Lists from external systems use `{status: ok | unavailable | not_configured, error, items}`. An external system that is down must never break the app: catch `httpx.HTTPError` and parse errors, set a timeout (6 s is a good default), return `unavailable` plus a short message. An exception in your code becomes an error page for the user, so catch what you can foresee.
- **Never log secrets, tokens, passwords or full addresses with credentials.** The admin log shows what you log at warning level or above.
- **Personal data only with personal access.** If data belongs to a person (documents, tasks, requests), each person connects their own account. There is no shared admin login that reads everyone's data.
- **Roles:** protect write endpoints with `require_min_role(ROLE_PARTNER)` (`ROLE_CHILD`, `ROLE_PARTNER`, `ROLE_ADMIN` from `app.models.user`; `require_min_role` from `app.core.security`) as a dependency: `Depends(require_min_role(ROLE_PARTNER))`. Guests mostly read: see the role table in [security](security.md).
- **Notifications:** call `await notify(user_id, title, body, category=…, data={"route": "/…"})` from `app.services.notify`. Quiet hours and channels are handled for you, and the text is translated for the recipient when it is a known hub text; texts from your plugin stay as you write them, so write them in the language you want or pick one per recipient yourself.
- **Texts in two languages.** In the manifest, `name`, `description`, `label` and `help` can be `{"de": …, "en": …}`; the app shows the text in its language (the admin's choice, else the phone's), and falls back to German, then English. For texts your endpoints return (`error` and the like), use `request_language(request)` from `app.core.i18n` (it returns `"de"` or `"en"` from `X-App-Language` / `Accept-Language`) and pick the text yourself, as in the example above. Texts that are only a single string are shown as they are in every language.
- **Database tables:** installed plugins cannot ship migrations and must not create tables in the hub's database themselves. Keep state in the service you connect to, or in settings. If you need tables, open an issue; built-in plugins use Alembic migrations in the main repository.
- **App screens:** a plugin can only extend the server. If it needs its own screens in the app, open an issue first: app screens are part of the main repository.

### Test it

Mock the external system with `respx`, never call real services in tests. The template's tests show the pattern: the plugin's router is mounted on a small FastAPI app, the login is replaced (`app.dependency_overrides[get_current_user]`), and the service is simulated:

```python
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GROCY_URL", "https://grocy.example.org")     # get_setting also reads the environment
    app = FastAPI()
    for router in GrocyPlugin().routers():
        app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: object()
    return TestClient(app)


def test_stock_down(client):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()                  # the test client itself
        http.get("https://grocy.example.org/api/stock").mock(return_value=httpx.Response(500))
        body = client.get("/api/plugins/grocy/stock").json()
    assert body["status"] == "unavailable" and body["items"] == []
```

Run them with the hub's backend on the path (a checkout of this repository): `DATA_DIR=$(mktemp -d) PYTHONPATH=/path/to/familienhub/backend pytest`. Also test that the manifest is valid: `from app.plugins.manifest import validate_manifest` accepts it (the template has that test).

Try it for real before you publish: push to a branch of your repository and install `https://github.com/<you>/<repo>/tree/<branch>` on a test hub. *Check for update* picks up further commits of that branch.

### Checklist before you publish

- The manifest validates and every field is filled in honestly (`hosts`, `capabilities`, `license`).
- Setting keys start with `<ID>_`, secrets use `type: password`.
- Every endpoint answers `{status, error, items}` (or a documented shape) and survives the service being down, slow or answering nonsense.
- Write endpoints check the role.
- No token, password or private address in the repository, the tests or the logs.
- The README says what the plugin reads and writes, whose credentials it uses and which hosts it contacts.
- Tests pass; the version is raised.

## Tasks: where a task lands

`POST /api/tasks?provider=auto` (what the app sends) routes by recipient; an explicit `provider=` keeps the old behaviour for older clients.

- **Preferred task place** per person: their explicit choice (profile, `PUT /api/tasks/me/place`), else derived from the connected accounts in this order: CalDAV (Nextcloud) account, Habitica account (native writes released), the hub itself. `GET /api/tasks/me/place` returns `place`, `explicit`, `auto` and the options. A stale choice (account removed) is ignored.
- **Task for another person** is written with the **recipient's own connector and stored credentials**, never the creator's account. If she has no usable account for her place, or the provider errors, the task is stored in the hub (`placed.fallback: true`). A Habitica error leaves that account's write lock in place (see the Habitica contract), the task is then kept in the hub; a duplicate is possible if Habitica did create it.
- **Family tasks and household rotation** go to the family list of the first source of the area that can hold one (`family_tasks=True` on the plugin; sources per area apply), else the hub.
- **Own tasks** go to the creator's preferred place. Native Habitica types (habit, daily, reward) are still created in the Habitica account screen.
- **"Von mir"** reads the `task_assignments` records (creator, recipient, provider, remote id, title, status). Open/done is read on each request through the recipient's connector and fails soft (`stale: true`, last known status). Tasks deleted by the recipient drop out. The creator never sees anything else from the recipient's lists. Hub tasks are listed natively, other providers appear as read-only items (`provider: "assigned"`, `via`).
- Providers without a creator field (Habitica) get a "Von <name>" line in the notes.

## Install in a custom Docker image

The older route still works, for plugins that are not on GitHub or hubs without internet access: build a small image on top of the Familienhub image: `ghcr.io/brottuetchen/familienhub:latest`, or `familienhub:local` if you build from source (`docker compose -f docker-compose.yml -f docker-compose.dev.yml build` tags it that way):

```dockerfile
FROM ghcr.io/brottuetchen/familienhub:latest
RUN pip install --no-cache-dir familienhub-plugin-grocy==0.1.0
```

Then point `docker-compose.yml` at that image and restart. The package must register itself in the entry-point group `familienhub.plugins` (see the `pyproject.toml` above); the hub loads every entry point at start-up. Plugins loaded this way are trusted as part of the image: the manifest and the route rules of the installer do not apply, and their routes may live anywhere. They appear under *Plugins & access* like any other plugin and are managed in the image, not in the app.

## Share a plugin

- Publish the repository on GitHub with the topic `familienhub-plugin`. Users install it with the repository link. Name the repository `familienhub-plugin-<name>`.
- Tag releases and say in the README which commit or branch to install; the app installs exactly the commit behind the link (the default branch if the link has no `/tree/…`).
- In the README, state the capabilities, the settings, the hosts it contacts and what data the plugin reads or writes.
- If it reads personal data, say whose credentials it uses.
- Keep `hosts` and `capabilities` in the manifest complete: admins decide on them.
- A plugin can only extend the server. If it needs its own screens in the app, open an issue first: app screens are part of the main repository.

A catalogue for one-click installation is on the [roadmap](roadmap.md) as an open idea (plugin and theme store).
