# Familienhub plugin template

A ready-to-copy plugin for [Familienhub](https://github.com/Brottuetchen/familienhub). It has one setting (the address of a service), one secret (a token) and one endpoint that returns `{status, error, items}` and never fails with an error page.

Admins install it by pasting the GitHub link of your repository into **Administration → Plugins & access → Install plugin**. The app reads `familienhub-plugin.json`, shows what the plugin is and needs, asks for the settings and installs it. The full guide is [docs/plugins.md](../../docs/plugins.md).

## Use this template

1. **Copy** this folder into a new GitHub repository (on GitHub: copy the files, or create the repository and push them). The files `familienhub-plugin.json` and `pyproject.toml` must be at the repository root, or in a folder you link to.
2. **Choose a plugin id** (lowercase letters, digits, `_`, 2–31 characters, not used by the hub or a built-in plugin) and replace `example_notes` everywhere:
   - `id` in `familienhub-plugin.json` and `id=` in `plugin.py`,
   - the router prefix in `plugin.py`: `/api/plugins/<id>`,
   - every setting key: it must start with the id in capitals, e.g. `MYSERVICE_URL`,
   - the Python package folder `fh_plugin_example_notes/` (pick a unique name such as `fh_plugin_<id>`), the `entry_point` in the manifest and the entry point in `pyproject.toml`.
3. **Describe your plugin** in `familienhub-plugin.json`: name, description (text, or `{"de": …, "en": …}`), author, license, the hosts it contacts, the capabilities it provides.
4. **Write the plugin** in `plugin.py`. Read settings with `get_setting("KEY")`, call your service with `httpx`, and answer `{status: ok | unavailable | not_configured, error, items}`.
5. **Test it:** `pip install pytest respx httpx fastapi`, then `DATA_DIR=$(mktemp -d) PYTHONPATH=/path/to/familienhub/backend pytest` (`DATA_DIR` keeps the hub code from writing into `/app/data`). The tests mock your service with `respx`.
6. **Publish** the repository on GitHub, then in the app: *Administration → Plugins & access → Install plugin* → paste `https://github.com/<you>/<repo>`.
7. **Update:** push a change and raise `version` in the manifest. The app offers *Check for update* on the installed plugin; it installs exactly the commit that it showed.

Do not commit tokens, passwords or `.env` files. Tests use fake values only.
