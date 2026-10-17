# Quellen anbinden: Mitteilungen von anderen Systemen

Andere Systeme schicken Mitteilungen über den Hub. Der Hub legt sie im Verlauf ab und pusht sie an die Geräte der Empfänger. Ruhezeiten und abgeschaltete Kategorien gelten dabei.

**Ablauf für jede Quelle:**

1. In der App unter *Mehr → Dienst-Schlüssel* einen Schlüssel anlegen (Admin), einen pro Quelle. Er wird nur einmal angezeigt.
2. Die Quelle schickt `Authorization: Bearer fhs_…` mit.

In den Beispielen steht `https://hub.example` für die Adresse des Hubs.

## Allgemein: `POST /api/notify`

```json
{"title": "🧺 Waschmaschine fertig", "body": "Bitte ausräumen",
 "to": "family", "category": "house", "route": "/today", "silent": false}
```

| Feld | Bedeutung |
|------|-----------|
| `to` | `family`, `admins`, ein Benutzername oder eine Liste davon (Groß-/Kleinschreibung egal). |
| `category` | Eine von: `house`, `shopping`, `media`, `documents`, `reminder`, `task_due`, `task_assigned`, `system`. |
| `route` | Bereich, der sich beim Antippen öffnet, z. B. `/shopping`. |
| `silent` | `true` legt die Mitteilung nur im Verlauf ab, ohne Push. Gedacht für Quellen, die selbst schon pushen. |

- Antwort: `{"recipients": [...], "delivered": <Anzahl Pushes>}`.
- Unbekannte Empfänger oder Kategorien ergeben `422`.

## Home Assistant

### `rest_command` in der `configuration.yaml`

```yaml
rest_command:
  familienhub_mitteilung:
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
  familienhub_ankunft:
    url: "https://hub.example/api/reminders/arrived"
    method: post
    headers:
      Authorization: !secret familienhub_notify_auth
    content_type: "application/json"
    payload: '{"user": {{ user | tojson }}}'
    timeout: 10
```

Danach in HA *Entwicklerwerkzeuge → YAML → REST-Befehle neu laden*.

### Skript „Familienhub: Mitteilung“

Ein Skript mit den Feldern `title`, `body`, `to`, `category`, `route` und `silent` ruft `rest_command.familienhub_mitteilung` auf. Automationen nutzen dann nur noch das Skript.

```yaml
action: script.familienhub_mitteilung
data:
  title: "🧺 Waschmaschine fertig"
  body: "Bitte ausräumen"
  category: house
continue_on_error: true   # Hub nicht erreichbar → Automation läuft trotzdem weiter
```

### Vorlagen

**Waschmaschine fertig:**
- HA pusht selbst über die Companion-App.
- Der Hub bekommt die Mitteilung mit `silent: true` nur für den Verlauf, so gibt es keinen doppelten Push.

**Müll morgen** (ein Abfallkalender, z. B. aus der Integration „Waste Collection Schedule“):

```yaml
triggers:
  - trigger: calendar
    event: start
    entity_id: calendar.abfall
    offset: "-5:00:00"          # Termin 0 Uhr → Vorabend 19 Uhr
actions:
  - action: script.familienhub_mitteilung
    data:
      title: "🗑️ Morgen: {{ trigger.calendar_event.summary }}"
      body: "Tonne heute Abend rausstellen."
      category: house
```

**Fenster offen und Regen:**

```yaml
triggers:
  - trigger: state
    entity_id: weather.home
    to: [rainy, pouring, lightning-rainy]
conditions:
  - condition: state
    entity_id: binary_sensor.fenster_alle   # Gruppe aller Fenster
    state: "on"
actions:
  - action: script.familienhub_mitteilung
    data:
      title: "🌧️ Es regnet – Fenster offen"
      body: "{{ expand('binary_sensor.fenster_alle') | selectattr('state','eq','on') | map(attribute='name') | join(', ') }}"
      category: house
```

**Ankunft melden**, für die Erinnerungen „Wenn ich nach Hause komme“:

```yaml
mode: parallel
triggers:
  - trigger: state
    entity_id: person.alex
    to: home
    not_from: [unavailable, unknown]
    id: alex                    # = Benutzername im Hub
actions:
  - action: rest_command.familienhub_ankunft
    data:
      user: "{{ trigger.id }}"
    continue_on_error: true
```

Der Hub schickt dann die offenen Ankunfts-Erinnerungen dieser Person. Familien-Erinnerungen bekommt, wer zuerst heimkommt.

## Shelfarr (Bücherwünsche)

In Shelfarr unter *Einstellungen → Webhook*:

| Einstellung | Wert |
|-------------|------|
| URL | `https://hub.example/api/books/webhook` |
| Token | der Dienst-Schlüssel (`fhs_…`) |
| Ereignisse | `request_completed,request_failed,request_attention` |

| Ereignis | geht an |
|----------|---------|
| Fertig | nur an die Person, die gewünscht hat |
| Fehlgeschlagen oder Eingriff nötig | an diese Person und die Admins |
| Test-Knopf | an die Admins |

Weichen die Benutzernamen in Shelfarr ab, ordnet `SHELFARR_USER_MAP` sie zu.

## Paperless-ngx (neues Dokument)

Einen Workflow anlegen:

- **Auslöser:** „Dokument hinzugefügt“.
- **Aktion:** „Webhook“.
  - URL: `https://hub.example/api/notify`.
  - Parameter verwenden: an. Als JSON senden: an.
  - Header: `{"Authorization": "Bearer fhs_…"}`.
  - Parameter (Paperless rendert sie mit Jinja):

| Schlüssel | Wert |
|-----------|------|
| `title` | `📄 Neues Dokument` |
| `body` | `{{ doc_title }}{% if correspondent %} · {{ correspondent }}{% endif %}` |
| `to` | `{{ owner_username }}` |
| `category` | `documents` |

- Die Mitteilung geht an den Eigentümer des Dokuments, dessen Paperless-Benutzername dem im Hub entsprechen muss.
- Dokumente ohne Eigentümer erzeugen keine Mitteilung.
