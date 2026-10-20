# Backup und Wiederherstellen

Ein Backup ist eine einzige ZIP-Datei, die ihr in der App erzeugt. **Macht eins, bevor ihr den Hub aktualisiert**, und prüft ab und zu, ob die Sicherungen auch außerhalb des Servers liegen.

## Backup erstellen (nur Admins)

*Mehr → Verwaltung → Backup*:

- **Backup herunterladen:** speichert eine ZIP-Datei über den Browser. Sie enthält die ganze Datenbank (Personen, Einstellungen, Themes, Einträge installierter Plugins, Profilbilder …) **und die Schlüssel des Hubs** (`secret_key`, `vapid.json`). Gespeicherte Plugin-Zugangsdaten bleiben so verschlüsselt, wie sie in der Datenbank stehen; der Schlüssel in der Datei macht sie auf einem neuen Rechner wieder lesbar. **Bewahrt die Datei wie ein Passwort auf**: Wer sie hat, kann eure Zugangsdaten lesen.
- **Backup auf dem Hub ablegen:** schreibt dieselbe Datei nach `/app/data/backups` (Volume `familienhub_data`).
- **Nächtliches Backup** (standardmäßig aus): ab 03:30 Uhr (Hub-Zeit) legt der Hub jede Nacht ein Backup dort ab und behält die letzten N (1 bis 30, Standard 7). Voreinstellung über `BACKUP_AUTO` und `BACKUP_KEEP` in der `.env`.
- Die Verwaltung zeigt das Datum des letzten Backups. Ein fehlgeschlagenes Backup wird dort und im Log gemeldet; es stoppt den Hub nie.

## Was nicht drin ist

- **Dokumente, Aufgaben, Einkaufslisten** u. ä., die in angebundenen Diensten liegen (Paperless, Nextcloud …), sind nicht Teil des Backups. Sichert diese Dienste selbst.
- Der **Code installierter Plugins** steckt nicht in der Datei; der Hub kennt aber deren Einträge. Nach einer Wiederherstellung auf ein leeres Volume installiert fehlende Plugins unter *Plugins & Zugänge* neu.

Das Backup funktioniert für PostgreSQL und SQLite gleich; eine Sicherung aus dem einen lässt sich laut Dokumentation in das andere einspielen.

## Wichtig: Backup liegt neben den Daten

Die Sicherungen unter `/app/data/backups` liegen im selben Volume wie die Daten, die sie schützen. **Kopiert die Dateien regelmäßig woanders hin** (andere Festplatte, anderer Rechner). Bewahrt auch eure `.env` auf, falls ihr eine habt.

## Wiederherstellen

1. *Verwaltung → Backup*, neben dem gespeicherten Backup **Wiederherstellen**.
2. Der Hub prüft die Datei und zeigt eine Warnung: **Alle aktuellen Daten werden ersetzt.**
3. Bevor etwas ersetzt wird, legt der Hub den **aktuellen Stand als eigenes Backup** ab (`familienhub-prerestore-…`, die letzten drei bleiben).
4. Danach den **Hub neu starten**, weil Einstellungen und Schlüssel beim Start geladen werden:

   ```bash
   docker compose restart familienhub
   ```

5. Personen, die nicht im Backup stehen, sind abgemeldet.

**Einschränkungen:**
- Ein Backup einer **neueren** Familienhub-Version wird abgelehnt. Ebenso eines mit abweichendem Datenbank-Aufbau (älter): Startet diese Version, spielt es ein und aktualisiert dann.
- Ist `SECRET_KEY` ausdrücklich in der Umgebung gesetzt, lässt eine Wiederherstellung ihn unangetastet; die Zugangsdaten im Backup funktionieren dann nur mit demselben Schlüssel.

### Eine heruntergeladene Datei auf einen neuen Hub bringen

Kopiert sie in das Daten-Volume, dann erscheint sie in der Liste:

```bash
docker compose cp familienhub-backup-20261018-120000.zip familienhub:/app/data/backups/
```

Alternativ über die API (Admin-Token nötig): `POST /api/admin/backup/upload`, siehe [Getting started, Abschnitt 7](https://github.com/Brottuetchen/familienhub/blob/main/docs/getting-started.md#7-backup).

## Home-Assistant-Add-on

Home-Assistant-Backups enthalten den `/data`-Ordner automatisch, siehe [Home-Assistant-Add-on](Installation-Home-Assistant-Add-on).

Referenz (Englisch): [Getting started: Backup](https://github.com/Brottuetchen/familienhub/blob/main/docs/getting-started.md#7-backup) · [Security](https://github.com/Brottuetchen/familienhub/blob/main/docs/security.md)
