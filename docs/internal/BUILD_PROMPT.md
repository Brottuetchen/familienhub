# Bauauftrag Familienhub v1, Version 2 (verbindlich)

> Ersetzt Version 1. Gilt für jeden Agenten, der in diesem Repo arbeitet.
> Grund für Version 2: Paket 1–3 wurden am 13.10. mit roten Tests gemergt. Erfolg wurde ohne Beleg gemeldet,
> Anforderungen wurden still weggelassen (CalDAV pro Nutzer, Ansichten-Filter, Push bei Zuweisung), und ein Test wurde so
> umgebaut, dass er sich selbst bestätigt. Version 2 legt deshalb Schnittstellen, Testfälle und Arbeitsweise genau fest.

---

## Teil A: Arbeitsweise (nicht verhandelbar)

### A1. Ablauf pro Arbeitspaket
1. Branch `wp-<nr>-<kurzname>` von aktuellem `main` (vorher `git pull`).
2. **Zuerst die Tests aus der Testliste des Pakets schreiben**, mit genau den angegebenen Namen. Laufen lassen und die
   roten Ergebnisse festhalten.
3. Implementieren, bis die neuen Tests **und alle bestehenden Tests** grün sind.
4. Pflicht-Prüfungen ausführen (A3) und die **wörtliche Ausgabe** in den PR kopieren.
5. PR gegen `main` mit dem Template aus A5. **Niemals selbst mergen** (Branch-Schutz: nur Maintainer dürfen).
6. Auf Review warten. Änderungswünsche im selben Branch umsetzen. Erst nach dem Merge das nächste Paket beginnen.

### A2. Verboten
- Erfolg melden ohne kopierte Befehlsausgabe. Eine Formulierung wie „alle Tests grün“ ist nur mit der Ausgabe
  `N passed` ohne `failed`/`error` zulässig.
- **Bestehende Tests ändern oder löschen**, außer der PR nennt unter „Geänderte Tests“ jeden betroffenen Test mit Grund und
  mit dem Verweis auf die Entscheidung in `docs/internal/ENTSCHEIDUNGEN.md`, die ihn überholt (Beispiel: Plex entfernt).
- **Mocks, die das erwartete Ergebnis vorgeben.** Ein Mock simuliert das Fachsystem (HTTP-Antworten, CalDAV-Objekte).
  Er beantwortet nie die Frage, die der Test prüft. Beispiel für Verbotenes: `connector.is_enabled = enabled`.
- **Fehler schlucken:** `except Exception: return []`, `except: pass`, `contextlib.suppress(Exception)`.
  Erlaubt ist das Abfangen nur an der Konnektor-Grenze, und dann gilt:
  - Der Fehler wird mit `logger.warning(..., exc_info=True)` geloggt.
  - Die API-Antwort setzt `status: "unavailable"` und `error: "<kurze Ursache>"`.
  - Ein Test prüft genau diesen Fehlerfall.
- **Platzhalter im Produktivcode:** `return True  # später überschreiben`, `pass`-Funktionen, `TODO`-Stubs, `NotImplementedError` in
  ausgelieferten Pfaden.
- **Erfundene Bibliotheks-APIs.** Wer eine Bibliotheksfunktion nutzt, die er nicht in der installierten Version nachgesehen
  hat (`python -c "import caldav, inspect; print(inspect.signature(...))"`), verstößt gegen diese Regel.
- Hausdaten im Code (IPs, Domains, Personennamen, echte Entitäten außer den dokumentierten Defaults), Geheimnisse im Repo.
- Schreibzugriffe auf echte Homelab-Dienste, Push an echte Geräte, Deployment.

### A3. Pflicht-Prüfungen vor jedem PR
```
cd backend && PYTHONPATH=. ~/fh-venv/bin/python -m pytest -q 2>&1 | tail -15
cd backend && ~/fh-venv/bin/python -m ruff check app tests --select E9,F63,F7,F82 2>&1 | tail -5   # nur echte Fehler (wie Upstream-CI)
# nur wenn app/ geändert wurde (auf dem Build-Server, siehe CLAUDE.md):
cd ~/familienhub/app && flutter analyze 2>&1 | tail -5 && flutter test 2>&1 | tail -5
git diff --stat main...HEAD
```
Ein PR ist nur zulässig, wenn pytest **0 failed / 0 errors** meldet, ruff ohne Befund ist und (falls betroffen) `flutter analyze`
**0 errors** und `flutter test` alles grün meldet.

