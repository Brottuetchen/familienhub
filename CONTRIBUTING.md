# Contributing

Thanks for helping! Familienhub is a family project that grew up, so please keep changes small and well tested.

## Ways to help
- **Report bugs or wishes:** open an issue. From the app: *More → Send feedback → To the developers* pre-fills one with the app version and platform.
- **Translate:** copy `app/lib/l10n/app_en.arb` to `app_<code>.arb`, translate the values, and add the language to `appLanguages` in `app/lib/l10n/l10n.dart`.
- **Server texts** (error messages, push notifications, plugin names and settings) are written in German in the code and translated in `backend/app/core/i18n.py`. The server answers in the app's language (`X-App-Language` / `Accept-Language`) and sends push texts in each person's last-used app language. `tests/test_i18n.py` fails when a new German text has no English entry.
- **Themes:** see [docs/themes.md](docs/themes.md). Share a `theme.json` on GitHub, or propose a built-in one.
- **Plugins:** see [docs/plugins.md](docs/plugins.md). Most integrations can live in their own package.
- **Code:** pick an issue, or open one first for larger changes.

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
- Code, comments, commits and PR texts in English. UI texts go into the ARB files (German template, English translation); server texts get an entry in `backend/app/core/i18n.py`.
- No secrets and no personal or household data in code, tests or screenshots.
- CI runs tests and security scans (gitleaks, pip-audit, OSV-Scanner, Trivy, Bandit, Semgrep) on every PR.

## License
By contributing you agree that your contribution is licensed under the [AGPL-3.0](LICENSE).
