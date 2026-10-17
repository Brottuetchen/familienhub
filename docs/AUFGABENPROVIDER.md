# Aufgabenprovider: Nextcloud und Habitica (#47)

## Grundsatz und Bedienung

Der Hub bündelt Fachsystemplugins, statt deren Aufgaben als eigene Fachobjekte zu führen.
Nextcloud und Habitica laufen allein oder nebeneinander. Es gibt keine automatische
Nextcloud↔Habitica-Spiegelung, keinen Export gewöhnlicher Nextcloud-Aufgaben und keine
CalDAV-Schattenobjekte für Habitica. Die Registry wurde erweitert, nicht durch eine zweite
Plugin-/Syncengine ersetzt. Der Kern darf einen anbieterspezifischen Refresh/Sync anstoßen;
Mapping, Konfliktbehandlung, Daten und Fachaktionen bleiben im Plugin/Fachsystem.

In **Aufgaben** öffnet das Kontosymbol den persönlichen Habitica-Zugang. Der Server kommt aus
der Betreiberkonfiguration, nicht aus einer beliebigen vom Nutzer eingegebenen URL. User-ID
und API-Zugang werden gegen `/api/v3/user` geprüft, verschlüsselt und nie zurückgegeben.
„Verfügbare eigene Aufgaben“ zeigt nur durch Habitica bestätigte eigene Remoteobjekte.
Eine Auswahl bedeutet `(Anbieter, eigenes Konto, Remote-ID)`; sie legt kein weiteres
Aufgabenobjekt an und importiert nicht automatisch sämtliche Aufgaben. Die Auswahl funktioniert
auch im zunächst schreibgeschützten Betrieb. Bereits ausgewählte eigene Aufgaben erscheinen
neben Nextcloud in Aufgaben/Heute. Pull-to-refresh bzw. die Aktualisierung in der Kontomaske
liest externe Änderungen aus dem jeweiligen Fachsystem erneut.

Das Plus in Aufgaben bietet die konfigurierten eigenen Konten. Ohne Nextcloud kann man
Habitica-Aufgaben anlegen, bearbeiten und – nach Betreiberfreigabe – nativ bedienen.
Nextcloud behält seine vorhandene Haushalts-, Listen-, Zuweisungs-, Wiederholungs- und
Rotationsbedienung. Der Habitica-Editor ergänzt nur erforderliche Funktionalität im bestehenden
Design. Das angekündigte Designpapier und ein späterer Designumbau sind nicht Teil von #47.

## Native Habitica-Funktionen

- Typen: Habit, Daily, Todo, Reward; Titel/Text, Notizen, Alias, Attribut, native Schwierigkeit,
  eigene Tags (aus den nativen Optionen), Reminders.
- Habits: positive/negative Richtung unabhängig, täglicher/wöchentlicher/monatlicher Reset.
  `+`/`−` werden serverseitig gegen Typ und erlaubte Richtung geprüft; keine generische Checkbox.
- Dailies: tägliche/wöchentliche/monatliche/jährliche Frequenz, `everyX`, Startdatum,
  alle sieben Wochentage, Monats-/Wochenpositionen, Streak und Checklistenkollaps.
- Todos: Datum (einschließlich Löschen des Datums), Checklistenkollaps.
- Rewards: nativer GP-Preis und „Belohnung einlösen“. Kein `down`, kein Refund.
- Checklisten für Daily/Todo: hinzufügen, Text ändern, löschen, gezielt abhaken.
  Unterpunkte werden mit einem ausdrücklich gewünschten Zielzustand per nativem PUT
  geändert, nicht mit einem blind wiederholbaren Toggle oder Parent-Score. Reihenfolge
  wird unter Erhalt von IDs und unbekannten Unterfeldern angepasst.
- Daily/Todo: native Erledigung bzw. erlaubtes Rückgängigmachen. Habitica verantwortet
  Punkte, Undo-Semantik, Tageswechsel, Reset und Wiederholungen. Der Hub berechnet sie nicht.
