# Calendar, tasks and your phone

The hub shows the calendars and task lists of your CalDAV server (Nextcloud, Radicale, mailbox.org …), its own family calendar and calendar subscriptions (ICS) in one place. Your phone can use **the same CalDAV server** with its own apps. Whatever you enter on the phone shows up in the hub, and the other way round.

## In the app

- **Views:** list, week and month. The app remembers your choice.
- **Colours and filter:** every calendar keeps its colour from the server. Tap a chip to hide or show a calendar; this is stored per device.
- **Create in the right calendar:** the new-event sheet asks *which* calendar. The family calendar comes first, then the calendar you used last. Events are written to exactly that calendar, never to a "default" one. Place, notes and repeat (daily, weekly, monthly, yearly) are optional.
- **Details, edit, delete:** tap an event. You can edit events in your own CalDAV calendars and in the hub's family calendar. Subscriptions (ICS) are read-only. For repeating CalDAV events, only title, place and notes can be changed in the hub.
- **Birthdays:** a read-only *Birthdays* calendar shows birthdays and anniversaries, see [birthdays](birthdays.md).
- **Times** are written with the hub's time zone (*Basics* in the setup wizard), so repeating events stay at the same local time across daylight saving changes.

## Set up the family calendar

1. On the CalDAV server, create one calendar for the family (e.g. *Family*) and share it **with write access** with everyone. In Nextcloud: Calendar → ⋯ next to the calendar → *Share* → add the people, tick *can edit*. A shared task list works the same way (a calendar with tasks, in Nextcloud *New calendar with task list*).
2. Admin: *Administration → Plugins & access → CalDAV* → **Name of the family calendar** (`CALDAV_FAMILY_CALENDAR`), e.g. `Family`. Several names are allowed, comma-separated. New events suggest this calendar first.
3. Everyone adds their own account in the app: *More → CalDAV account* (server address, user name, app password). Each person sees their own calendars plus the shared ones.

Without a CalDAV server, the hub's own family calendar is used (*Administration → Sources per area*).

## Connect your phone

Use an **app password**, not your normal password. CalDAV cannot do single sign-on (OIDC). In Nextcloud: *Settings → Security → Devices & sessions → Create new app password*. Use one per device, so you can revoke a lost phone.

The server address must be reachable from the phone. If your server is only reachable at home, keep a VPN (e.g. WireGuard) on; the phone syncs whenever it can reach the server.

### iPhone, iPad, Mac

**With a profile (easiest).** The hub ships a generator for an Apple configuration profile. It contains no password; the device asks for it during installation, so you can send the file by mail or messenger.

```bash
docker compose exec familienhub python -m scripts.caldav_profile \
  --host cloud.example.org --user anna --contacts > anna.mobileconfig
```

Open the file on the iPhone → *Settings → Profile downloaded → Install* → enter the app password. Leave out `--contacts` to add calendars and reminders only. For a server other than Nextcloud, pass its DAV path, e.g. `--dav-path /dav`.

**By hand.** *Settings → Apps → Calendar → Calendar Accounts → Add Account → Other → Add CalDAV Account*: server `cloud.example.org`, user name, app password. For Nextcloud, iOS finds the rest by itself.

Then:
- *Settings → Apps → Calendar → Default Calendar* and *Settings → Apps → Reminders → Default List*: choose a calendar or list of the new account, so new entries no longer go to iCloud.
- Shared calendars (e.g. *Family*) appear automatically.

### Android

Android has no built-in CalDAV. Use **[DAVx⁵](https://www.davx5.com/)** (F-Droid or Play Store):

1. DAVx⁵ → *+* → *Login with URL and user name* → `https://cloud.example.org/remote.php/dav`, user name, app password. With the Nextcloud app installed, *Login with Nextcloud* also works.
2. Tick the calendars, task lists and address books you want.
3. Calendars then appear in any calendar app (Google Calendar, Fossify Calendar, Etar …).
4. For **tasks**, install [jtx Board](https://jtx.techbee.at/) or [Tasks.org](https://tasks.org/) and choose it in DAVx⁵ under *Tasks app*.

### Moving from iCloud or Google

Export the old calendars as `.ics` (iCloud: share the calendar publicly for a moment and download the link, or export on a Mac; Google: *Settings → Import & export*) and import them into the new calendar (Nextcloud Calendar → *Settings → Import calendar*). Keep the old calendars for a while until everything is in place.

Reminders cannot be exported from Apple's Reminders app. Move open reminders by hand, or drag them in Reminders on a Mac from the iCloud list to the new list.

**What tasks over CalDAV can do:** due date and time, repeat, notes, priority, subtasks and alarms. iCloud-only features (tags, smart lists, location reminders, attachments) are not available.

## Tasks

Task lists of the same CalDAV account show up under *Tasks* (source *CalDAV*). Several sources (hub, CalDAV, Habitica) can be active side by side; see [plugins](plugins.md).
