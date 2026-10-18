# Security

Continuous checks on every pull request, on `main` and weekly (`.forgejo/workflows/security.yml`):
- gitleaks (secrets)
- pip-audit and OSV-Scanner (known vulnerabilities in Python and Flutter dependencies)
- Trivy (Dockerfile, Compose)
- Bandit and Semgrep (unsafe patterns)

Run them locally with `.forgejo/ci/security.sh`. A full manual review was done on 2026-10-18; its findings and fixes are in [`internal/SICHERHEIT.md`](internal/SICHERHEIT.md) (German).

## Principles
- **Sign-in:** local accounts (bcrypt) or OIDC with PKCE, `state` and `nonce`. Short-lived access tokens (JWT), rotating refresh tokens. The app's OIDC return (`familienhub://auth`) is bound to the app by PKCE.
- **Stored secrets:**
  - refresh tokens, API keys, service keys and invite codes: SHA-256 only
  - credentials for other services (Nextcloud, Paperless, Habitica, plugin secrets): Fernet-encrypted
- **Personal data only with personal access**, e.g. each person's own Paperless token or Seerr user. No shared admin login reads everyone's data.
- **Hardening:**
  - security headers, `/docs` off in production
  - 2 MB request limit
  - the secret key is generated on first start (kept in `<DATA_DIR>/secret_key`, mode 0600); production refuses to start with a default or short key if none can be stored
  - CORS same-origin by default
- **No secrets and no household data in the repository.**

## First admin and secret key
- **First admin:** on a new hub, the first person to open it creates the admin account, and only while no active admin exists. Until then, anyone who can reach the hub could claim it. If the hub is reachable from the internet before setup, set `SETUP_REQUIRE_CODE=true`: the hub then logs a setup code at start (`docker compose logs familienhub`) that is needed to create the admin. The startup log says which mode is active.
- **Secret key:** if `SECRET_KEY` is empty, the hub generates one and stores it in the `familienhub_data` volume. Treat that volume like the database: it is part of the backup, and anyone who can read it can forge sign-in tokens. An explicitly set `SECRET_KEY` always wins.

## Roles

| | Guest | Child | Partner | Admin |
|---|:-:|:-:|:-:|:-:|
| Read Today, shopping, events, reminders, meals, tasks | ✓ | ✓ | ✓ | ✓ |
| Add and tick off shopping items, own reminders, ntfy | ✓ | ✓ | ✓ | ✓ |
| Tick off tasks and family reminders, delete shopping items | | ✓ | ✓ | ✓ |
| Request books, movies and shows; connect own Nextcloud/Habitica | | ✓ | ✓ | ✓ |
| Create and edit tasks, events, meal plan, recipes, family reminders | | | ✓ | ✓ |
| Control the house (lights, switches, scenes) | | | ✓ | ✓ |
| Administration: people, plugins, themes, service keys, log | | | | ✓ |

The server enforces every rule (`require_min_role`). The app also hides what a role cannot do.

## Public endpoints (no sign-in)
- `/api/health`
- `/api/auth/login`, `/api/auth/refresh`, `/api/auth/oidc/{start,callback,exchange}`
- `/api/setup/{status,admin}`: only while no admin exists; with `SETUP_REQUIRE_CODE=true` also needs the setup code from the server log
- `/api/invites/accept`: invite code, attempts limited
- `/api/push/vapid-public-key`
- `/api/reminders/{id}/action`: short-lived token per reminder and person

Everything else requires sign-in.

## Reporting a vulnerability
Please do not open a public issue. Use GitHub's private advisory (*Security → Report a vulnerability*), see [SECURITY.md](../SECURITY.md).
