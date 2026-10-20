# Erste Schritte

Der Hub läuft, und ihr öffnet `http://<server>:8000` (oder eure HTTPS-Adresse). Wie es weitergeht:

## 1. Admin-Konto anlegen

Ein neuer Hub zeigt **Einrichten**. Die **erste Person, die ihn öffnet**, legt das Admin-Konto an. Das geht nur, solange es noch keinen Admin gibt.

- **Benutzername:** 2 bis 40 Zeichen, nur Kleinbuchstaben, Ziffern und `. _ -`, ohne Leerzeichen. Beispiel: `mia`. Großbuchstaben werden beim Anlegen in Kleinbuchstaben umgewandelt.
- **Passwort:** mindestens 10 Zeichen.
- **E-Mail:** eine gültige Adresse (wird auch für Einladungen und Anmeldung über OIDC genutzt).
- Der **Anzeigename** ist frei wählbar (max. 40 Zeichen).

Ist der Hub vorher aus dem Internet erreichbar? Dann braucht ihr den **Einrichtungscode** aus dem Log, siehe [Installation](Installation-Docker-Compose).

## 2. Der Einrichtungsassistent

Danach führt der Assistent in vier Schritten durch die Grundlagen:

1. **Grundlagen:** Name und Zeitzone.
2. **Bereiche:** Wo leben Aufgaben, Einkaufsliste und Kalender: im Hub selbst und/oder in einem Dienst (z. B. Nextcloud, Home Assistant, Mealie)?
3. **Dienste:** Die gewählten Dienste kommen zuerst, mit **Verbindung testen**. Kalender-Abos (Schulferien, Müllabfuhr …) gibt es als Liste mit Prüfung. Hakt an, was ihr nutzen wollt. **Nicht angehakte Dienste werden am Ende ausgeschaltet** (auch Wetter und CalDAV); ihr könnt sie später unter *Verwaltung → Plugins & Zugänge* wieder einschalten.
4. **Familie:** Personen einladen, siehe [Personen und Rollen](Personen-und-Rollen).

**Ohne jeden Dienst** funktioniert der Hub allein: Aufgaben, Einkaufsliste und Familienkalender liegen dann im Hub. Den Assistenten könnt ihr jederzeit unter *Mehr → Verwaltung* erneut starten.

## 3. Danach

- **Apps** auf die Handys: [Apps installieren](Apps-installieren)
- **Mitteilungen** einrichten: [Push-Benachrichtigungen](Push-Benachrichtigungen)
- **Backup** einschalten: [Backup und Wiederherstellen](Backup-und-Wiederherstellen)
- **Heute-Bildschirm anpassen:** Mit dem Regler-Symbol in der Kopfzeile von *Heute* ordnet jede Person ihre eigenen Karten (Reihenfolge, ein-/ausblenden, in Kachel-Themes halbe Breite). Admins können ihre Anordnung als Familienstandard speichern.
- **Aussehen:** *Mehr → Aussehen*, Themes siehe [Store: Plugins und Themes](Store-Plugins-und-Themes).
- **Dienste verbinden** (Nextcloud, Home Assistant, Paperless, Seerr, Shelfarr, Cookidoo, Habitica, ntfy, Wetter): *Verwaltung → Plugins & Zugänge*. Zugangsdaten werden verschlüsselt gespeichert und wirken ohne Neustart. Persönliche Konten (Nextcloud, Habitica, Paperless-Token, ntfy) trägt jede Person selbst in der App ein.
- **Kalender auf dem Handy** mit einem CalDAV-Server teilen: [Kalender und Handy](https://github.com/Brottuetchen/familienhub/blob/main/docs/calendar.md) (Englisch).

Referenz (Englisch): [Getting started](https://github.com/Brottuetchen/familienhub/blob/main/docs/getting-started.md)
