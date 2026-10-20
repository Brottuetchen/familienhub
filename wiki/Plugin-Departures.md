# Plugin: Abfahrten

Eine Karte auf **Heute** mit den nächsten Bus- und Bahnabfahrten an eurer Haltestelle, gedacht für den Schulweg:

```
Musterstadt Schulzentrum                           12 min
Bus 12 → Schulzentrum · 7:42 (+2)       leave in 5 min
Bus 14 → Hauptbahnhof · 7:44            leave in 7 min
Bus 12 → Schulzentrum · 7:50            cancelled
```

(Die Beispielzeilen stammen aus der README; Texte der Karte folgen der App-Sprache.) Das Abzeichen zeigt die Minuten bis zur nächsten Abfahrt, die fährt; `(+2)` ist die Verspätung; mit **Gehzeit** werden nicht mehr erreichbare Abfahrten ausgeblendet. Die Karte erscheint nur im gewählten **Zeitfenster** (z. B. 06:30 bis 08:30, Mo–Fr) und nie ohne Abfahrten.

Voraussetzung: **Familienhub 1.0.0-beta.3 oder neuer**. Ausführlich (Englisch): [README des Plugins](https://github.com/Brottuetchen/familienhub-store/tree/main/plugins/departures)

## Woher die Daten kommen

Von einer öffentlichen [transport.rest](https://transport.rest)-Instanz (kostenlose Schnittstelle vor den HAFAS-Systemen der Verkehrsunternehmen, von Freiwilligen betrieben). Standard: `https://v6.db.transport.rest`; regionale Instanzen wie `https://v6.vbb.transport.rest` (Berlin/Brandenburg) funktionieren genauso.

**Bitte fair nutzen:** Instanzen sind frei und geteilt. Das Plugin merkt sich Antworten 45 Sekunden, fragt nur im Zeitfenster und nur, wenn jemand die App offen hat (ungefähr eine Anfrage pro Minute). Wer viele Hubs betreibt oder Zuverlässigkeit braucht, betreibt eine **eigene Instanz**. Verfügbarkeit ist nicht garantiert; fällt die Instanz aus, fehlt die Karte einfach.

## Einstellungen

| Einstellung | Bedeutung |
|---|---|
| `DEPARTURES_STOP` (Pflicht) | Haltestellen-ID der Instanz, z. B. `8000105`. Ein Name geht auch, kann aber die falsche Haltestelle erwischen |
| `DEPARTURES_BASE_URL` | Adresse der Instanz (Standard `https://v6.db.transport.rest`) |
| `DEPARTURES_LINES` | optional: Linien, z. B. `Bus 12, Bus 14` |
| `DEPARTURES_DIRECTIONS` | optional: Teile des Zielnamens, z. B. `Schulzentrum` |
| `DEPARTURES_MAX` | Anzahl Abfahrten, 1 bis 6, Standard 4 |
| `DEPARTURES_WALK_MINUTES` | Gehzeit, 0 bis 90, Standard 0 (aus) |
| `DEPARTURES_SHOW_FROM` / `DEPARTURES_SHOW_UNTIL` | Zeitfenster `HH:MM` (Hub-Zeitzone) |
| `DEPARTURES_WEEKDAYS_ONLY` | nur Montag bis Freitag |

## Haltestellen-ID finden

IDs unterscheiden sich je Instanz; sucht auf der Instanz, die ihr nutzt:

```
curl 'https://v6.db.transport.rest/locations?query=Musterstadt%20Schulzentrum&results=5&stops=true&addresses=false&poi=false'
```

Jedes Ergebnis hat `id` und `name`. Tragt die `id` der richtigen Haltestelle ein. Alternativ den Namen eintragen und **Verbindung testen**: Der Test nennt die gefundene ID und die nächsten Treffer. Zeigt die Karte die falsche Richtung (oft gibt es eine ID je Richtung oder Steig), probiert die Nachbareinträge oder den Richtungsfilter.

Der **Verbindungstest** meldet z. B. *"Stop found: Musterstadt Schulzentrum. Next: Bus 12 → Schulzentrum · 7:42 (+2) (in 12 min)."* und warnt, wenn eure Filter nichts treffen. (Die Testtexte sind englisch.)

## Gut zu wissen

- **Wer die Basis-Adresse ändert, sendet die Haltestellen-ID an diesen Host.** Nehmt nur Instanzen, denen ihr traut. Die Liste der Hosts im Manifest ist Information, keine Sperre.
- Echtzeitdaten gibt es nur, wo die Instanz sie hat; sonst die Plan-Zeit ohne Verspätung.
- Das Kartensymbol ist immer ein Bus.
- Antwortet die Instanz nicht innerhalb von etwa 3,5 Sekunden, fehlt die Karte bei diesem Aufruf.
- Es werden nur die nächsten 90 Minuten (plus Gehzeit) abgefragt.

## Was getestet wurde

Automatische Tests laufen gegen nachgebildete Antworten (teils echten Antworten von `v6.vbb.transport.rest` nachempfunden). Ein manueller Lauf gegen die echte VBB-Instanz (Suche, Abfahrten, Verbindungstest, Karte) hat funktioniert. Die **Standard-Instanz `v6.db.transport.rest` konnte nicht getestet werden** (sie antwortete zum Testzeitpunkt mit HTTP 503). **Ausgefallene Abfahrten wurden nie live gesehen**; ihre Behandlung folgt der Dokumentation von `hafas-client`.

Siehe auch: [Store: Plugins und Themes](Store-Plugins-und-Themes)