### A4. Fortschrittsmeldungen
Im Issue „Fortschritt Familienhub v1“ nach jedem PR genau dieses Format:
```
WP <nr> – <Titel> – PR #<n>
Tests: <letzte pytest-Zeile wörtlich>
Neu: <Liste der neuen Testnamen>
Geänderte Tests: <keine | Name – Grund – Verweis>
Abweichungen vom Auftrag: <keine | was und warum>
Offen: <keine | was>
```

### A5. PR-Template
Das Template liegt in `.forgejo/pull_request_template.md` und muss vollständig ausgefüllt sein.

---

## Teil B: Gemeinsame technische Vorgaben

### B1. Benutzer und Identität
- Hub-Nutzer = Tabelle `users` (vorhanden). Rollen `admin|partner|kind|gast` (vorhanden).
- Jede API ist authentifiziert (`get_current_user`), außer `/api/health` und den OIDC-Endpunkten.
- Antworten nutzen **Hub-User-IDs** (int) für Personen, niemals Nextcloud-Benutzernamen.

### B2. Fehler- und Statusformat für alle Listen-Endpunkte
```json
{ "status": "ok" | "unavailable" | "not_configured", "error": null | "kurzer Text", "items": [ ... ] }
```
HTTP 200 auch bei `unavailable`. HTTP 4xx nur bei Eingabefehlern (422) und fehlender Berechtigung (403). 5xx ist ein Bug.

### B3. Konfiguration
Alle neuen Einstellungen in `app/config.py` (pydantic-settings) mit Default und Eintrag in `.env.example` (Platzhalter).
Nutzerbezogene Geheimnisse (CalDAV-App-Passwort, Habitica-Key) **verschlüsselt** in der DB über `app/core/crypto.py`
und nie in API-Antworten (dort `"has_password": true`).

### B4. Migrationen
Jede Modelländerung = Alembic-Migration mit `upgrade` und `downgrade`. Test `tests/test_migrations.py` muss grün bleiben.

---

## Teil C: Arbeitspakete

Reihenfolge ist verbindlich. **WP 0 läuft bereits** (Branch `korrektur`).

### WP 0 – Korrektur (Bestand reparieren)
Ziel: `main` + Korrekturen = alle Tests grün, ohne Tests abzuschwächen.
- Feature-Flags zentral in der Registry: Zuordnung Konnektor-Name → Flag als Konstante `FEATURE_BY_CONNECTOR`
  in `app/connectors/registry.py`. Konnektoren ohne Eintrag sind immer aktiv. **Kein** `is_enabled` an Konnektoren.
- `added_to_kitchenowl` in der Meals-API umbenennen in `added_to_shopping`. Ziel ist `HA_SHOPPING_TODO`.
- Branding: `APP_NAME` wirkt in `index.html`, `login.html`, `manifest.webmanifest` und `/api/health` (`app_name`).
  HTML-Escaping prüfen (Test mit `Unser <Hub> & "Familie"` existiert).
- Pflicht-Tests: Die vorhandenen Tests in `tests/test_features.py` laufen **unverändert** gegenüber `main` (`git diff main -- backend/tests/test_features.py` leer).
  Ausnahme ist eine im PR begründete Änderung.
- Abnahme: pytest 0 failed.

### WP 2b – Aufgaben über Nextcloud CalDAV, richtig
Ersetzt die Umsetzung aus Paket 2.

**Modelle (Migration):**
- `caldav_accounts`: `id`, `user_id` (unique, FK users), `url`, `username`, `password_enc`, `created_at`, `updated_at`.
- `task_lists`: `id`, `user_id` (Besitzer im Hub), `caldav_url` (URL der Liste, unique), `display_name`,
  `kind` (`personal`|`family`|`hidden`), `owner_user_id` (für wen die Liste gilt; bei `family` = NULL).

**CalDAV-Zugriff** (`app/connectors/nextcloud_tasks_connector.py`, Bibliothek `caldav==1.4.0`):
- Verbindung **pro Hub-Nutzer** mit dessen `caldav_accounts`-Eintrag. Kein globales Konto.
  `CALDAV_*` in der `.env` dient nur noch als Fallback für Admin-Tests und ist in der Doku so markiert.
