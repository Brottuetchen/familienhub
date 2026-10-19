# Timetable for children

A weekly timetable per child: school lessons, sports, music and clubs. You find it under *More → Timetable* and as a card on *Today*.

## Who can do what

| Role | Timetable |
|---|---|
| Admin, partner | see every child, add, edit, delete, copy, change the settings |
| Child | sees their own timetable only, cannot change anything |
| Guest | no access |

Children are the accounts with the **Child** role. The rules are enforced by the server, not only hidden in the app.

## Entering the timetable

The screen is a day-by-day list (Monday to Sunday), so it fits any phone at any text size. Each entry has a title, a kind (school, sports, music, club, other), a start and end time, an optional place and the weekday.

To enter things quickly:

- **Copy a day:** the copy button next to a weekday copies that day to the weekdays you tick. The target days are replaced.
- **Copy a week:** with A/B weeks switched on, the menu has *Copy week A to week B* (and back). The target week is replaced.

## A/B weeks

Some schools alternate two timetables every other week. Open *Menu → Settings*, switch on **A/B weeks** and pick any day inside a week that is an **A week**. The weeks then alternate automatically from that reference week; the screen shows which one is current.

Entries are marked *Every week*, *Week A* or *Week B*. Without A/B weeks only the *Every week* entries are used.

## School holidays

Lessons (kind *School*) are hidden on school-holiday days. Sports, music and clubs stay.

The holidays come from one of your **calendar subscriptions** (ICS):

1. An admin adds the school-holiday calendar of your state or school under *Administration → Calendar subscriptions* (for example the public ICS feed of your state's school holidays).
2. A parent opens *Timetable → Menu → Settings* and chooses that subscription as the **Holiday calendar**. Every event in it counts as a holiday period (all-day events end on the day before their end date, as in any calendar).

Without a chosen calendar, or if the subscription cannot be reached, lessons are simply shown. The choice applies to all children.

## Today

The *Timetable* card on *Today* says, for example: **Mia: School until 13:15, Swimming 16:00**. A child sees their own day, parents see all children. On holidays it says *School holidays* in place of the lessons. The card only appears when there is something to show, and can be moved or hidden like the other cards (*Today → customise*).

Days and times follow the hub's time zone (*Basics* in the setup wizard).

## For developers

| Endpoint | Purpose | Role |
|---|---|---|
| `GET /api/timetable/children` | children the caller may see | child (self), partner, admin |
| `GET /api/timetable?child_id=` | entries, settings, current week, holidays | same |
| `POST /api/timetable`, `PATCH/DELETE /api/timetable/{id}` | edit entries | partner, admin |
| `POST /api/timetable/copy-day`, `/copy-week` | copy | partner, admin |
| `GET/PUT /api/timetable/settings` | `ab_reference` (a date), `holiday_feed` (subscription id) | partner, admin |
| `GET /api/timetable/today` | the same data as the `timetable` key of `GET /api/today` | any signed-in user |

Entries live in `timetable_entries`; the two settings are stored in `config_overrides` (`TIMETABLE_AB_REFERENCE`, `TIMETABLE_HOLIDAY_FEED`).
