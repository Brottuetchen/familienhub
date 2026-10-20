# Home-Assistant-Add-on

Das Add-on betreibt Familienhub direkt in Home Assistant. Es ist **experimentell**.

## Was ihr bekommt

- Server und Web-App in einem Add-on, mit einer **SQLite**-Datenbank (statt PostgreSQL). Alle Daten liegen im `/data`-Ordner des Add-ons.
- Erreichbar auf Port **8000**: `http://<home-assistant-adresse>:8000`.
- Die Add-on-Version entspricht der Familienhub-Version.

## Installieren

1. Home Assistant: **Einstellungen → Add-ons → Add-on-Store**.
2. Menü (drei Punkte oben rechts) → **Repositories** → `https://github.com/Brottuetchen/familienhub-ha-addon` hinzufügen. (Oder den Badge-Knopf in der [README des Add-on-Repositorys](https://github.com/Brottuetchen/familienhub-ha-addon) benutzen.)
3. **Familienhub** installieren. Beim ersten Mal baut Home Assistant das Add-on-Image aus dem veröffentlichten Familienhub-Image; das dauert eine Minute und braucht Internet.
4. Optionen ansehen, Add-on starten, `http://<home-assistant-adresse>:8000` öffnen (oder *Web-UI öffnen*).
5. Beim ersten Öffnen das **Admin-Konto** anlegen, dann führt der [Einrichtungsassistent](Erste-Schritte) weiter.

Ist Home Assistant aus dem Internet erreichbar, schaltet **vor dem ersten Start** die Option *Require setup code* (`setup_require_code`) ein. Der Code steht dann im Add-on-Log.

## Optionen

| Option | Bedeutung |
|---|---|
| `timezone` | Zeitzone, Standard Europe/Berlin |
| `log_level` | debug, info, warning oder error |
| `setup_require_code` | Einrichtungscode für das erste Admin-Konto verlangen |
| `secure_cookies` | nur bei reinem HTTPS-Zugriff (Reverse Proxy). Für HTTP im Heimnetz auf `false` lassen |
| `public_url` | Adresse, die ihr benutzt, z. B. `https://familienhub.example.org` (für Links in Mitteilungen) |
| `cors_origins` | leer lassen, außer eine Webseite unter anderer Adresse ruft die API auf |
| `plugins_disabled` | Plugin-IDs abschalten, z. B. `weather` |
| `oidc_*` | optionale Anmeldung über Authentik/Keycloak; braucht `public_url` |

Alles andere (Nextcloud, Home Assistant, Paperless …) stellt ihr als Admin in der App unter *Mehr → Verwaltung → Plugins & Zugänge* ein. Um Familienhub mit eurem Home Assistant zu verbinden, erzeugt in eurem HA-Profil ein **langlebiges Zugriffstoken** und tragt es dort ein.

## Backup und Update

- Home-Assistant-Backups enthalten den `/data`-Ordner automatisch. Das Add-on steht auf *cold backup*: Es wird kurz angehalten, damit die Datenbank konsistent ist. Beim Wiederherstellen kommt auch der geheime Schlüssel mit zurück.
- Update: Erscheint eine neue Version im Add-on-Store, Changelog lesen und aktualisieren; die Datenbank wird beim Start automatisch migriert. **Vorher ein Backup machen** (*Einstellungen → System → Backups*).

## Bekannte Einschränkungen

- **Kein Eintrag in der HA-Seitenleiste (Ingress).** Die Web-App ist für den Pfad `/` gebaut. Daran wird gearbeitet ([#28](https://github.com/Brottuetchen/familienhub/issues/28)). Behelf: In HA ein *Webseite*-Dashboard anlegen, das auf die HTTPS-Adresse des Hubs zeigt.
- **Kein automatischer Umzug** von SQLite nach PostgreSQL. Wer später wechseln will, nutzt die Docker-Compose-Variante; eine Sicherung aus der App lässt sich laut Dokumentation zwischen beiden Datenbanken einspielen (siehe [Backup](Backup-und-Wiederherstellen)).
- Die Apps gehören nicht zum Add-on, siehe [Apps installieren](Apps-installieren). Das Handy muss die Adresse erreichen (Heim-WLAN, VPN wie WireGuard oder Tailscale, oder Reverse Proxy). Port 8000 nicht ohne HTTPS ins Internet freigeben.
- Firebase-Push, eigene VAPID-Schlüssel und der Downloads-Ordner sind keine Add-on-Optionen. Web Push funktioniert ohne Zutun (Schlüssel in `/data/vapid.json`).

Referenz: [DOCS.md des Add-ons](https://github.com/Brottuetchen/familienhub-ha-addon/blob/main/familienhub/DOCS.md)
