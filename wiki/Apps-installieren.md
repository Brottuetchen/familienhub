# Apps installieren

Die Apps stecken in jedem [GitHub-Release](https://github.com/Brottuetchen/familienhub/releases/latest): eine **APK** (Android) und eine **IPA** (iOS, unsigniert). Beim ersten Start fragt die App nach der **Adresse eures Hubs**, z. B. `https://familienhub.example.org` oder `http://<server>:8000`. Das Handy muss diese Adresse erreichen (Heim-WLAN, VPN oder Reverse Proxy).

| Gerät | Weg |
|---|---|
| **Android** | APK aus dem Release installieren |
| **iPhone / iPad** | **Web-App** (am einfachsten) oder die **IPA sideloaden** |
| **Computer** | Web-App im Browser |

## Android (APK)

1. Auf dem Handy die `.apk` von der [Release-Seite](https://github.com/Brottuetchen/familienhub/releases/latest) laden.
2. Öffnen und die Installation aus dieser Quelle erlauben (Android fragt danach).
3. App starten, Hub-Adresse eintragen, anmelden.
4. Benachrichtigungen erlauben, wenn Android fragt.

Tipps:
- [Obtainium](https://obtainium.imranr.dev/) kann die Release-Seite beobachten und bei neuen Versionen aktualisieren.
- Der Hub kann APKs auch selbst ausliefern (`/downloads/`): Ordner einbinden, wie in der `docker-compose.yml` kommentiert, und `DOWNLOADS_DIR` setzen.
- Die Android-App hat Widgets, Schnellaktionen und eine Warteschlange für Änderungen ohne Netz.
- Damit APK-Updates über die alte Installation drüberlaufen, müssen alle Releases mit demselben Schlüssel signiert sein. Das betrifft Bauherren eigener APKs, siehe [releasing.md](https://github.com/Brottuetchen/familienhub/blob/main/docs/releasing.md).

## iPhone und iPad

**Variante A: Web-App (PWA).** Hub in **Safari** öffnen → Teilen → **Zum Home-Bildschirm**. Web Push funktioniert dort ab iOS 16.4, siehe [Push-Benachrichtigungen](Push-Benachrichtigungen).

**Variante B: iOS-App sideloaden.** Die unsignierte `.ipa` aus dem Release mit **Sideloadly** oder **SideStore** und einer kostenlosen Apple-ID installieren. Die App muss alle **7 Tage neu signiert** werden (SideStore kann das auf dem Handy erledigen). Push läuft hier über **ntfy**, denn Apples Push (APNs) braucht ein bezahltes Entwicklerkonto. TestFlight und iPhone-Widgets sind aus demselben Grund noch nicht möglich ([#9](https://github.com/Brottuetchen/familienhub/issues/9)).

## Web-App / PWA am Computer und Handy

Einfach die Hub-Adresse im Browser öffnen. Die Web-App lässt sich im Browser installieren (Android/Chrome: *App installieren*). Eine installierte Web-App kann Rezeptseiten aus dem Browser-Teilen-Menü annehmen, siehe [Rezepte importieren](Rezepte-importieren) (abhängig vom Browser).

## Probleme?

Siehe [Fehlerbehebung: App erreicht den Server nicht](Fehlerbehebung#die-app-erreicht-den-server-nicht).

Referenz (Englisch): [Getting started, Abschnitt 3](https://github.com/Brottuetchen/familienhub/blob/main/docs/getting-started.md#3-get-the-apps)
