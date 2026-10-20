# Push-Benachrichtigungen einrichten

Alle Mitteilungen laufen durch eine Stelle im Hub. Sie landen **immer** im Verlauf (*Mehr → Mitteilungen*) und werden danach auf **allen Kanälen** der Person gepusht, außer in ihren **Ruhezeiten** oder wenn sie die Kategorie abgeschaltet hat.

## Welcher Kanal passt?

| Kanal | Für wen | Aufwand für den Admin | Aufwand für die Person |
|---|---|---|---|
| **Web Push** | Browser und Web-App auf dem Home-Bildschirm, auch iPhone ab iOS 16.4 | keiner: Schlüssel entstehen beim ersten Start von selbst | *Mehr → Benachrichtigungen & Geräte → Benachrichtigungen auf diesem Gerät aktivieren* |
| **ntfy** | alle mit der ntfy-App, besonders iPhones mit sideloader App | ntfy-Plugin einrichten (siehe unten) | *Benachrichtigungen über ntfy* einschalten, das gezeigte Topic in der ntfy-App abonnieren |
| **Firebase (FCM)** | Android-App | Firebase-Projekt, Dienstkonto, **eigener App-Build** mit `google-services.json` | Benachrichtigungen erlauben |

**Empfehlung für die fertige APK:** Firebase-Push funktioniert nur, wenn App und Hub dasselbe Firebase-Projekt benutzen. Ohne Firebase läuft die App trotzdem, Mitteilungen kommen dann über ntfy oder Web Push. Laut Release-Doku ist für eine öffentliche APK deshalb **ntfy** der Kanal, der für alle funktioniert. ([releasing.md](https://github.com/Brottuetchen/familienhub/blob/main/docs/releasing.md))

Auf einem Handy dürfen mehrere Kanäle gleichzeitig aktiv sein; jede Mitteilung geht an alle.

## Web Push

- Funktioniert ohne Einstellung. Der Hub legt seine Schlüssel beim ersten Start unter `/app/data/vapid.json` im Daten-Volume ab. Eigene Schlüssel: `VAPID_PUBLIC_KEY` und `VAPID_PRIVATE_KEY` (erzeugen mit `docker compose exec familienhub python -m scripts.generate_vapid`).
- Kontaktadresse für die Push-Dienste ist die E-Mail des ersten Admins; `VAPID_EMAIL` überschreibt sie.
- iPhone: die Web-App muss auf dem **Home-Bildschirm** liegen (ab iOS 16.4).
- Browser verlangen für Web Push im Allgemeinen eine sichere Verbindung (HTTPS); nutzt dafür den [Reverse Proxy](Reverse-Proxy-und-HTTPS). (Allgemeines Browser-Verhalten, nicht Teil der Projektdoku.)

## ntfy

[ntfy](https://ntfy.sh) liefert echte Push-Mitteilungen auch ohne Familienhub-App.

**Admin:** *Verwaltung → Plugins & Zugänge → ntfy* aktivieren:
- `NTFY_URL`: der ntfy-Server, z. B. `https://ntfy.sh` oder euer eigener.
- `NTFY_PUBLIC_URL` (optional): die Adresse, die Handys in der ntfy-App eintragen, falls sie von der des Hubs abweicht.
- `NTFY_TOKEN` (optional): nötig, wenn euer Server anonymes Senden verbietet.
- `HUB_PUBLIC_URL` (optional): erreichbare Hub-Adresse; ermöglicht Antippen zum Öffnen und die Knöpfe *Erledigt / In 1 Std / Morgen* bei Erinnerungen.

**Jede Person:** *Mehr → Benachrichtigungen & Geräte → Benachrichtigungen über ntfy* einschalten. Der Hub erzeugt ein geheimes Topic (`fh_…`). In der ntfy-App den Server eintragen und das Topic abonnieren.

**Datenschutz:** Das Topic ist das Passwort. Wer es kennt, kann mitlesen. *Neues Topic* ersetzt ein verratenes. Über das öffentliche `ntfy.sh` laufen Titel und Text über einen fremden Server; ein **selbst gehosteter ntfy** wird empfohlen. Für einen eigenen Server mit `deny-all` und den nötigen Befehlen siehe [ntfy](https://github.com/Brottuetchen/familienhub/blob/main/docs/ntfy.md) (Englisch). Für sofortige Zustellung auf iOS muss die iOS-App exakt die `base-url` des Servers benutzen.

## Firebase (nur eigener Build)

Wer die App selbst baut, bindet das Dienstkonto-JSON in den Container ein (siehe Kommentar in der `docker-compose.yml`), setzt `FCM_PROJECT_ID` und `FCM_SERVICE_ACCOUNT_FILE` und legt die Datei für die Container-Benutzerkennung 10001 lesbar ab:

```bash
chown 10001:10001 fcm-service-account.json && chmod 600 fcm-service-account.json
```

Die `google-services.json` gehört **nie** ins Repository.

## Ruhezeiten, Kategorien, Test

- Jede Person stellt Ruhezeiten ein und schaltet Kategorien an/aus: Aufgabe zugewiesen, Aufgabe fällig, Erinnerung, Einkauf, Haus, Medien, Dokumente, Sterne, Plugins, System.
- **Test:** *Mehr → Benachrichtigungen & Geräte → Test-Benachrichtigung senden*. Die App sagt, wie viele Kanäle erreicht wurden.
- Plugins senden über die Kategorie *Plugins* (max. 20 Push-Aufrufe pro Plugin und Stunde).

## Mitteilungen von anderen Systemen

Home Assistant, Shelfarr, Paperless und eigene Skripte können über einen **Dienst-Schlüssel** (*Verwaltung → Dienst-Schlüssel*) an die Familie senden: [Notification sources](https://github.com/Brottuetchen/familienhub/blob/main/docs/notification-sources.md) (Englisch, mit fertigen Home-Assistant-Beispielen).

Nichts kommt an? Siehe [Fehlerbehebung](Fehlerbehebung#push-kommt-nicht-an).

Referenz (Englisch): [Notifications](https://github.com/Brottuetchen/familienhub/blob/main/docs/notifications.md) · [ntfy](https://github.com/Brottuetchen/familienhub/blob/main/docs/ntfy.md)
