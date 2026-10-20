# Getting started

Familienhub is one Docker container (FastAPI backend, which also serves the web app) plus PostgreSQL.

## 1. Start the server

```bash
mkdir familienhub && cd familienhub
curl -fsSLO https://raw.githubusercontent.com/Brottuetchen/familienhub/main/docker-compose.yml
# Current public beta; :latest is reserved for stable releases.
FAMILIENHUB_VERSION=1.0.0-beta.2 docker compose up -d
```

This pulls the prebuilt image and needs no configuration beyond pinning the current beta (Docker Compose v2.24 or newer). For anonymous pulls, the GitHub Container Registry package must be public. The secret key is generated on first start and kept in the `familienhub_data` volume; the database password defaults to a value that is only reachable inside the compose network. Optional settings (port, plugins, OIDC, a different database password) go into a `.env` file next to `docker-compose.yml`: copy [`.env.example`](../.env.example) and edit it before the first start.

Open `http://<host>:8000` in a browser, or enter that address in the app. A new hub shows **Set up**:
1. The first person to open the hub creates the admin account. No code is needed, and this works only while no admin exists. **If the hub is reachable from the internet before you have done this, set `SETUP_REQUIRE_CODE=true` in `.env` first:** the hub then logs a setup code (`docker compose logs familienhub | grep -i code`) that is valid only while no admin exists and changes on every restart and after ten wrong attempts. Alternative without a code: `docker compose exec familienhub python -m scripts.create_admin`.
2. The **setup wizard** then guides you through:
   1. **Basics:** name and time zone
   2. **Areas:** where tasks, the shopping list and the calendar live, in the hub and/or a service
   3. **Services:** the ones you chose come first, with *Test connection*; calendar subscriptions (school holidays, bins …) as a list with a check
      Tick what you want to use. Unticked services, also weather and CalDAV that work without settings, are switched off at the end; you can turn them on later under *Administration → Plugins & access*.
   4. **Family:** invite people

   Without any service, tasks, shopping list and family calendar are stored in the hub. You can rerun the wizard under *More → Administration*.

### Building from source

