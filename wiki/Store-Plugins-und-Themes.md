# Store: Plugins und Themes installieren

Unter **Mehr → Verwaltung → Store** installieren Admins geprüfte Plugins und Themes mit einem Klick. Der Store ist auch aus *Plugins & Zugänge* verlinkt. **Nur Admins** sehen und nutzen ihn.

## Installieren

1. *Verwaltung → Store* öffnen. Filter: Alle, Themes, Plugins; Suche nach Name, Beschreibung, Autor oder Tag. Zum Aktualisieren der Liste nach unten ziehen.
2. Eintrag antippen: Screenshots, Beschreibung, Version, **Hosts, mit denen das Plugin spricht**, und die Einstellungen, nach denen es fragt.
3. **Installieren.** Bei einem **Plugin** erscheint der Prüfbildschirm mit Warnhinweis (siehe unten) und einem Vertrauens-Häkchen, danach das **Einstellungsformular** (Adressen, Zugangsdaten).
4. **Verbindung testen** (falls das Plugin einen Test hat): prüft die eingetragenen Werte. Das Ergebnis erscheint im Installationsbildschirm. Ein fehlgeschlagener Test macht die Installation nicht rückgängig; ihr könnt die Einstellungen danach korrigieren (*Verwaltung → Plugins & Zugänge → das Plugin*).
5. Das Plugin ist sofort aktiv, **ohne Neustart**.

Ein **Theme** wird geprüft und gespeichert wie ein Theme aus einem Link und steht dann der ganzen Familie unter *Mehr → Aussehen* zur Verfügung. Themes enthalten keinen Code.

## Zugangsdaten

- Eingaben für Passwörter, Schlüssel und Tokens werden **verschlüsselt gespeichert** und nie wieder angezeigt (im Formular steht *gespeichert, leer lassen zum Behalten*).
- Fehlt eine Pflichtangabe, steht das Plugin als **nicht eingerichtet** in der Liste und tut nichts.
- Spätere Änderungen: *Verwaltung → Plugins & Zugänge → Plugin*. Auch dort gibt es **Verbindung testen**; getestet werden die Werte, die gerade im Formular stehen, **bevor** gespeichert wird.

## Updates

Zeigt der Store bei einem Eintrag **Update verfügbar**, wurde im Index ein neuer, geprüfter Stand eingetragen. **Nichts aktualisiert sich von selbst.** Ihr seht Alt und Neu, die bisherigen Werte sind vorausgefüllt; nur neue Pflichtfelder brauchen Eingaben. Läuft die neue Version nicht, bleibt die alte aktiv.

## Entfernen

Im Menü des Plugins unter *Plugins & Zugänge* → *Entfernen*: Das Plugin wird abgeschaltet, seine Dateien und gespeicherten Einstellungen (auch Geheimnisse) werden gelöscht. Wichtig beim [Bildschirmzeit-Plugin](Plugin-Screentime): Vorher entsperrte Geräte werden dann nicht mehr automatisch gesperrt.

## Sicherheit: so viel Vertrauen ist nötig

- **Plugins laufen im Hub mit vollem Zugriff** (Datenbank, gespeicherte Zugangsdaten, alles, was der Hub erreicht). Das ist keine Sandbox. Installiert nur Plugins, denen ihr traut.
- Der **offizielle Store** listet nur Einträge, die die Maintainer geprüft haben (Pull Request im Store-Repository). Jeder Eintrag ist an einen **genauen Commit** gebunden; installiert wird genau dieser Stand, nicht der aktuelle Zweig. Es gibt keine Signaturen; das Vertrauen kommt aus Prüfung plus festem Commit.
- Die angezeigte Liste der Hosts ist eine **Information für die Prüfung**; der Hub erzwingt sie nicht.
- Eigene Quellen (GitHub-Repositories mit einer `index.json`) fügt ein Admin unter *Store → Quellen* hinzu (höchstens 10). Ihre Einträge tragen das Etikett **Nicht geprüft** und fordern Bestätigungen beim Hinzufügen und bei jeder Installation.
- `PLUGIN_INSTALL_ENABLED=false` schaltet die Installation von Plugins ganz ab (Themes bleiben möglich).
- Jede Installation und Änderung der Quellen steht im Log (*Verwaltung → Log*).
- Der Hub braucht ausgehendes HTTPS zu GitHub-Servern (raw.githubusercontent.com, codeload.github.com; für Plugins auch api.github.com und Python-Paketquellen). Ein Reverse Proxy darf die Installation nicht nach kurzer Zeit abbrechen, siehe [Reverse Proxy und HTTPS](Reverse-Proxy-und-HTTPS).

## Die sieben offiziellen Plugins

Sie brauchen alle **Familienhub 1.0.0-beta.3 oder neuer**. Auf beta.2 werden sie zwar gelistet, bleiben aber inaktiv und sagen, dass sie beta.3 brauchen ([Fehlerbehebung](Fehlerbehebung#plugin-sagt-braucht-100-beta3)).

| Plugin | Was es tut |
|---|---|
| [Immich](Plugin-Immich) | "An diesem Tag"-Fotos aus eurem Immich auf *Heute* |
| [WebUntis](Plugin-WebUntis) | Stundenplan der Kinder, Push bei Ausfall und Vertretung |
| [Bildschirmzeit](Plugin-Screentime) | Internetzeit als Belohnung (Fritz!Box, AdGuard Home, Pi-hole) |
| [DWD](Plugin-DWD) | Amtliche Wetterwarnungen und Pollenflug |
| [Abfahrten](Plugin-Departures) | Nächste Bus- und Bahnabfahrten an eurer Haltestelle |
| [Grocy](Plugin-Grocy) | Grocy als Einkaufsliste, bald ablaufende Vorräte |
| [Tandoor](Plugin-Tandoor) | Tandoor als Rezeptquelle |

**Ehrlicher Hinweis:** Alle sieben wurden bisher **nur gegen simulierte Antworten** automatisch getestet, teils mit einzelnen Ausnahmen (siehe die jeweilige Seite). Rechnet mit Abweichungen bei eurer Version und meldet sie als Issue.

## Themes

Die elf Themes aus der [Theme-Galerie](https://github.com/Brottuetchen/familienhub-themes) stehen im Store (jeweils hell und dunkel). Zusätzlich bringt der Hub fünf eingebaute Themes mit (Warm, Liquid Glass, Clean Cards, Neo-Brutalism, Pixel). Jede Person wählt Thema und *Hell / Dunkel / Automatisch* je Gerät unter *Mehr → Aussehen*. Ein Theme aus einem Link installiert ein Admin unter *Mehr → Aussehen → Von GitHub*. Eigene Themes bauen: [Themes](https://github.com/Brottuetchen/familienhub/blob/main/docs/themes.md) (Englisch).

## Eigene Plugins

Plugins schreiben, teilen und über einen Link installieren: [Plugin-Anleitung](https://github.com/Brottuetchen/familienhub/blob/main/docs/plugins.md) (Englisch) und die [Plugin-Vorlage](https://github.com/Brottuetchen/familienhub/tree/main/examples/plugin-template). Aufnahme in den Store per Pull Request, siehe [Mitmachen](Mitmachen).

Referenz (Englisch): [Store](https://github.com/Brottuetchen/familienhub/blob/main/docs/store.md) · [Plugins](https://github.com/Brottuetchen/familienhub/blob/main/docs/plugins.md) · [Store-Repository](https://github.com/Brottuetchen/familienhub-store)
