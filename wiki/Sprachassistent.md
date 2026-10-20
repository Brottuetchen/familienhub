# Sprachassistent (Home Assistant Assist)

Sprecht mit dem Hub über **Home Assistants Assist** (Handy, Voice Preview Edition, jeder Satellit):

- "Setz Milch und Brot auf die Einkaufsliste"
- "Was steht auf der Einkaufsliste?"
- "Was gibt es heute zu essen?"
- "Was steht morgen an?"
- "Erinnere mich um 18 Uhr an Oma anrufen"
- "Neue Aufgabe Blumen gießen für Anna"

Home Assistant versteht den Satz (eigene Sätze, *custom sentences*) und ruft kleine, stabile Schnittstellen des Hubs unter `/api/voice` auf. Der Hub erledigt die Arbeit mit den normalen Quellen und antwortet mit einem kurzen Sprechtext. Deutsch und Englisch werden unterstützt.

Der Aufbau ist in den **Einstellungs-Dateien von Home Assistant** (YAML) zu erledigen. Die vollständigen Vorlagen (`rest_command`, `intent_script`, Sätze auf Deutsch und Englisch) stehen in der Referenz und sind zu lang für dieses Wiki: **[Voice assistant](https://github.com/Brottuetchen/familienhub/blob/main/docs/voice-assistant.md)** (Englisch, Code deutsch/englisch).

## Ablauf in vier Schritten

1. **Zugang in der App erstellen:** *Mehr → Zugänge für Assistenten → Neuer Zugang.* Benennt ihn (z. B. "Home Assistant"). Er entsteht mit der Vorlage *Sprache* (genau sechs Berechtigungen, sonst nichts). Der Schlüssel (`fhp_…`) wird **nur einmal** angezeigt; der Hub speichert nur einen Hash. Ein Schlüssel handelt **als die Person, die ihn erstellt hat**: Erinnerungen und Aufgaben gehören ihr, und es gelten ihre Rollen. Widerrufen geht jederzeit in demselben Bildschirm.
2. **Schlüssel in Home Assistant ablegen:** in der `secrets.yaml` eine Zeile `familienhub_auth: "Bearer fhp_HIER_DEN_SCHLUESSEL"`.
3. **`rest_command` und `intent_script`** in die `configuration.yaml` übernehmen (Vorlage in der Referenz) und `hub.example.org` durch die Hub-Adresse ersetzen (HTTPS, wenn von außen erreichbar).
4. **Sätze** je Sprache in `custom_sentences/de/familienhub.yaml` (und `en`) anlegen, dann Sätze neu laden (Home Assistant neu starten, *Entwicklerwerkzeuge → YAML* oder Aktion `conversation.reload`) und unter *Einstellungen → Sprachassistenten → Debug* ausprobieren.

## Was der Hub versteht

- **Einkauf:** "Milch, Brot und Eier" werden drei Einträge (getrennt bei Komma, "und", "&"); höchstens 20 pro Aufruf. Sie landen in der Einkaufsliste-Quelle des Hubs, genau wie in der App.
- **Aufgaben:** Die Person ist optional (Vorname, Anzeigename oder Benutzername einer aktiven Person, keine Gäste); "mich/mir" = Schlüssel-Besitzer. Unbekannte oder mehrdeutige Namen werden nicht geraten. **Kinder und Gäste können keine Aufgaben anlegen**, wie in der App.
- **Erinnerungen** sind immer privat für den Schlüssel-Besitzer. Zeitangaben deutet der Hub in seiner Zeitzone: "um 6" = die *nächste* 6 Uhr; "in 20 Minuten", "morgen um halb sieben", "am Freitag um 15 Uhr", "viertel vor sieben". Wurde die Zeit nicht verstanden oder ist sie vorbei, legt er nichts an und sagt es.
- **Essen und Termine:** für heute, morgen oder ein Datum.

## Probleme

- **Assist sagt, der Hub sei nicht erreichbar:** Adresse und `Authorization`-Secret prüfen; denselben Aufruf mit `curl` vom Home-Assistant-Rechner testen.
- **403 "lacks scope":** Der Schlüssel hat die Berechtigung nicht; neuen mit der Vorlage *Sprache* anlegen.
- **Nichts passiert bei einem Satz:** Er wurde nicht erkannt. Unter *Sprachassistenten → Debug* testen; Platzhalter brauchen den `lists`-Block.
- **Erinnerung zur falschen Stunde:** "um 6" ist die *nächste* 6 Uhr. Sagt "morgens um 6" oder "morgen um 6" und prüft die Zeitzone (`TIMEZONE`) des Hubs.

Ein Schlüssel mit Berechtigungen darf **nur** `/api/voice/…` aufrufen; alles andere antwortet mit 403.

Referenz (Englisch): [Voice assistant](https://github.com/Brottuetchen/familienhub/blob/main/docs/voice-assistant.md)
