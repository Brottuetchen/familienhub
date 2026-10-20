# Mitmachen

Familienhub ist ein Familienprojekt, das gewachsen ist. Jede Hilfe zählt, auch eine verbesserte Wiki-Seite.

## Fragen, Ideen, Zeigen

- [GitHub Discussions](https://github.com/Brottuetchen/familienhub/discussions): Fragen, Ideen, "so nutzen wir es".
- Dieses **Wiki** darf von allen bearbeitet werden, die ein GitHub-Konto mit Schreibrecht haben. Fehlt etwas oder ist etwas veraltet, ändert die Seite oder schreibt es in die Discussions. Schreibt hier **keine echten Adressen, Namen oder Zugangsdaten** eures Haushalts hinein; nehmt Beispiele wie "Mia" und `familienhub.example.org`.

## Fehler und Wünsche melden

- Ein [Issue anlegen](https://github.com/Brottuetchen/familienhub/issues): auch auf Deutsch. Schreibt Version, was ihr erwartet habt, was passiert ist, und Logzeilen ohne Geheimnisse.
- Aus der App: *Mehr → Feedback senden → An die Entwickler* füllt ein Issue mit App-Version und Plattform vor.
- Fehler in einem **Plugin**, das nur gegen simulierte Antworten getestet wurde (siehe [Store](Store-Plugins-und-Themes)): Bitte meldet Abweichungen eurer Version. Das hilft am meisten.

## Sicherheitslücken

Bitte **nicht öffentlich** melden. Nutzt GitHubs privates Advisory (*Security → Report a vulnerability*) im Hauptrepository, siehe [SECURITY.md](https://github.com/Brottuetchen/familienhub/blob/main/SECURITY.md).

## Übersetzen

Deutsch und Englisch gibt es. Weitere Sprachen sind willkommen; geplant ist **Weblate** ([#25](https://github.com/Brottuetchen/familienhub/issues/25)). Bis dahin: `app/lib/l10n/app_en.arb` nach `app_<code>.arb` kopieren, Werte übersetzen und die Sprache in `appLanguages` in `app/lib/l10n/l10n.dart` eintragen, wie in [CONTRIBUTING](https://github.com/Brottuetchen/familienhub/blob/main/CONTRIBUTING.md) beschrieben. Texte des Servers (Fehlermeldungen, Mitteilungen) werden in `backend/app/core/i18n.py` übersetzt.

## Themes und Plugins beitragen

- **Themes:** eine `theme.json` auf GitHub teilen oder per Pull Request in die [Theme-Galerie](https://github.com/Brottuetchen/familienhub-themes) legen. Anleitung: [Themes](https://github.com/Brottuetchen/familienhub/blob/main/docs/themes.md).
- **Plugins:** Die meisten Anbindungen können in einem eigenen Repository leben; startet mit der [Plugin-Vorlage](https://github.com/Brottuetchen/familienhub/tree/main/examples/plugin-template), Admins installieren per GitHub-Link. Anleitung: [Plugins](https://github.com/Brottuetchen/familienhub/blob/main/docs/plugins.md).
- **In den Store:** Pull Request an das [Store-Repository](https://github.com/Brottuetchen/familienhub-store); die Maintainer prüfen den Code an einem festen Commit. Siehe [Store, Abschnitt "Submitting an entry"](https://github.com/Brottuetchen/familienhub/blob/main/docs/store.md#submitting-an-entry).

## Code

[CONTRIBUTING](https://github.com/Brottuetchen/familienhub/blob/main/CONTRIBUTING.md) (Englisch) beschreibt Entwicklungsumgebung und Pull Requests. Kurz: kleine, getestete Änderungen; Code, Kommentare und Commits auf Englisch; keine Geheimnisse und keine Haushaltsdaten im Code.

## Unterstützen

Familienhub ist kostenlos und entsteht in der Freizeit. Für echte native Apps braucht das Projekt eine Apple-Entwicklerlizenz (99 € pro Jahr, für TestFlight, App Store und Widgets auf dem iPhone, [#9](https://github.com/Brottuetchen/familienhub/issues/9)) und einmalig ein Google-Play-Entwicklerkonto (rund 25 €): Jahresziel **150 €**. Wenn der Hub eurer Familie hilft:

- [Ko-fi](https://ko-fi.com/brottuetchen)
- [GitHub Sponsors](https://github.com/sponsors/Brottuetchen)

Ebenso hilfreich: Sterne auf GitHub, Erfahrungsberichte, Screenshots (ohne echte Daten) und Wiki-Pflege.

## Wie geht es weiter?

Die [Roadmap](https://github.com/Brottuetchen/familienhub/blob/main/docs/roadmap.md) (Englisch) zeigt, was in Arbeit ist.
