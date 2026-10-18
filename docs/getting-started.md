# Getting started

Familienhub is one Docker container (FastAPI backend, which also serves the web app) plus PostgreSQL.

## 1. Start the server

```bash
mkdir familienhub && cd familienhub
curl -fsSLO https://raw.githubusercontent.com/Brottuetchen/familienhub/main/docker-compose.yml
docker compose up -d
```

This pulls the prebuilt image and needs no configuration (Docker Compose v2.24 or newer). The secret key is generated on first start and kept in the `familienhub_data` volume; the database password defaults to a value that is only reachable inside the compose network. Optional settings (port, plugins, OIDC, a different database password) go into a `.env` file next to `docker-compose.yml`: copy [`.env.example`](../.env.example) and edit it before the first start.

Open `http://<host>:8000` in a browser, or enter that address in the app. A new hub shows **Set up**:
1. The first person to open the hub creates the admin account. No code is needed, and this works only while no admin exists. **If the hub is reachable from the internet before you have done this, set `SETUP_REQUIRE_CODE=true` in `.env` first:** the hub then logs a setup code (`docker compose logs familienhub | grep -i code`) that is valid only while no admin exists and changes on every restart and after ten wrong attempts. Alternative without a code: `docker compose exec familienhub python -m scripts.create_admin`.
2. The **setup wizard** then guides you through:
   1. **Basics:** name and time zone
   2. **Areas:** where tasks, the shopping list and the calendar live, in the hub and/or a service
   3. **Services:** the ones you chose come first, with *Test connection*; calendar subscriptions (school holidays, bins …) as a list with a check
   4. **Family:** invite people

   Without any service, tasks, shopping list and family calendar are stored in the hub. You can rerun the wizard under *More → Administration*.

### Building from source

```bash
git clone https://github.com/Brottuetchen/familienhub.git && cd familienhub
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

The image is tagged `familienhub:local`, the base for [plugins](plugins.md#install-a-plugin).

Database migrations run automatically on start (Alembic).

## 2. Make it reachable

- Run it behind a reverse proxy with HTTPS (Nginx Proxy Manager, Traefik, Caddy). The container listens on port 8000.
- The app asks for the address on first start.
- For access from outside, a VPN (e.g. WireGuard) is safer than exposing the hub publicly.

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

- **Web Push:** generate keys with

  ```bash
  docker compose exec familienhub python -m scripts.generate_vapid
  ```

## 6. Plugins

Enter credentials for Nextcloud, Home Assistant, Paperless, Seerr, Shelfarr, Cookidoo, Habitica, ntfy and weather under **Administration → Plugins & access**. They are stored encrypted and take effect without a restart. You can also put them in `.env`. Personal accounts (Nextcloud, Habitica, Paperless token, ntfy) are set up by each person in the app. Details: [plugins](plugins.md).

With a CalDAV server, set the shared family calendar and connect the phones to the same server, so the iPhone and Android calendar and reminder apps show the same data as the hub: [calendar & phone](calendar.md).

## 7. Backup

Back up the PostgreSQL volume (`familienhub_db`), the data volume (`familienhub_data`, holds the generated secret key; without it stored plugin credentials cannot be decrypted) and `.env` if you have one. Tasks, shopping lists, documents and the like live in the connected services.

## 8. Update

```bash
docker compose pull && docker compose up -d
```

To pin a version, set `FAMILIENHUB_VERSION` in `.env` (default `latest`). If you build from source: `git pull` and then the build command from above.
