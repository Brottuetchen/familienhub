# Contributing

Thanks for helping! Familienhub is a family project that grew up, so please keep changes small and well tested.

## Ways to help
- **Report bugs or wishes:** open an issue. From the app: *More → Send feedback → To the developers* pre-fills one with the app version and platform.
- **Translate:** see [Translations](#translations) below. No Git needed, just a browser.
- **Server texts** are translated in `backend/app/core/i18n.py` (see below).
- **Themes:** see [docs/themes.md](docs/themes.md). Share a `theme.json` on GitHub, or propose a built-in one.
- **Plugins:** see [docs/plugins.md](docs/plugins.md). Most integrations can live in their own repository: start from [examples/plugin-template](examples/plugin-template/) and admins install it with a GitHub link.
- **Code:** pick an issue, or open one first for larger changes.

## Translations

The app's texts live in `app/lib/l10n/app_<code>.arb`. **German (`app_de.arb`) is the template**: every new text is written there first, and all other languages are translated from it.

### Translate in the browser (Weblate)
Translations are managed on Hosted Weblate (link: _to be added once the project exists, see [#25](https://github.com/Brottuetchen/familienhub/issues/25)_). Sign in, pick a language, translate. Weblate opens pull requests for us; you never touch Git. Leave a string empty if you are unsure: untranslated texts fall back to German until someone translates them, so a partial translation is fine and useful.

Keep placeholders such as `{count}` or `{name}` exactly as in the source, and keep plural forms (`{count, plural, =1{...} other{...}}`) intact.

### Add a new language
1. In Weblate: *Start new translation* and choose the language. Or without Weblate: copy `app/lib/l10n/app_en.arb` to `app/lib/l10n/app_<code>.arb` (e.g. `app_fr.arb`) and set `"@@locale"` to the same code.
2. Translate `languageName` first: it is the language's own name, shown in the language picker (for example `"Français"`).
3. Translate as much as you like. Missing keys fall back to German.
4. For iOS, add the code to `CFBundleLocalizations` in `app/ios/Runner/Info.plist` (a maintainer can do this in the pull request).

Nothing else is needed: the app picks the language up from the generated locales. Adding a language is a good first contribution.

### Check your file
```bash
python3 tools/check_arb.py
```
CI runs the same check. It fails on invalid JSON, duplicate keys, keys that do not exist in the German template, missing `languageName` and placeholder mismatches.

### Server texts
Error messages, push notifications, plugin names and settings are written in German in the code and translated in `backend/app/core/i18n.py` (German text to translation, one dictionary per language). The server answers in the app's language (`X-App-Language` / `Accept-Language`) and sends push texts in each person's last-used app language. `backend/tests/test_i18n.py` fails when a new German text has no English entry. These texts are not in Weblate yet, see [docs/translations.md](docs/translations.md#server-texts).

Maintainers: Weblate setup is described in [docs/translations.md](docs/translations.md).

## Development

```bash
# backend
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. pytest -q

# app (Flutter 3.47)
cd app && flutter pub get
flutter analyze && flutter test
flutter run -d chrome          # web app against a local backend
```

`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build` builds and runs everything from source (see [getting started](docs/getting-started.md)).

## Pull requests
- Branch from `main`, one topic per PR.
- **Tests first:**
  - Add tests for new behaviour.
  - Don't change existing tests without explaining why in the PR.
  - Mock external systems (`respx` for HTTP), never call real services.
- Paste the output of `pytest -q`, `flutter analyze` and `flutter test` into the PR.
- Code, comments, commits and PR texts in English. UI texts go into the ARB files (German template, English translation; other languages come via Weblate); server texts get an entry in `backend/app/core/i18n.py`.
- No secrets and no personal or household data in code, tests or screenshots.
- CI runs tests and security scans (gitleaks, pip-audit, OSV-Scanner, Trivy, Bandit, Semgrep) on every PR.

## License
By contributing you agree that your contribution is licensed under the [AGPL-3.0](LICENSE).
