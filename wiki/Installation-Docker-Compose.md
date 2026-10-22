# Installation mit Docker Compose

Familienhub besteht aus **einem Container** (Server und Web-App) plus **PostgreSQL**. Es ist keine Konfiguration nötig, um zu starten.

## Voraussetzungen

- Ein Rechner oder Server mit Docker und **Docker Compose v2.24 oder neuer** (die Compose-Datei liest eine optionale `.env`-Datei).
- Ein freier Port (Standard: 8000).

## Schritt für Schritt

1. Ordner anlegen und Compose-Datei laden:

   ```bash
   mkdir familienhub && cd familienhub
   curl -fsSLO https://raw.githubusercontent.com/Brottuetchen/familienhub/main/docker-compose.yml
   ```

2. **Version.** Das stabile Release ist **1.0.0**, und `latest` zeigt darauf. Ohne weitere Angabe reicht Schritt 3. Wer eine Version festnageln will, schreibt sie in eine `.env` neben der `docker-compose.yml`:

   ```bash
   echo "FAMILIENHUB_VERSION=1.0.0" > .env
   ```

   Die aktuelle Version steht auf der [Release-Seite](https://github.com/Brottuetchen/familienhub/releases/latest). Eine Beta ist nie `latest`: dafür `FAMILIENHUB_VERSION` auf genau diese Beta setzen.

3. Starten:

   ```bash
   docker compose up -d
   ```

4. Im Browser `http://<server>:8000` öffnen. Ein neuer Hub zeigt **Einrichten**: Die erste Person, die ihn öffnet, legt das **Admin-Konto** an. Danach führt der [Einrichtungsassistent](Erste-Schritte) durch den Rest.

## Wichtig vor dem ersten Start

- **Ist der Hub schon vor der Einrichtung aus dem Internet erreichbar?** Dann setzt `SETUP_REQUIRE_CODE=true` in der `.env`. Der Hub schreibt dann einen Einrichtungscode ins Log (`docker compose logs familienhub | grep -i code`), ohne den kein Admin angelegt werden kann. Ohne diesen Schutz könnte jeder, der die Adresse kennt, das Admin-Konto anlegen.
- Alternative ohne Code: `docker compose exec familienhub python -m scripts.create_admin`.
- **Datenbank-Passwort** ändern geht nur vor dem ersten Start (`POSTGRES_PASSWORD` in der `.env`). Die Datenbank ist nur im Compose-Netzwerk erreichbar, der Standard ist deshalb in Ordnung.
- Den **geheimen Schlüssel** erzeugt der Hub beim ersten Start selbst und legt ihn im Volume `familienhub_data` ab. Er signiert Anmeldungen und verschlüsselt gespeicherte Zugangsdaten. **Nie später ändern**, sonst sind gespeicherte Zugangsdaten unlesbar und alle werden abgemeldet. Das Volume gehört zum [Backup](Backup-und-Wiederherstellen).

## Weitere Einstellungen (optional)

Alle Optionen stehen kommentiert in der [`.env.example`](https://github.com/Brottuetchen/familienhub/blob/main/.env.example). Kopiert sie nach `.env` und ändert nur, was ihr braucht, zum Beispiel:

| Einstellung | Wofür |
|---|---|
| `PORT` | Port auf dem Host (Standard 8000) |
| `TIMEZONE` | Zeitzone des Haushalts (Standard Europe/Berlin) |
| `SECURE_COOKIES=true` | wenn der Hub nur über HTTPS erreichbar ist, siehe [Reverse Proxy und HTTPS](Reverse-Proxy-und-HTTPS) |
| `HUB_PUBLIC_URL` | erreichbare Adresse des Hubs, für Klick-Links und Erinnerungs-Knöpfe in Mitteilungen |
| `BACKUP_AUTO`, `BACKUP_KEEP` | nächtliche Sicherung, siehe [Backup](Backup-und-Wiederherstellen) |
| `OIDC_*` | Anmeldung über Authentik, Keycloak u. ä. |

Zugangsdaten für Nextcloud, Home Assistant & Co. tragt ihr später als Admin in der App ein (*Mehr → Verwaltung → Plugins & Zugänge*), ohne Neustart.

## Aus dem Quellcode bauen

```bash
git clone https://github.com/Brottuetchen/familienhub.git && cd familienhub
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Weiter

- [Erste Schritte](Erste-Schritte)
- [Reverse Proxy und HTTPS](Reverse-Proxy-und-HTTPS)
- Referenz (Englisch): [Getting started](https://github.com/Brottuetchen/familienhub/blob/main/docs/getting-started.md)