- Eigene vorhandene Tags werden mit Namen angeboten und Aufgaben zugeordnet oder entfernt.
  Serverseitig wird jede verwendete Tag-ID gegen die Tags des aktuellen externen Nutzers geprüft.
  Die Tagstammdaten selbst verwaltet weiterhin Habitica; kein zusätzliches Hub-Tagsystem.
- Reminders lassen sich mit ID, Zeitpunkt und optionalem Startdatum bearbeiten. Neue Reminder
  erhalten App-UUIDv4, neue Checklisteneinträge eine Habitica-ID; bestehende IDs bleiben erhalten.
- Native Nur-Lese-Zustände (u. a. Erledigungsdatum, nächster Fälligkeitstermin, Historie und
  Zähler) bleiben sichtbar; unbekannte Properties bleiben beim minimalen PATCH unberührt.
  Der Typ vorhandener Aufgaben wird nicht heimlich konvertiert.

Neue `everyX`-Werte werden auf 1–9999 begrenzt. Historische native Sonderwerte wie 0 bleiben
beim Lesen und unveränderten Titel-PATCH unangetastet; sie werden nicht still auf 1 umgeschrieben.
Tagesbeginn und Zeitzonenoffset aus den Habitica-Optionen sind sichtbar; Einstellungen des
Fachsystems werden nicht durch eine parallele Hub-Zeit-/Recurrenceberechnung ersetzt.

## API-/Kontovertrag

Alle Aufrufe benötigen die normale authentifizierte Hub-Sitzung. Konto-IDs sind technische
Referenzen, keine Zugangsdaten: aus aktuellem Nutzer, Server und externem Konto abgeleitet.
Gleiche Remote-UIDs verschiedener Provider/Konten bleiben verschiedene Objekte; Flutter
verwendet die JSON-Identität `[provider, account, uid]` für Auswahl, Aktionen und Listenelemente.

| Endpunkt | Vertrag |
|---|---|
| `GET /api/tasks/providers` | Aktive Aufgabenplugins und **nur eigene** Kontokontexte; `configured`, `account`, `status` |
| `GET /api/tasks?provider=all` | Isolierte Aggregation aller aktiven persönlichen Provider, kein Schreib-/Exportpfad |
| `GET /api/tasks?provider=P&account=A` | Gewählten Anbieter lesen; Nextcloud-Views `mine`, `all`, `family`, `by_user` bleiben erhalten |
| `GET /api/tasks/lists?provider=P&account=A` | Anbietereigene Listen; Kontext darf nicht beim Listenwechsel verloren gehen |
| `POST /api/tasks?provider=P&account=A` | Gewählten Anbieter direkt erstellen; Habitica `native` plus eindeutige `operation_id` |
| `PATCH /api/tasks/{uid}?provider=P&account=A` | Minimales Update; Habitica `native`, `expected_version`, eindeutige `operation_id` |
| `POST /api/tasks/{uid}/complete?provider=P&account=A` | Legacy-Nextcloud-Abschluss bleibt kompatibel; Habitica verwendet die native Aktion |
| `DELETE /api/tasks/{uid}?provider=P&account=A&operation_id=…` | Gewählten Anbieter löschen; Habitica verlangt Operations-ID |
| `PUT /api/tasks/{uid}/selection?provider=P&account=A` | `{ "selected": true/false }`, nur vorhandenes, nachweislich eigenes Remoteobjekt |
| `POST /api/tasks/{uid}/actions?provider=P&account=A` | `{ "action": "…", "item_id": "…", "fields": {}, "operation_id": "UUID" }`; Validierung/Umsetzung im Connector |
| `GET/PUT /api/habitica/account` | Persönlichen verschlüsselten Zugang lesen/prüfen/ersetzen; kein Token-Readback |
| `GET /api/habitica/tasks` | Alle bestätigten eigenen nativen Aufgaben zur expliziten Auswahl |
| `GET /api/habitica/options` | Eigene Tags, Tagesbeginn/Zeitzonenoffset, aktuelle Schreibfreigabe |

