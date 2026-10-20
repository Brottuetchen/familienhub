# Kindermodus und Belohnungen

Eingebaute Motivation für Kinder, ohne Habitica: Eltern vergeben **Sterne** für Aufgaben und legen **Belohnungen** mit Sternpreis fest. Kinder sammeln Sterne und wünschen sich Belohnungen; Eltern geben frei oder lehnen ab. Die Funktion heißt in der App **Sterne** (*Mehr → Sterne*).

## So funktioniert es

1. **Sterne an Aufgaben.** Ein Elternteil (Rolle Partner oder Admin) setzt beim Anlegen oder Bearbeiten einer Aufgabe das Feld "Sterne für diese Aufgabe". Wer die Aufgabe erledigt, bekommt die Sterne.
2. **Belohnungen** legen Eltern unter *Mehr → Sterne* an, mit Sternpreis (z. B. "30 Min. Medienzeit" oder "1 € Taschengeld"). Eine ausgeblendete Belohnung behält die Historie.
3. **Wunsch.** Ein Kind tippt bei einer Belohnung, die es sich leisten kann, auf *Wünschen*. Die Sterne werden **reserviert** (nicht doppelt ausgebbar), und alle Eltern bekommen eine Mitteilung (Kategorie *Sterne und Belohnungen*). Ein Elternteil **bewilligt** (Sterne werden abgebucht) oder **lehnt ab** (Reservierung wird freigegeben). Ein Kind kann einen offenen Wunsch zurückziehen.
4. **Verlauf.** Jedes Kind sieht den eigenen Verlauf; Eltern sehen alle, können Bonus oder Abzug geben und sehen die Kontostände.
5. **Optional: Erledigtes bestätigen.** Mit *Erledigte Aufgaben bestätigen* (unter *Mehr → Sterne*, nur Eltern) bleiben Sterne von Kindern *wartend*, bis ein Elternteil bestätigt; nur bestätigte Sterne zählen. Eltern können auch ablehnen. Sterne von Erwachsenen werden nie zurückgehalten.
6. **Heute.** Die Karte *Sterne* zeigt Kontostand und nächste Belohnung mit Fortschrittsbalken (Eltern sehen auch, wie viele Entscheidungen warten). Sie steht standardmäßig ganz unten: Verschiebt sie für ein Kind nach oben (*Heute* anpassen).

## Welche Aufgaben-Quellen zählen

- **Aufgaben im Hub:** Sterne beim Anlegen oder Bearbeiten; eine rotierende Haushaltsaufgabe gibt ihre Sterne an die nächste Runde weiter.
- **Externe Aufgaben (z. B. Nextcloud):** Sterne lassen sich in der App setzen; sie liegen nur im Hub. **Sterne gibt es nur, wenn die Aufgabe über den Hub (App) erledigt wird.** Erledigt ihr sie in einer anderen App, erfährt der Hub nichts und zahlt nichts aus.
- **Habitica** hat eigene Belohnungen und ist ausgenommen.
- Eine wiederkehrende externe Aufgabe zahlt einmal pro Vorkommen; doppelt erledigen zahlt nicht doppelt.

## Regeln, die der Server erzwingt

- Nur Eltern (Partner, Admin) setzen Sterne, verwalten Belohnungen, entscheiden über Wünsche und Bestätigungen und ändern Kontostände. Ein Kind sieht nur seine eigenen Daten, wünscht und zieht eigene Wünsche zurück.
- Niemand entscheidet über eigene Wünsche, bestätigt eigene Sterne oder ändert das eigene Konto.
- Das Guthaben wird nie negativ und nie kleiner als das, was offene Wünsche reservieren; zwei Eltern, die dasselbe genehmigen, erzeugen nur eine Buchung.

## Belohnung mit Bildschirmzeit (Internet freischalten)

Ein **Plugin** kann Aktionen anbieten, die bei der Genehmigung laufen. Das offizielle Plugin [Bildschirmzeit](Plugin-Screentime) schaltet bei Genehmigung z. B. das Tablet für 30 Minuten frei und sperrt es danach wieder.

1. Plugin installieren und einrichten ([Plugin: Bildschirmzeit](Plugin-Screentime)).
2. Beim Anlegen oder Bearbeiten der Belohnung im Auswahlfeld **Aktion (Plugin)** die Aktion wählen und ihre Felder ausfüllen (Gerät, Minuten).
3. Genehmigt ein Elternteil den Wunsch, wird **zuerst** genehmigt und gebucht; **danach** läuft die Aktion. Ihr Ergebnis sieht das genehmigende Elternteil, das Kind erfährt, wenn es geklappt hat. **Eine fehlschlagende Aktion macht die Genehmigung nie rückgängig.**

## Tipps

- Kinder brauchen ein Konto mit der Rolle **Kind**, siehe [Personen und Rollen](Personen-und-Rollen).
- Startet mit wenigen, klar benannten Belohnungen und kleinen Preisen.

Referenz (Englisch): [Kids mode](https://github.com/Brottuetchen/familienhub/blob/main/docs/kids-mode.md) · [Reward actions](https://github.com/Brottuetchen/familienhub/blob/main/docs/plugins.md#reward-actions-kids-mode)
