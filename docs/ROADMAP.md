# Roadmap

Stand 16.10.2026. Jede Zeile ist ein Issue im Issue-Tracker des Projekts, gruppiert in Meilensteine.

| Etappe | Inhalt | Issues |
|---|---|---|
| **1 – Fundament** | DB-Backup · Altlasten raus · Plugin-Schnittstelle · Bereiche dynamisch · Flutter in CI | #16–#20 |
| **2 – Zentrale & Erinnerungen** | Benachrichtigungs-Eingang `/api/notify` · Quellen (HA, Shelfarr, Paperless) → `docs/QUELLEN.md` · Mitteilungsverlauf · Wiederholungen · Aktionen in Mitteilungen · „wenn ich nach Hause komme“ | #21–#26 |
| **3 – Familie** | Cookidoo-Wochenplan aus der App · Haus-Karte · Haushalt mit Rotation | #27–#29 |
| **4 – Ausbau** | Dokumente (Paperless) · Medien (Seerr) · Offline-Warteschlange · deutsche Bücherquellen | #30–#32, #7 |
| **5 – Veröffentlichung** | Einrichtungs-Assistent · Englisch · README/Lizenz/GitHub | #33–#35 |
| **6 – Feinschliff** | Redesign (Material You) · iOS | #36–#37 |

Grundsätze: Integrationen als Plugins (`docs/PLUGINS.md`), persönliche Daten nur mit persönlichem Zugang,
jede Quelle darf ausfallen ohne die App zu stören, Tests zuerst.

Nächste freigegebene Schritte (Nutzerentscheidung: #45 vor #47): nach #29 und #46 – schnelle Seitenwechsel mit Cache-first und Hintergrundaktualisierung – zuerst #45 – Haus-Karte steuern (An/Aus, Dimmer, freigegebene Skripte/Szenen); erst danach #47 – unabhängige Aufgabenprovider (Nextcloud und native persönliche Habitica-Auswahl) bidirektional bedienen, ohne zentrale Spiegelengine. Diese Priorisierung ersetzt die frühere Reihenfolge #46 → #47 → #45. Offline-Schreibwarteschlange (#32), allgemeine Einstellungsoberfläche (#33) und Redesign (#36) bleiben separate Pakete.

Haushaltsrotation (#29): Bedienung, API und bewusste Grenzen stehen in `docs/HAUSHALT.md`.

Gesamtarchitektur: Hub bündelt Fachsystemplugins und stößt deren Refresh/Sync nur an; siehe `ENTSCHEIDUNGEN.md`. Das angekündigte Designpapier und der spätere Designumbau bleiben außerhalb #47.