`P` ist ein aktiver registrierter Provider, `A` dessen Konto aus der aktuellen Sitzung.
Kein Namen-Fallback auf den ersten globalen TasksProvider. Für alte Clients bleiben ausschließlich
Nextcloud-Aufrufe ohne `provider`/`account` kompatibel. Neue andere Einzelzugriffe verlangen
das ausdrücklich gewählte Konto (422 fehlt, 403 fremd/veraltet). `provider=all` akzeptiert kein
einzelnes Konto. Fehler eines Plugins werden isoliert und als Status/Fehler sichtbar, nicht als
leere erfolgreiche Daten oder Grund für einen Fallback-Write.

Native Aktionen: `up`, `down`, `checklist_add`, `checklist_edit`, `checklist_delete`,
`checklist_move`, `move`. Typ-/Richtungs-/Besitzprüfung erfolgt
**vor jedem** Remote-Write; Rewards kennen ausschließlich `up`. Optimistische Änderungen
prüfen Habiticas `updatedAt`; fehlt die native Version, bleibt Bearbeiten fail-closed. PATCH sendet nur
geänderte erlaubte Felder, nicht den gesamten gelesenen Zustand.

## Sicherheit, Operationsbelege und ehrliche Fehler

- Plugin aus oder Server geändert: auch direkte/warm bereits bekannte Konten dürfen nicht
  weiter schreiben. Persönliche Kontoreferenzen ändern sich beim Kontowechsel; alte Auswahl
  und technische Belege verleihen dem neuen Konto keine Rechte.
- Jeder Zugriff prüft `userId`/`_id` des tatsächlichen externen Besitzers; fremde, fehlende
  oder nicht eindeutig bestätigte Objekte werden nicht benutzt. Der Habitica-Adapter exportiert
  keine Nextcloud-Objekte. Nextclouds `habitica-…`-Legacyspiegel sind im neuen API-Schreibpfad
  bewusst schreibgeschützt (409), damit sie nicht parallel nativ gescort werden.
- Ein natives Create/Score/Delete kann Punkte/Objekte verändern, obwohl die Antwort verloren
  geht. Ein DB-Operationsbeleg (ID, Konto, Fingerprint, Ergebnis/unklarer Zustand) und atomare
  persönliche Kontosperre verhindern Replay. Gleiche ID + gleicher Inhalt liefert nur ein
  bereits gesichertes Ergebnis; gleicher Schlüssel mit anderem Inhalt und neue Aktionen während
  eines unklaren Vorgangs werden abgewiesen. Auch lesende Vorprüfungen fehlschlagend: kein POST.
- Die App sperrt gleichzeitig laufende native Aktionen im bestehenden sitzungsgebundenen
  API-Client, nicht nur im Widget. Sie folgt keinen Redirects und wiederholt native Writes nach
  Auth-Refresh nicht. Bei Timeout/Redirect/unklarem 5xx bleibt die Kontoschreibsperre sichtbar;
  Remount oder zweiter Klick umgeht sie nicht. Keine generische Offline-Schreibqueue.
- Eindeutige Ablehnungen lösen die lokale Sperre; verlorene Antworten werden **nicht** als
  Erfolg dargestellt. Ein serverseitig unklarer Vorgang blockiert weitere Remote-Writes dauerhaft und wird niemals automatisch freigegeben,
  auch nicht durch Konto-Neueingabe. Es gibt absichtlich keinen Nutzer-„erneut versuchen“- oder
  Selbstfreigabeschalter. Betreiber müssen erst Zustand/Operationsbeleg und Fachsystem prüfen;
  ohne eindeutigen Nachweis bleibt das Konto gesperrt. Ein Komfort-Reconciliation-Workflow ist
  nicht vorgetäuscht oder als zusätzliche Fachengine implementiert.
- Fernzugang wird mit einem an `SECRET_KEY` gebundenen Fernet-Schlüssel verschlüsselt.
  Verlust/Änderung dieses Schlüssels benötigt bewusstes Wiederverbinden; Klartextmigration,
  Logging des API-Tokens oder Nutzung eines beliebigen fremden Server-URLs gibt es nicht.

## Verbindlicher Single-Writer-Cutover (Betreiber, **nicht** durch diese Entwicklung ausgeführt)

