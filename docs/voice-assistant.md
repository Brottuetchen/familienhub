# Voice assistant (Home Assistant Assist)

Talk to the hub through Home Assistant's Assist (phone, Voice Preview Edition, any satellite):

- "Put milk and bread on the shopping list"
- "What is on the shopping list?"
- "What's for dinner today?"
- "What's on tomorrow?"
- "Remind me to call Grandma at 6"
- "Add a task water the plants for Anna"

Home Assistant understands the sentence (custom sentences) and calls small, stable endpoints of the hub under `/api/voice`. The hub does the work with the normal sources (shopping list, tasks, meal plan, calendar, reminders) and answers with JSON that contains a short `speech` text. Assist reads that text aloud. German and English are supported.

```
you ──► Assist ──► custom sentence ──► intent_script ──► rest_command ──► Familienhub /api/voice/...
                                                              ◄── {"ok": true, "speech": "Added Milk and Bread ..."}
```

## 1. Create an access key in the app

1. Open the app: **More → Access for assistants → New access**.
2. Name it, for example "Home Assistant". The key is created with the **voice** preset, which grants exactly the six scopes below and nothing else.
3. Copy the key (`fhp_...`). It is shown **once**. The hub stores only a hash.

A key acts as the person who created it: reminders and tasks belong to that person, and the same roles apply as in the app. Use a separate key (and ideally a separate account) per household member if you want "my" reminders for each. Revoke a key in the same screen; it stops working immediately.

A key with scopes can **only** call `/api/voice/...`. Everything else (`/api/tasks`, `/api/today`, ...) answers `403` for it.

You can also create a key through the API (for example to grant fewer scopes):

```bash
curl -X POST https://hub.example.org/api/auth/api-tokens \
  -H "Authorization: Bearer <your app access token>" -H "Content-Type: application/json" \
  -d '{"name": "Kitchen display", "scopes": ["meals:read", "calendar:read"]}'
```

### Scopes

