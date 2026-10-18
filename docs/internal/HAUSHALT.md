# Haushalt mit Rotation (#29)

## Bedienung

Unter **Aufgaben → + Aufgabe → Haushaltsrotation** Titel eingeben, Wiederholung wählen
und Personen in der gewünschten Reihenfolge antippen. Die Zahlen zeigen die Reihenfolge;
erneutes Antippen entfernt eine Person. Der erste Termin ist vorbelegt auf heute, lässt sich
aber über die Fälligkeit ändern. Die erste ausgewählte Person beginnt.

Die Aufgaben erscheinen unter **Familie**, mit zuständiger Person und Wiederholung.
Details zeigen die vollständige Rotation. Das sichtbare Kästchen an jeder Aufgabe (alternativ
nach rechts wischen) erledigt den aktuellen Termin und erzeugt genau einen Nachfolger für
die nächste Person. Während der Anfrage sind weitere Abschlussaktionen gesperrt; bei Fehlern
bleibt die Aufgabe erhalten. Nach links wischen löscht nach
Bestätigung den aktuellen Termin und beendet damit die Fortsetzung.

Voraussetzung: eigener Nextcloud-Zugang und eine als `family` zugeordnete, beschreibbare
Aufgabenliste. Andere Personen brauchen ihre eigene Nextcloud-Freigabe und Zuordnung.
Es werden keine fremden persönlichen Zugangsdaten verwendet; private und ausgeblendete
Listen werden für Haushaltsrotation weder benutzt noch zusätzlich veröffentlicht.

## Bestehende Aufgaben-API

Kein neuer Aufgabenbestand, Scheduler oder Fremddienst: VTODOs bleiben in Nextcloud.
`POST /api/tasks` akzeptiert zusätzlich zum bisherigen Format:

```json
{
  "title": "Müll rausbringen",
  "due": "2026-10-16",
  "list": "family",
  "recurrence": "weekly",
  "rotation": [1, 2],
  "habitica": false
}
```

Die IDs sind beispielhafte Hub-User-IDs. Erlaubte Muster entsprechen den bestehenden
Erinnerungen: `daily`, `weekdays`, `weekly`, `monthly`. Eine Rotation enthält 1–50 verschiedene,
aktive Nicht-Gast-Nutzer; Fälligkeit und nichtleerer Titel (maximal 200 Zeichen) sind Pflicht.
Ein zusätzliches `assignee_id` muss, falls angegeben, der ersten Person entsprechen.
Ungültige Eingaben liefern 422; fehlender eigener Zugang bzw. fehlende Familienlisten-Zuordnung
409; nicht erreichbare Schreiboperationen 503. Fehlendes Schreibrecht beim Anlegen bleibt 409.

Erstellen, Ändern und Löschen ist für `admin`/`partner` vorgesehen. Erledigen dürfen Erwachsene
sowie das jeweils zuständige Kind, nicht Gäste. Die bestehenden CalDAV-Leserechte bleiben
maßgeblich. `GET /api/tasks?view=family` und die üblichen Detailantworten enthalten zusätzlich
`recurrence`, `rotation`, `habitica`; Abschluss bleibt `POST /api/tasks/{uid}/complete`.

## Fortsetzung und Grenzen

- Rotation schreitet **beim Erledigen im Hub** fort, nicht beim Ablauf einer Woche. Die nächste
  Fälligkeit wird mit der bestehenden Wiederholungslogik aus der bisherigen Fälligkeit berechnet,
  nicht aus dem Abschlusszeitpunkt. Überfällige Termine werden nicht übersprungen.
- Datum ohne Uhrzeit bleibt DATE; Uhrzeiten folgen der konfigurierten lokalen Zeitzone auch
  über die Zeitumstellung. Monatliche Termine werden auf den letzten gültigen Tag gekürzt,
  entsprechend der bestehenden Wiederholungslogik.
- Nachträglich deaktivierte/entfernte Personen werden beim Wechsel übersprungen. Gibt es keine
  aktive Person mehr, bleibt der Abschluss erfolglos und wiederholbar.
- Wiederholung/Rotation stehen in `X-FAMILIENHUB-*` am VTODO. Ein DB-Abschlussbeleg mit eindeutiger
  UID serialisiert gleichzeitige Abschlüsse; die deterministische Nachfolger-UID gilt auch über
  verschiedene Nextcloud-Freigabe-URLs. Wiederholte Abschlüsse erzeugen keinen weiteren Termin.
- Erst wird der Nachfolger gespeichert, dann der bisherige Termin abgeschlossen. Scheitert ein
  Schritt, lässt sich derselbe Abschluss wiederholen; ein schon vorhandener Nachfolger bleibt
  unverändert. Nextcloud und Hub-DB haben keine gemeinsame Transaktion: nach einem Teilfehler
  können vorübergehend beide Termine offen sichtbar sein. Der erneute Abschluss repariert dies.
- Abschluss direkt in Nextcloud/iOS startet derzeit **keine** Hub-Rotation. Keine neue Polling-
  oder Webhook-Infrastruktur. Rotation ändern: aktuellen Termin löschen und neu anlegen.
- Keine neue automatische Erinnerung/Push-Planung, keine Haussteuerung (#45 ist separat).
- #47 ersetzt den alten impliziten Belohnungshook: Nextcloud-Haushaltsabschlüsse rufen Habitica niemals auf.
  Das alte API-Feld `habitica` bleibt für kompatible Anfrageformen bekannt, autorisiert aber keinen
  Export/Score und wird bei neu angelegten Rotationsterminen auf `false` gesetzt. Historische
  VTODO-Felder sind kein Schreibrecht auf einen anderen Anbieter. Native Habitica-Aufgaben und
  ihre eigenen Score-/Undo-/Reward-Aktionen werden ausdrücklich dort ausgewählt und bedient
  (`docs/internal/AUFGABENPROVIDER.md`).

Migration `a7b8c9d0e1f2` ergänzt nur `task_completions(uid)` und hat einen Downgrade.
Die Belege enthalten keine Titel, Notizen, Personen oder Zugangsdaten und bleiben für den
Replay-Schutz erhalten. Ein Downgrade entfernt diesen Schutz für alte Abschlüsse.
