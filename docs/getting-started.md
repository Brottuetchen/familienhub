# Getting started

Familienhub is one Docker container (FastAPI backend, which also serves the web app) plus PostgreSQL.

## 1. Start the server

```bash
git clone https://github.com/Brottuetchen/familienhub.git && cd familienhub
cp .env.example .env
# at least: SECRET_KEY  (python3 -c "import secrets;print(secrets.token_urlsafe(48))")
#           POSTGRES_PASSWORD
#           CORS_ORIGINS  (your own address, e.g. https://hub.example.org)
docker compose up -d --build
docker compose logs familienhub | grep -i code
```

Open the app or `https://hub.example.org` in a browser. A new hub shows **Set up**:
1. Create the first admin account with the setup code from the log. The code is valid only while no admin exists; it changes on every restart and after ten wrong attempts. Alternative: `docker compose exec familienhub python -m scripts.create_admin`.
2. The **setup wizard** then guides you through:
   1. **Basics:** name and time zone
   2. **Areas:** where tasks, the shopping list and the calendar live, in the hub and/or a service
   3. **Services:** the ones you chose come first, with *Test connection*; calendar subscriptions (school holidays, bins …) as a list with a check
   4. **Family:** invite people

   Without any service, tasks, shopping list and family calendar are stored in the hub. You can rerun the wizard under *More → Administration*.

Database migrations run automatically on start (Alembic).

## 2. Make it reachable

- Run it behind a reverse proxy with HTTPS (Nginx Proxy Manager, Traefik, Caddy). The container listens on port 8000.
- The app asks for the address on first start.
- For access from outside, a VPN (e.g. WireGuard) is safer than exposing the hub publicly.

## 3. Get the apps

| Platform | How |
|---|---|
| **Android** | Build your own APK (`cd app && flutter build apk --release`, with your own `google-services.json` for push), or serve APKs from the hub under `/downloads/` (`DOWNLOADS_DIR`). [Obtainium](https://obtainium.imranr.dev/) can watch that page for updates. |
| **iPhone / iPad** | Either the **web app**: open the hub in Safari → *Add to Home Screen*. Or **sideload the iOS app**: the GitHub workflow `ios.yml` builds an unsigned IPA; install it with Sideloadly or SideStore and a free Apple ID (re-sign every 7 days, SideStore does it on the phone). |
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

## 7. Backup

Back up the PostgreSQL volume (`familienhub_db`) and `.env`. Tasks, shopping lists, documents and the like live in the connected services.

## 8. Update

```bash
git pull && docker compose up -d --build
```