- Listen finden: `client.principal().calendars()`. Davon nur Kalender, deren `get_supported_components()` `"VTODO"` enthält.
  Die Signaturen vorher in der installierten Version prüfen (Regel A2).
- Lesen: `calendar.todos(include_completed=<bool>)`. Pro Objekt `obj.icalendar_component` auswerten.
- Anlegen: VTODO mit `UID` (uuid4), `SUMMARY`, optional `DESCRIPTION`, `DUE` (DATE oder DATE-TIME mit TZID Europe/Berlin aus
  Konfiguration `TIMEZONE`), `PRIORITY` (1/5/9), `STATUS:NEEDS-ACTION`, `X-FAMILIENHUB-CREATED-BY`, `X-FAMILIENHUB-ASSIGNEE`.
  Danach `calendar.save_todo(ical=...)` bzw. die in 1.4.0 vorhandene Entsprechung.
- Ändern: Objekt laden, **nur die geänderten Properties** am geladenen `icalendar_component` setzen, dann speichern.
  Alle anderen Properties (zum Beispiel `X-APPLE-SORT-ORDER`, `RELATED-TO`, `CATEGORIES`) bleiben byte-gleich erhalten.
- Erledigen: `todo.complete()` (in 1.4.0 vorhanden), Ergebnis: `STATUS:COMPLETED`, `COMPLETED:<utc>`, `PERCENT-COMPLETE:100`.
- **Hinweis:** `principal.tasks_list()` gibt es in caldav 1.4.0 nicht (geprüft 13.10.). Die bisherige Umsetzung lieferte deshalb immer eine leere Liste.
- Aufgabe für eine andere Person: in deren `personal`-Liste anlegen, mit den Zugangsdaten des **Erstellers**.
  Die Liste muss dem Ersteller in Nextcloud mit Schreibrecht geteilt sein. Fehlt das Recht (HTTP 403 vom Server),
  antwortet die API mit **HTTP 409** und `{"error": "no_write_access", "list": "<display_name>"}`.

**API** (`app/routers/tasks.py`):

| Methode | Pfad | Eingabe | Ausgabe |
|---|---|---|---|
| GET | `/api/tasks?view=mine\|for_me\|from_me\|family\|all&include_done=false` | – | B2 mit `items: Task[]` |
| POST | `/api/tasks` | `{title, notes?, due?, priority?, assignee_id?, list?: "family"}` | `201 Task` |
| PATCH | `/api/tasks/{uid}` | Teilfelder | `200 Task` |
| POST | `/api/tasks/{uid}/complete` | – | `200 Task` |
| DELETE | `/api/tasks/{uid}` | – | `204` |
| GET/PUT | `/api/me/caldav` | `{url, username, password}` | `{url, username, has_password}` |
| GET/PUT | `/api/me/task-lists` | Liste von `{caldav_url, kind, owner_user_id?}` | gespeicherte Zuordnung |

`Task = {uid, title, notes, due, priority, done, list: {name, kind}, created_by: user_id|null, assignee: user_id|null, etag}`

**Ansichten** (Ich = aktueller Nutzer):
- `mine`: in meiner `personal`-Liste, `assignee` ist ich oder leer.
- `for_me`: in meiner `personal`-Liste, `created_by` ≠ ich.
- `from_me`: in einer fremden `personal`-Liste, `created_by` = ich.
- `family`: in der `family`-Liste.
- `all`: Vereinigung, ohne `hidden`-Listen.

**Push:** `POST /api/tasks` mit `assignee_id` ≠ Ersteller ruft `notify(assignee, category="task_assigned", ...)` auf (WP 4 liefert `notify`;
bis dahin ein Interface `app/services/notify.py` mit `async def notify(user_id, title, body, data, category)`, das im Test gemockt wird).

**Habitica:** Erledigen mit hinterlegtem Habitica-Account erzeugt einen Score-up. Ein Fehler dabei wird geloggt und blockiert nicht (Test!).

