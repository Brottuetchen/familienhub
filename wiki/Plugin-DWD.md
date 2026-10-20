# Plugin: DWD (Wetterwarnungen und Pollen)

Bringt zwei Dinge vom Deutschen Wetterdienst auf den Heute-Bildschirm: **amtliche Wetterwarnungen** für euren Ort (mit Push-Mitteilung) und den **Pollenflug-Gefahrenindex** für eure Region. Kein Konto und kein API-Schlüssel nötig. Nur für Orte in **Deutschland**.

Voraussetzung: **Familienhub 1.0.0-beta.3 oder neuer**. Ausführlich (Englisch): [README des Plugins](https://github.com/Brottuetchen/familienhub-store/tree/main/plugins/dwd)

## Was es tut

- **Karte "Wetterwarnung(en)"** erscheint nur, wenn für euren Ort eine Warnung aktiv oder angekündigt ist: höchste Stufe, je Warnung eine Zeile mit Zeitfenster (mehr als sechs: "+N weitere").
- **Karte "Pollen · Region"** nur, wenn eine Pollenart heute mindestens eure Mindeststufe erreicht ("Birke: hoch", darunter ggf. "morgen: mittel").
- Ist nichts relevant oder ein Dienst nicht erreichbar: keine Karte, nie eine Fehlermeldung auf Heute.
- **Push** alle 15 Minuten für jede neue Warnung ab `DWD_MIN_SEVERITY` an Admins, Partner und Kinder (Gäste nicht). Jede Warnung wird einmal gemeldet; steigt die Stufe, gibt es eine Meldung "Aktualisiert: …". Mehr als drei neue Warnungen auf einmal werden zu einer Sammelmeldung. Jede Person kann *Plugins* in den Benachrichtigungs-Einstellungen abschalten.

## Einstellungen (alle optional)

| Einstellung | Bedeutung | Standard |
|---|---|---|
| `DWD_LATITUDE`, `DWD_LONGITUDE` | euer Standort in Dezimalgrad (z. B. `50.11` und `8.68`), beide oder keiner | Standort des Wetter-Plugins |
| `DWD_MIN_SEVERITY` | niedrigste Stufe für Push: `minor`, `moderate`, `severe`, `extreme` (die Karte zeigt alle) | `moderate` |
| `DWD_NOTIFY` | Push an/aus | an |
| `DWD_POLLEN_REGION` | Pollen-Region (Nummer oder Name) | Bundesland des Standorts |
| `DWD_POLLEN_TYPES` | Liste der Pollenarten (deutsch oder englisch) | alle |
| `DWD_POLLEN_MIN` | Mindeststufe: `low`, `medium`, `high` | `medium` |

**Standort:** Das Wetter-Plugin hat intern einen Standard-Standort (Berlin). Das DWD-Plugin übernimmt den **nicht** als euer Zuhause: Solange kein echter Standort gesetzt ist, bleibt es "nicht eingerichtet" und verlangt `DWD_LATITUDE`/`DWD_LONGITUDE`. Wohnt ihr wirklich in Berlin, tragt die Koordinaten hier ein.

**Warnstufen:** `minor` = Wetterwarnung, `moderate` = Markante Wetterwarnung, `severe` = Unwetterwarnung, `extreme` = Extreme Unwetterwarnung. Der Standard `moderate` hält Frost und leichten Wind aus der Hosentasche.

**Pollen-Region:** Der DWD veröffentlicht 27 Regionen. Ohne Angabe nimmt das Plugin das Bundesland; hat es mehrere Regionen (z. B. Hessen), gilt die **höchste** Stufe. Für genaue Werte tragt Nummer oder Namen eurer Region ein; die Liste mit allen Nummern steht in der [README des Plugins](https://github.com/Brottuetchen/familienhub-store/tree/main/plugins/dwd). Der Verbindungstest nennt die gültigen Regionen, wenn eure nicht gefunden wird.

**Verbindung testen:** prüft die eingegebenen Werte vor dem Speichern, fragt den Warndienst für euren Ort ab (die Meldung nennt den gefundenen Ort und ob Warnungen aktiv sind) und sucht die Pollen-Region.

## Wohin gehen eure Daten?

- `api.brightsky.dev`: Warnungen. Erhält eure auf vier Nachkommastellen gerundeten Koordinaten. Bright Sky ist ein kostenloser Dienst eines Freiwilligen, der DWD-Daten ausliefert.
- `opendata.dwd.de`: Pollenfile, erhält nichts über euch.
- Beides vom Hub-Server aus, nicht vom Handy. Sonst wird nichts gesendet.

## Grenzen

- **Kein Ersatz für amtliche Warn-Apps** wie NINA oder WarnWetter, wenn es um Sicherheit geht: Das Plugin fragt alle 15 Minuten ab, eine Mitteilung kann bis zu etwa 20 Minuten später kommen. Fällt Bright Sky aus, gibt es keine Warnungen (Pollen sind davon unabhängig).
- Pollen: pro Region, nicht pro Straße, einmal täglich (gegen 11 Uhr) veröffentlicht.
- Der erste Lauf nach der Installation meldet auch bereits aktive Warnungen.
- Selten kann eine geänderte Warnung nochmal als neu gemeldet werden.
- Quelle der Daten: Deutscher Wetterdienst.
- Die README nennt die Tests als Simulation (`respx`); die Pollen-Testdatei ist eine Aufzeichnung der echten DWD-Datei, das Format der Warnungen folgt der Bright-Sky-Dokumentation.

Siehe auch: [Push-Benachrichtigungen](Push-Benachrichtigungen)