Das bestehende produktive Legacy-Syncskript/sein Cronjob werden durch #47 weder gestoppt noch
verändert. Standardmäßig sind native Habitica-Writes **aus**. Lesen/Auswählen bleibt möglich.
Ein normaler Nutzer kann die Freigabe nicht mit einer Behauptung „Legacy gestoppt“ erteilen.
Die Freigabe `HABITICA_NATIVE_WRITE_ACCOUNTS` ist eine ausdrückliche Betreiberberechtigung mit
einer Liste geprüfter `HTTPS-Server|Habitica-Konto-UUID`-Paare, nicht ein Plugin-Formular-Handshake des Kontoinhabers.

Vor Freigabe **je externem Konto**:
1. Habitica-/Nextcloud-/Hub-Bestand und Legacy-Zuordnungen/Operationsbelege sichern.
2. Cron, Timer, laufende Legacy-Prozesse und weitere schreibende Brücken dieses Kontos ermitteln,
   kontrolliert stilllegen und tatsächlich fehlende weitere Läufe bestätigen. Nicht blind am
   vorhandenen Produktionssync arbeiten oder nur den Nutzer nach einer Checkbox fragen.
3. Bestand, historische Scores, abgeschlossene/gelöschte Objekte und Legacy-VTODOs abgleichen;
   keine aufgelaufenen Legacy-Änderungen später erneut als Punkte exportieren lassen.
4. Nur danach das konkrete Hub-Konto im vom Betreiber geschützten Setting freigeben.
   API-Status `writes_enabled` prüfen; alle nicht freigegebenen Konten bleiben fail-closed.
5. Erst im bewusst gewählten Fachkonto testen. Legacy-Brücke nie neben der nativen Schreib-
   integration für dasselbe Konto wieder starten. Rückkehr: native Writes zuerst sperren,
   laufende/unklare Operationen vollständig abgleichen, dann erst einen anderen Writer zulassen.

Die Freigabe ist ein dokumentierter Single-Writer-Betriebsvertrag, kein technisch erfundener
Beweis über fremde Cronhosts. Ohne nachgewiesenen Cutover darf der Betreiber sie nicht setzen.
Diese Implementierungs-/Testarbeit führt **keinen** Cutover und keine echten Punkteaktionen aus.

## Migration

`b8c9d0e1f2a3` ergänzt ausschließlich persönliche Konten, native Auswahlen und technische
Operationsbelege. Reguläres Alembic-Upgrade und gestempeltes Legacy-`create_all` werden geprüft;
vorhandene Nextcloud-Konten/-Listen/Abschlussbelege bleiben erhalten. Downgrade entfernt diese
drei neuen Tabellen samt Zugang, Auswahl und Operationsnachweisen **destruktiv**, nicht aber
Nextcloud-/sonstige Hub-Daten. Nie bei laufendem/unklarem Write oder ohne gesicherten Bestand
downgraden: verlorene Operationsbelege sind keine Erlaubnis zu erneutem Scoring.

## Bestand und Grenzen

Nextclouds persönliche/geteilte/zugewiesene/Familien-Tasks, CRUD, Abschluss, Serien, Rotation
und Kalender-/Shopping-/HA-/Cachefunktionen werden nicht durch Habitica ersetzt. Historische
Nextcloud-Felder bleiben lesbar, sind aber keine Habitica-Autorisierung. Historische eigene
Rezept-/Essensplan-/Erinnerungsmodelle außerhalb #47 entsprechen noch nicht vollständig dem
nun ausdrücklich präzisierten allgemeinen Aggregatorziel; ihre Löschung oder Migration wäre
ein gesonderter Auftrag. Vikunja ist ein Erweiterungsbeispiel, **kein gelieferter Connector**.
Es gibt keinen neuen Service, keine neue Abhängigkeit, keine zweite Syncengine und keine
spekulative visuelle Neugestaltung.

Habitica 5.51.0 bietet auf dem Aufgaben-PUT keinen hier verwendbaren atomaren Compare-and-Swap. `updatedAt` verhindert erkennbar veraltete Edits, garantiert aber keine Transaktion mit gleichzeitig schreibenden externen Clients. Native Monatsarrays werden vor Verkleinerung gezielt geleert; schlägt der nachfolgende PUT fehl, bleibt der Teilfortschritt unbestätigt und gesperrt statt ihn automatisch zu wiederholen.