```bash
git clone https://github.com/Brottuetchen/familienhub.git && cd familienhub
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

The image is tagged `familienhub:local`, the base for [plugins](plugins.md#install-in-a-custom-docker-image).

Database migrations run automatically on start (Alembic).

## 2. Make it reachable

- Run it behind a reverse proxy with HTTPS (Nginx Proxy Manager, Traefik, Caddy). The container listens on port 8000.
- The app asks for the address on first start.
- Under a path prefix or in the Home Assistant sidebar: see [Home Assistant and sub-paths](home-assistant.md).
- For access from outside, a VPN (e.g. WireGuard) is safer than exposing the hub publicly.

## Public beta installations

For a pre-release, either download the `docker-compose.yml` **attached to that exact GitHub release**, or set `FAMILIENHUB_VERSION` to the advertised beta version before running Docker Compose. The default `:latest` container tag is published with a stable release, not with a beta.

```bash
FAMILIENHUB_VERSION=1.0.0-beta.2 docker compose up -d
```

Do not use the default `latest`-based quick start from the repository until a stable release exists. Check that the image is publicly accessible and the relevant GitHub Actions build has finished.

## 3. Get the apps

APK and IPA are attached to each GitHub release: <https://github.com/Brottuetchen/familienhub/releases/latest>.

| Platform | How |
|---|---|
| **Android** | Install the APK from the release (or build your own, `cd app && flutter build apk --release`, with your own `google-services.json` for push). You can also serve APKs from the hub under `/downloads/` (`DOWNLOADS_DIR`, mount a folder as shown in `docker-compose.yml`). [Obtainium](https://obtainium.imranr.dev/) can watch the release page for updates. |
| **iPhone / iPad** | Either the **web app**: open the hub in Safari → *Add to Home Screen*. Or **sideload the iOS app**: install the unsigned IPA from the release with Sideloadly or SideStore and a free Apple ID (re-sign every 7 days, SideStore does it on the phone). |
| **Desktop** | The web app in any browser. |

## 4. People and sign-in

- **Invite people** under *Administration → Family & roles → Invite person*. The hub creates a message with the app link, server address and a one-time code (valid 7 days). The person redeems it in the app and sets their own password.
- **OIDC** (optional, e.g. Authentik, Keycloak):
  - Set `OIDC_ISSUER`, `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET`, and register the redirect URIs from `.env.example` with the provider. Authentik providers need the grant types `authorization_code` and `refresh_token`.
  - Invited people sign in with the same email address.
  - With `OIDC_AUTO_CREATE=true`, accounts are created on first sign-in. In that case, restrict the application to your family at the provider (e.g. bind an Authentik group).
- **Roles:** admin, partner, child, guest. See [security](security.md#roles).

## 5. Notifications

Firebase (Android app), Web Push (browser and home-screen web app) and ntfy (anyone with the ntfy app, e.g. iPhones). Set up one or more channels as described in [notifications](notifications.md).

- **Firebase:** mount the service account JSON readable by the container user (UID 10001):

  ```bash
  chown 10001:10001 fcm-service-account.json && chmod 600 fcm-service-account.json
  ```

- **Web Push:** works out of the box. The hub creates its keys on first start and keeps them in the data volume (`/app/data/vapid.json`). To use your own, set `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` (`docker compose exec familienhub python -m scripts.generate_vapid`). As contact for the push services the hub uses the email of the first admin; `VAPID_EMAIL` overrides it.

## 6. Plugins

Enter credentials for Nextcloud, Home Assistant, Paperless, Seerr, Shelfarr, Cookidoo, Habitica, ntfy and weather under **Administration → Plugins & access**. They are stored encrypted and take effect without a restart. You can also put them in `.env`. Personal accounts (Nextcloud, Habitica, Paperless token, ntfy) are set up by each person in the app. Details: [plugins](plugins.md).

With a CalDAV server, set the shared family calendar and connect the phones to the same server, so the iPhone and Android calendar and reminder apps show the same data as the hub: [calendar & phone](calendar.md).

### Customise "Today"

Everyone arranges their own "Today" screen with the sliders icon in its header: drag cards to reorder them, switch them on or off and, in tile themes (see [themes](themes.md)), choose half width so two cards sit side by side. "Reset to default" returns to the family default. Admins can save their arrangement as the family default (shown to everyone without an own layout) in the same editor. Without a family default the classic arrangement applies. The layout is stored on the server (`GET/PUT/DELETE /api/me/today-layout`, admin default under `/api/admin/today-layout`); an older server simply keeps the classic arrangement.

## 7. Backup

**In the app:** *Administration → Backup* (admins only).

- **Download backup** saves one ZIP file through your browser. It contains the whole database (people, settings, themes, installed-plugin records, profile pictures and so on), and the hub's keys (`secret_key`, `vapid.json`). Stored plugin credentials stay encrypted exactly as they are in the database; the secret key in the file is what makes them readable again on a new machine. **Keep the file like a password**, anyone with it can read your credentials.
- **Store a backup on the hub** writes the same file to `/app/data/backups` (the `familienhub_data` volume).
- **Nightly backup** (off by default): from 03:30 (hub time zone) the hub stores a backup there every night and keeps the last N (1 to 30, default 7). `BACKUP_AUTO` and `BACKUP_KEEP` in `.env` set the defaults.
- *Administration* shows the date of the last backup. A failed backup is reported there and in the hub log; it never stops the hub.
- Documents, tasks, shopping lists and the like live in the connected services (Paperless, Nextcloud, ...) and are not part of this backup.
- The installed plugins' code is not in the file. The hub keeps their records; after a restore onto an empty volume, reinstall them under *Plugins & access* if they are missing.

The backup is a logical dump, so it works the same for the bundled PostgreSQL and for SQLite (which is copied with SQLite's online backup first, never as a live file). A backup from one can be restored into the other.

**Restoring:** click *Restore* next to a stored backup. The hub checks the file first and shows a warning: **all current data is replaced.** Before it replaces anything, the hub stores the current state as a backup of its own (`familienhub-prerestore-...`, the last three are kept). Afterwards **restart the hub** (`docker compose restart familienhub`), because settings and keys are loaded at start. People who are not in the backup are signed out.

- A backup from a **newer** Familienhub version is refused. So is a backup with a different database layout (an older version): run that version, restore, then update.
- To restore a downloaded file onto a hub (for example a new installation), copy it into the data volume, and it shows up in the list:

  ```bash
  docker compose cp familienhub-backup-20261018-120000.zip familienhub:/app/data/backups/
  ```

  Or upload it through the API (admin token needed): `curl -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/octet-stream" --data-binary @file.zip https://<hub>/api/admin/backup/upload`.
- If `SECRET_KEY` is set explicitly in the environment, a restore leaves it alone; credentials in the backup then only work if it is the same key.

Not covered by the app: the backup lives next to the data it protects. Copy the files from `/app/data/backups` somewhere else (another disk, another machine) regularly. Also keep your `.env` if you have one.

## 8. Update

```bash
docker compose pull && docker compose up -d
```

To pin a version, set `FAMILIENHUB_VERSION` in `.env` (default `latest`). If you build from source: `git pull` and then the build command from above.

**Update notice:** the hub checks the GitHub releases of `Brottuetchen/familienhub` a few times a day (cached, nothing but the request itself is sent). When a newer release exists, *Administration* shows a notice with the version, a link to the release notes and the update command. Pre-releases (`-beta.N`) are only offered while you run a pre-release yourself; then the command pins the version, because `latest` never points at a pre-release. Under *Administration → Updates* you can switch the check off, or point it to a fork (`UPDATE_CHECK=false`, `UPDATE_CHECK_REPO=owner/name` in `.env`). If GitHub is not reachable nothing is shown. Development builds (no version number) skip the check. Make a backup before you update.
