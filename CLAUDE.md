# Working rules (contributors and coding agents)

- **Language:** code, comments, commits, pull requests and docs in **English** (since 2026-10-18). Older German comments are translated when a file is touched anyway, with no mass-translation PRs. UI texts are localised in `app/lib/l10n/app_<lang>.arb` (German is the template). The German design notes in `docs/internal/` stay as they are.
- **No secrets in the repo:** no tokens, passwords, `google-services.json`, Firebase service account JSON, VAPID private keys or `.env`.
  - Examples belong in `.env.example` with placeholders.
- **No household data in code:** no real IPs, domains or names as defaults. Everything comes from configuration.
- **Tests first.**
  - Existing tests must stay green: `cd backend && PYTHONPATH=. pytest -q`; `cd app && flutter analyze && flutter test`.
  - Change existing tests only with a reason in the PR.
  - Mocks simulate the external system; they never decide the result under test.
- **Fail softly:** a plugin that is not configured or not reachable returns empty data plus a status, never an exception into the UI.
- **Database changes only via Alembic migrations.**
- **Small, focused commits.** Read the existing code before larger changes.
- **Report success only with the copied command output.** Never merge your own PR (`main` is protected).
- Design decisions and history: `docs/internal/ENTSCHEIDUNGEN.md` and `docs/internal/BUILD_PROMPT.md` (German, binding for agents).