**Testliste** (Datei `tests/test_tasks_caldav.py`, Fake-CalDAV als In-Memory-Klasse mit `principal().calendars()`,
`get_supported_components()`, `todos()`, `save_todo()`/`save()`, `delete()`; Fixtures für zwei Nutzer A und B):
- `test_lists_only_vtodo_calendars`
- `test_view_mine` / `test_view_for_me` / `test_view_from_me` / `test_view_family` / `test_view_all_excludes_hidden`
- `test_create_for_other_lands_in_their_list_with_x_props`
- `test_create_for_other_without_write_access_returns_409`
- `test_update_preserves_unknown_properties` (Fixture-VTODO mit `X-APPLE-SORT-ORDER` und `CATEGORIES`)
- `test_complete_sets_status_completed_and_percent`
- `test_assignment_triggers_notify_once` / `test_self_assignment_does_not_notify`
- `test_caldav_password_encrypted_and_not_returned`
- `test_unreachable_server_returns_status_unavailable`
- `test_habitica_failure_does_not_block_completion`

### WP 3b – Einkauf und Essensplan über Home Assistant, Tests nachliefern
Die Umsetzung aus Paket 3 bleibt, sofern die Tests sie bestätigen.

**HA-REST, exakt so verwenden:**
- `POST /api/services/todo/get_items?return_response` mit Body `{"entity_id": "<todo>"}`.
  Antwort: `{"service_response": {"<todo>": {"items": [{"uid","summary","status":"needs_action|completed","description?","due?"}]}}}`.
- `POST /api/services/todo/add_item` mit `{"entity_id", "item": "<Text>"}`.
- `POST /api/services/todo/update_item` mit `{"entity_id", "item": "<uid>", "status": "completed"|"needs_action"}`.
  Es wird die **UID** verwendet, nicht der Text.
- `POST /api/services/todo/remove_item` mit `{"entity_id", "item": ["<uid>"]}`.
- `GET /api/calendars/<calendar>?start=<ISO>&end=<ISO>`. Antwort: Liste mit `summary`, `start.date|start.dateTime`, `end`, `description?`, `uid?`.

**API:**
- `GET /api/shopping` liefert `{status, error, groups: [{key:"manual", entity, items}, {key:"recipes", entity, items}]}`.
- `POST /api/shopping` `{item}` → `HA_SHOPPING_TODO`.
- `PATCH /api/shopping/{uid}` `{done}`, `DELETE /api/shopping/{uid}` (nur `manual`).
- `GET /api/meals?week=YYYY-Www` liefert `{status, error, days: [{date, entries: [{source:"cookidoo"|"hub", title, id?}]}]}`.
  `cookidoo`-Einträge sind schreibgeschützt.

**Testliste** (`tests/test_ha_shopping_meals.py`, `respx==0.21.1` (in `requirements.txt` aufnehmen); der Mock prüft URL, Methode und Body):
- `test_shopping_groups_manual_and_recipes`
- `test_add_item_posts_to_shopping_todo`
- `test_toggle_uses_uid_not_summary`
- `test_delete_only_manual`
- `test_meals_week_merges_cookidoo_and_hub_sorted_by_day`
- `test_cookidoo_entries_read_only` (PATCH/DELETE darauf → 403)
- `test_ha_unreachable_returns_unavailable_not_500`
- `test_missing_entity_returns_unavailable` (HA antwortet 400/404)
- `test_week_plan_to_shopping_writes_to_ha`

### WP 4 – Push (FCM + Web Push)
- **Modell `push_devices`:** `id`, `user_id`, `kind` (`fcm`|`webpush`), `token` (FCM) bzw. `subscription_json` (Web Push), `device_name`,
  `last_seen`, `created_at`. Migration übernimmt bestehende `PushSubscriptionRecord`-Zeilen als `webpush`.
- **`app/services/notify.py`:** `async def notify(user_id, title, body, data: dict, category: str) -> int` (Anzahl erfolgreich).
  - Ruhezeiten und Kategorien pro Nutzer (`notification_prefs`: `user_id`, `category`, `enabled`, `quiet_start`, `quiet_end`).
