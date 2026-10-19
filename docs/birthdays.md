# Birthdays, anniversaries and gift ideas

Keep birthdays and anniversaries of family, relatives and friends in the hub (*More → Birthdays*). Everything is stored in the hub itself; no external service is needed.

## Entries

- **Birthday or anniversary** (wedding day, moving-in day …), repeating every year.
- The **year is optional.** With a year the hub shows the age or the number of years ("Grandma turns 80 in 3 days", "Anna & Tom: 10. anniversary tomorrow"); without it, only the date.
- **29 February:** in years without a leap day the hub uses **28 February** (calendar, Today and reminder), so the day is never skipped. With a year given, 29 February is only accepted for leap years.
- **Reminder:** choose how many days before the hub sends a notification (on the day, 1, 3, 7, 14 or 30 days before, or none). Default: 7 days. The notice goes out once per person from 08:00 local time, through the same notification machinery as other reminders (category *Reminders*, so it follows each person's quiet hours and notification settings).
- **Link to a hub account** (optional): marks the entry as that person's own birthday. See *Gift ideas* below.

## Calendar and Today

- **Calendar:** a read-only calendar *Birthdays* appears as its own chip with all-day entries ("🎂 Oma (80)"). It can be hidden like any other calendar and is not editable from the calendar (change entries under *More → Birthdays*). The chip only appears once there is at least one entry.
- **Today:** the *Birthdays* card lists the next entries within 30 days. It is part of the customisable Today layout (hide, reorder, size) and is empty (hidden) when nothing is coming up. Birthdays are not repeated in the *Events* card.

## Gift ideas

Tap an entry to collect gift ideas through the year: text, optional link (`http://` or `https://` only), tick off what is already bought.

**The person themselves never sees them.** If an entry is linked to a hub account, the server answers every gift-idea request from that account (list, add, change, delete) with *not found* and reports no count in the list. This holds for every role including admins, and the ideas appear nowhere else (not in the calendar, Today or notifications). Advance reminders for that entry are not sent to the linked person either.

For entries that are not linked to an account (grandparents, friends), all adults and children see the ideas.

## Who may do what

| Role | See list, calendar, Today card, get reminders | Add gift ideas, tick them off | Delete gift ideas | Create, edit, delete entries |
| --- | --- | --- | --- | --- |
| Guest | no (403, no calendar chip, no reminder) | no | no | no |
| Child | yes | yes | only their own | no |
| Partner / admin | yes | yes | any | yes |

Reasoning: guests are outside the family and should not learn dates or presents. Children can help collect ideas (they often have the best ones) but do not manage the family's data, as with the family calendar.

## API (for developers)

| Endpoint | Purpose |
| --- | --- |
| `GET /api/birthdays` | Entries with `next_date`, `days_until`, `turns`, `gift_count` (null for the linked person) |
| `POST/PUT/DELETE /api/birthdays[/{id}]` | Manage entries (partner and up) |
| `GET/POST /api/birthdays/{id}/gifts`, `PATCH/DELETE …/gifts/{gift_id}` | Gift ideas (404 for the linked person) |
| `GET /api/today` | Adds `birthdays` (next 30 days, max. 5) |
| `GET /api/calendar/events`, `/api/calendar/calendars` | Virtual calendar `birthdays` (source `birthdays`, read-only) |

Database: tables `birthdays` and `gift_ideas` (Alembic migration `18b9d2f4a6c1`).
