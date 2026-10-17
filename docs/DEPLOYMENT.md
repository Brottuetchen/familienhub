# Betrieb

Familienhub ist ein Docker-Container (FastAPI-Backend, liefert auch die Web-App aus) plus PostgreSQL.

## 1. Starten

```bash
cp .env.example .env
# Mindestens: SECRET_KEY (python3 -c "import secrets;print(secrets.token_urlsafe(48))"),
#             POSTGRES_PASSWORD, CORS_ORIGINS (eigene Adresse)
docker compose up -d --build
docker compose exec familienhub python -m scripts.create_admin
```

Datenbankänderungen laufen beim Start automatisch über Alembic.

## 2. Erreichbarkeit

- Hinter einem Reverse-Proxy (Nginx Proxy Manager, Traefik, Caddy) mit HTTPS betreiben; Port 8000 im Container.
- Die App fragt beim ersten Start nach der Adresse (`https://hub.example.org`).
- Von unterwegs am besten per VPN (z. B. WireGuard) statt öffentlich.

## 3. Anmeldung

- Lokale Konten: `scripts.create_admin`, weitere Personen in der App unter **Verwaltung → Familie & Rollen**.
- OIDC (optional): `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, Redirect-URIs aus `.env.example` beim
  Anbieter eintragen. Bei Authentik muss der Provider die Grant-Types `authorization_code` und `refresh_token` haben.

## 4. Push-Mitteilungen

- **Android:** Firebase-Projekt anlegen, Dienstkonto-JSON herunterladen und in `docker-compose.yml` einbinden,
  `FCM_PROJECT_ID` und `FCM_SERVICE_ACCOUNT_FILE` setzen. Der Container läuft als unprivilegierter Nutzer
  (UID 10001): `chown 10001:10001 fcm-service-account.json && chmod 600 fcm-service-account.json`. Die `google-services.json` gehört nur in den eigenen
  App-Build, nie ins Repo.
- **Web/PWA (auch iPhone ab iOS 16.4):** `cd backend && python -m scripts.generate_vapid`, Werte als
  `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` eintragen.

## 5. Plugins

Zugänge (Nextcloud, Home Assistant, Paperless, Seerr, Shelfarr, Cookidoo, Habitica, Wetter) entweder in `.env`
oder als Admin in der App unter **Verwaltung → Plugins & Zugänge** (verschlüsselt gespeichert, ohne Neustart).
Die Übersicht in der Verwaltung zeigt, ob jedes Plugin erreichbar ist.

Persönliche Zugänge (Nextcloud-Konto, Habitica, Paperless-Token) trägt jede Person selbst in der App ein.

## 6. App-Builds

- **Android:** `cd app && flutter build apk --release`. Eigene `google-services.json` nach `app/android/app/` legen.
- **iOS:** Build auf macOS (z. B. CI mit macOS-Runner), Installation per Sideload.

## 7. Sicherung

Gesichert werden muss nur die PostgreSQL-Datenbank (Volume `familienhub_db`) und `.env`. Alle Inhalte wie Aufgaben,
Einkauf und Dokumente liegen in den angebundenen Diensten.

## 8. Sicherheitsprüfung

Jeder PR, `main` und wöchentlich: `.forgejo/workflows/security.yml` mit gitleaks (Geheimnisse), pip-audit und
OSV-Scanner (bekannte Lücken in Python- und Flutter-Abhängigkeiten), Trivy (Dockerfile/Compose), Bandit und
Semgrep (unsichere Muster). Lokal: `.forgejo/ci/security.sh`.
