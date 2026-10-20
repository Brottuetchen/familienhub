# Häufige Fragen (FAQ)

### Was ist Familienhub?
Ein selbst gehosteter Familien-Hub mit App für Aufgaben, Einkauf, Essen, Termine und Erinnerungen. Er läuft auf eurem Server und braucht keinen weiteren Dienst. Mehr auf der [Startseite](Home).

### Was kostet es?
Nichts. Familienhub ist freie Software ([AGPL-3.0](https://github.com/Brottuetchen/familienhub/blob/main/LICENSE)) und entsteht in der Freizeit. Wer unterstützen möchte: [Mitmachen](Mitmachen).

### Brauche ich Nextcloud, Home Assistant oder andere Dienste?
Nein. Ohne jeden Dienst liegen Aufgaben, Einkaufsliste und Familienkalender im Hub selbst. Dienste sind Zusatz, siehe [Erste Schritte](Erste-Schritte).

### Wie viele Container sind das?
Zwei: Familienhub (Server und Web-App) und PostgreSQL. Das [Home-Assistant-Add-on](Installation-Home-Assistant-Add-on) kommt mit SQLite ohne Datenbank-Container aus.

### Gibt es eine App für iPhone?
Ja, aber zum **Sideloaden** (unsignierte IPA, alle 7 Tage neu signieren), oder ihr nutzt die **Web-App** auf dem Home-Bildschirm. Echte App-Store-Apps, TestFlight und iPhone-Widgets brauchen eine Apple-Entwicklerlizenz und sind noch nicht möglich ([#9](https://github.com/Brottuetchen/familienhub/issues/9)). Push auf dem iPhone: Web-App (ab iOS 16.4) oder ntfy. Siehe [Apps installieren](Apps-installieren).

### Gibt es eine App im Play Store?
Nicht nach der Projekt-Doku: Die APK hängt am GitHub-Release ([Apps installieren](Apps-installieren)). Ein Google-Play-Konto steht als Ziel in der Finanzierung ([README](https://github.com/Brottuetchen/familienhub#unterst%C3%BCtzen)).

### Welche Sprachen gibt es?
Deutsch und Englisch. Weitere sind willkommen, siehe [Mitmachen](Mitmachen).

### Kann ich Familienhub von außen erreichen?
Ja, per [Reverse Proxy mit HTTPS](Reverse-Proxy-und-HTTPS) oder besser per VPN (z. B. WireGuard). Port 8000 nie ohne HTTPS freigeben.

### Wie lege ich Konten an?
Per Einladung (*Verwaltung → Familie & Rollen → Person einladen*), siehe [Personen und Rollen](Personen-und-Rollen). Der Benutzername muss kleingeschrieben sein (Großbuchstaben werden umgewandelt).

### Welche Rolle bekommt wer?
Eltern: Partner (oder Admin). Kinder: Kind. Besuch und Großeltern: Gast. Tabelle in [Personen und Rollen](Personen-und-Rollen).

### Ich habe mein Passwort vergessen.
Beim Prüfen des Codes fand sich **keine** "Passwort vergessen"-Funktion und kein Zurücksetzen durch einen anderen Admin; angemeldet kann man sein Passwort ändern (mindestens 10 Zeichen). Das Skript `python -m scripts.create_admin` legt nur einen Admin an, solange noch keiner existiert. Wer sich ausgesperrt hat, fragt in den [Discussions](https://github.com/Brottuetchen/familienhub/discussions) und hält ein [Backup](Backup-und-Wiederherstellen) bereit. Nutzt ihr OIDC, setzt das Passwort beim Identitätsanbieter zurück.

### Wo sind meine Daten?
Im Docker-Volume `familienhub_db` (PostgreSQL) und `familienhub_data` (Schlüssel, Backups, Plugins). Beide gehören zum Backup.

### Kann ich Daten von Nextcloud/Habitica/Home Assistant weiter dort behalten?
Ja, genau dafür gibt es Plugins: Der Hub zeigt die Daten an und lässt sie, wo sie sind ([Plugins](https://github.com/Brottuetchen/familienhub/blob/main/docs/plugins.md), Englisch). Persönliche Konten (Nextcloud, Habitica) verbindet jede Person selbst.

### Ist der Store sicher?
Der offizielle Store listet nur geprüfte Einträge, jeweils an einen genauen Commit gebunden. Plugins laufen trotzdem **mit vollem Zugriff im Hub**; es gibt keine Sandbox. Installiert nur, was ihr versteht oder wem ihr traut. Details: [Store](Store-Plugins-und-Themes).

### Die neuen Plugins sagen, sie bräuchten beta.3. Was nun?
Hub auf 1.0.0-beta.3 oder neuer aktualisieren: [Update](Update-auf-neue-Version), [Fehlerbehebung](Fehlerbehebung#plugin-sagt-braucht-100-beta3).

### Sind die Plugins schon an echten Geräten getestet?
Die offiziellen Plugins wurden bisher mit **simulierten Antworten** getestet; Ausnahmen stehen auf den jeweiligen Seiten (z. B. wurde die Abfahrten-Anzeige manuell gegen eine echte Instanz geprüft). Rechnet mit Abweichungen und meldet sie bitte.

### Wie sicher ist die Bildschirmzeit-Sperre?
Sie ist **kein Sicherheitsprodukt**; DNS-Sperren lassen sich umgehen. Details auf [Plugin: Bildschirmzeit](Plugin-Screentime).

### Kann ich Themes ändern?
Ja: *Mehr → Aussehen*. Themes aus dem [Store](Store-Plugins-und-Themes) oder per GitHub-Link.

### Wo melde ich Fehler oder Wünsche?
Als [Issue](https://github.com/Brottuetchen/familienhub/issues) (auch auf Deutsch) oder in der App unter *Mehr → Feedback senden*. Sicherheitslücken bitte **privat**, siehe [Mitmachen](Mitmachen).

### Wie halte ich den Hub aktuell?
Siehe [Update auf eine neue Version](Update-auf-neue-Version). Die Verwaltung zeigt auch einen Update-Hinweis.
