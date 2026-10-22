# Roadmap

Status: October 2026. Familienhub 1.0.0 is the current stable release and runs daily in its first household. Open work is tracked as [issues](https://github.com/Brottuetchen/familienhub/issues); ideas and questions go to [Discussions](https://github.com/Brottuetchen/familienhub/discussions).

## Done

**Everyday**
- Today overview, customisable per person (order, show/hide, half or full size) with a family default set by the admin
- Tasks (own, shared, assigned, household rotation), shopping, meal plan, calendar (list, week, month), reminders (time, recurring, "when I get home")
- Works out of the box: tasks, shopping list and family calendar are stored in the hub, and sources are chosen per area
- Sources: CalDAV/Nextcloud, Habitica, Home Assistant, Mealie, Cookidoo, calendar subscriptions (ICS)
- Recipe import from a link, see [recipe import](recipe-import.md) ([#16](https://github.com/Brottuetchen/familienhub/issues/16))
- Template lists, see [templates](templates.md) ([#20](https://github.com/Brottuetchen/familienhub/issues/20))

**Family**
- Kids mode: stars for tasks and rewards, see [kids mode](kids-mode.md) ([#17](https://github.com/Brottuetchen/familienhub/issues/17))
- Birthdays and anniversaries with gift ideas, see [birthdays](birthdays.md) ([#18](https://github.com/Brottuetchen/familienhub/issues/18))
- Timetable for children, see [timetable](timetable.md) ([#19](https://github.com/Brottuetchen/familienhub/issues/19))
- Roles (admin, partner, child, guest), invites, OIDC (e.g. Authentik) with optional auto-create

**Home and services**
- Home Assistant: house tiles with control, shopping lists
- Paperless-ngx, Seerr (with a notice when a requested title is available), Shelfarr and book discovery with German titles, weather
- Voice assistant via Home Assistant Assist, see [voice assistant](voice-assistant.md) ([#21](https://github.com/Brottuetchen/familienhub/issues/21))

**Admin and safety**
- Setup wizard and admin panel (health, family, house, plugins, themes, log, feedback)
- Backup and restore in Administration, with nightly backups, see [getting started](getting-started.md#7-backup) ([#14](https://github.com/Brottuetchen/familienhub/issues/14))
- Update notice in Administration, see [getting started](getting-started.md#8-update) ([#15](https://github.com/Brottuetchen/familienhub/issues/15))
- Push through Firebase, Web Push and ntfy, with quiet hours, categories, history and action buttons
- Feedback from the app to the family admins or as a GitHub issue

**Make it yours**
- Plugin and theme store with reviewed entries and pinned commits, see [store](store.md) ([#7](https://github.com/Brottuetchen/familienhub/issues/7)); the index lives in [familienhub-store](https://github.com/Brottuetchen/familienhub-store)
- Themes with light/dark variants and fonts, installable from GitHub; [theme gallery](https://github.com/Brottuetchen/familienhub-themes)
- Plugins from GitHub links, with a [guide and template](plugins.md)
- German and English, including server texts

**Apps**
- Android app with widgets and quick actions, web app (PWA), iOS app for sideloading, offline queue
- Bottom navigation labels stay on one line with wide theme fonts ([#29](https://github.com/Brottuetchen/familienhub/issues/29))

**Ecosystem**
- Home Assistant add-on as an experimental repository ([familienhub-ha-addon](https://github.com/Brottuetchen/familienhub-ha-addon), part of [#23](https://github.com/Brottuetchen/familienhub/issues/23))
- The hub serves under a path prefix (`X-Ingress-Path` or `ROOT_PATH`), which is what Home Assistant ingress needs ([#28](https://github.com/Brottuetchen/familienhub/issues/28), [Home Assistant](home-assistant.md))
- Documentation website: <https://brottuetchen.github.io/familienhub/> ([#26](https://github.com/Brottuetchen/familienhub/issues/26))

## In progress / next

- **Kiosk mode** for a wall tablet: first as the web app with its own account ([#5](https://github.com/Brottuetchen/familienhub/issues/5))
- **Home Assistant add-on sidebar:** the hub's sub-path support is in 1.0.0; the add-on still has to enable ingress ([#28](https://github.com/Brottuetchen/familienhub/issues/28))
- **Public demo instance**, planned on the Oracle Cloud free tier ([#22](https://github.com/Brottuetchen/familienhub/issues/22))
- **One-click install** beyond the add-on: Unraid, TrueNAS, Proxmox ([#23](https://github.com/Brottuetchen/familienhub/issues/23))
- **iOS widgets and TestFlight**, which need the Apple Developer licence and are the funding goal ([#9](https://github.com/Brottuetchen/familienhub/issues/9))

## Later

- **F-Droid build** without Firebase ([#24](https://github.com/Brottuetchen/familienhub/issues/24))
- **iOS push via APNs**, once the project has an Apple Developer account (until then: ntfy or the web app)
- **More sources:** Grocy, Vikunja/Todoist, Google and Microsoft
- **Small follow-ups from the docs:**
  - an entry for the native Android app in the share sheet for [recipe import](recipe-import.md#share-into-the-app) (the web app already has a share target)
  - a Home Assistant custom integration on top of the stable `/api/voice` endpoints, see [voice assistant](voice-assistant.md)
- Passkeys and 2FA are not planned in the hub: use them through your identity provider (Authentik etc.)

## Community welcome

- **More languages** with Weblate ([#25](https://github.com/Brottuetchen/familienhub/issues/25)), a good first issue. Until it is set up, add `app/lib/l10n/app_<code>.arb`, see [CONTRIBUTING](https://github.com/Brottuetchen/familienhub/blob/main/CONTRIBUTING.md).
- **Themes:** share yours, see [themes](themes.md) and the [gallery](https://github.com/Brottuetchen/familienhub-themes).
- **Plugins:** start from the [plugin template](https://github.com/Brottuetchen/familienhub/tree/main/examples/plugin-template) and propose it for the store.
- **Docs, bug reports and ideas:** open an issue or start a discussion.
