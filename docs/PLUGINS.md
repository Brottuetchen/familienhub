# Plugins schreiben

Jede Integration im Familienhub ist ein **Plugin**: Nextcloud (Aufgaben, Termine), Habitica (native persönliche Aufgaben), Home Assistant
(Einkauf, Cookidoo-Essensplan lesend), Cookidoo (Rezepte suchen und einplanen), Shelfarr (Bücher), Wetter.
Eigene Plugins sind normale Python-Pakete.

## Aufbau

```python
# mein_grocy/plugin.py
from fastapi import APIRouter
from app.plugins import Plugin, Setting, get_setting

router = APIRouter(prefix="/api/grocy", tags=["grocy"])

@router.get("/status")
async def status():
    return {"status": "ok", "url": get_setting("GROCY_URL")}

class GrocyPlugin(Plugin):
    def __init__(self):
        super().__init__(
            id="grocy",                      # eindeutig, klein, ohne Leerzeichen
            name="Grocy",
            version="0.1.0",
            description="Vorräte und Einkauf aus Grocy",
            capabilities=frozenset({"shopping"}),
            settings=(
                Setting("GROCY_URL", "Adresse"),
                Setting("GROCY_API_KEY", "API-Schlüssel", secret=True),
            ),
        )

    def routers(self):
        return [router]
```

```toml
# pyproject.toml des Plugin-Pakets
[project.entry-points."familienhub.plugins"]
grocy = "mein_grocy.plugin:GrocyPlugin"
```

