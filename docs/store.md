# Plugin and theme store

Admins install plugins and themes with one click under **Administration → Store**. The Store is also linked from **Plugins & access**. Entries come from a central index that the maintainers review, plus any extra GitHub repositories an admin adds as their own sources.

The store builds on the link installers described in [plugins.md](plugins.md) and [themes.md](themes.md). Installing from the store runs the same checks. The difference is that the commit is pinned by the index and is not resolved from a branch.

## How it works

1. The hub fetches `index.json` from the official store and from every custom source, and caches it for `STORE_CACHE_SECONDS` (300 s by default). Pull down to refresh, which skips the cache.
2. The app shows each entry as a card with its screenshot, name, short description, author, type and a **Reviewed** or **Not reviewed** badge. You can filter by type (All, Themes, Plugins) and search by name, description, author or tag.
3. The detail page shows:
   - a screenshot carousel and the long description,
   - the version and pinned commit, and a link to the repository,
   - for a plugin, its capabilities, the hosts it connects to and the settings it asks for, read from its manifest at the pinned commit,
   - for a theme, its colours.
4. **Install** or **Update** installs exactly the commit the index pins:
   - A plugin goes through the usual review screen, with the full-access warning and the trust checkbox, and then the settings form.
   - A theme is validated and stored like a theme installed from a link.
5. When the index pins a different commit than the one installed, the entry shows **Update available**. The hub never updates anything by itself.

## Official index