| Scope | Endpoint | Role needed |
|---|---|---|
| `shopping:write` | `POST /api/voice/shopping/items` | any (like the app) |
| `shopping:read` | `GET /api/voice/shopping` | any |
| `tasks:write` | `POST /api/voice/tasks` | partner or admin |
| `meals:read` | `GET /api/voice/meals` | any |
| `calendar:read` | `GET /api/voice/events` | any |
| `reminders:write` | `POST /api/voice/reminders` | any (always a private reminder for the key's owner) |

Keys created before scopes existed keep working as before (unrestricted). Prefer a scoped key for assistants.

## 2. Store the key in Home Assistant

Add one line to `secrets.yaml` (the value contains the word `Bearer`, a space and the key):

```yaml
# secrets.yaml
familienhub_auth: "Bearer fhp_PASTE_YOUR_KEY_HERE"
```

The hub address is written directly into the `rest_command` URLs below, because Home Assistant cannot put a secret into the middle of a URL. Replace `hub.example.org` with your hub's address (use HTTPS if the hub is reachable from outside).

## 3. `rest_command` and `intent_script`

Add this to `configuration.yaml` (or an included file). Every intent has a spoken fallback in both languages if the hub cannot be reached at all, so Assist never ends with a generic error.

```yaml
# configuration.yaml
rest_command:
  familienhub_shopping_add:
    url: "https://hub.example.org/api/voice/shopping/items"
    method: post
    headers:
      authorization: !secret familienhub_auth
      content-type: application/json
    payload: '{"items": {{ items | tojson }}}'
    timeout: 15
  familienhub_shopping_open:
    url: "https://hub.example.org/api/voice/shopping"
    method: get
    headers:
      authorization: !secret familienhub_auth
    timeout: 15
  familienhub_task_add:
    url: "https://hub.example.org/api/voice/tasks"
    method: post
    headers:
      authorization: !secret familienhub_auth
      content-type: application/json
    payload: '{"title": {{ title | tojson }}, "assignee": {{ (assignee | default("")) | tojson }}}'
    timeout: 15
  familienhub_meals:
    url: "https://hub.example.org/api/voice/meals?day={{ day }}"
    method: get
    headers:
      authorization: !secret familienhub_auth
    timeout: 15
  familienhub_events:
    url: "https://hub.example.org/api/voice/events?day={{ day }}"
    method: get
    headers:
      authorization: !secret familienhub_auth
    timeout: 15
  familienhub_reminder_add:
    url: "https://hub.example.org/api/voice/reminders"
    method: post
    headers:
      authorization: !secret familienhub_auth
      content-type: application/json
    payload: '{"text": {{ text | tojson }}, "when": {{ when | tojson }}}'
    timeout: 15

intent_script:
  FamilienhubShoppingAdd:
    action:
      - action: rest_command.familienhub_shopping_add
        data:
          items: "{{ items }}"
        continue_on_error: true
        response_variable: hub
      - variables:
          reply:
            speech: >-
              {{ hub.content.speech if hub is defined and hub.content is mapping and hub.content.speech is defined
                 else "Familienhub is not reachable. / Familienhub ist nicht erreichbar." }}
      - stop: "done"
        response_variable: reply
    speech:
      text: "{{ action_response.speech }}"

  FamilienhubShoppingOpen:
    action:
      - action: rest_command.familienhub_shopping_open
        continue_on_error: true
        response_variable: hub
      - variables:
          reply:
            speech: >-
              {{ hub.content.speech if hub is defined and hub.content is mapping and hub.content.speech is defined
                 else "Familienhub is not reachable. / Familienhub ist nicht erreichbar." }}
      - stop: "done"
        response_variable: reply
    speech:
      text: "{{ action_response.speech }}"

  FamilienhubTaskAdd:
    action:
      - action: rest_command.familienhub_task_add
        data:
          title: "{{ title }}"
          assignee: "{{ assignee | default('') }}"
        continue_on_error: true
        response_variable: hub
      - variables:
          reply:
            speech: >-
              {{ hub.content.speech if hub is defined and hub.content is mapping and hub.content.speech is defined
                 else "Familienhub is not reachable. / Familienhub ist nicht erreichbar." }}
      - stop: "done"
        response_variable: reply
    speech:
      text: "{{ action_response.speech }}"

  FamilienhubMeals:
    action:
      - action: rest_command.familienhub_meals
        data:
          day: "{{ day | default('today') }}"
        continue_on_error: true
        response_variable: hub
      - variables:
          reply:
            speech: >-
              {{ hub.content.speech if hub is defined and hub.content is mapping and hub.content.speech is defined
                 else "Familienhub is not reachable. / Familienhub ist nicht erreichbar." }}
      - stop: "done"
        response_variable: reply
    speech:
      text: "{{ action_response.speech }}"

  FamilienhubEvents:
    action:
      - action: rest_command.familienhub_events
        data:
          day: "{{ day | default('today') }}"
        continue_on_error: true
        response_variable: hub
      - variables:
          reply:
            speech: >-
              {{ hub.content.speech if hub is defined and hub.content is mapping and hub.content.speech is defined
                 else "Familienhub is not reachable. / Familienhub ist nicht erreichbar." }}
      - stop: "done"
        response_variable: reply
    speech:
      text: "{{ action_response.speech }}"

  # "at 6", "18:30", "halb sieben" ...
  FamilienhubReminderAt:
    action:
      - action: rest_command.familienhub_reminder_add
        data:
          text: "{{ text }}"
          when: "at {{ when }}"
        continue_on_error: true
        response_variable: hub
      - variables:
          reply:
            speech: >-
              {{ hub.content.speech if hub is defined and hub.content is mapping and hub.content.speech is defined
                 else "Familienhub is not reachable. / Familienhub ist nicht erreichbar." }}
      - stop: "done"
        response_variable: reply
    speech:
      text: "{{ action_response.speech }}"

  # "in 20 minutes", "in einer Stunde"
  FamilienhubReminderIn:
    action:
      - action: rest_command.familienhub_reminder_add
        data:
          text: "{{ text }}"
          when: "in {{ when }}"
        continue_on_error: true
        response_variable: hub
      - variables:
          reply:
            speech: >-
              {{ hub.content.speech if hub is defined and hub.content is mapping and hub.content.speech is defined
                 else "Familienhub is not reachable. / Familienhub ist nicht erreichbar." }}
      - stop: "done"
        response_variable: reply
    speech:
      text: "{{ action_response.speech }}"

  # "tomorrow at 8", "morgen um 18 Uhr"
  FamilienhubReminderTomorrow:
    action:
      - action: rest_command.familienhub_reminder_add
        data:
          text: "{{ text }}"
          when: "tomorrow at {{ when }}"
        continue_on_error: true
        response_variable: hub
      - variables:
          reply:
            speech: >-
              {{ hub.content.speech if hub is defined and hub.content is mapping and hub.content.speech is defined
                 else "Familienhub is not reachable. / Familienhub ist nicht erreichbar." }}
      - stop: "done"
        response_variable: reply
    speech:
      text: "{{ action_response.speech }}"
```

The `action_response` of an `intent_script` and `response_variable` on `rest_command` need a current Home Assistant release (2024.8 or newer). Check configuration (**Developer tools → YAML → Check configuration**) and reload scripts or restart.

## 4. Custom sentences

Put one file per language in `<config>/custom_sentences/<language>/`. The intent names must match the `intent_script` names above. The `{...}` words are slots: wildcards take whatever you said; `day` only accepts the listed words.

### English

```yaml
# custom_sentences/en/familienhub.yaml
language: "en"
intents:
  FamilienhubShoppingAdd:
    data:
      - sentences:
          - "(put|add) {items} (on|to) [the|my|our] (shopping|grocery) list"
          - "we need {items} from the (shop|store|supermarket)"
  FamilienhubShoppingOpen:
    data:
      - sentences:
          - "what is on [the|our] (shopping|grocery) list"
          - "what (do we|do I) need to buy"
  FamilienhubTaskAdd:
    data:
      - sentences:
          - "(add|create) [a] task {title} for {assignee}"
          - "(add|create) [a] task {title}"
  FamilienhubMeals:
    data:
      - sentences:
          - "what is [for] (dinner|lunch|the menu|on the menu) [{day}]"
          - "what are we (eating|having|cooking) [{day}]"
  FamilienhubEvents:
    data:
      - sentences:
          - "what is on [the calendar] {day}"
          - "what (events|appointments) do (we|I) have {day}"
          - "do (we|I) have (any|something) (events|appointments) {day}"
  FamilienhubReminderAt:
    data:
      - sentences:
          - "remind me to {text} at {when}"
          - "remind me at {when} to {text}"
  FamilienhubReminderIn:
    data:
      - sentences:
          - "remind me to {text} in {when}"
          - "remind me in {when} to {text}"
  FamilienhubReminderTomorrow:
    data:
      - sentences:
          - "remind me to {text} tomorrow at {when}"
          - "remind me tomorrow at {when} to {text}"
lists:
  items:
    wildcard: true
  title:
    wildcard: true
  assignee:
    wildcard: true
  text:
    wildcard: true
  when:
    wildcard: true
  day:
    values:
      - in: "today"
        out: "today"
      - in: "tomorrow"
        out: "tomorrow"
```

### German

```yaml
# custom_sentences/de/familienhub.yaml
language: "de"
intents:
  FamilienhubShoppingAdd:
    data:
      - sentences:
          - "(setz|setze|schreib|schreibe|pack|packe) {items} auf die Einkaufsliste"
          - "(füge|fuege) {items} zur Einkaufsliste hinzu"
          - "wir brauchen {items} [vom Einkaufen]"
  FamilienhubShoppingOpen:
    data:
      - sentences:
          - "was steht auf der Einkaufsliste"
          - "was müssen wir einkaufen"
          - "was brauchen wir noch"
  FamilienhubTaskAdd:
    data:
      - sentences:
          - "(erstelle|lege|leg) [eine] Aufgabe {title} (für|fuer) {assignee} an"
          - "(erstelle|lege|leg) [eine] Aufgabe {title} an"
          - "neue Aufgabe {title} (für|fuer) {assignee}"
          - "neue Aufgabe {title}"
  FamilienhubMeals:
    data:
      - sentences:
          - "was gibt es {day} (zu essen|zum Abendessen|zum Mittagessen)"
          - "was gibt es zu essen"
          - "was kochen wir [{day}]"
  FamilienhubEvents:
    data:
      - sentences:
          - "welche Termine (haben wir|habe ich) {day}"
          - "was steht {day} an"
          - "was ist {day} im Kalender"
  FamilienhubReminderAt:
    data:
      - sentences:
          - "erinnere mich um {when} an {text}"
          - "erinnere mich an {text} um {when}"
  FamilienhubReminderIn:
    data:
      - sentences:
          - "erinnere mich in {when} an {text}"
          - "erinnere mich an {text} in {when}"
  FamilienhubReminderTomorrow:
    data:
      - sentences:
          - "erinnere mich morgen um {when} an {text}"
          - "erinnere mich morgen an {text} um {when}"
lists:
  items:
    wildcard: true
  title:
    wildcard: true
  assignee:
    wildcard: true
  text:
    wildcard: true
  when:
    wildcard: true
  day:
    values:
      - in: "heute"
        out: "today"
      - in: "morgen"
        out: "tomorrow"
```

Reload the conversation sentences (restart Home Assistant, or **Developer tools → YAML**, or the `conversation.reload` action). Then try the phrases in **Settings → Voice assistants → Debug**.

## 5. What the hub understands

### Shopping

"milk, bread and eggs" becomes three entries (split at commas, "and", "und", "&"). Leading words such as "some", "a", "ein" are dropped and the first letter is capitalised. At most 20 entries per call. Items go to whatever source the hub uses for the shopping list (Home Assistant to-do list, Mealie or the hub's own list), exactly like the app.

### Tasks

`assignee` is optional: a first name, display name or username of an active family member (not guests). "me", "myself", "mich", "mir" mean the key's owner. Unknown or ambiguous names are not guessed; the answer asks you to say the name again. The task lands where the app would put it (the recipient's own task place, with her account) and she gets the usual notification. Children and guests cannot add tasks, like in the app.

### Spoken times for reminders

The `when` text is interpreted in the hub's time zone (`TIMEZONE`):

| You say | Meaning |
|---|---|
| "at 6", "um 6" | the next 6 o'clock (18:00 if it is 07:00, 06:00 if it is 05:00) |
| "18:30", "6:30 pm", "um 18 Uhr 30" | exactly that time; today, or tomorrow if already past |
| "6 Uhr" | 06:00 (German "Uhr" means the 24-hour clock) |
| "in 20 minutes", "in einer Stunde", "in half an hour", "in 2 hours and 15 minutes" | relative to now |
| "tomorrow at 8", "morgen um halb sieben", "übermorgen um 10 Uhr" | with a day; a bare 1 to 6 means afternoon, 7 to 11 morning |
| "friday at 3", "am Freitag um 15 Uhr" | next such weekday |
| "quarter past 6", "viertel vor sieben", "noon", "midnight" | as said |

If nothing usable was said, the hub answers "I did not understand the time ..." and creates nothing. A time that is already over answers "That time has already passed." Reminders are always private to the key's owner.

### Meals and events

`day` is `today`, `tomorrow` or a date (`2026-10-24`). Meals come from every active meal-plan source; events from every active calendar source, for the key's owner.

## 6. Language and errors

The `speech` language is the key owner's app language. Override it per call with `?lang=de` / `?lang=en` or an `Accept-Language` header.

Every answer is HTTP 200 with the same shape, also when something went wrong:

```json
{"ok": false, "status": "unavailable", "lang": "en", "speech": "The shopping list is not reachable right now.", "items": []}
```

`status` is one of `ok`, `invalid` (nothing understood), `not_found` / `ambiguous` (person), `forbidden` (role too low), `partial` (some shopping items failed) and `unavailable` (a source is down). Only a wrong or missing key (`401`) or a missing scope (`403`) are HTTP errors, so a broken setup is loud.

## Testing without Assist

```bash
KEY=fhp_...
curl -s -H "Authorization: Bearer $KEY" "https://hub.example.org/api/voice/meals?day=tomorrow&lang=en"
curl -s -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"items": "milk, bread and eggs"}' https://hub.example.org/api/voice/shopping/items
curl -s -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"text": "call Grandma", "when": "at 6"}' https://hub.example.org/api/voice/reminders
```

## Troubleshooting

- **Assist says the hub is not reachable:** check the URL and the `Authorization` secret; `curl` the same call from the Home Assistant host.
- **403 "lacks scope":** the key was created without that scope; create a new one with the voice preset.
- **Nothing happens for a sentence:** the sentence did not match. Test it under **Voice assistants → Debug**; wildcards need the `lists` block.
- **Reminder at the wrong hour:** "at 6" is the *next* 6 o'clock. Say "6 in the morning", "6 am" or "tomorrow at 6" (afternoon) to be explicit; check `TIMEZONE` of the hub.

## Future work

A Home Assistant custom integration (config flow with the hub address and key, a todo entity for the shopping list, calendar entities and services instead of hand-written `rest_command`s) is possible later. The `/api/voice` endpoints are kept small and stable so such an integration can build on them.
