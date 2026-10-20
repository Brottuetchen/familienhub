# Plugin: WebUntis (Stundenplan)

Für Schulen, die **WebUntis** nutzen: Das Plugin füllt den [Stundenplan](Stundenplan) jedes Kindes automatisch und schickt eine Mitteilung bei **Ausfall** und **Vertretung**.

Voraussetzung: **Familienhub 1.0.0-beta.3 oder neuer**. Ausführlich (Englisch): [README des Plugins](https://github.com/Brottuetchen/familienhub-store/tree/main/plugins/webuntis)

> **Status: noch nicht an einer echten Schule getestet.** Der Code ist gegen einen simulierten Server getestet (115 Tests) und gegen den Quelltext eines Open-Source-WebUntis-Clients abgeglichen. Schulen konfigurieren WebUntis unterschiedlich; passt die Antwort nicht, zeigt das Plugin nichts an, statt zu scheitern, und der Verbindungstest sagt, was es gesehen hat. Bitte meldet, was ihr findet.

## Was es tut

- **Stundenplan** je Kind für die angesehene Woche, mit Raum, Lehrkraft, Hinweis und Stundennummer. Ausfall ist durchgestrichen, Vertretung hervorgehoben. Zu sehen unter *Mehr → Stundenplan → Diese Woche* und auf *Heute* ("Mia: Schule bis 13:15, 3.–4. Stunde entfällt"). Eure eigenen Einträge (Sport, Musik, Verein) bleiben.
- **Mitteilungen** alle 15 Minuten, nur zwischen 06:00 und 22:00 Uhr (Hub-Zeit): neue Ausfälle und Vertretungen für heute (und morgen, je nach Einstellung) gehen an die Eltern (Partner und Admin) und an das Kind. Jede Person kann die Kategorie *Plugins* abschalten.

## Was du brauchst

Ein **Eltern- oder Schüler-Konto** der Schule in WebUntis (ein Elternkonto sieht alle seine Kinder). Fragt im Sekretariat; der Login der WebUntis-App der Eltern funktioniert. Ein **Lehrer-Konto taugt nicht**, es hat keine verknüpften Schüler.

### Server und Schulname finden

Öffnet den WebUntis-Login eurer Schule im Browser. Die Adresse sieht so aus:

```
https://xyz.webuntis.com/WebUntis/?school=my-school-city#/basic/login
        └──── Server ────┘                └── Schule ──┘
```

Der Teil nach `https://` bis `/WebUntis` ist der **Server**, der Wert nach `school=` die **Schule**. Sonderzeichen genau wie in der Adresse übernehmen (`%20` ist ein Leerzeichen).

## Einrichten

1. Installieren: *Verwaltung → Store → WebUntis* (oder per Link `https://github.com/Brottuetchen/familienhub-store/tree/main/plugins/webuntis`).
2. Einstellungen:

   | Einstellung | Bedeutung |
   |---|---|
   | `WEBUNTIS_SERVER` (Pflicht) | z. B. `xyz.webuntis.com`, ohne `https://` und Pfad |
   | `WEBUNTIS_SCHOOL` (Pflicht) | Login-Name der Schule |
   | `WEBUNTIS_USERNAME` (Pflicht) | Login des Eltern- oder Schülerkontos |
   | `WEBUNTIS_PASSWORD` (Pflicht, geheim) | dessen Passwort, verschlüsselt gespeichert |
   | `WEBUNTIS_NOTIFY` | Mitteilungen bei Ausfall/Vertretung, Standard an |
   | `WEBUNTIS_NOTIFY_DAYS` | Vorschau in Tagen: 1 = heute und morgen, 0 = nur heute, höchstens 7 |

3. **Verbindung testen**, z. B. *"Connected to my-school as parent.demo; students visible: 2"*.
4. **Kinder zuordnen:** *Stundenplan → Menü → Stundenplan-Quellen*: je Kind **WebUntis** wählen und aussuchen, wer das Kind in WebUntis ist (Auswahlliste der Schüler des Kontos).

## Grenzen und gutes Wissen

- Ein Schul-Konto für alle Kinder; es sieht nur, was es in WebUntis sehen darf. Manche Schulen verbergen Lehrkräfte, Räume oder Vertretungstexte: Fehlendes wird weggelassen.
- Ohne Stundenraster der Schule nennen Mitteilungen die Uhrzeit ("08:50") statt "2. Stunde".
- **Erster Lauf:** Das Plugin merkt sich nur den aktuellen Stand, es gibt keine Flut alter Meldungen.
- **Falsches Passwort:** Nach einem abgelehnten Login versucht das Plugin 10 Minuten lang nichts mehr (damit das Schul-Konto nicht gesperrt wird). Passwort in den Einstellungen korrigieren.
- Ist der Schulserver langsam (der Hub wartet 3 Sekunden), erscheinen zuerst zuletzt bekannte Daten bzw. eure eigenen Einträge; der nächste Aufruf ist vollständig. Ist WebUntis aus, zeigt der Hub Daten, die bis zu 6 Stunden alt sind.
- Eine von der Schule zurückgenommene Änderung wird nicht gemeldet.
- Ferientage ohne Unterricht liefern nichts; dann gelten eure eigenen Einträge und die Ferien-Logik.
- Gespeichert wird nur eine kleine Datei mit Fingerabdrücken schon gemeldeter Änderungen; Stunden selbst werden nicht gespeichert. Das Plugin schreibt nichts in WebUntis und kontaktiert nur euren WebUntis-Server.

## Was nicht bestätigt ist

Fehlercodes (z. B. falsches Passwort), die Antwort bei falschem Schulnamen, ob Elternkonten ihre Kinder über die App-Schnittstelle sehen, und das Format der Wochen-Webdaten sind **Annahmen**, nicht an echten Servern bestätigt. Läuft es bei euch nicht, hilft der Verbindungstest, und wir freuen uns über ein [Issue](https://github.com/Brottuetchen/familienhub/issues).

Siehe auch: [Stundenplan](Stundenplan) · [Store: Plugins und Themes](Store-Plugins-und-Themes)
