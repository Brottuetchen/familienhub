# Roadmap

Status: October 2026. Familienhub runs daily in its first household; the first public release is being prepared.

## Done (1.0)
- Today overview, tasks (own, shared, assigned, household rotation), shopping, meal plan, events, reminders (time, recurring, "when I get home")
- Plugins: Nextcloud, Habitica, Home Assistant (shopping, house tiles with control), Cookidoo, Paperless-ngx, Shelfarr, Seerr, weather, ntfy
- Android app with widgets and quick actions, web app (PWA), iOS app for sideloading
- Push through Firebase, Web Push and ntfy, with quiet hours, categories, history and action buttons
- Offline mode with a queue for changes
- Roles (admin, partner, child, guest), invites, OIDC (e.g. Authentik) with optional auto-create
- Setup wizard, admin panel (health, family, house, plugins, themes, log, feedback)
- Themes with light/dark variants and fonts, installable from GitHub
- German and English
- Feedback from the app to the family admins or as a GitHub issue

## Next: first public release
- **Repository and docs:** English README with screenshots, guides for plugins, themes and notifications, contribution guide
- **Server texts in both languages:** push texts in the recipient's language, error messages via `Accept-Language`
- **Media requests:** Seerr webhook (notify when a requested movie or show is available)
- **Books:** "Discover" with German-language sources
- **iOS widgets** (WidgetKit extension)

## Later
- **Customisable home screen:** each person arranges "Today" (show or hide cards, order, size), with defaults set by the admin
- **Kiosk mode** for a wall-mounted tablet: fullscreen, screen stays on, large tiles, exit by PIN, its own restricted device account
- **iOS push via APNs**, once the project has an Apple Developer account (until then: ntfy or the web app)
- **More languages**: add `app/lib/l10n/app_<code>.arb`

## Ideas, not decided
- **Plugin and theme store:** a shared catalogue to install plugins and themes with one click. Open questions: review, signing, updates, and the security of code plugins.

Ideas and wishes are welcome as issues, see [CONTRIBUTING](../CONTRIBUTING.md).
