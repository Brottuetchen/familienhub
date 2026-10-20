# Plugin: Bildschirmzeit (Internet als Belohnung)

Kinder sammeln Sterne und lösen sie gegen "30 Minuten Internet" ein. Genehmigt ein Elternteil, **entsperrt das Plugin das Gerät des Kindes für N Minuten und sperrt es danach automatisch wieder**. Es arbeitet mit dem, was ihr zu Hause habt:

| System | So wird gesperrt | Ihr braucht |
|---|---|---|
| **Fritz!Box** | TR-064-Hostfilter für die IPv4-Adresse des Geräts | einen Fritz!Box-Benutzer, feste IP für das Gerät |
| **AdGuard Home** | Gerät kommt auf die Liste "nicht erlaubte Clients" | einen AdGuard-Benutzer, IP oder ClientID des Geräts |
| **Pi-hole v6** | je Gerät eine Pi-hole-*Gruppe*, die alles blockiert; Gruppe an = gesperrt | ein App-Passwort, eine Gruppe je Gerät |

Voraussetzung: **Familienhub 1.0.0-beta.3 oder neuer**, und der [Kindermodus](Kindermodus-und-Belohnungen). Ausführlich (Englisch): [README des Plugins](https://github.com/Brottuetchen/familienhub-store/tree/main/plugins/screentime)

## Was es tut

- **Belohnungs-Aktion "Internet freischalten"** (*Mehr → Sterne → Belohnung → Aktion*): Das Elternteil wählt Gerät und Minuten (5 bis 240, Standard 30). Bei Genehmigung geht das Gerät online ("Mias Tablet ist bis 17:30 online"). Wird erneut eingelöst, während das Gerät online ist, **addiert** sich die Zeit (nie mehr als 8 Stunden auf einmal).
- **Automatisch wieder sperren**, auf die Minute, solange der Hub läuft. Ein Job alle 5 Minuten ist das Sicherheitsnetz, auch nach einem Neustart.
- **Mitteilungen:** Das Kind erhält "noch ca. 5 Minuten" und "Internetzeit ist vorbei". Eltern erfahren, wenn ein Gerät **nicht wieder gesperrt werden konnte**.
- **Karte "Internet freigeschaltet"** auf *Heute* nur für Eltern.

## Einrichten

*Verwaltung → Store → Bildschirmzeit → Installieren*.

| Einstellung | | |
|---|---|---|
| `SCREENTIME_BACKEND` | Pflicht | `fritzbox`, `adguard` oder `pihole` |
| `SCREENTIME_URL` | Pflicht | Fritz!Box `http://fritz.box:49000`, AdGuard `http://adguard.lan:3000`, Pi-hole `http://pi.hole` |
| `SCREENTIME_USERNAME` | Fritz!Box, AdGuard | bei Pi-hole leer |
| `SCREENTIME_PASSWORD` | Pflicht, geheim | bei Pi-hole ein **App-Passwort** |
| `SCREENTIME_DEVICES` | Pflicht | `Mias Tablet=192.168.178.42, Bens Switch=192.168.178.50` (Name = was Eltern sehen; höchstens 20 Geräte) |
| `SCREENTIME_DEFAULT_LOCKED` | Standard an | an: Gerät wird nach Ablauf wieder gesperrt. Aus: Das Plugin sperrt nie selbst und meldet nur das Ende (sinnvoll, wenn ein Zeitplan im Router sperrt) |
| `SCREENTIME_VERIFY_TLS` | Standard an | ausschalten bei `https://` mit selbstsigniertem Zertifikat |

### Wichtig: Geräte zuerst einmal sperren

Das Plugin sperrt ein Gerät **nicht von sich aus**. Es öffnet es für eine Belohnung und schließt es danach. "Normalerweise aus" ist ein Gerät nur, wenn ihr es einmal im System sperrt. Der Verbindungstest zeigt, welche Geräte noch online sind.

### Fritz!Box

1. *Heimnetz → Netzwerk → Netzwerkeinstellungen → Heimnetzfreigaben*: **Zugriff für Anwendungen zulassen** einschalten (TR-064).
2. *System → FRITZ!Box-Benutzer → Benutzer hinzufügen*: langes Zufallspasswort, nur Recht **FRITZ!Box Einstellungen**, **kein** Zugang aus dem Internet. (Die Menünamen hängen von der FRITZ!OS-Version ab.)
3. **Feste IP** für das Gerät vergeben (Gerät anklicken → "Diesem Netzwerkgerät immer die gleiche IPv4-Adresse zuweisen").
4. Einstellungen im Hub eintragen, Gerät einmal sperren (am einfachsten: 5-Minuten-Belohnung einlösen), **Verbindung testen**.

### AdGuard Home

Das Plugin nutzt *Einstellungen → DNS-Einstellungen → Zugriffseinstellungen → Nicht zugelassene Clients*; so ein Gerät bekommt gar keine DNS-Antworten. Eure übrigen Einträge bleiben unberührt.
1. Einen eigenen AdGuard-Benutzer anlegen.
2. **Keine "Zugelassenen Clients" verwenden**: Ist diese Liste nicht leer, wird alles andere blockiert, und das Plugin kann nichts öffnen (der Test meldet das als Fehler).
3. Gerät per **IP** (im Router reservieren) oder **ClientID** angeben, z. B. `Mias Tablet=192.168.178.42, Bens Switch=ben-switch`.
4. Geräte einmal in die Liste *Nicht zugelassene Clients* eintragen.

### Pi-hole (v6)

Pi-hole kennt keinen "Client blockieren"-Schalter, deshalb: eine **Gruppe je Gerät** mit einer Sperrregel für alles.
1. *Groups*: Gruppe anlegen, z. B. `kids-mia` (der Name ist die Geräte-Kennung in den Einstellungen).
2. *Clients*: Gerät (IP oder MAC) hinzufügen, in der Gruppenzuordnung **nur** `kids-mia` (nicht *Default*).
3. *Domains*: Typ **Regex**, Domain `.*`, **Deny**, nur Gruppe `kids-mia`.
4. *Einstellungen → Web-Oberfläche / API → App-Passwort*: als Passwort eintragen, Benutzername leer.
5. Geräte: `Mias Tablet=kids-mia`. Am Ende ist die Gruppe aktiviert, das Gerät also gesperrt. **Verbindung testen.**

## Wenn etwas schiefgeht ("im Zweifel sperren")

- **Entsperren schlägt fehl:** Gerät bleibt gesperrt, Eltern sehen "Konnte nicht entsperren …". Die Sterne bleiben ausgegeben (eine fehlschlagende Aktion macht die Genehmigung nie rückgängig); entsperrt von Hand oder löst erneut ein.
- **Wieder-Sperren schlägt fehl:** Wiederholung alle 5 Minuten; nach dem 2. Fehlversuch werden alle Eltern benachrichtigt, dann stündlich. Das Gerät kann solange online bleiben: der **einzige Fail-open-Fall**, und er wird gemeldet.
- **Hub neu gestartet:** Endzeiten stehen in einer Datei; gesperrt wird, sobald der Hub wieder läuft.
- **Hub ganz aus:** Niemand sperrt. Das Plugin hat keinen Code im Router. Für ein hartes Limit zusätzlich einen Zeitplan im Router nutzen.
- **Plugin ausgeschaltet oder entfernt, während ein Gerät entsperrt ist:** Es wird **nicht** wieder gesperrt. Von Hand sperren.

## Grenzen (ehrlich)

- **Kein Sicherheitsprodukt.** DNS-Sperren (AdGuard, Pi-hole) lassen sich mit eigenem DNS, DNS-over-HTTPS im Browser, VPN oder fest eingetragenen Adressen umgehen; Apps laufen nach der Sperre noch ein paar Minuten (Zwischenspeicher). Die Fritz!Box sperrt per IPv4: **IPv6 ist eventuell nicht abgedeckt**.
- Zufällige MAC-Adressen ("private WLAN-Adresse") ändern die IP: im Heimnetz ausschalten.
- Kein Tageskontingent und keine App-Limits; die Sternpreise sind das Budget.
- Endzeiten sind exakt, solange der Hub läuft, nach einem Neustart bis ca. 5 Minuten verspätet.
- Pi-hole v5 und Fritz!Boxen ohne TR-064 werden nicht unterstützt.
- Es nutzt **ein gemeinsames Haushaltskonto** für Router bzw. DNS-Server und kontaktiert nur die eine Adresse, die ihr einträgt.

## Nur gegen simulierte Systeme getestet

Alle automatischen Tests laufen gegen **simulierte** Systeme. **Eine echte Fritz!Box, ein echtes AdGuard Home und ein echtes Pi-hole standen nicht zur Verfügung.** Unbestätigt sind u. a.: die genauen Antworten der Fritz!Box (und ob das Recht "FRITZ!Box Einstellungen" reicht), das sofortige Wirken der AdGuard-Änderung in eurer Version, und beim Pi-hole der Header `X-FTL-SID` sowie die Gruppen-Einrichtung. **Bitte nach dem Einrichten: Verbindung testen, einmal eine 5-Minuten-Belohnung einlösen, Abweichungen als Issue melden.**

Siehe auch: [Kindermodus und Belohnungen](Kindermodus-und-Belohnungen)
