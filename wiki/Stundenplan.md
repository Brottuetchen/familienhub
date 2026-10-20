# Stundenplan für Kinder

Ein Wochenplan je Kind: Unterricht, Sport, Musik und Verein. Zu finden unter *Mehr → Stundenplan* und als Karte auf *Heute* ("Mia: Schule bis 13:15, Schwimmen 16:00").

## Wer darf was

| Rolle | Stundenplan |
|---|---|
| Admin, Partner | sehen jedes Kind, anlegen, ändern, löschen, kopieren, Einstellungen |
| Kind | sieht nur den eigenen, kann nichts ändern |
| Gast | kein Zugriff |

"Kind" sind die Konten mit der Rolle *Kind*. Gibt es noch keins, legt eins an ([Personen und Rollen](Personen-und-Rollen)).

## Eintragen

Die Ansicht ist eine Tagesliste (Montag bis Sonntag). Ein Eintrag hat Titel, Art (Schule, Sport, Musik, Verein, Sonstiges), Beginn, Ende, optional Ort und den Wochentag.

- **Tag kopieren:** Der Kopier-Knopf neben dem Wochentag kopiert den Tag auf angehakte Tage (vorhandene Einträge dort werden ersetzt).
- **Woche kopieren:** Bei A/B-Wochen im Menü *Woche A nach B kopieren* (und zurück).

## A/B-Wochen

Wechselt der Stundenplan eurer Schule alle zwei Wochen? *Menü → Einstellungen*: **A/B-Wochen** einschalten und einen beliebigen Tag in einer **A-Woche** wählen. Danach wechseln die Wochen automatisch. Einträge sind *Jede Woche*, *A-Woche* oder *B-Woche*.

## Schulferien

Unterricht (Art *Schule*) wird an Ferientagen ausgeblendet; Sport, Musik und Verein bleiben.

1. Ein Admin legt unter *Verwaltung → Kalender-Abos* den Schulferien-Kalender (ICS) eures Bundeslands an.
2. Ein Elternteil wählt unter *Stundenplan → Menü → Einstellungen* diesen Kalender als **Ferienkalender**. Die Wahl gilt für alle Kinder.

Ohne Ferienkalender oder wenn das Abo nicht erreichbar ist, wird der Unterricht einfach angezeigt.

## Stundenplan aus der Schul-App (Plugin)

Ein Plugin kann Stunden eines Kindes liefern, **mit Ausfall und Vertretung**. Das offizielle Plugin dafür ist [WebUntis](Plugin-WebUntis). Die Quelle wählt ein Elternteil je Kind unter *Stundenplan → Menü → Stundenplan-Quellen*. Das Kind bekommt dann zusätzlich zum **Wochenplan** (eure Einträge) die Ansicht **Diese Woche** mit echten Daten: Ausfälle durchgestrichen, Vertretungen hervorgehoben.

An Tagen, für die das Plugin Stunden liefert, **ersetzen** sie eure eigenen Schul-Einträge; Sport, Musik und Verein bleiben. Liefert das Plugin nichts (Ferien, Wochenende, nicht erreichbar), gelten eure Einträge wie vorher.

Tage und Zeiten richten sich nach der Zeitzone des Hubs.

Referenz (Englisch): [Timetable](https://github.com/Brottuetchen/familienhub/blob/main/docs/timetable.md)
