# Entscheidungen und Zielbild (Stand 2026-10-16)

## Nutzer und Geräte
- **Person A:** Android. Bekommt **die native Android-App zuerst**.
- **Person B:** iPhone.
  - Zuerst die **installierte Web-App (PWA)** mit Web-Push über Safari, Voraussetzung iOS 16.4+ und App auf dem Home-Bildschirm.
  - Später die native iOS-App aus derselben Flutter-Codebasis (braucht Apple-Developer-Account und TestFlight).
- Weitere Rollen sind im Datenmodell vorhanden (Kind, Gast), werden aber noch nicht genutzt.

## Push
- Android-App: **Firebase Cloud Messaging (FCM, HTTP v1)**. Ausdrücklich **nicht** über ntfy oder UnifiedPush.
- PWA: **Web Push (VAPID)**. Das ist im Backend schon vorhanden und muss auf iOS Safari funktionieren.
- Ein Backend-Dienst verschickt an alle registrierten Geräte eines Nutzers (FCM-Token und Web-Push-Subscriptions).

## Aufgaben: unabhängige Anbieterplugins (#47 präzisiert den früheren Nextcloud-Fokus)
Grund: iOS-Erinnerungen binden Nextcloud per CalDAV-Account nativ an. Person B sieht ihre Aufgaben dann auch ohne Hub-App.
Vikunja wäre bei Zuweisungen stärker, ist aber schlechter in iOS-Erinnerungen einzubinden. Vikunja ist ein Beispiel für spätere Plugin-Erweiterbarkeit; im aktuellen Main ist kein Vikunja-Konnektor vorhanden oder durch #47 geliefert.

Modell:
- Jede Person hat eine eigene Liste (z. B. „Anna“, „Ben“). Dazu kommt eine gemeinsame Liste **„Familie“**.

---

## Vom Agenten entschieden

### Paket 1: Aufräumen und Fokus

- **Feature-Flags:** Settings für Module (Medien, Finanzen, Pakete, Inventar, Dokumente, KitchenOwl, Vikunja) – alle default aus, konfigurierbar über `.env`.
  - Feature-Flag-System in `core/features.py` implementiert.
  - Alle betroffenen Router prüfen Flags: ausgeschaltete Module geben 404 oder leere Listen zurück, nie ein Fehler im Backend.
  - So bleibt die API sauber und Frontend muss nicht mit deaktiviertem Code rechnen.

