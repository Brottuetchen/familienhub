# Rezepte importieren

Ein Rezept von einer Webseite in euer Rezeptbuch holen, ohne abzutippen.

## So geht's

1. In der App: *Essen → Rezeptbuch* → **Link-Symbol**.
2. Die Adresse der Rezeptseite einfügen und **Rezept lesen** tippen.
3. Der Hub holt die Seite selbst und liest die strukturierten Rezeptdaten (schema.org `Recipe` als JSON-LD, ersatzweise Microdata).
4. Ihr bekommt das Rezept im normalen Editor: Titel, Bild, Portionen, Zeit, Zutaten, Schritte und Quellen-Link. **Prüfen, bei Bedarf ändern, dann Speichern.** Vorher wird nichts gespeichert.
5. Danach ist es ein normales Hub-Rezept: auf einen Tag planen, Zutaten auf die Einkaufsliste.

## Gut zu wissen

- Seiten **ohne Rezeptdaten** zeigen eine Meldung, es wird nichts gespeichert.
- Zeiten kommen aus ISO-8601-Angaben (`PT1H30M`); fehlt die Gesamtzeit, werden Vorbereitung und Kochen addiert. Abschnitte in den Schritten behalten ihre Überschriften.
- Das **Bild** bleibt ein Link zur Quellseite und wird nicht in den Hub kopiert. Entfernt die Seite das Bild, zeigt das Rezept keines mehr.
- Rezepte anlegen oder ändern dürfen Personen ab der Rolle **Partner**.
- **Sicherheit:** Der Hub ruft die Adresse selbst ab, deshalb nur `http`/`https` auf Standard-Ports, 10 Sekunden Zeitlimit, höchstens 2 MB und 4 Weiterleitungen; interne und private Adressen sind gesperrt.

## Aus dem Browser teilen

Die **Web-App (PWA)** meldet sich als Teilen-Ziel an. Nach der Installation kann "Teilen" im Browser eine Rezeptseite an Familienhub schicken, was "Von Link importieren" mit der Adresse öffnet. Das hängt vom Browser ab (Chrome unter Android unterstützt es für installierte PWAs). Ein Teilen-Eintrag in der nativen Android-App gehört **noch nicht** dazu.

## Andere Rezeptquellen

Rezepte können auch aus Mealie, Cookidoo oder [Tandoor](Plugin-Tandoor) kommen.

Referenz (Englisch): [Recipe import](https://github.com/Brottuetchen/familienhub/blob/main/docs/recipe-import.md)
