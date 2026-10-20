# Plugin: Grocy

Verbindet euer selbst gehostetes [Grocy](https://grocy.info) mit Familienhub: Grocy kann die **Einkaufsliste** des Hubs sein, *Heute* zeigt **bald ablaufende Vorräte**, und Eltern bekommen **eine Mitteilung pro Produkt**, bevor es abläuft.

Voraussetzung: **Familienhub 1.0.0-beta.3 oder neuer**. Ausführlich (Englisch): [README des Plugins](https://github.com/Brottuetchen/familienhub-store/tree/main/plugins/grocy)

## Was es tut

- **Einkaufsliste:** Wählt Grocy unter *Mehr → Verwaltung → Quellen je Bereich → Einkauf*. Ab dann nutzt alles im Hub diese Liste: Einkaufsbildschirm, [Vorlagen](Vorlagen), Rezept-Zutaten und der [Sprachassistent](Sprachassistent) ("Milch auf die Einkaufsliste"). **Ohne diese Auswahl wird die Liste des Plugins nicht benutzt.**
  - Passt der Name zu einem aktiven Grocy-Produkt (Groß-/Kleinschreibung egal), wird ein Produkt-Eintrag angelegt, sonst Freitext. Eine reine Zahl als Beschreibung ist die Menge, anderes (`500 g`) landet in der Notiz. Doppelte offene Einträge gibt es nicht.
- **Karte "Vorräte"** auf Heute: z. B. "Läuft bald ab: Joghurt (morgen), Milch (2 Tage)", "Abgelaufen: …", "Fehlt: 3 Produkte". Keine Karte, wenn nichts relevant oder Grocy nicht erreichbar ist.
- **Tägliche Mitteilung an Eltern** (Admins und Partner): Ab `GROCY_NOTIFY_HOUR` eine Mitteilung pro Produkt und Datum für Produkte, die innerhalb von `GROCY_DUE_DAYS` Tagen ablaufen (Kategorie *Plugins*).
- **Optional:** Mit `GROCY_ADD_MISSING` ruft der Hub einmal täglich Grocys "Fehlende Produkte auf die Einkaufsliste" auf.

## API-Schlüssel in Grocy erstellen

Grocy → Zahnrad → **API-Schlüssel verwalten** → **Hinzufügen** → Schlüssel in den Hub kopieren. Der Schlüssel hat die Rechte des Grocy-Benutzers, der ihn erstellt hat: nehmt einen Benutzer, der die Einkaufsliste bearbeiten darf.

## Einstellungen

| Einstellung | Standard | Bedeutung |
|---|---|---|
| `GROCY_URL` (Pflicht) | | Adresse von Grocy, wie der Hub sie erreicht, z. B. `http://grocy.lan:9283`, ohne `/api` |
| `GROCY_API_KEY` (Pflicht, geheim) | | der API-Schlüssel |
| `GROCY_SHOPPING_LIST_ID` | 1 | welche Grocy-Einkaufsliste (1 = Standardliste) |
| `GROCY_DUE_DAYS` | 2 | "Läuft bald ab" = innerhalb dieser Tage (0 bis 365) |
| `GROCY_NOTIFY` | an | tägliche Mitteilung an Eltern |
| `GROCY_NOTIFY_HOUR` | 8 | Uhrzeit (0 bis 23, Hub-Zeit), ab der gemeldet wird |
| `GROCY_ADD_MISSING` | aus | fehlende Produkte täglich auf die Liste |

**Verbindung testen** prüft die eingegebenen Werte vor dem Speichern: Meldung *"Connected, Grocy 4.x"* und ob die Einkaufsliste mit dieser ID existiert.

## Daten

Das Plugin kontaktiert **nur die Adresse, die ihr bei `GROCY_URL` eintragt**. Es liest Systeminfo, Einkaufslisten, Produkte, Einheiten und den Vorratsüberblick; es schreibt Einkaufslisten-Einträge (anlegen, abhaken, umbenennen, löschen) und – nur mit `GROCY_ADD_MISSING` – "Fehlende Produkte hinzufügen". Bestand, Produkte und Rezepte ändert es nie. Alles wird für den Haushalt gelesen, nicht je Person; ein gemeinsamer Schlüssel genügt.

## Grenzen

- Produkt-Einträge benennt man in Grocy um, nicht im Hub.
- Produktnamen werden **exakt** (ohne Groß-/Kleinschreibung) verglichen, kein unscharfes Suchen: "Milch" findet "Milk" nicht.
- Listen und Karte sind bis zu 60 Sekunden zwischengespeichert; Änderungen in Grocy erscheinen entsprechend später.
- Produkte ohne Haltbarkeitsdatum oder "läuft nie ab" werden ignoriert. Der Job läuft alle 30 Minuten; war der Hub zur eingestellten Stunde aus, kommt die Meldung später am selben Tag.
- Der Hub erlaubt höchstens 20 Plugin-Pushes pro Stunde.
- **Nur gegen simulierte Grocy-Antworten getestet (62 Tests), nicht gegen einen echten Grocy-Server.** Insbesondere die Formate von `/api/stock/volatile` und `/api/objects/shopping_list` sowie die Fehlercodes für fehlende Einträge (404 angenommen) sollten an einer echten Instanz bestätigt werden.

Siehe auch: [Vorlagen](Vorlagen) · [Store: Plugins und Themes](Store-Plugins-und-Themes)
