# Update auf eine neue Version

**Immer zuerst ein Backup.** Das geht in der App in zwei Minuten und rettet euch im Zweifel den Tag.

## Ablauf (Docker Compose)

1. **Backup herunterladen:** *Mehr → Verwaltung → Backup → Backup herunterladen*. Bewahrt die Datei wie ein Passwort auf, siehe [Backup und Wiederherstellen](Backup-und-Wiederherstellen).
2. **Changelog lesen:** [CHANGELOG.md](https://github.com/Brottuetchen/familienhub/blob/main/CHANGELOG.md) (Englisch). Dort steht auch, ob neue Einstellungen dazukommen.
3. **Neue Version ziehen und starten.**
   - Stabiles Release (aktuell **1.0.1**): `docker compose pull && docker compose up -d` folgt dem Tag `latest`.
   - Eine Version festnageln: `FAMILIENHUB_VERSION` in der `.env` ändern (zum Beispiel auf `1.0.1`) und denselben Befehl ausführen. Ohne Eintrag in der `.env`, einmalig für diesen Aufruf:

     ```bash
     FAMILIENHUB_VERSION=1.0.1 docker compose pull && FAMILIENHUB_VERSION=1.0.1 docker compose up -d
     ```

   - Eine Beta: `FAMILIENHUB_VERSION` auf genau diese Beta setzen. `latest` zeigt nie auf eine Beta.
4. Die **Datenbank-Migrationen laufen beim Start automatisch** (Alembic). Prüft mit `docker compose logs -f familienhub`, dass der Start ohne Fehler durchläuft.
5. App aktualisieren: neue APK von der [Release-Seite](https://github.com/Brottuetchen/familienhub/releases/latest), siehe [Apps installieren](Apps-installieren).

Aus dem Quellcode gebaut? Dann `git pull` und den Build-Befehl wiederholen.

## Update-Hinweis in der App

Die Verwaltung zeigt, wenn es eine neuere Version gibt (mit Link zu den Release-Notes und dem Update-Befehl). Der Hub fragt dafür ein paar Mal am Tag die GitHub-Releases ab. Vorabversionen (`-beta.N`) werden nur angeboten, wenn ihr selbst eine Vorabversion betreibt. Abschalten: *Verwaltung → Updates* oder `UPDATE_CHECK=false` in der `.env`.

## Beispiel: von beta.2 auf beta.3

Laut Changelog: Backup, neue Version starten, drei neue Migrationen laufen beim Start, keine neuen Einstellungen. Beta.3 behebt außerdem ein Einfrieren des Servers unter Last und bringt die ersten sieben [offiziellen Plugins](Store-Plugins-und-Themes). Auf beta.2 bleiben diese Plugins nach der Installation inaktiv und melden, dass sie beta.3 brauchen, siehe [Fehlerbehebung](Fehlerbehebung).

## Home-Assistant-Add-on

Update im Add-on-Store anstoßen, vorher ein HA-Backup machen, siehe [Home-Assistant-Add-on](Installation-Home-Assistant-Add-on).

## Wenn etwas schiefgeht

Eine Sicherung einer **neueren** Version wird nicht in eine ältere eingespielt (der Hub lehnt sie ab). Ein Zurückgehen auf eine ältere Version ist in der Dokumentation nicht beschrieben; verlasst euch deshalb auf das Backup von vorher und meldet das Problem als [Issue](https://github.com/Brottuetchen/familienhub/issues).

Referenz (Englisch): [Getting started, Abschnitt Update](https://github.com/Brottuetchen/familienhub/blob/main/docs/getting-started.md#8-update)
