# Notification sources: Home Assistant, Shelfarr, Paperless & co.

Other systems send notifications through the hub. The hub stores them in the history and pushes them to the recipients' channels (see [notifications](notifications.md)). Quiet hours and switched-off categories apply.

**For every source:**

1. As admin, create a key under *More → Administration → Service keys*, one per source. It is shown only once.
2. The source sends `Authorization: Bearer fhs_…`.

`https://hub.example` stands for your hub's address below.

## Generic: `POST /api/notify`

```json
{"title": "🧺 Washing machine done", "body": "Please empty it",
 "to": "family", "category": "house", "route": "/today", "silent": false}
```

| Field | Meaning |
|------|-----------|
| `to` | `family`, `admins`, a username or a list of them (case-insensitive) |
| `category` | one of `house`, `shopping`, `media`, `documents`, `reminder`, `task_due`, `task_assigned`, `system` |
| `route` | area that opens on tap, e.g. `/shopping` |
| `silent` | `true` stores the notification in the history without push, for sources that push themselves |

- Response: `{"recipients": [...], "delivered": <number of pushes>}`.
- Unknown recipients or categories return `422`.

## Home Assistant

### `rest_command` in `configuration.yaml`

```yaml
rest_command:
  familienhub_notify:
    url: "https://hub.example/api/notify"
    method: post
    headers:
      Authorization: !secret familienhub_notify_auth   # secrets.yaml: "Bearer fhs_…"
    content_type: "application/json"
    payload: >-
      {"title": {{ title | tojson }}, "body": {{ (body | default('')) | tojson }},
       "to": {{ (to | default('family')) | tojson }}, "category": {{ (category | default('house')) | tojson }},
       "route": {{ (route | default('/today')) | tojson }}, "silent": {{ (silent | default(false)) | tojson }}}
    timeout: 10
  familienhub_arrived:
    url: "https://hub.example/api/reminders/arrived"
    method: post
    headers:
      Authorization: !secret familienhub_notify_auth
    content_type: "application/json"
    payload: '{"user": {{ user | tojson }}}'
    timeout: 10
```

Then reload REST commands in HA (*Developer tools → YAML*).

### Script "Familienhub: notify"

A script with the fields `title`, `body`, `to`, `category`, `route` and `silent` calls `rest_command.familienhub_notify`. Automations then only use the script:

```yaml
action: script.familienhub_notify
data:
  title: "🧺 Washing machine done"
  body: "Please empty it"
  category: house
continue_on_error: true   # hub unreachable → the automation keeps running
```

### Examples

**Washing machine done:** if HA already pushes via the companion app, send the hub `silent: true` so it lands in the history without a second push.

**Bins tomorrow** (a waste calendar, e.g. from "Waste Collection Schedule"):

```yaml
triggers:
  - trigger: calendar
    event: start
    entity_id: calendar.waste
    offset: "-5:00:00"          # event at midnight → 7 pm the evening before
actions:
  - action: script.familienhub_notify
    data:
      title: "🗑️ Tomorrow: {{ trigger.calendar_event.summary }}"
      body: "Put the bin out tonight."
      category: house
```

**Window open and rain:**

```yaml
triggers:
  - trigger: state
    entity_id: weather.home
    to: [rainy, pouring, lightning-rainy]
conditions:
  - condition: state
    entity_id: binary_sensor.all_windows   # group of all windows
    state: "on"
actions:
  - action: script.familienhub_notify
    data:
      title: "🌧️ It's raining – window open"
      body: "{{ expand('binary_sensor.all_windows') | selectattr('state','eq','on') | map(attribute='name') | join(', ') }}"
      category: house
```

**Arrived home**, for "when I get home" reminders:

```yaml
mode: parallel
triggers:
  - trigger: state
    entity_id: person.alex
    to: home
    not_from: [unavailable, unknown]
    id: alex                    # = username in the hub
actions:
  - action: rest_command.familienhub_arrived
    data:
      user: "{{ trigger.id }}"
    continue_on_error: true
```

The hub then sends this person's open arrival reminders. Family reminders go to whoever gets home first.

## Shelfarr (book requests)

In Shelfarr under *Settings → Webhook*:

| Setting | Value |
|-------------|------|
| URL | `https://hub.example/api/books/webhook` |
| Token | the service key (`fhs_…`) |
| Events | `request_completed,request_failed,request_attention` |

| Event | goes to |
|----------|---------|
| completed | the person who requested it |
| failed or needs attention | that person and the admins |
| test button | the admins |

If usernames in Shelfarr differ, map them with `SHELFARR_USER_MAP` (`hubname=shelfarrname,…`).

## Paperless-ngx (new document)

Create a workflow:

- **Trigger:** "Document added"
- **Action:** "Webhook"
  - URL `https://hub.example/api/notify`
  - use parameters: on; send as JSON: on
  - headers `{"Authorization": "Bearer fhs_…"}`
  - parameters (rendered by Paperless with Jinja):

| Key | Value |
|-----------|------|
| `title` | `📄 New document` |
| `body` | `{{ doc_title }}{% if correspondent %} · {{ correspondent }}{% endif %}` |
| `to` | `{{ owner_username }}` |
| `category` | `documents` |

The notification goes to the document owner, whose Paperless username must match the hub username. Documents without an owner produce no notification.
