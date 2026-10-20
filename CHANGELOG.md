# Changelog

All notable changes per release. Versions follow the Git tags (`v1.0.0-beta.2` → image `ghcr.io/brottuetchen/familienhub:1.0.0-beta.2`).

## [1.0.0-beta.4]

Home Assistant sidebar support, a documentation website, a wiki and the groundwork for more languages.

### New
- **Run under a sub-path / Home Assistant ingress:** the hub works behind a path prefix, from the `X-Ingress-Path` header of Home Assistant or a fixed `ROOT_PATH`. Direct access on the port works as before. With this release the [Home Assistant add-on](https://github.com/Brottuetchen/familienhub-ha-addon) can show Familienhub in the HA sidebar. See [Home Assistant](docs/home-assistant.md). (#28)
- **Documentation website:** https://brottuetchen.github.io/familienhub/ (#26)
- **Wiki** with German how-tos, FAQ and troubleshooting: https://github.com/Brottuetchen/familienhub/wiki
- **Translations:** the language picker is built from the available languages, so a new language only needs an `app_<code>.arb` file. A CI check guards the translation files. Translating through Weblate is being set up. See [translations](docs/translations.md). (#25)

### Fixed
- Bottom navigation: labels no longer wrap mid-word with wide theme fonts or large text. (#29)

### Upgrading from 1.0.0-beta.3
1. Download a backup in Administration first.
2. `FAMILIENHUB_VERSION=1.0.0-beta.4 docker compose pull && FAMILIENHUB_VERSION=1.0.0-beta.4 docker compose up -d`
3. No database migrations. New optional settings, all off by default: `ROOT_PATH`, `TRUST_INGRESS_HEADER`, `INGRESS_PROXY_IPS`. See [`.env.example`](.env.example).

## [1.0.0-beta.3]

Plugins can now do much more, and the store lists the first seven official plugins.

### New
- **Seven official plugins** in *Administration → Store*. Each asks for its addresses and credentials during installation and has a connection test. See the [store](https://github.com/Brottuetchen/familienhub-store#currently-listed).
  - **Immich:** "On this day" photos on the Today screen.
  - **WebUntis:** the children's timetable, with a push for cancellations and substitutions.
  - **Screen time:** internet time as a reward. Unlocks a device on a Fritz!Box, AdGuard Home or Pi-hole and locks it again.
  - **DWD:** official weather warnings and the pollen forecast, with a push for warnings.
  - **Departures:** the next departures at your stop, with delays and walking time.
  - **Grocy:** Grocy as the shopping list, expiring stock on Today.
  - **Tandoor:** Tandoor as a recipe source next to Cookidoo.
- **Plugin extension points:** plugins can add Today cards, calendars, scheduled jobs, push notifications, reward actions ("unlock internet for 30 minutes"), a shopping list, a recipe source and a timetable. See [plugins](docs/plugins.md).
- **Connection test while installing:** a plugin can check the entered values before they are saved.

### Fixed
- The server could freeze under load because signing in blocked the event loop. (#36)
- Create person: usernames with capital letters are accepted (stored in lower case), an invalid username is explained, and the fields no longer overlap.
- `min_hub_version` compares pre-releases correctly. Hubs still on 1.0.0-beta.2 list the new plugins anyway; installed there, the plugins stay inactive and say that they need 1.0.0-beta.3.

### Upgrading from 1.0.0-beta.2
1. Download a backup in Administration first.
2. `FAMILIENHUB_VERSION=1.0.0-beta.3 docker compose pull && FAMILIENHUB_VERSION=1.0.0-beta.3 docker compose up -d`
3. Three new database migrations run on start. No new settings.

## [1.0.0-beta.2]

The second public beta: eleven new features. The first public installs also brought a few fixes.

### New
- **Plugin and theme store** under *Administration → Store*: browse reviewed themes and plugins with screenshots and install or update them with one click. Admins can add their own GitHub sources, marked "Not reviewed". The [store](https://github.com/Brottuetchen/familienhub-store) launches with the eleven gallery themes. See [store](docs/store.md). (#7)
- **Customisable Today screen:** everyone arranges their own cards (order, show or hide, half or full width), and the admin sets a family default. (#6)
- **Backup and restore** in Administration: download, stored backups, optional nightly backups. A restore checks the backup and saves the current state first. See [getting started](docs/getting-started.md). (#14)
- **Update notice:** Administration shows when a newer release is available, with the update command. It can be switched off. (#15)
- **Recipe import from a link:** paste a recipe page and check the recipe before it is saved to the recipe book. The web app can also be a share target. See [recipe import](docs/recipe-import.md). (#16)
- **Kids mode:** stars for tasks, rewards that parents approve, optional confirmation of completed tasks. See [kids mode](docs/kids-mode.md). (#17)
- **Birthdays and anniversaries** with age, a calendar of their own, a Today card, reminders and gift ideas the birthday person cannot see. See [birthdays](docs/birthdays.md). (#18)
- **Timetable for children** with A/B weeks and school holidays from a calendar subscription. See [timetable](docs/timetable.md). (#19)
- **Template lists** such as packing lists and weekly shopping, for the shopping list or as tasks. See [templates](docs/templates.md). (#20)
- **Voice assistant:** voice endpoints and a ready-made Home Assistant Assist configuration ("Put milk on the shopping list"). See [voice assistant](docs/voice-assistant.md). (#21)
- **Home Assistant add-on** (experimental) in its own repository: [familienhub-ha-addon](https://github.com/Brottuetchen/familienhub-ha-addon).

### Fixed
- Setup wizard: weather and CalDAV were always ticked and listed as connected. Every service can now be unticked, and only ticked services stay on.
- The meal week strip on Today no longer overflows with large text. (#8)

### Changed
- README, German README and roadmap rewritten. Screenshots are current, in light and dark. (#10)
- API keys created in the app for assistants are limited to the voice endpoints. Existing keys keep working as before.

### Upgrading from 1.0.0-beta.1
1. Download a backup or copy your database first. Backup and restore arrive with this release, so beta.1 has no backup button yet.
2. `FAMILIENHUB_VERSION=1.0.0-beta.2 docker compose pull && FAMILIENHUB_VERSION=1.0.0-beta.2 docker compose up -d`
3. The database migrations run on start. Nine new migrations ran without errors from a beta.1 database in testing.
4. New optional settings, all off or with defaults: `BACKUP_AUTO`, `BACKUP_KEEP`, `UPDATE_CHECK`, `UPDATE_CHECK_REPO`, `STORE_INDEX_URL`, `STORE_CACHE_SECONDS`. See [`.env.example`](.env.example).
5. The setup wizard is not re-run. Services that were on before stay on.

## [1.0.0-beta.1]

First public beta.
