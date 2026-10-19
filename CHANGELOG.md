# Changelog

All notable changes per release. Versions follow the Git tags (`v1.0.0-beta.2` → image `ghcr.io/brottuetchen/familienhub:1.0.0-beta.2`).

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