Paket ins Backend-Image installieren (`pip install mein-grocy`), Neustart. Das Plugin erscheint unter
`GET /api/modules` und im Admin-Bereich (Einstellungen mit Verbindungstest folgt, Issue #33).

## Regeln

- **Fähigkeiten** (`capabilities`) bestimmen, welche Bereiche die App zeigt: `tasks`, `calendar`, `shopping`,
  `meal_source`, `meal_planning`, `books`, `weather`. Bei Aufgaben laufen alle aktiven Provider nebeneinander (`providers("tasks")`); der explizite Lookup prüft das persönliche Konto. Die alte „erstes aktives Plugin“-Auswahl bleibt für noch nicht umgestellte Bestandsbereiche kompatibel, ist aber kein Zielmuster für neue Integrationen.
- **Einstellungen** liest ein Plugin nur über `get_setting(KEY)`: Admin-Eintrag > Kern-Einstellung > Umgebung.
  Geheime Felder (`secret=True`) werden verschlüsselt gespeichert und nie zurückgegeben.
- **Aktiv** ist ein Plugin, wenn alle Pflicht-Einstellungen gesetzt sind und es nicht in `PLUGINS_DISABLED` steht.
  `is_configured()` darf überschrieben werden (z. B. Konten pro Person).
- **Antwortformat** für Listen aus Fremdsystemen: `{status: ok|unavailable|not_configured, error, items}` – ein
  ausgefallenes System darf die App nie zum Absturz bringen.
- **Datenschutz:** Persönliche Daten nur mit den Zugangsdaten der jeweiligen Person, kein gemeinsamer Admin-Zugang.
- Ein Plugin, das beim Laden scheitert, wird übersprungen und protokolliert – der Hub läuft weiter.

## Endpunkte

- `GET /api/modules` – aktive Bereiche und Plugins (für die App)
- `GET/PUT /api/admin/settings` – Plugin-Einstellungen (nur Admin)

## Haus-Karte in „Heute“ (#28)

Die Auswahl wird über die bestehende **Admin-API** (`PUT /api/admin/settings`, Schlüssel
`HA_HOUSE_ENTITIES`) oder in `.env` (`HA_HOUSE_ENTITIES=`) konfiguriert: bis zu sechs
Entitäts-IDs kommagetrennt. Eine allgemeine Plugin-Einstellungsoberfläche ist separat in #33 geplant.
Ohne Auswahl, ohne HA-Zugang oder bei deaktiviertem HA-Plugin bleibt die Karte verborgen.
Änderungen über die Admin-API gelten ohne Neustart; Reihenfolge entspricht der Auswahl, doppelte IDs
werden nur einmal angezeigt. Ungültige IDs oder mehr als sechs verschiedene IDs werden beim Speichern abgelehnt.

Beispiel-Auswahl (Platzhalter, in HA vorhandene IDs einsetzen):
`sensor.washer_status,sensor.room_temperature,binary_sensor.baby_monitor,sensor.waste_tomorrow`.
Anzeigenamen und Einheiten stammen aus HA. Für „Müll morgen“ oder einen verständlichen Maschinenstatus
einen passenden HA-Sensor auswählen; der Hub erfindet weder Abholtermine noch Gerätezustände.

`GET /api/today` liefert zusätzlich `house: {status, error, items}`. Ein Eintrag enthält nur
`entity_id`, `name`, `state` und `unit`, keine weiteren Attribute, Kamera-URLs oder Tokens.
Alle angemeldeten Hub-Nutzer sehen dieselbe Auswahl: nur familiengeeignete Zustände freigeben.
`unknown`, `unavailable` und fehlende Entitäten erscheinen als „Nicht verfügbar“; die übrigen
Zustände bleiben sichtbar. HA-Ausfall liefert `unavailable`, ohne andere Heute-Karten zu blockieren.
Binäre Werte erscheinen als „An“/„Aus“, andere Werte wie von HA geliefert.

Die Leseauswahl bleibt ohne Geräteaktionen oder Streams. Momentaufnahme beim Laden bzw.
Herunterziehen zum Aktualisieren von „Heute“, keine Echtzeitüberwachung (insbesondere kein Babyphon-Ersatz).
Offline gilt der vorhandene Cache samt „Offline, Stand …“-Hinweis. Ältere Server ohne `house`-Feld
bleiben kompatibel; es sind keine zusätzlichen Pakete oder Datenbankmigrationen nötig.

## Haussteuerung in „Heute“ (#45)

#45 ist auf ausdrücklichen Nutzerwunsch **vor #47 (Habitica)** priorisiert; keine Habitica-, Redesign-
oder allgemeine Einstellungsoberfläche in diesem Paket. Die bisherige Aussage „rein lesende Haus-Karte“
bezieht sich weiterhin auf die Leseauswahl und den unveränderten `/api/today`-Vertrag, nicht auf neue,
separat freigegebene Aktionen.

**Konfiguration:** `HA_HOUSE_WRITE_ENTITIES` ist standardmäßig **leer**. Bis zu sechs verschiedene,
exakte `light.*`, `switch.*`, `script.*` oder `scene.*`-IDs, kommagetrennt in Anzeigereihenfolge;
Leerzeichen außen werden entfernt, Duplikate zusammengefasst. Keine automatische Übernahme aus
`HA_HOUSE_ENTITIES`, keine impliziten Schreibrechte für bisherige Leser. IDs erhält man in Home Assistant
unter Entwicklerwerkzeuge → Zustände. Nur familiengeeignete Geräte und ausdrücklich unbedenkliche
Skripte/Szenen freigeben: deren hinterlegte HA-Automation kann mehrere Geräte beeinflussen.
Speichern über die bestehende Admin-API, z. B. `PUT /api/admin/settings` mit
`{"values":{"HA_HOUSE_WRITE_ENTITIES":"light.example,switch.example,script.example,scene.example"}}`
(Platzhalter ersetzen). Leerer Wert widerruft alle Aktionen sofort; kein Neustart, keine zusätzliche UI
für Einstellungen (#33). HA-Zugang und aktives HA-Plugin sind immer erforderlich.

| Methode | Pfad | Vertrag |
|---|---|---|
| GET | `/api/house/controls` | Authentifiziert, `Cache-Control: no-store`; `{status,error,items}`. Eintrag: `{entity_id,name,state,actions,brightness}`. Nur Schreibauswahl, keine privaten Attribute. |
| POST | `/api/house/actions` | Admin/Partner; `{entity_id,action,brightness?}`. Nur `turn_on`, `turn_off` (Licht/Schalter), `brightness` (nachgewiesen dimmbares Licht), `activate` (Skript/Szene). Keine zusätzlichen Felder/Queryparameter. |

Helligkeit ist ein strikter Integer **0–255 inklusive** und ausschließlich bei `action: "brightness"`
Pflicht; bool, Fließkommazahl, String, null und Werte außerhalb werden abgelehnt. Dimmbarkeit wird an
aktuellen `supported_color_modes` erkannt (brightness, color_temp, hs, xy, rgb, rgbw, rgbww, white), nicht
an vorhandener Helligkeit allein. Fehlt der Nachweis, bleibt das Licht nur schaltbar. Bei Kind/Gast ist
`actions` leer; Zustände bleiben lesbar. `unknown`, `unavailable`, fehlende und ungültige Zustände
haben `state: null` und keine Aktionen. Ausfall einzelner Entitäten lässt andere lesbar.

Jeder POST prüft Auswahl, aktives Plugin, Zugang und den aktuellen Zustand/die Fähigkeit erneut vor
seinem einzigen HA-Serviceaufruf. `activate` und `brightness` werden intern ausschließlich auf
`<domain>/turn_on` abgebildet, `brightness` ergänzt nur den gleichnamigen Wert. Keine frei wählbare
Domain, kein Service- oder `service_data`-Proxy. Erfolg ist `200 {"accepted":true}`: HA hat die Anfrage
angenommen, nicht der Beweis einer physischen Gerätezustandsänderung. Eingabefehler → 422,
fehlende Rolle → 403, fehlende Anmeldung → 401; blockierter Zustand/Konfiguration oder HA-Fehler → 409.
Damit präzisiert #45 für Geräteaktionen das allgemeine Listen-Fehlerformat aus BUILD_PROMPT B2:
fehlgeschlagene Schreibaktionen sind niemals stille HTTP-200-Erfolge.

**Flutter:** Die zusätzliche Karte „Haus steuern“ lädt ihre Freigaben frisch und nur im Arbeitsspeicher;
Heute-Cache und gehaltene Lesezustände erteilen keine Steuerrechte. Bei fehlender Konfiguration oder
älteren Servern (404) bleibt sie verborgen. An/Aus, Aktivieren und nur bei tatsächlicher Dimmbarkeit
ein nativer Slider; Vorschau ohne POST, Versand erst beim Loslassen. Laufende Aktionen sperren die
Bedienung, auch während eines konkurrierenden Heute-Refreshs. Nach Annahme werden Heute-Daten
invalidiert und echte HA-Zustände neu gelesen, keine optimistische Erfolgsmeldung. Fehler erscheinen
sichtbar; „Haus aktualisieren“ liest nur und sendet keine Aktion erneut. Bei Offline-/Ladezuständen,
HA-Ausfall und unbekannten Zuständen sind keine Aktionen verfügbar. Logout/Serverwechsel verwirft
Freigaben und verspätete Antworten.

Keine Offline-Warteschlange, keine automatischen POST-Retries, keine Wiederholung nach Token-Refresh
oder HTTP-Redirect. Ein Timeout kann bedeuten, dass HA die Aktion bereits ausgeführt hat: Fehler zeigen,
Zustand prüfen, **nicht blind wiederholen**. Skripte/Szenen haben keine allgemeine physische
Erfolgsbestätigung; ihr frisch gelesener HA-Zustand bleibt maßgeblich. Keine Streams, kein Polling,
keine individuellen Skriptparameter, keine Farben/Temperaturen und keine Änderungen an echten Geräten
während Entwicklung/Tests.


## Fachsystemgrenze für alle Integrationen (#47)

Der Hub ist zunächst Aggregator/Bedienoberfläche vorhandener Fachsysteme. Fachlogik, native Daten,
Mapping, Konfliktbehandlung und Aktionen verbleiben im jeweiligen Anbieterplugin/Fachsystem.
Der Kern übernimmt Auth/Rechte, Pluginverwaltung/Routing, gemeinsame Darstellung und notwendige
technische Metadaten/Cache. Er darf den jeweiligen anbieterspezifischen Refresh/Sync **anstoßen**,
nicht eine zentrale generische Spiegelengine oder ein zweites Fachsystem betreiben.
Das präzisiert ältere Bestandsbeschreibungen ausdrücklich; kein ungefragter Komplettumbau der
bestehenden Rezept-, Essensplan-, Erinnerungs- oder anderen Fachmodule in #47.
Keine personenbezogenen Sonderfälle, keine verpflichtende Nextcloud-Schicht für weitere Plugins.

### Aufgabenadapter

`Plugin.task_connector(user_id, db)` liefert den persönlichen Adapter. Die bestehende Registry
verlangt einen aktiven Provider und prüft eine mitgesendete Kontoreferenz gegen dessen `account_ref`.
`GET /api/tasks/providers` liefert nur Konten der aktuellen Sitzung. `provider=all` liest unabhängig
alle aktiven Anbieter; Ausfall eines Adapters verhindert nicht das Lesen der übrigen. Es schreibt nie.
Einzellisten, Create/PATCH/Completion/Delete, Auswahl und native Aktionen tragen `provider` und
`account`; nur alte Nextcloud-Aufrufe dürfen den bisherigen Default ohne expliziten Account behalten.
Neue Kontoreferenzen sind an Nutzer, Server und externes Konto gebunden, nicht nur an Remote-UIDs.

Nextcloud und Habitica sind konkrete Implementierungen. Native Optionen/Aktionen werden im
jeweiligen Connector und der konkreten Flutter-Bedienung umgesetzt, nicht auf Checkboxen reduziert
und nicht in einer neuen UI-Schemaengine nachgebaut. Der Fake im Registry-/Routertest liest und
schreibt durch dieselben Endpunkte; sein Name erfordert keine Kernrouteränderung.
Ein Vikunja-Plugin wird mit #47 weder behauptet noch spekulativ gebaut.

Details/Bedienung/API und Betreiberfreigabe: `AUFGABENPROVIDER.md`.