The official index is the `index.json` on the `main` branch of [`brottuetchen/familienhub-store`](https://github.com/brottuetchen/familienhub-store):

```
STORE_INDEX_URL=https://raw.githubusercontent.com/brottuetchen/familienhub-store/main/index.json
```

That value is the default. An operator can point it at their own index (an https URL), or set it to an empty value to switch the official source off. Only entries the maintainers reviewed are in the official index. A review means that a pull request to the store repository was merged.

### Submitting an entry

1. Publish your plugin or theme in a public GitHub repository and pick the exact commit you want to ship.
2. Open a pull request to the store repository that:
   - adds your entry to `index.json`,
   - adds your screenshots under `screenshots/<entry-id>/` (see [Screenshots](#screenshots)).
3. The maintainers check the code at that commit. For a plugin they read the code, look at what the manifest declares and check which hosts it contacts. Then they merge.
4. For an update, open a pull request that changes `sha` and `version`. The maintainers review the difference between the old and the new commit.

## Custom sources

An admin can add their own GitHub repository as an extra source under **Store → Sources**:

- **Address:** `https://github.com/<owner>/<repo>` (default branch) or `https://github.com/<owner>/<repo>/tree/<branch>`.
- **Format:** the repository holds an `index.json` in its root, in the same format as the official one, with its screenshots next to it.
- **Warnings:** entries from custom sources carry a **Not reviewed** badge. The app shows a warning when the source is added, which must be acknowledged, and again before each install from it. The server enforces both: `acknowledge` and `acknowledge_unverified`.
- **Limit:** at most 10 custom sources. Removing a source does not remove what was installed from it.

## Index format

```json
{
  "version": 1,
  "name": "Familienhub store",
  "entries": [
    {
      "type": "theme",
      "id": "nordic-fjord",
      "name": "Nordic Fjord",
      "summary": {"de": "Kühle Blautöne", "en": "Cool shades of blue"},
      "description": {"de": "…", "en": "…"},
      "author": "Jane Doe",
      "repo": "https://github.com/jane/familienhub-themes",
      "path": "nordic-fjord",
      "sha": "0123456789abcdef0123456789abcdef01234567",
      "version": "1.0.0",
      "screenshots": ["screenshots/nordic-fjord/1.png", "screenshots/nordic-fjord/2.png"],
      "tags": ["blue", "dark"],
      "min_hub_version": "0.1.0"
    }
  ]
}
```

A complete example that the test suite validates is in [`examples/store/index.json`](../examples/store/index.json).

| Field | Required | Rules |
|---|---|---|
| `version` (top level) | yes | must be `1`; any other value rejects the whole index |
| `name` (top level) | no | name of the source, up to 80 characters |
| `type` | yes | `theme` or `plugin` |
| `id` | yes | plugin: the manifest id (`^[a-z][a-z0-9_]{1,30}$`, not reserved), and it must equal the `id` in `familienhub-plugin.json`; theme: `^[a-z][a-z0-9_-]{1,40}$` |
| `name` | yes | string or `{"de", "en"}`, up to 60 characters |
| `summary` | yes | string or `{"de", "en"}`, up to 140 characters (shown on the card) |
| `description` | no | string or `{"de", "en"}`, up to 2000 characters (detail page; falls back to `summary`) |
| `author` | yes | up to 60 characters |
| `repo` | yes | `https://github.com/<owner>/<repo>`, without `/tree/…` |
| `path` | no | folder inside the repository: the plugin folder holding `familienhub-plugin.json`, or the folder holding `theme.json` |
| `sha` | yes | full 40-character lowercase commit id; exactly this commit is installed |
| `version` | yes | version shown in the app, e.g. `1.2.0` |
| `screenshots` | no | at most 8; `.png`, `.jpg`/`.jpeg` or `.webp` |
| `tags` | no | at most 8 strings of up to 24 characters, used by the search |
| `min_hub_version` | no | the entry cannot be installed on older hubs |

Unknown fields are not allowed. If an entry is invalid, only that entry is skipped. The reason is logged and listed on the source (`skipped`), and the other entries stay available. Texts in `de` and `en` fall back to the other language.

### Screenshots

Screenshots live in the store repository itself, one folder per entry:

```
index.json
screenshots/
  nordic-fjord/
    1.png
    2.png
  grocy_sync/
    1.png
```

`index.json` references them by **relative path** (`screenshots/<entry-id>/1.png`). The path is resolved against the folder `index.json` was fetched from. The same applies to custom sources. Absolute URLs are only accepted on `raw.githubusercontent.com`, or on the host of the operator's own `STORE_INDEX_URL`.

The hub fetches screenshots and serves them to the app. App clients never contact GitHub, and the web app's CSP stays untouched. The proxy has these limits:

- only images listed in the current index are served,
- PNG, JPEG or WebP only, checked by their content (SVG is refused),
- at most 2 MB per image,
- cached in memory for `STORE_CACHE_SECONDS`.

## Security model

- **No signatures.** Trust comes from two things:
  - The official index lists only reviewed entries.
  - Every entry pins an exact commit. The hub installs only that commit, never the branch head. If the index changes between review and install, the install is refused (`409`) and the admin reloads.
- **What is installed is what the admin saw.** The app sends back the commit it showed, and the server installs only if that commit still equals the one in the index.
- **Plugins still run with full access.** A reviewed plugin is not sandboxed. The full-access warning and trust checkbox from the link installer appear for every plugin install from the store.
- **Limited network access.** The hub contacts only `raw.githubusercontent.com` for indexes, themes and screenshots (plus the host of a custom `STORE_INDEX_URL`), and `codeload.github.com` for plugin source tarballs. Every request uses https, follows no redirects, and has timeouts and size limits: 1 MB for an index, 64 KB for a theme, 2 MB for a screenshot, and 10 MB for a plugin tarball.
- **Admins only.** All store endpoints require the admin role. `PLUGIN_INSTALL_ENABLED=false` also switches off plugin installs from the store. Themes stay installable because they contain no code.
- **Logged.** Every install and every added or removed source is logged as a warning, so it shows up under **Administration → Log**.
- **Known limitation: fork commits.** GitHub also serves a commit that only exists in a fork of a repository under the original repository's address. Reviewers must check that the pinned commit is on a branch of the listed repository.

## API (admin only)

| Method and path | Purpose |
|---|---|
| `GET /api/admin/store[?refresh=true]` | merged entries with `source`, `verified` and `state` (`available`, `installed`, `update`, `conflict`), plus the status of each source (`ok`, `unreachable`, `invalid`, `stale`) |
| `POST /api/admin/store/inspect` | `{source, type, id}`: for a plugin, the manifest and settings form at the pinned commit; for a theme, the validated theme |
| `POST /api/admin/store/install` | `{source, type, id, sha, settings, acknowledge_unverified}`: installs a new entry, or updates an installed one |
| `GET /api/admin/store/sources` | official and custom sources with their status |
| `POST /api/admin/store/sources` | `{url, acknowledge: true}`: add a custom source (its index must be valid) |
| `DELETE /api/admin/store/sources/{id}` | remove a custom source |
| `GET /api/admin/store/screenshot/{source}/{type}/{id}/{n}` | screenshot proxy |

An installed plugin remembers its store source in `installed_plugins.store_source`. A theme from the store stores `store_id`, `store_source`, `store_sha` and `store_version`, and an update replaces it in place. Custom sources are stored in the `store_sources` table (migration `f8a9b0c1d2e3`).
