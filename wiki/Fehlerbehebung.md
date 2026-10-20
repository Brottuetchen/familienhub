# Fehlerbehebung

Erst die Grundregeln: **Logs ansehen** (`docker compose logs -f familienhub`, oder in der App *Verwaltung → Log*) und **Version prüfen** (steht auf der Einrichtungsseite und in der Verwaltung). Meldet ungelöste Probleme als [Issue](https://github.com/Brottuetchen/familienhub/issues), mit Version und Logzeilen, aber **ohne Passwörter, Schlüssel oder Adressen eures Haushalts**.

## Inhalt

- [Ich kann mich nicht anmelden](#ich-kann-mich-nicht-anmelden)
- [Die App erreicht den Server nicht](#die-app-erreicht-den-server-nicht)
- [Push kommt nicht an](#push-kommt-nicht-an)
- [Plugin sagt "braucht 1.0.0-beta.3"](#plugin-sagt-braucht-100-beta3)
- [Verbindungstest: was die Meldungen heißen](#verbindungstest-was-die-meldungen-heißen)
- [Der Server hing, bevor beta.3 kam](#der-server-hing-bevor-beta3-kam)
- [Weiteres](#weiteres)

## Ich kann mich nicht anmelden

- **Benutzername:** Die Anmeldung ignoriert Groß-/Kleinschreibung (`Mia` = `mia`). Gespeichert wird immer klein. Achtet auf Leerzeichen.
- **Gesperrt?** Nach **5 falschen Versuchen** für denselben Benutzernamen von derselben Adresse aus innerhalb von **15 Minuten** antwortet der Hub mit "Too many login attempts" (HTTP 429). Kurz warten und es noch einmal mit dem richtigen Passwort versuchen.
- **Passwort vergessen:** siehe [FAQ](FAQ#ich-habe-mein-passwort-vergessen).
- **Kein Konto?** Der Admin muss euch [einladen](Personen-und-Rollen). Der Einladungs-Code gilt 7 Tage.
- **Im Browser klappt der Login nicht, in der App schon (oder umgekehrt):** Prüft `SECURE_COOKIES`. Es muss `true` sein, wenn der Hub **nur** über HTTPS erreichbar ist, und `false` bei reinem HTTP im Heimnetz. Siehe [Reverse Proxy und HTTPS](Reverse-Proxy-und-HTTPS).
- **Nach der Wiederherstellung** eines Backups sind Personen, die nicht im Backup stehen, abgemeldet.
- **Nach Änderung des `SECRET_KEY`** sind alle abgemeldet und gespeicherte Zugangsdaten unlesbar. Den Schlüssel nie ändern; stellt ihn aus dem Backup wieder her.
- **OIDC:** Weiterleitungs-Adressen beim Anbieter müssen zu `OIDC_REDIRECT_URI_*` passen; eingeladene Personen müssen dieselbe E-Mail-Adresse haben.

## Die App erreicht den Server nicht

1. Öffnet im Browser **des Handys** `http://<server>:8000/api/health` (bzw. die HTTPS-Adresse). Das ist ohne Anmeldung erreichbar. Kommt keine Antwort, liegt es am Netz, nicht an der App.
2. Läuft der Container? `docker compose ps` und `docker compose logs --tail 50 familienhub`.
3. **Adresse in der App:** mit `http://` oder `https://`, mit Port (`:8000`), wenn kein Reverse Proxy davorsteht. Kein Schrägstrich-Anhängsel nötig.
4. **Netz:** Ist das Handy im selben WLAN oder per VPN (WireGuard, Tailscale) verbunden? Von unterwegs ohne VPN oder Reverse Proxy ist ein Heimserver nicht erreichbar.
5. **Firewall/Port:** Ist der Port am Server freigegeben? Ein geänderter `PORT` in der `.env` ändert auch die Adresse.
6. **Reverse Proxy:** Weiterleitung auf `localhost:8000`, HTTPS-Zertifikat gültig? Siehe [Reverse Proxy und HTTPS](Reverse-Proxy-und-HTTPS).
7. Die App arbeitet zuerst aus dem Zwischenspeicher; Änderungen ohne Verbindung landen in einer Warteschlange und werden später gesendet.

## Push kommt nicht an

1. **Test senden:** *Mehr → Benachrichtigungen & Geräte → Test-Benachrichtigung senden*. Die App sagt, wie viele Kanäle erreicht wurden. Bei **0** hat die Person keinen aktiven Kanal.
2. **Welcher Kanal?** Die öffentliche APK hat nach Projekt-Doku keinen Firebase-Push; nehmt **ntfy** oder die Web-App. Siehe [Push-Benachrichtigungen](Push-Benachrichtigungen).
3. **Ruhezeiten und Kategorien:** Außerhalb der Ruhezeiten und bei eingeschalteter Kategorie kommt Push; sonst steht die Mitteilung nur im Verlauf (*Mehr → Mitteilungen*). Prüft beides in den Benachrichtigungs-Einstellungen. Plugins senden in der Kategorie *Plugins*.
4. **ntfy:** Hat die Person *Benachrichtigungen über ntfy* eingeschaltet **und** das Topic in der ntfy-App abonniert? Stimmt der Server in der ntfy-App mit `NTFY_PUBLIC_URL` bzw. `NTFY_URL` überein? Verbietet euer Server anonymes Senden, ist `NTFY_TOKEN` nötig. Auf iOS muss die App exakt die `base-url` des Servers verwenden.
5. **Web Push:** Auf dem iPhone muss die Web-App auf dem **Home-Bildschirm** liegen (iOS 16.4 oder neuer). Im Browser müssen Mitteilungen für die Seite erlaubt sein.
6. **Erinnerungs-Knöpfe fehlen oder öffnen nichts:** `HUB_PUBLIC_URL` setzen (Adresse, die Handys erreichen).
7. **Von Plugins:** höchstens 20 Push-Aufrufe pro Plugin und Stunde; darüber hinaus werden sie verworfen (manche Plugins versuchen es später erneut).
8. Android: Akkuoptimierung der App ausschalten (allgemeiner Hinweis, nicht Teil der Projektdoku).

## Plugin sagt "braucht 1.0.0-beta.3"

Die sieben offiziellen Plugins ([Store](Store-Plugins-und-Themes)) brauchen **Familienhub 1.0.0-beta.3 oder neuer**. Hubs auf beta.2 listen sie zwar, aber ein dort installiertes Plugin bleibt **inaktiv** und meldet, dass es eine neuere Version braucht (z. B. "needs Familienhub 1.0.0-beta.3 or newer"). Die Installation kann auch mit "Das Plugin braucht Familienhub … oder neuer" abgelehnt werden.

**Lösung:** Hub aktualisieren, siehe [Update auf eine neue Version](Update-auf-neue-Version). Danach wird das Plugin aktiv; sonst einmal neu installieren.

## Verbindungstest: was die Meldungen heißen

Der Test prüft die Werte, wie ihr sie gerade eingegeben habt (vor dem Speichern). Die Meldungen der Plugins sind englisch.

| Meldung (sinngemäß) | Bedeutung und Abhilfe |
|---|---|
| *Connected as …, Immich …* / *Connected, Grocy 4.x* / *Connected, 42 recipes* / *Connected to … as …; students visible: 2* | Alles in Ordnung |
| *… rejected the API key* / *token rejected (401/403)* / *wrong key or missing permissions* | Schlüssel/Token falsch, abgelaufen oder zu wenige Rechte. Neu erstellen, siehe die jeweilige Plugin-Seite |
| *… is not reachable* / *did not answer in time* | Der **Hub** erreicht die Adresse nicht. Adresse so eintragen, wie der Hub-Container sie erreicht (nicht wie euer Laptop); Docker-Netzwerk, Firewall, `http`/`https` prüfen |
| *This address does not look like Immich. Check the address (no /api at the end)* / *no Tandoor API at that address* | Falsche Adresse. **Ohne `/api`** am Ende eintragen |
| *check server and school* (WebUntis) | Server oder Schulname falsch, siehe [Plugin: WebUntis](Plugin-WebUntis) |
| Grocy: Liste existiert nicht | `GROCY_SHOPPING_LIST_ID` prüfen |
| AdGuard: Fehler wegen "Allowed clients" | Die Liste *Zugelassene Clients* muss leer sein, siehe [Plugin: Bildschirmzeit](Plugin-Screentime) |
| DWD: Region nicht gefunden | Der Test listet die gültigen Regionen, siehe [Plugin: DWD](Plugin-DWD) |

Ein **fehlgeschlagener Test direkt nach der Installation** macht die Installation nicht rückgängig: Korrigiert die Werte unter *Plugins & Zugänge*. Hängt ein Test länger als 15 Sekunden, gilt er als fehlgeschlagen.

**Der Hub erreicht den Dienst nicht, obwohl ihr ihn erreicht?** `localhost` im Plugin bedeutet *den Hub-Container selbst*. Nehmt den Namen im gemeinsamen Docker-Netz oder die LAN-Adresse des Servers.

## Der Server hing, bevor beta.3 kam

In **1.0.0-beta.2 und früher** konnte der Server unter Last einfrieren, weil die Anmeldung die Ereignisschleife blockierte ([#36](https://github.com/Brottuetchen/familienhub/issues/36)). Das ist in **1.0.0-beta.3 behoben**.

- Sofort helfen: `docker compose restart familienhub`.
- Dauerhaft: auf beta.3 oder neuer aktualisieren ([Update](Update-auf-neue-Version)). Vorher ein Backup.

## Weiteres

- **Plugin-Installation bricht ab / Zeitüberschreitung:** Der Reverse Proxy kappt lange Anfragen. Erhöht das Zeitlimit für `/api/` (siehe [Reverse Proxy](Reverse-Proxy-und-HTTPS)). Prüft danach die Plugin-Liste: Die Installation kann trotzdem fertig geworden sein. Der Hub braucht ausgehendes HTTPS zu GitHub.
- **Plugin-Dateien weg nach Neuaufbau des Containers:** Das Volume `familienhub_data` fehlt in eurer Compose-Datei. Dieselbe Version einfach neu installieren.
- **GitHub-Limit:** Anonyme GitHub-Zugriffe sind auf 60 pro Stunde und IP begrenzt; zu viele Versuche nacheinander schlagen fehl.
- **Heute-Karte fehlt:** Die meisten Plugin-Karten erscheinen nur, wenn es etwas anzuzeigen gibt (z. B. DWD ohne Warnung). Mit dem Regler-Symbol auf *Heute* prüfen, ob die Karte ausgeblendet ist.
- **Falsche Uhrzeit bei Erinnerungen und Plugins:** `TIMEZONE` bzw. die Zeitzone im Einrichtungsassistenten prüfen.
- **Backup-Wiederherstellung wird abgelehnt:** Backup einer neueren Version, siehe [Backup](Backup-und-Wiederherstellen).

Referenz (Englisch): [Security](https://github.com/Brottuetchen/familienhub/blob/main/docs/security.md) · [Plugins](https://github.com/Brottuetchen/familienhub/blob/main/docs/plugins.md)
