# Roadmap

Status: October 2026. Familienhub runs daily in its first household; the first public release is being prepared.

## Done (1.0)
- Today overview, tasks (own, shared, assigned, household rotation), shopping, meal plan, events, reminders (time, recurring, "when I get home")
- Plugins: Nextcloud, Habitica, Home Assistant (shopping, house tiles with control), Cookidoo, Paperless-ngx, Shelfarr, Seerr, weather, ntfy
- Android app with widgets and quick actions, web app (PWA), iOS app for sideloading
- Push through Firebase, Web Push and ntfy, with quiet hours, categories, history and action buttons
- Install plugins from GitHub with a link in the app, with a [guide and template](plugins.md) for writing them
- Server texts in German and English: error messages in the app's language, push texts in the recipient's language, plugin names and settings
- Offline mode with a queue for changes
- Roles (admin, partner, child, guest), invites, OIDC (e.g. Authentik) with optional auto-create
- Setup wizard, admin panel (health, family, house, plugins, themes, log, feedback)
- Themes with light/dark variants and fonts, installable from GitHub
- German and English
- Feedback from the app to the family admins or as a GitHub issue

## Next: first public release
- **Works out of the box:** tasks, shopping list and family calendar stored in the hub; sources chosen per area *(done 18.10.)*
- **More sources:** calendar subscriptions (ICS: school holidays, waste collection, clubs), Mealie (recipes, meal plan, shopping), then Grocy, Vikunja/Todoist, Google and Microsoft
- **Repository and docs:** English README with screenshots, guides for plugins, themes and notifications, contribution guide
- **Media requests:** notify when a requested movie or show is available *(done 18.10.: polling, webhook optional)*
- **Books:** "Discover" with German-language sources *(done 18.10.: Open Library shelves, German titles)*
- **Customisable home screen:** each person arranges "Today" (show or hide cards, order, size), with defaults set by the admin *(done 19.10.)*
- **Kids mode:** stars for tasks and rewards parents define, requests parents approve, optional confirmation of completed tasks, a stars card on the child's Today, see [kids mode](kids-mode.md) *(done 19.10.)*
- **iOS widgets** (WidgetKit extension)

## Later
- **Kiosk mode** for a wall-mounted tablet: fullscreen, screen stays on, large tiles, exit by PIN, its own restricted device account
- **iOS push via APNs**, once the project has an Apple Developer account (until then: ntfy or the web app)
- **More languages**: add `app/lib/l10n/app_<code>.arb`

## Ideas, not decided
- **Plugin and theme store:** a shared catalogue to find plugins and themes (installing from a link already works). Open questions: review, signing, automatic update checks, and the security of code plugins.

Ideas and wishes are welcome as issues, see [CONTRIBUTING](../CONTRIBUTING.md).
