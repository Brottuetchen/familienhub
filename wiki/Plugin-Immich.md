# Plugin: Immich ("An diesem Tag")

Zeigt Fotos von diesem Tag in früheren Jahren auf dem **Heute**-Bildschirm ("Vor 3 Jahren"), aus eurer selbst gehosteten [Immich](https://immich.app)-Fotobibliothek.

Voraussetzung: **Familienhub 1.0.0-beta.3 oder neuer**. Ausführliche Beschreibung (Englisch): [README des Plugins](https://github.com/Brottuetchen/familienhub-store/tree/main/plugins/immich)

## Was es tut

- Eine Karte pro Foto (bis zur eingestellten Anzahl, Standard 3), mit Hinweis, wie viele Jahre es her ist, ggf. der Beschreibung aus Immich und dem Datum. Antippen öffnet das Foto in Immich, aber nur, wenn eure Immich-Adresse mit `https://` beginnt.
- Quelle sind Immichs eigene "An diesem Tag"-Erinnerungen. Favoriten werden bevorzugt, verschiedene Jahre vor einem zweiten Foto desselben Jahres.
- Keine Karte, wenn es nichts gibt oder Immich nicht antwortet. Der Heute-Bildschirm zeigt deswegen nie einen Fehler.
- Nur Fotos, keine Videos. Das Ergebnis wird für den Tag zwischengespeichert.

## Was du brauchst

- Eine laufende Immich-Instanz, die der **Hub** erreichen kann.
- Einen **API-Schlüssel** aus Immich.

### API-Schlüssel in Immich erstellen

1. In Immich: **Kontoeinstellungen** (Avatar oben rechts) → **API-Schlüssel**.
2. **Neuer API-Schlüssel**, Name z. B. "Familienhub".
3. Berechtigungen: Das Plugin liest nur. Mindestens `asset.read`, `asset.view`, `memory.read`, `album.read` (nur bei Album-Filter), `server.about` und `user.read`. "Alle" funktioniert auch.
4. Schlüssel kopieren (Immich zeigt ihn nur einmal) und im Plugin eintragen.

Das Plugin handelt als **Besitzer des Schlüssels**: Es sieht dessen Bibliothek samt geteilter Fotos. Nehmt den Schlüssel der Person (oder eines Familienkontos), deren Fotos die Familie sehen soll, und nutzt Album-Filter, wenn nur manche Fotos erscheinen sollen.

## Einstellungen

| Einstellung | Pflicht | Bedeutung |
|---|---|---|
| `IMMICH_URL` | ja | Adresse von Immich, wie der **Hub** sie erreicht, z. B. `https://photos.example.org` oder `http://immich:2283`. Ohne `/api` am Ende. |
| `IMMICH_API_KEY` | ja | Der API-Schlüssel (verschlüsselt gespeichert) |
| `IMMICH_ALBUM_IDS` | nein | Komma-getrennte Album-IDs (letzter Teil der Album-Adresse `/albums/<id>`). Leer = ganze Bibliothek |
| `IMMICH_INCLUDE_ARCHIVED` | nein | auch archivierte Fotos (Standard aus) |
| `IMMICH_MAX_PHOTOS` | nein | 1 bis 5 Karten pro Tag, Standard 3 |

## Verbindungstest: typische Meldungen

- `Connected as Alex, Immich 1.135.3`: alles gut.
- `Immich rejected the API key (wrong key or missing permissions: user.read)`: Schlüssel falsch oder Berechtigung fehlt.
- `This address does not look like Immich. Check the address (no /api at the end)`: Adresse prüfen.
- `Immich is not reachable…` / `Immich did not answer in time…`: Adresse und Netzwerk zwischen Hub und Immich prüfen.

## Datenschutz

Fotos bleiben in Immich. Der Hub reicht nur **Vorschaubilder** der heute ausgewählten Fotos an angemeldete Familienmitglieder weiter; die App erfährt weder Immich-Adresse noch Schlüssel. **Alle angemeldeten Personen (auch Kinder und Gäste) sehen dieselben Karten**: Wählt Schlüssel und Alben entsprechend. Das Plugin schreibt nichts nach Immich und kontaktiert nur die Adresse, die ihr eintragt.

## Grenzen

- "Heute" ist das Datum des Hub-Servers; der 29. Februar passt nur in Schaltjahren.
- Mit Album-Filter oder archivierten Fotos sucht das Plugin nach Datum (mehr Anfragen, bis 15 Jahre zurück).
- Jedes Foto ist eine eigene Karte; im Heute-Editor lassen sie sich ausblenden oder verschieben.
- Antwortet Immich nicht innerhalb von etwa 3,5 Sekunden, gibt es bis zum nächsten Versuch (nach zwei Minuten) keine Karte.
- **Nur gegen simulierte Antworten getestet, nicht gegen einen echten Immich-Server.** Immichs API ändert sich zwischen Versionen; das Plugin folgt der dokumentierten API von Immich 1.1xx/2.x. Bitte Abweichungen melden.

Siehe auch: [Store: Plugins und Themes](Store-Plugins-und-Themes) · [Fehlerbehebung](Fehlerbehebung)
