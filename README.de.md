<div align="center">

# Familienhub

**Selbst gehostete Familien-App, die eure vorhandenen Dienste zusammenbringt.**

Heute auf einen Blick, Aufgaben für sich und füreinander, Einkauf, Essensplan, Termine und Erinnerungen, mit echten Push-Mitteilungen, Widgets und Offline-Modus.

[English](README.md) · Die ausführliche Doku ist auf Englisch: [Einstieg](docs/getting-started.md) · [Kalender & Handy](docs/calendar.md) · [Mitteilungen](docs/notifications.md) · [Plugins](docs/plugins.md) · [Plugin-Vorlage](examples/plugin-template/) · [Themes](docs/themes.md) · [Roadmap](docs/roadmap.md)

<img src="docs/screenshots/de/today-light.png" width="23%" alt="Heute"> <img src="docs/screenshots/de/tasks.png" width="23%" alt="Aufgaben"> <img src="docs/screenshots/de/meals.png" width="23%" alt="Essensplan"> <img src="docs/screenshots/de/today-pixel.png" width="23%" alt="Pixel-Theme">

</div>

## Warum

Eine App für alle in der Familie, die **allein funktioniert und anbindet, was ihr schon betreibt**.

- **Sofort nutzbar:** Aufgaben, Einkaufsliste, Familienkalender, Essensplan und Erinnerungen speichert der Hub selbst. Ein weiterer Dienst ist nicht nötig.
- **Alles anschließbar:** Jeder Bereich kann seine Daten statt aus dem Hub oder zusätzlich aus einem Dienst holen. Beispiele:
  - Aufgaben aus jedem CalDAV-Server (Nextcloud, iCloud, Radicale …) oder Habitica
  - die Einkaufsliste aus Home Assistant
  - Dokumente aus Paperless
  - und alles, was ein Plugin liefert

  Angebundene Daten bleiben, wo sie sind.

| Bereich | Im Hub | Oder aus (Plugins) |
|---|:-:|---|
| Aufgaben | ✓ | CalDAV (Nextcloud, iCloud, Radicale …), Habitica, auch mehrere nebeneinander |
| Einkaufsliste | ✓ | Home Assistant, Mealie |
| Kalender | ✓ Familienkalender | CalDAV, Kalender-Abos (ICS), alles zusammen |
| Essensplan & Rezepte | ✓ Wochenplan und Rezeptbuch | Mealie, Cookidoo |
| Dokumente · Bücher · Filme & Serien | – | Paperless-ngx · Shelfarr · Seerr |

Die Quelle jedes Bereichs wählt der Admin im Einrichtungs-Assistenten oder unter *Verwaltung → Quellen je Bereich*.

## Was es kann

- **Heute:** Begrüßung, Aufgaben (meine / für mich / Familie), Einkauf, Termine, Essensplan, Erinnerungen und Haus-Kacheln auf einem Bildschirm
- **Kalender:** Liste, Woche und Monat, Farben und Filter je Kalender; neue Termine landen genau im gewählten Kalender (Familie zuerst), bearbeiten und löschen; dieselben CalDAV-Kalender und Erinnerungen auf iPhone und Android, siehe [Kalender & Handy](docs/calendar.md)
- **Aufgaben:** eigene, gemeinsame und zugewiesene Aufgaben, Haushaltsrotation; Nextcloud und Habitica nebeneinander. Eine Aufgabe für jemanden landet am Aufgabenort des Empfängers (im Profil einstellbar), nicht dort, wo der Ersteller arbeitet
- **Einkauf, Essen, Rezepte:** Einkaufsliste, Wochenplan, Rezeptbuch im Hub (Zutaten, Zubereitung, Link); Rezepte auf Tage legen und Zutaten auf die Liste, auch von Cookidoo
- **Erinnerungen:** zu einer Zeit, wiederkehrend oder *wenn ich heimkomme* (über Home Assistant), mit Knöpfen direkt in der Mitteilung
- **Haus:** Zustände sowie Licht, Schalter und Szenen aus Home Assistant, ausgewählt vom Admin
- **Dokumente und Medien:** Paperless durchsuchen, Fristen als Erinnerung; Filme, Serien und Bücher wünschen
- **Mitteilungen:** Firebase (Android-App), Web Push (Browser/Web-App) und ntfy (z. B. iPhone), mit Ruhezeiten und Kategorien
- **Familie:** Rollen (Admin, Partner, Kind, Gast), Einladungen, Anmeldung per OIDC (Authentik, Keycloak …) oder lokal
- **Apps:** Android-App mit Widgets und Offline-Warteschlange, Web-App (PWA), iOS-App zum Sideloaden
- **Anpassbar:** Themes mit Hell/Dunkel und Schriften, installierbar aus GitHub (elf in der [Theme-Galerie](https://github.com/Brottuetchen/familienhub-themes)); Deutsch und Englisch

<details>
<summary>Weitere Screenshots</summary>

<img src="docs/screenshots/de/today-dark.png" width="23%" alt="Heute, dunkel"> <img src="docs/screenshots/de/shopping.png" width="23%" alt="Einkauf"> <img src="docs/screenshots/de/calendar.png" width="23%" alt="Termine"> <img src="docs/screenshots/de/themes.png" width="23%" alt="Themes">

</details>

## Schnellstart

```bash
mkdir familienhub && cd familienhub
curl -fsSLO https://raw.githubusercontent.com/Brottuetchen/familienhub/main/docker-compose.yml
# Öffentliche Beta: Version explizit angeben; :latest gibt es erst mit einem stabilen Release.
FAMILIENHUB_VERSION=1.0.0-beta.1 docker compose up -d
```

Es ist keine Konfiguration nötig. Dann `http://<host>:8000` im Browser öffnen (oder die Adresse in der App eintragen): Wer einen neuen Hub zuerst öffnet, legt das Admin-Konto an, danach führt der Einrichtungs-Assistent durch den Rest. Ist der Hub vor der Einrichtung aus dem Internet erreichbar, `SETUP_REQUIRE_CODE=true` setzen (siehe [Sicherheit](docs/security.md#first-admin-and-secret-key), englisch). APK und IPA hängen an jedem [GitHub-Release](https://github.com/Brottuetchen/familienhub/releases/latest). Mehr dazu (Reverse-Proxy, Selbst bauen, Sicherung) im [Einstieg](docs/getting-started.md) (englisch).

## Mitmachen

Eigene Plugins gibt es per GitHub-Link direkt in der App (*Verwaltung → Plugins & Zugänge → Plugin installieren*); die Anleitung zum Schreiben und eine Vorlage stehen in [docs/plugins.md](docs/plugins.md) (englisch) und [examples/plugin-template](examples/plugin-template/).

Fehler und Wünsche gern als Issue, auch auf Deutsch, oder direkt aus der App: *Mehr → Feedback senden → An die Entwickler*. Code, Übersetzungen, Themes und Plugins: siehe [CONTRIBUTING](CONTRIBUTING.md).

## Lizenz

[AGPL-3.0](LICENSE). Wer eine veränderte Fassung anderen als Dienst anbietet, muss den Quellcode ebenfalls zugänglich machen.