- **Plex-Konnektor entfernt:**
  - Grund: Laut `docs/internal/ENTSCHEIDUNGEN.md` ist Plex nicht mehr im Einsatz (vgl. „Medien: Finanzen, Pakete, Inventar (Homebox), Dokumente (Paperless). Der Code bleibt, die Module sind per Feature-Flag aus. **Plex gibt es nicht mehr.**").
  - Gelöschte Dateien: `plex_connector.py`, Imports aus `registry.py`, Endpunkte `/media/streams` und `/media/recent` aus `media.py`.
  - Plex-Optionen in `config.py` entfernt; Konfigurationsplatzhalter in `.env.example` kommentiert.

- **APP_NAME konfigurierbar:** Default-Wert auf „Familienhub" gesetzt, kann per `APP_NAME`-Env überschrieben werden.

- **Router bereinigt:**
  - `media.py`: Nur noch Hörbücher, Tonies, Sonarr, Radarr, Overseerr. Aggregierter Endpunkt `/now-playing` ohne Plex.
  - Alle Endpunkte nutzen Feature-Flags; ausgeschaltete Module geben 404 (bei Writes) oder [] (bei Reads).
- Die Listen sind in Nextcloud gegenseitig mit Schreibrecht geteilt.
- **„Für den anderen“** heißt: Die Aufgabe wird in der Liste der anderen Person angelegt.
  - Ersteller und Zuständige stehen zusätzlich in `X-FAMILIENHUB-CREATED-BY` und `X-FAMILIENHUB-ASSIGNEE`. So zeigt der Hub „von Anna für Ben“.
  - iOS-Erinnerungen ignorieren diese Felder; die Liste allein reicht dort zur Orientierung.
- Ansichten im Hub: **Meine**, **Für mich von anderen**, **Von mir für andere**, **Familie**.
- Die Liste „Habitica“ (bestehender Sync) wird im Hub ausgeblendet.

## Habitica
Die frühere Entscheidung „nur Belohnungsschicht“ ist durch die ausdrückliche Nutzerkorrektur zu #47 ersetzt: Habitica ist ein eigenständiges persönliches Aufgabenprovider-Plugin, ohne Nextcloud-Pflicht. Ausgewählte native Aufgaben bleiben in Habitica; der Hub zeigt und bedient sie dort. Nextcloud-Aufgaben erzeugen weder Habitica-Aufgaben noch Punkte. Keine personenbezogenen Sonderfälle, keine automatischen Spiegelbindungen.

## Einkauf und Essensplan: Cookidoo über Home Assistant
Cookidoo (Thermomix) ist in Home Assistant integriert. Der Hub liest und schreibt über die HA-API und nicht direkt bei Cookidoo:

| HA-Entität | Bedeutung im Hub |
|---|---|
| `calendar.cookidoo_speiseplan` | Essensplan (Wochenansicht) |
| `todo.cookidoo_einkaufsliste` | Zutaten aus geplanten Rezepten |
| `todo.cookidoo_zusatzliche_kaufe` | Freie Einkaufsartikel. Hier landen manuell hinzugefügte Artikel. |

Das Abo ist Premium und läuft bis 26.11.2026; ohne Abo muss es weiter funktionieren (leere Daten statt Fehler).
- Die eigenen Essensplan- und Rezept-Module aus Hermes bleiben für Gerichte ohne Cookidoo.
- KitchenOwl wird nicht mehr genutzt.

## Termine
Nextcloud-Kalender über CalDAV (bestehender Konnektor), mit Farben pro Person.

## Was vorerst ausgeblendet wird
Medien (Sonarr, Radarr, Plex, Overseerr, Audiobookshelf, TeddyCloud), Finanzen, Pakete, Inventar (Homebox), Dokumente (Paperless).
Der Code bleibt, die Module sind per Feature-Flag aus. **Plex gibt es nicht mehr.**

## Später
- Android-Widgets (Heute, Einkauf) und Schnellaktionen
- Smartview (Flur-Monitor) und ein Sprachassistent als Clients der Hub-API bzw. per MCP
- Veröffentlichung als Open-Source-Projekt: keine Hausnamen oder IPs im Code, alles über Konfiguration

## Betrieb (Referenzinstallation)
- Docker-Container im eigenen Heimnetz.
- Login über einen OIDC-Anbieter (z. B. Authentik).
- HTTPS über einen Reverse-Proxy, erreichbar intern und per VPN.
- Das Firebase-Projekt für Android-Push legt der Betreiber an.

## Cache-first-Leseseiten (#46)

- Heute, Aufgaben (je Ansicht), Einkauf, Essensplan (je Woche) und Termine zeigen den vorhandenen SharedPreferences-Cache zuerst. Riverpod hält geladene Lesedaten beim Reiterwechsel; Rückkehr und Pull-to-refresh laden im Hintergrund nach, ohne vorhandene Inhalte durch einen Ladebildschirm zu ersetzen. Gleichzeitige identische GETs teilen denselben HTTP-Aufruf.
- Die Anzeige nennt den Datenstand und laufende bzw. fehlgeschlagene Aktualisierung. Ein Cachetreffer allein bedeutet **nicht offline**; erst ein Netzwerkfehler zeigt den Offline-Hinweis. Der erste Abruf ohne Cache wartet weiterhin auf HTTP.
- Erfolgreiche Schreibaktionen invalidieren zentral die betroffenen Lesedaten; bereits sichtbare Inhalte bleiben bis zur Antwort erhalten. Seit #32 gibt es eine eng begrenzte Offline-Warteschlange (siehe unten); HA-Aktionen werden nie gemerkt oder wiederholt.
- Persistierte Schlüssel sind nach Server und angemeldeter Identität gehasht getrennt. Logout, erneuter Login und Serverauswahl verwerfen Cache und gehaltene Lesedaten; verspätete Antworten der alten Sitzung werden verworfen. Abgelaufene Access-Tokens erlauben keinen Cache-Fallback, auch bereits sichtbare Lesedaten werden bei Ablauf ausgeblendet. 401/403 sind keine Offline-Erfolge. Serverseitigen Widerruf erkennt weiterhin erst der HTTP-Abgleich; bis dahin ist lokal gültiger Cache nur ein ausdrücklich datierter Zwischenstand.
- Bestehende ungetrennte Cacheeinträge werden nicht migriert oder angezeigt: Der erste Abruf nach diesem Update benötigt einmal das Netz. Keine zweite Datenbank, keine Backend-Änderung.
- Sitzungswechsel serialisieren Token-Writes und binden Login/OIDC/Logout an den auslösenden Übergang; überholte Starts und Abmeldungen ändern auch den sichtbaren Loginzustand nicht mehr.
- Bewusste Sicherheitsdegradation: Der zweite Token-/Widget-Schreiber im WorkManager-Isolate entfällt. Alte periodische Widget-Aufträge werden gezielt storniert; der Dispatcher beendet Restaufträge ohne Zugriffe. Heute-/Einkaufswidgets aktualisieren sich weiterhin beim Laden im Vordergrund, **nicht mehr alle 30 Minuten im Hintergrund**. Wiederaufnahme erst mit atomarer sitzungsgebundener nativer Publikation; ein weiterer read-only HTTP-Client allein verhindert das Publikationsrennen nicht. Bereits angezeigte Widgettexte werden hierdurch nicht gelöscht.


## Haussteuerung und Reihenfolge (#45 vor #47)

- Nutzerfreigabe: Nach #46 kommt **#45 vor #47**. Die bisherige Roadmap-Reihenfolge ist damit überholt. Keine Habitica-Umsetzung, kein Redesign, keine generische Einstellungsoberfläche in #45.
- #28 und sein unverändertes `today.house` bleiben eine lesende Momentaufnahme. Neu ist ausschließlich die separat konfigurierte, standardmäßig leere Schreibauswahl `HA_HOUSE_WRITE_ENTITIES` über dieselbe Plugin-/Admin-Konfiguration. `HA_HOUSE_ENTITIES` verleiht niemals Schreibrecht.
- Admin/Partner dürfen ausgewählte Lampen/Schalter an- und ausschalten, nachgewiesen dimmbare Lampen dimmen und explizit freigegebene Skripte/Szenen aktivieren. Kind/Gast bleiben lesend. Keine beliebigen HA-Services, Domains, Nutzdaten oder Skriptparameter.
- Flüchtige, authentifizierte Netzabfragen liefern Steuerfähigkeiten; weder persistierter Cache noch gehaltene Heute-Daten erteilen Freigaben. Serverseitig werden Plugin, Konfiguration, exakte Auswahl und aktueller Zustand/Fähigkeit vor jedem Serviceaufruf erneut geprüft. Unbekannt/nicht verfügbar blockiert die betroffene Aktion.
- Für POST präzisiert diese Entscheidung BUILD_PROMPT B2: HA-Ausfall oder unbestätigte Geräteaktion liefert HTTP 409 statt stillen HTTP-200-Erfolg. Listen behalten ihr Statusformat. Annahme einer Aktion ist kein Nachweis einer physischen Zustandsänderung.
- Keine Offline-Warteschlange und keine automatische Wiederholung einer Geräteaktion, auch nicht nach Token-Refresh oder Redirect; mehrdeutige Timeouts bleiben sichtbare Fehler. Pending-Sperre übersteht konkurrierende Leseaktualisierung. Details und Grenzen: `docs/internal/PLUGINS.md`, Abschnitt #45.
- **Revision 2026-10-17 (#66, Nutzerwunsch „so reibungslos wie in Home Assistant“):** Die Kachel zeigt den erwarteten Zustand sofort (wie das HA-Frontend). Bestätigt wird über den Zustand, den HA in der Service-Antwort meldet, sonst durch Nachlesen; ohne Bestätigung binnen 4 s fällt die Kachel auf den gelesenen Zustand zurück. Die Pending-Sperre gilt **pro Gerät**, verschiedene Geräte schalten parallel. Die Karte liest im Vordergrund alle 5 s nach. Unverändert: genau ein POST je Aktion, nie automatisch wiederholt, unklarer Ausgang bleibt sichtbar bis zur Bestätigung.

## Offline-Warteschlange (#32)

- Nur Einkauf (hinzufügen, abhaken/öffnen, löschen) und Nextcloud-Aufgaben (abhaken; anlegen ohne Haushaltsrotation, seit #72) gehen ohne Netz. Offline angelegte Aufgaben erscheinen vorläufig in der passenden Liste (Meine/Von mir/Familie, bei Fälligkeit bis heute auch auf Heute) und lassen sich erst nach dem Senden abhaken oder bearbeiten. Nie: Haus, Habitica (Punkte würden doppelt zählen), Essensplan, Erinnerungen, Profil, Verwaltung – diese scheitern offline weiterhin sichtbar.
- Ablauf: erst senden; nur bei Netzwerkfehler wird gemerkt. Gemerkte Änderungen liegen in SharedPreferences, getrennt nach Server und Identität wie der Cache; Abmelden, Login und Serverwechsel verwerfen sie (Hinweis im Abmelden-Dialog).
- Anzeige: Gemerkte Änderungen werden zentral über die gelesenen Daten gelegt (Einkauf, Heute, Aufgabenlisten, Widgets), Einträge tragen eine Wolke; das Status-Symbol zeigt die Zahl, antippen listet sie mit „Jetzt senden“ und „Verwerfen“.
- Senden: der Reihe nach, sobald ein Lesen wieder klappt, beim Zurückkehren in die App und alle 30 s. Jede Änderung trägt einen festen `Idempotency-Key`; das Backend merkt sich erfolgreiche Anlagen (Einkauf, Aufgaben) 24 h und legt bei Wiederholung nichts doppelt an. Abhaken/Löschen sind ohnehin wiederholbar.
- Konflikte: Lehnt der Server ab (4xx), bleibt die Änderung mit Grund sichtbar, bis man sie verwirft; „gibt es nicht mehr“ bei 404. Löschen von bereits Gelöschtem gilt als erledigt. Bei Serverausfall (5xx/429) wird später erneut gesendet.



## Verbindliche Gesamtarchitektur: Hub bündelt, Fachsystemplugins handeln (#47)

Nutzerpräzisierung: **„alles was wir tun muss auf Plugin Basis sein. Unser Service soll erstmal nur bündeln“**.
Das gilt für alle künftigen Integrationen, nicht nur für Aufgaben oder einzelne Personen.
- Fachlogik, native Daten, Mapping, Konfliktbehandlung und native Aktionen gehören zum jeweiligen Plugin/Fachsystem.
- Kern: Authentifizierung/Rechte, vorhandene Pluginverwaltung und Routing, gemeinsame Darstellung sowie notwendige technische Auswahl-, Operations- und Cachemetadaten. Keine parallelen Fachsysteme oder Schatten-Aufgabenhaltung.
- **„Die syncengiene in dem Sinne nur, das der jeweilige sync angestoßen wird.“** Der Kern darf anbieterspezifischen Refresh/Sync anstoßen und koordinieren, implementiert aber keine zentrale generische Spiegel-/All-to-all-Engine.
- Mehrere Provider laufen nebeneinander. Eine Aktion bezeichnet den ausdrücklich gewählten Anbieter, das eigene Konto und die Remote-ID. Nextcloud ist weder Pflichtunterbau noch Ersatz-Fallback anderer Anbieter.
- #47 erweitert die vorhandene Registry und liefert Nextcloud/Habitica tatsächlich; ein kleiner Fake-Drittanbieter belegt Erweiterbarkeit ohne Namenszweig im Kernrouter. Keine zweite Pluginengine und kein spekulativer dritter echter Anbieter.
- Ältere Aussagen dieses Dokuments zu lokalen Fachmodulen, globalem „ersten Provider“ oder zentraler Habitica-Belohnung sind Bestandsbeschreibung, **keine Ausnahme von diesem Zielbild**. Bestehende Fachfeatures außerhalb #47 bleiben erhalten; deren Bereinigung wird separat entschieden (u. a. eigene Rezepte/Essensplanung und Erinnerungen).
- Kein vorgezogener Designumbau: Das vom Nutzer angekündigte Designpapier und eine spätere App-Bereinigung bleiben separate Arbeit. #47 ergänzt nur funktional notwendige Anbieter-/Konto-/Auswahl- und native Aktionsbedienung im vorhandenen Design.

Verträge, Single-Writer-Cutover und bewusste Grenzen: `docs/internal/AUFGABENPROVIDER.md`.


## Plugins per GitHub-Link installieren (Nutzerwunsch 18.10.: „Anleitung, Installer ähnlich wie bei Themes, interaktiv, alles sicher gespeichert“)

- **Ablauf wie beim Theme-Installer:** Link einfügen → `POST /api/plugins/inspect` löst auf **einen Commit** auf und liest `familienhub-plugin.json` → Prüfbildschirm (Autor, Version, Commit, Hosts, Fähigkeiten, Warnung, Bestätigung) → Formular aus den Manifest-Einstellungen → `POST /api/plugins/install` (genau dieser Commit) → Hot-Load ohne Neustart. Aktualisieren = erneut prüfen und installieren (Werte bleiben, nur neue Pflichtfelder fragen); Entfernen löscht Routen, Dateien, Datensatz und Einstellungen sofort.
- **Das Manifest ist die Wahrheit** (Konfigurationsdatei, wie gewünscht): strenge Prüfung, unbekannte Felder abgelehnt, höchstens 64 KB. Einstellungsschlüssel müssen mit `<ID in Großbuchstaben>_` beginnen; Plugin-IDs, die zu Kern-/Eingebaut-Namen führen würden (Präfixe von Kern-Settings, eingebaute IDs, Fähigkeitsnamen), sind reserviert. Der Installer ersetzt Name, Version, Beschreibung und Einstellungen des Plugin-Objekts durch die Manifestwerte und verweigert das Laden, wenn die Klasse mehr Einstellungen oder Fähigkeiten deklariert als das Manifest.
- **Sicherheitsgrenzen (bewusst):** Nur Admins; Schalter `PLUGIN_INSTALL_ENABLED` (Standard an); nur `api.github.com`, `raw.githubusercontent.com`, `codeload.github.com` (https, keine Weiterleitungen, Zeit- und Größengrenzen); Tarball höchstens 10 MB, sicher entpackt (keine Links/Geräte/`..`, höchstens 2000 Dateien/50 MB); `pip install --target <DATA_DIR>/plugins/site/<id>` ohne Shell, mit Zeitlimit und ohne Hub-Geheimnisse in der Umgebung; Routen installierter Plugins nur unter `/api/plugins/<id>/` und immer mit Anmeldung; Geheimnisse wie bisher Fernet-verschlüsselt (`config_store`), nie zurückgegeben; Installation/Entfernen im Protokoll. **Kein Sandbox:** Plugin-Code läuft im Hub-Prozess mit vollem Zugriff, die Oberfläche sagt das vor jeder Installation. Der Admin bestätigt die Quelle.
- **Speicherort:** `<DATA_DIR>/plugins/{src,site,tmp}`; Tabelle `installed_plugins` (Migration `d1e2f3a4b5c6`). **`/app/data` muss ein dauerhaftes Volume sein.** Das Standard-Compose hat `familienhub_data`; die Referenzinstallation (`/opt/stacks/familienhub/compose.yml`) bindet `/app/data` **nicht** ein: dort gehen installierte Plugins bei jedem `up -d --build` verloren (Datensatz bleibt, Fehler in der Liste, gleicher Commit erneut installieren repariert). Vor produktiver Nutzung Volume ergänzen.
- **Grenzen:** Aktualisieren/Entfernen von Plugins mit kompilierten Erweiterungen braucht einen Neustart (die App sagt es). Installierte Plugins können keine Alembic-Migrationen mitbringen. Lange Installationen (pip) brauchen ein Proxy-Timeout von mindestens 300 s. Kein Katalog, keine Signaturen, keine automatische Update-Prüfung.
- Anleitung für Plugin-Autoren und Vorlage: `docs/plugins.md`, `examples/plugin-template/` (die Vorlage ist durch `tests/test_plugin_template.py` abgesichert).


## Vorlagenlisten (#20)

- Vorlagen gehören der Familie (nicht pro Person). Lesen: alle Rollen. Anlegen/Ändern/Löschen und „Einkaufsliste als Vorlage speichern“: ab Partner.
- Anwenden auf die Einkaufsliste: jede Rolle (wie `POST /api/shopping`), über die aktive Quelle; offene Einträge werden nicht doppelt angelegt (ohne Groß-/Kleinschreibung und überzählige Leerzeichen). Anwenden auf Aufgaben: ab Partner (wie Aufgabe anlegen), eine Aufgabe je Eintrag über `provider=auto`, weil die Aufgabenquellen keine Listen mit Einträgen kennen. Beschreibung: `docs/templates.md`.

## Plugin- und Theme-Store (#7, Entscheidung des Owners 19.10.)

- **Offizieller Index** = `index.json` im Repo `brottuetchen/familienhub-store` (Branch `main`), einstellbar über `STORE_INDEX_URL` (leer = aus). Aufgenommen wird nur, was die Maintainer geprüft haben (Prüfung = gemergter PR im Store-Repo).
- **Eigene Quellen:** Admins dürfen zusätzliche GitHub-Repos mit `index.json` im selben Format hinzufügen. Einträge daraus tragen „Nicht geprüft“; Warnung vor dem Hinzufügen und vor jeder Installation, serverseitig erzwungen (`acknowledge`, `acknowledge_unverified`).
- **Keine Signaturen.** Vertrauen = offizieller Index + jeder Eintrag pinnt einen exakten Commit (`sha`); installiert wird nur dieser. Die App schickt den geprüften Commit mit; weicht der Index inzwischen ab, gibt es 409.
- **Updates:** „Update verfügbar“, wenn der Index einen anderen Commit pinnt als installiert; Aktualisieren nur per Klick, nie automatisch.
- **Screenshots** liegen im Store-Repo (`screenshots/<id>/1.png`), relativ zur `index.json` referenziert; der Hub lädt sie (nur erlaubte Hosts, PNG/JPEG/WebP nach Inhalt, höchstens 2 MB) und reicht sie an die App durch, damit Clients GitHub nie direkt kontaktieren.
- Plugins aus dem Store laufen weiterhin mit vollem Zugriff; dieselbe Warnung und Bestätigung wie beim Link-Installer. Ungültige Einträge werden mit Grund übersprungen, nicht der ganze Index.
- Speicher: Tabelle `store_sources`, Spalten `installed_plugins.store_source` und `themes.store_*` (Migration `f8a9b0c1d2e3`). Format und Ablauf: `docs/store.md`.
