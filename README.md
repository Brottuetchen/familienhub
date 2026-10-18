# Familienhub

Eine selbst gehostete App für die Familienorganisation: **Heute-Übersicht, Aufgaben (eigene, gemeinsame,
füreinander), Einkauf, Essensplan, Termine und Erinnerungen** – mit echten Push-Mitteilungen,
Home-Widgets und Offline-Modus. Der Hub bündelt Dienste, die man oft schon betreibt; die eigentlichen
Daten bleiben dort (Nextcloud, Home Assistant, Paperless, …).

- **Android-App** (Flutter), iOS aus derselben Codebasis (Sideload), Web-App als PWA
- **Backend:** FastAPI + PostgreSQL, ein Docker-Container
- **Anmeldung:** lokal oder per OIDC (z. B. Authentik, Keycloak)
- **Vier Designsprachen** (Warm/Material You, Liquid Glass, Clean Cards, Neo-Brutalism), eigene Themes installierbar

## Plugins

Alles außer dem Kern läuft als Plugin und lässt sich in der App unter **Mehr → Verwaltung → Plugins & Zugänge**
an- und abschalten und einrichten (ohne Neustart).

| Plugin | Fähigkeit |
|---|---|
| Nextcloud (CalDAV) | Aufgaben je Person, Familienliste, Kalender |
| Habitica | Aufgaben, Gewohnheiten, Belohnungen |
| Home Assistant | Einkaufsliste, Haus-Kacheln (Zustände, Licht/Schalter/Szenen), Cookidoo-Wochenplan |
| Cookidoo | Rezepte suchen und einplanen |
| Paperless-ngx | Dokumente suchen, Fristen als Erinnerung – mit dem eigenen Paperless-Zugang |
| Shelfarr | E-Books und Hörbücher wünschen |
| Seerr | Filme und Serien wünschen (als eigener Seerr-Nutzer) |
| Wetter | Wetter auf „Heute“ |

## Schnellstart

```bash
cp .env.example .env          # SECRET_KEY, POSTGRES_PASSWORD und Adresse eintragen
docker compose up -d --build
docker compose logs familienhub | grep Einrichtungscode
```

Danach die App (oder `https://hub.example.org` im Browser) öffnen: Ein neuer Hub zeigt **„Einrichten“**. Mit dem
Einrichtungscode aus dem Log legt man das erste Konto an; der **Einrichtungs-Assistent** führt dann durch Name,
Zeitzone, Dienste (mit „Verbindung testen“) und Familie. Später erneut unter **Mehr → Verwaltung**. Hinweise zu Push (Firebase/Web-Push), OIDC und Reverse-Proxy: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Dokumentation

- Entscheidungen und Zielbild: [`docs/ENTSCHEIDUNGEN.md`](docs/ENTSCHEIDUNGEN.md)
- Plugins und ihre Schnittstellen: [`docs/PLUGINS.md`](docs/PLUGINS.md)
- Mitteilungen aus anderen Systemen (Home Assistant & Co.): [`docs/QUELLEN.md`](docs/QUELLEN.md)
- Sicherheit (Prüfbericht, Melden von Lücken): [`docs/SICHERHEIT.md`](docs/SICHERHEIT.md)
- Arbeitsregeln für Beitragende und Agenten: [`CLAUDE.md`](CLAUDE.md), [`docs/BUILD_PROMPT.md`](docs/BUILD_PROMPT.md)

## Entwicklung

```bash
cd backend && pip install -r requirements.txt && PYTHONPATH=. pytest -q
cd app && flutter pub get && flutter analyze && flutter test
```

## Lizenz

[GNU Affero General Public License v3.0](LICENSE). Wer Familienhub verändert und anderen als Dienst anbietet,
muss den geänderten Quellcode ebenfalls zugänglich machen.
