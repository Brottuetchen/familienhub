# Plugin: Tandoor

Macht euren eigenen [Tandoor-Recipes](https://tandoor.dev)-Server zur **Rezeptquelle** in Familienhub. In der App steht er neben Mealie und Cookidoo als **Rezept aus Tandoor**:

- **Suchen** (mindestens 3 Buchstaben), mit Vorschaubild und Kochzeit
- **Schnellansicht:** Bild, Portionen, Arbeits- plus Wartezeit, Zutaten, Schritte, Link zum Rezept in Tandoor
- **Planen:** Rezept auf einen Tag des Essensplans legen
- **Zutaten auf die Einkaufsliste**

Voraussetzung: **Familienhub 1.0.0-beta.3 oder neuer** (auf älteren Hubs lehnt die Installation ab). Ausführlich (Englisch): [README des Plugins](https://github.com/Brottuetchen/familienhub-store/tree/main/plugins/tandoor)

## Einrichten

1. In Tandoor: **Einstellungen → API** → Token erstellen (Name z. B. "Familienhub"; **Lese-Rechte genügen**, das Plugin schreibt nie nach Tandoor).
2. In Familienhub: *Verwaltung → Store → Tandoor Recipes → Installieren*, Einstellungen eintragen, **Verbindung testen**.

| Einstellung | Pflicht | Bedeutung |
|---|---|---|
| `TANDOOR_URL` | ja | Adresse von Tandoor, wie der **Hub** sie erreicht, z. B. `http://tandoor.lan:8080` (ohne `/api`) |
| `TANDOOR_TOKEN` | ja | der API-Token (verschlüsselt gespeichert) |

Der **Verbindungstest** fragt Tandoor nach einem Rezept und meldet z. B. *"Connected, 42 recipes"*; er unterscheidet: nicht erreichbar, Token abgelehnt (401/403), keine Tandoor-API an dieser Adresse, sonstige Fehler.

## So werden Rezepte übernommen

- Zeit = Arbeitszeit + Wartezeit.
- Zutaten: eine Zeile je Zutat in Schrittreihenfolge (z. B. `200 ml Sahne`, `salt (to taste)`); Gruppen-Überschriften entfallen.
- Schritte: der Anleitungstext jedes Schritts; `{{ scale(40) }}`-Platzhalter werden zur Zahl. Eingebettete Rezepte werden zwei Ebenen tief aufgelöst.
- **Einkaufsliste:** Der Hub legt die Zutaten auf **seine eigene** Einkaufsliste und führt gleiche zusammen, wie bei Mealie. Tandoors eigene Einkaufsliste bleibt unberührt.
- **Bilder** laufen über den Hub (nur Rezept-Bilder, kein offener Proxy); Tandoor muss dafür vom Hub erreichbar sein. Der Token geht nur an eure Tandoor-Adresse.

## Datenschutz und Verhalten

Das Plugin kontaktiert nur die Tandoor-Adresse, die ihr einträgt (kein Tracking, keine Dritten). Es nutzt den **gemeinsamen Haushalts-Token**: Alle Familienmitglieder, die den Essensplaner nutzen dürfen, können die Tandoor-Rezepte lesen. Ist Tandoor langsam oder aus, meldet die App "nicht erreichbar" für diese Suche; Suchergebnisse werden 60 s, Rezepte 5 Minuten zwischengespeichert.

## Grenzen

- Es wird nach dem **Namen** gesucht, nicht nach Zutaten oder Schlagwörtern.
- Nach einem Hub-Neustart kostet das erste Bild jedes geplanten Rezepts eine zusätzliche Abfrage.
- Es wird der Space des Token-Benutzers verwendet; es gibt keine Space-Einstellung.
- Anleitungen sind Klartext (Tandoors Markdown wird nicht dargestellt).
- **Nicht gegen einen echten Tandoor-Server und keinen laufenden Hub getestet** (die Tests simulieren Tandoor mit den Antwortformaten der API). Unbestätigt: die genauen Felder eurer Tandoor-Version, ob `/media/` bei euch öffentlich ist oder den Token braucht, und der Installationsablauf. Bitte Abweichungen melden.

Siehe auch: [Rezepte importieren](Rezepte-importieren) · [Store: Plugins und Themes](Store-Plugins-und-Themes)