- **FCM HTTP v1:** `POST https://fcm.googleapis.com/v1/projects/{FCM_PROJECT_ID}/messages:send`, Bearer-Token über `google-auth`
  aus `FCM_SERVICE_ACCOUNT_FILE`.
  - Nachricht: `{"message":{"token","notification":{"title","body"},"data":{...str},"android":{"priority":"HIGH","notification":{"channel_id":"<category>"}}}}`.
  - Antwort 404 bzw. `UNREGISTERED` → Gerät löschen.
- **Web Push:** `pywebpush` mit VAPID (vorhanden). HTTP 404 oder 410 → Gerät löschen.
- **API:**
  - `POST /api/push/devices` mit `{kind, token|subscription, device_name}`. Ein bekanntes Token aktualisiert den Eintrag, statt ihn zu duplizieren.
  - `GET /api/push/devices`, `DELETE /api/push/devices/{id}`, `POST /api/push/test`.
  - `GET/PUT /api/me/notification-prefs`.
- **PWA (iOS-tauglich):**
  - `manifest.webmanifest` mit `display: "standalone"` und Icons 192/512, dazu `apple-touch-icon` im HTML.
  - Erlaubnis nur im Klick-Handler (`Notification.requestPermission()`). Hinweis „Zum Home-Bildschirm hinzufügen“, solange `navigator.standalone` falsch ist.
  - `service-worker.js` ruft im `push`-Handler **immer** `self.registration.showNotification(...)` auf, sonst entzieht Safari die Erlaubnis.
  - `notificationclick` öffnet `data.url`.
- **Testliste** (`tests/test_push.py`):
  - `test_register_fcm_device_dedup`
  - `test_notify_sends_to_all_devices_of_user`
  - `test_fcm_unregistered_deletes_device`
  - `test_webpush_410_deletes_device`
  - `test_quiet_hours_suppress`
  - `test_category_disabled_suppresses`
  - `test_push_test_endpoint`
  - `test_migration_moves_old_webpush_subscriptions`
  - Die JS-Prüfung `tests/test_pwa_features.js` wird erweitert: Der Service Worker enthält `showNotification` im `push`-Handler.

### WP 5 – Anmeldung mit Authentik (OIDC)
- Authorization Code + PKCE. Endpunkte `GET /api/auth/oidc/start?client=app|web` (liefert `{url}` mit `state`, `nonce`, `code_challenge`)
  und `GET /api/auth/oidc/callback`.
- Token-Prüfung: Signatur gegen JWKS von `OIDC_ISSUER/.well-known/openid-configuration`, außerdem `iss`, `aud`, `exp`, `nonce`.
- Zuordnung zum Hub-Nutzer über `email` (case-insensitive). Unbekannte E-Mail → 403, außer `OIDC_AUTO_CREATE=true`.
- Danach die eigenen JWTs wie beim Passwort-Login. App-Redirect `familienhub://auth?code=...` (einmaliger Austauschcode, 60 s gültig),
  Web per Cookie.
- **Testliste:**
  - `test_oidc_start_contains_pkce_and_state`
  - `test_callback_rejects_wrong_state`
  - `test_callback_rejects_bad_signature`
  - `test_callback_maps_email_case_insensitive`
  - `test_unknown_email_403`
  - `test_app_exchange_code_single_use_and_expires`

  Den JWKS-Server mit selbst erzeugtem RSA-Schlüssel mocken.

### WP 6 – Android-App (Flutter, `app/`)
Wird nach WP 5 mit eigener, genauer Bildschirm-Spezifikation nachgereicht. Vorher nicht beginnen.

### WP 7 – PWA auf Stand der API, WP 8 – CI/APK
Werden ebenfalls genau nachgereicht.

---

## Teil D: Review-Kriterien (so prüft Claude jeden PR)
1. Pflicht-Ausgaben im PR vorhanden und selbst nachgestellt: gleiche Zahlen.
2. `git diff main -- backend/tests`: Jede Änderung an bestehenden Tests ist begründet.
3. Testliste des Pakets vollständig, mit genau diesen Namen. Die Tests prüfen das Verhalten, nicht die Mocks.
4. Kein `except Exception` ohne Log, Status und Test. Keine Platzhalter.
5. Die Schnittstellen entsprechen den Tabellen oben, Feldnamen eingeschlossen.
6. Keine Hausdaten, keine Geheimnisse.

Wird ein Kriterium nicht erfüllt, gibt es keinen Merge, sondern eine Änderungsliste.
