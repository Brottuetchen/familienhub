"""Server texts in the reader's language (#24).

The code keeps writing German texts (the original language of the project). They are translated on
the way out:

- error messages (`detail`, `error`) by the request's ``Accept-Language`` (see ``install``),
- push notifications by the recipient's ``users.language`` (see ``services/notify``),
- plugin names, descriptions and setting labels on the admin endpoints.

Entries with ``{name}`` placeholders match formatted messages; captured parts are translated again
when they are catalog entries themselves (e.g. "Hörbuch"). Unknown texts stay as they are, so a
missing translation never breaks anything. ``tests/test_i18n.py`` checks that every German message in
the code has an entry here.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

SUPPORTED = ("de", "en")
DEFAULT = "de"

EN: Dict[str, str] = {
    # --- push notifications ---
    "Neue Aufgabe zugewiesen": "New task for you",
    "⏰ Erinnerung": "⏰ Reminder",
    "🏠 Willkommen zu Hause": "🏠 Welcome home",
    "Test-Nachricht": "Test message",
    "Dies ist eine Testnachricht vom Familienhub.": "This is a test message from Familienhub.",
    "💬 Feedback von {name}": "💬 Feedback from {name}",
    "🎬 Seerr ist verbunden": "🎬 Seerr is connected",
    "🎬 „{title}“ ist da": "🎬 “{title}” is available",
    "🎬 „{title}“ abgelehnt": "🎬 “{title}” declined",
    "🎬 „{title}“ hat nicht geklappt": "🎬 “{title}” failed",
    "Jetzt in Jellyfin.": "Now in Jellyfin.",
    "Film/Serie": "Movie/show",
    "📚 Shelfarr ist verbunden": "📚 Shelfarr is connected",
    "📚 „{title}“ ist da": "📚 “{title}” is available",
    "📚 „{title}“ hat nicht geklappt": "📚 “{title}” failed",
    "📚 „{title}“ braucht Hilfe": "📚 “{title}” needs attention",
    "{kind} von {author} liegt in der Bibliothek.": "{kind} by {author} is in the library.",
    "{kind} liegt in der Bibliothek.": "{kind} is in the library.",
    "Buch": "Book",
    "Hörbuch": "Audiobook",
    "E-Book": "E-book",
    # --- errors (HTTP detail, "error" fields, forwarded ValueErrors) ---
    "Adresse antwortet mit HTTP {code}": "The address answers with HTTP {code}",
    "Adresse braucht Besitzer, Repository und Branch": "The address needs owner, repository and branch",
    "Adresse muss mit http:// oder https:// beginnen": "The address must start with http:// or https://",
    "Aktion abgelaufen oder ungültig": "Action expired or invalid",
    "Aktion nicht unterstützt": "Action not supported",
    "Aktion unbestätigt. Remotezustand prüfen; nicht blind wiederholen":
        "Action unconfirmed. Check the remote state; do not simply retry",
    "Aktion unbestätigt; nicht wiederholen, Betreiberprüfung erforderlich":
        "Action unconfirmed; do not retry, an operator needs to check",
    "Aktion vom Gerät nicht unterstützt": "The device does not support this action",
    "Anmeldung abgebrochen: {error}": "Sign-in cancelled: {error}",
    "Artikel fehlt": "Item missing",
    "Aufgabe gehört nicht zum eigenen Habitica-Konto": "The task does not belong to your own Habitica account",
    "Aufgabe konnte nicht angelegt werden": "The task could not be created",
    "Aufgabe wurde geändert; vor dem Bearbeiten neu laden": "The task has changed; reload before editing",
    "Aufgabenanbieter besitzt keinen persönlichen Adapter": "This task provider has no personal adapter",
    "Aufgabenanbieter ist nicht aktiv": "This task provider is not active",
    "Aufgabenanbieter nicht erreichbar": "Task provider not reachable",
    "Benutzername oder E-Mail gibt es schon": "Username or email already exists",
    "Benutzername: klein, ohne Leerzeichen (a–z, 0–9, . _ -)": "Username: lower case, no spaces (a–z, 0–9, . _ -)",
    "Betreiberfreigabe nach geprüftem Single-Writer-Übergang fehlt":
        "Operator approval after a verified single-writer handover is missing",
    "Bild ist größer als 512 KB": "The image is larger than 512 KB",
    "Bilddaten ungültig": "Invalid image data",
    "Bitte Anbieter und eigenes Aufgabenkonto ausdrücklich wählen": "Please choose the provider and your own task account",
    "Bitte zuerst eine HTTPS-Adresse für das Habitica-Plugin konfigurieren":
        "Please configure an HTTPS address for the Habitica plugin first",
    "Bitte zuerst eine Nextcloud-Familienliste zuordnen": "Please assign a Nextcloud family list first",
    "CalDAV-Adresse darf nicht auf den Hub selbst zeigen": "The CalDAV address must not point to the hub itself",
    "CalDAV-Adresse muss auf dem eingerichteten Nextcloud-Server liegen":
        "The CalDAV address must be on the configured Nextcloud server",
    "CalDAV-Adresse muss einen Hostnamen verwenden, keine IP-Adresse":
        "The CalDAV address must use a host name, not an IP address",
    "CalDAV-Adresse muss https verwenden": "The CalDAV address must use https",
    "Checklisten gehören zu Todo oder Daily": "Checklists belong to to-dos or dailies",
    "Checklistenpunkt benötigt Text": "A checklist item needs text",
    "Checklistenpunkt fehlt": "Checklist item missing",
    "Cookidoo ist nicht eingerichtet": "Cookidoo is not set up",
    "Cookidoo nicht erreichbar: {error}": "Cookidoo not reachable: {error}",
    "Cookidoo-Einträge sind schreibgeschützt": "Cookidoo entries are read-only",
    "Das ist keine Kalenderdatei (ICS)": "This is not a calendar file (ICS)",
    "Der Familienkalender im Hub ist abgeschaltet": "The hub's family calendar is switched off",
    "Der Hub ist bereits eingerichtet": "The hub is already set up",
    "Dienst-Schlüssel erforderlich": "Service key required",
    "Dienst-Schlüssel ungültig": "Invalid service key",
    "Diese E-Mail-Adresse gehört schon zu einer Person im Hub": "This email address already belongs to someone in the hub",
    "Diese Haushaltsaufgabe darfst du nicht ändern": "You may not change this household task",
    "Diese Rezeptquelle ist nicht aktiv": "This recipe source is not active",
    "Diese native Punktrichtung ist nicht erlaubt": "This native score direction is not allowed",
    "Dieser Anbieter verwendet Listenauswahl": "This provider uses list selection",
    "Dieser Aufgabenort ist nicht verfügbar. Bitte zuerst das Konto verbinden.":
        "This task place is not available. Please connect the account first.",
    "Dieses Aufgabenkonto gehört nicht zur aktuellen Sitzung": "This task account does not belong to the current session",
    "Dieses Habitica-Konto ist bereits zugeordnet": "This Habitica account is already linked",
    "Dieses Konto ist deaktiviert": "This account is disabled",
    "Dieses Topic ist schon vergeben": "This topic is already taken",
    "Eigene Admin-Rechte kann man nicht entfernen": "You cannot remove your own admin rights",
    "Ein Theme „{name}“ gibt es schon": "A theme “{name}” already exists",
    "Eindeutige kanonische Tag-UUIDs erforderlich": "Unique canonical tag UUIDs required",
    "Eine Kontoaktion läuft oder ist unbestätigt; nicht erneut senden":
        "An account action is running or unconfirmed; do not send again",
    "Eine Kontoreferenz erfordert einen ausdrücklich gewählten Anbieter": "An account reference requires an explicitly chosen provider",
    "Einladung nicht gefunden oder schon eingelöst": "Invite not found or already redeemed",
    "Einladungscode ungültig oder abgelaufen – bitte um einen neuen": "Invite code invalid or expired – please ask for a new one",
    "Einrichtungscode stimmt nicht (steht im Server-Log)": "Wrong setup code (it is in the server log)",
    "Eintrag nicht gefunden": "Entry not found",
    "Ende liegt vor dem Start": "The end is before the start",
    "Entität nicht zum Schreiben freigegeben": "This entity is not enabled for writing",
    "Erinnerung beim Heimkommen hat keine Uhrzeit": "A when-I-get-home reminder has no time",
    "Erinnerungen für die ganze Familie legen Erwachsene an": "Reminders for the whole family are created by adults",
    "Erinnerungen für die ganze Familie löschen Erwachsene": "Reminders for the whole family are deleted by adults",
    "Erinnerungen für die ganze Familie ändern Erwachsene": "Reminders for the whole family are changed by adults",
    "Farbe als #RRGGBB": "Colour as #RRGGBB",
    "Fälligkeit gehört nur zu nativen Todos": "A due date only belongs to native to-dos",
    "Für diesen Bereich gibt es genau eine Quelle": "This area has exactly one source",
    "GitHub antwortet {code}": "GitHub answers {code}",
    "GitHub nicht erreichbar": "GitHub not reachable",
    "GitHub-Adresse braucht Besitzer und Repository": "A GitHub address needs owner and repository",
    "Habitica hat die Anfrage nicht bestätigt": "Habitica did not confirm the request",
    "Habitica ist deaktiviert oder der Server wurde geändert": "Habitica is switched off or the server was changed",
    "Habitica ist nicht erreichbar": "Habitica is not reachable",
    "Habitica-Aufgabe nicht lesbar": "Habitica task not readable",
    "Habitica-Aufgabe wurde entfernt; Auswahl bleibt bis zum bewussten Entfernen erhalten":
        "The Habitica task was removed; the selection stays until you remove it",
    "Habitica-Aufgaben gehören ausschließlich zum eigenen Konto": "Habitica tasks belong to your own account only",
    "Habitica-Konto konnte nicht bestätigt werden": "The Habitica account could not be confirmed",
    "Habitica-Konto stimmt nicht mehr überein": "The Habitica account no longer matches",
    "Habitica-Zugang konnte nicht geprüft werden": "The Habitica access could not be checked",
    "Haus-Karte: höchstens 6 gültige Entitäts-IDs, kommagetrennt": "House card: at most 6 valid entity IDs, comma-separated",
    "Haus-Zustände gerade nicht verfügbar": "House states not available right now",
    "Haushalt benötigt Familienliste, Titel und eindeutige Rotation": "A household task needs a family list, a title and a unique rotation",
    "Haushalt benötigt Titel (1–200 Zeichen) und Fälligkeit": "A household task needs a title (1–200 characters) and a due date",
    "Haushalt benötigt eine Fälligkeit": "A household task needs a due date",
    "Haussteuerung nicht verfügbar": "House controls not available",
    "Haussteuerung: nur light, switch, script und scene erlaubt": "House controls: only light, switch, script and scene allowed",
    "Helligkeit erforderlich": "Brightness required",
    "Helligkeit nur für Dimmeraktion erlaubt": "Brightness is only allowed for the dim action",
    "Home Assistant nicht konfiguriert": "Home Assistant not configured",
    "In diesen Kalender kann der Hub nicht schreiben": "The hub cannot write to this calendar",
    "Kalender gerade nicht erreichbar": "Calendar not reachable right now",
    "Kalender größer als 2 MB": "Calendar larger than 2 MB",
    "Kalender nicht gefunden": "Calendar not found",
    "Kalender-Abo größer als 2 MB": "Calendar subscription larger than 2 MB",
    "Kanonische UUID erforderlich": "Canonical UUID required",
    "Kein Aufgabenort verfügbar": "No task place available",
    "Kein Paperless-Zugang": "No Paperless access",
    "Kein Profilbild": "No profile picture",
    "Kein aktives persönliches Habitica-Konto": "No active personal Habitica account",
    "Kein passender Seerr-Nutzer": "No matching Seerr user",
    "Keine aktive Person in der Rotation": "No active person in the rotation",
    "Keine anstehende Frist für dieses Dokument": "No upcoming deadline for this document",
    "Keine native Aktion für diesen Anbieter": "No native action for this provider",
    "Keine zusätzlichen Parameter erlaubt": "No additional parameters allowed",
    "Konto wurde geändert oder eine native Aktion läuft; neu laden": "The account changed or a native action is running; reload",
    "Legacy-Habitica-Spiegel bleiben schreibgeschützt; native Aufgaben direkt auswählen":
        "Legacy Habitica mirrors stay read-only; select native tasks directly",
    "Link muss mit http:// oder https:// beginnen": "The link must start with http:// or https://",
    "Mitgelieferte Themes lassen sich nicht löschen": "Built-in themes cannot be deleted",
    "Name fehlt": "Name missing",
    "Name fehlt oder ist länger als 60 Zeichen": "Name missing or longer than 60 characters",
    "Name ohne | und ;": "Name without | and ;",
    "Native Aufgabentypen sind nach Anlage unveränderlich": "Native task types cannot change after creation",
    "Native Habitica-Optionen nicht lesbar": "Native Habitica options not readable",
    "Native IDs müssen kanonische UUIDs sein": "Native IDs must be canonical UUIDs",
    "Native Schreibfreigabe fehlt: Betreiber muss zuerst den Single-Writer-Übergang prüfen":
        "Native write access missing: an operator must verify the single-writer handover first",
    "Native Schwierigkeit als Zahl erforderlich": "Native difficulty required as a number",
    "Native Schwierigkeit über native.priority angeben": "Give the native difficulty via native.priority",
    "Nicht erreichbar ({error})": "Not reachable ({error})",
    "Nicht gefunden": "Not found",
    "Nur Erwachsene verwalten Haushaltsaufgaben": "Only adults manage household tasks",
    "Nur JPEG, PNG oder WebP": "Only JPEG, PNG or WebP",
    "Nur Themes von GitHub (raw.githubusercontent.com)": "Only themes from GitHub (raw.githubusercontent.com)",
    "Nur http- oder https-Adressen": "Only http or https addresses",
    "Nur https-Adressen von GitHub ohne Zusätze": "Only plain https addresses from GitHub",
    "Open Library gerade nicht erreichbar": "Open Library not reachable right now",
    "Operationsschlüssel wurde für eine andere Aktion verwendet": "The operation key was used for a different action",
    "Option passt nicht zum Habitica-Aufgabentyp": "The option does not fit the Habitica task type",
    "Paperless ist nicht eingerichtet": "Paperless is not set up",
    "Paperless kennt dieses Token nicht": "Paperless does not know this token",
    "Paperless-Zugang ungültig": "Invalid Paperless access",
    "Person nicht gefunden": "Person not found",
    "Plugin nicht gefunden": "Plugin not found",
    "Position muss eine nichtnegative Ganzzahl sein": "The position must be a non-negative whole number",
    "Rezeptzutaten können nicht gelöscht werden": "Recipe ingredients cannot be deleted",
    "Rotation enthält ungültige Personen": "The rotation contains invalid people",
    "Schlüssel nicht gefunden": "Key not found",
    "Schon bearbeitet – zurückziehen geht nur, solange er auf Freigabe wartet":
        "Already processed – it can only be withdrawn while waiting for approval",
    "Seerr ist nicht eingerichtet": "Seerr is not set up",
    "Shelfarr ist nicht eingerichtet": "Shelfarr is not set up",
    "Sich selbst kann man nicht deaktivieren": "You cannot deactivate yourself",
    "Start und Ende als ISO-Datum angeben": "Give start and end as ISO dates",
    "Tags gehören nicht zum eigenen Habitica-Konto": "The tags do not belong to your own Habitica account",
    "Termin nicht gefunden": "Event not found",
    "Theme nicht gefunden": "Theme not found",
    "Titel erforderlich": "Title required",
    "Titel fehlt": "Title missing",
    "Unbekannte Aktion. Erlaubt: {allowed}": "Unknown action. Allowed: {allowed}",
    "Unbekannte Einstellung für dieses Plugin": "Unknown setting for this plugin",
    "Unbekannte Person": "Unknown person",
    "Unbekannte Rolle": "Unknown role",
    "Unbekannte Zeitzone, z. B. Europe/Berlin": "Unknown time zone, e.g. Europe/Berlin",
    "Unbekannte native Aktion": "Unknown native action",
    "Unbekannter Bereich": "Unknown area",
    "Unbekanntes Regal": "Unknown shelf",
    "Unbestätigte Aktion: Konto erst nach Betreiberprüfung ändern": "Unconfirmed action: change the account only after an operator check",
    "Ungültige CalDAV-Adresse": "Invalid CalDAV address",
    "Ungültige Checklistenposition": "Invalid checklist position",
    "Ungültige Checklistenänderung": "Invalid checklist change",
    "Ungültige E-Mail-Adresse": "Invalid email address",
    "Ungültige HA-Attribute": "Invalid HA attributes",
    "Ungültige HA-Zustandsattribute": "Invalid HA state attributes",
    "Ungültige HA-Zustandsliste": "Invalid HA state list",
    "Ungültige Wiederholung oder fehlende Fälligkeit": "Invalid repeat or missing due date",
    "Ungültige native Optionen": "Invalid native options",
    "Ungültige native Wiederholung": "Invalid native repeat",
    "Ungültiger HA-Zustand": "Invalid HA state",
    "Ungültiger Habitica-Aufgabentyp": "Invalid Habitica task type",
    "Ungültiger Idempotency-Key": "Invalid idempotency key",
    "Ungültiger Monatszeitplan": "Invalid monthly schedule",
    "Ungültiger Pfad": "Invalid path",
    "Ungültiges Wochenformat (erwartet YYYY-Www)": "Invalid week format (expected YYYY-Www)",
    "Vorschau ist kein Bild": "The preview is not an image",
    "Vorschau nicht verfügbar": "Preview not available",
    "Web Push nicht eingerichtet (VAPID-Schlüssel fehlen)": "Web Push not set up (VAPID keys missing)",
    "Weiterleitung nicht bestätigt": "Redirect not confirmed",
    "Wunsch nicht gefunden": "Request not found",
    "Zu viele Versuche, bitte kurz warten": "Too many attempts, please wait a moment",
    "Zum Leeren [] verwenden": "Use [] to clear",
    "Zuweisung nur an aktive Familienmitglieder": "Tasks can only be given to active family members",
    "code und state erforderlich": "code and state required",
    "font: nur title, body und label": "font: only title, body and label",
    "glass und uppercaseTitles sind true/false": "glass and uppercaseTitles are true/false",
    "ntfy ist auf diesem Hub nicht eingerichtet": "ntfy is not set up on this hub",
    "ntfy ist nicht aktiviert": "ntfy is not enabled",
    "recipe_id oder custom_title erforderlich": "recipe_id or custom_title required",
    "style einer Variante muss ein Objekt sein": "The style of a variant must be an object",
    "style muss ein Objekt sein": "style must be an object",
    "style.background und style.card müssen Objekte sein": "style.background and style.card must be objects",
    "theme.json ist größer als 64 KB": "theme.json is larger than 64 KB",
    "theme.json ist kein gültiges JSON": "theme.json is not valid JSON",
    "theme.json muss ein Objekt sein": "theme.json must be an object",
    "variants: nur „light“ und „dark“ erlaubt": "variants: only “light” and “dark” allowed",
    "{field}: erlaubt sind {allowed}": "{field}: allowed are {allowed}",
    "{field}: ganze Zahl von {lo} bis {hi}": "{field}: whole number from {lo} to {hi}",
    "{field}: höchstens {limit} #RRGGBB-Farben": "{field}: at most {limit} #RRGGBB colours",
    "{pid} kann diesen Bereich nicht liefern": "{pid} cannot provide this area",
    "{where} fehlt": "{where} missing",
    "{where}: Farbe {key} fehlt oder ist kein #RRGGBB-Wert": "{where}: colour {key} is missing or not a #RRGGBB value",
    # --- plugins: names, descriptions, setting labels and help ---
    "Aufgaben im Hub": "Tasks in the hub",
    "Einkaufsliste im Hub": "Shopping list in the hub",
    "Familienkalender im Hub": "Family calendar in the hub",
    "Kalender-Abos (ICS)": "Calendar subscriptions (ICS)",
    "Wetter (Open-Meteo)": "Weather (Open-Meteo)",
    "Aufgaben aus": "Tasks from",
    "Einkauf aus": "Shopping from",
    "Termine aus": "Events from",
    "Aufgaben direkt im Familienhub: privat, füreinander, Familienliste und Haushaltsrotation. Läuft ohne externen Dienst, auch neben Nextcloud oder Habitica.":
        "Tasks right in Familienhub: private, for each other, family list and household rotation. Works without any other service, also next to Nextcloud or Habitica.",
    "Aufgaben und Termine von jedem CalDAV-Server (Nextcloud, iCloud, mailbox.org, Radicale …), Konto pro Person.":
        "Tasks and events from any CalDAV server (Nextcloud, iCloud, mailbox.org, Radicale …), one account per person.",
    "Ausgewählte persönliche Aufgaben bidirektional anbinden": "Connect selected personal tasks both ways",
    "Dokumente suchen, neueste ansehen, Fristen als Erinnerung – mit dem eigenen Paperless-Zugang.":
        "Search documents, see the newest, deadlines as reminders – with your own Paperless access.",
    "E-Books und Hörbücher suchen und wünschen.": "Search and request e-books and audiobooks.",
    "Einkaufsliste, Cookidoo-Wochenplan und Haus-Zustände über Home Assistant.":
        "Shopping list, Cookidoo weekly plan and house states via Home Assistant.",
    "Filme und Serien suchen, wünschen und den Stand sehen – als eigener Seerr-Nutzer.":
        "Search and request movies and shows and follow their status – as your own Seerr user.",
    "Gemeinsame Einkaufsliste direkt im Familienhub. Wird genutzt, wenn keine andere Einkaufsquelle aktiv ist oder SHOPPING_SOURCE=hub_shopping gesetzt ist.":
        "Shared shopping list right in Familienhub. Used when no other shopping source is active or SHOPPING_SOURCE=hub_shopping is set.",
    "Gemeinsamer Familienkalender direkt im Familienhub, zusätzlich zu CalDAV-Kalendern und Kalender-Abos.":
        "Shared family calendar right in Familienhub, in addition to CalDAV calendars and calendar subscriptions.",
    "Aktuelles Wetter für „Heute“.": "Current weather for “Today”.",
    "Push-Mitteilungen über ntfy – z. B. für iPhones ohne App-Store-App. Jede Person abonniert ihr eigenes geheimes Topic.":
        "Push notifications via ntfy – e.g. for iPhones without an App Store app. Everyone subscribes to their own secret topic.",
    "Rezepte aus Mealie suchen und einplanen, Mealie-Essensplan im Wochenplan, Mealie-Einkaufsliste als Einkaufsquelle.":
        "Search and plan recipes from Mealie, Mealie's meal plan in the week, Mealie's shopping list as shopping source.",
    "Rezepte suchen, auf Tage legen und Zutaten auf die Cookidoo-Einkaufsliste setzen.":
        "Search recipes, put them on days and add the ingredients to the Cookidoo shopping list.",
    "Schulferien, Müllabfuhr, Vereinstermine: abonnierte Kalender erscheinen im Familienkalender (nur lesen).":
        "School holidays, bin collection, club events: subscribed calendars appear in the family calendar (read-only).",
    "API-Schlüssel (Einstellungen → Allgemein)": "API key (Settings → General)",
    "API-Token (Admin, Scopes search/requests)": "API token (admin, scopes search/requests)",
    "Abonnierte Kalender": "Subscribed calendars",
    "Adresse": "Address",
    "Adresse (vom Server aus erreichbar)": "Address (reachable from the server)",
    "Adresse des Hubs für Links und Knöpfe": "Hub address for links and buttons",
    "Adresse für Links in der App": "Address for links in the app",
    "Adresse, die in der ntfy-App eingetragen wird; leer = wie oben": "Address entered in the ntfy app; empty = same as above",
    "Bis zu 6 Entitäts-IDs, kommagetrennt in Anzeigereihenfolge; leer = ausgeblendet.":
        "Up to 6 entity IDs, comma-separated in display order; empty = hidden.",
    "Bis zu 6 light/switch/script/scene-IDs; leer = keine Aktionen. Unabhängig von Leseauswahl.":
        "Up to 6 light/switch/script/scene IDs; empty = no actions. Independent of the read selection.",
    "Breitengrad": "Latitude",
    "Längengrad": "Longitude",
    "E-Mail des Cookidoo-Kontos": "Email of the Cookidoo account",
    "Einkaufsliste (todo-Entität)": "Shopping list (todo entity)",
    "Essensplan (calendar-Entität)": "Meal plan (calendar entity)",
    "Rezept-Zutaten (todo-Entität)": "Recipe ingredients (todo entity)",
    "Gemeinsamer Kalender: Benutzer": "Shared calendar: user",
    "Gemeinsamer Kalender: CalDAV-Adresse": "Shared calendar: CalDAV address",
    "Gemeinsamer Kalender: Passwort": "Shared calendar: password",
    "Geprüfter Single-Writer-Übergang: Server|Konto-UUID": "Verified single-writer handover: server|account UUID",
    "HTTPS-Basisadresse ohne /api/v3": "HTTPS base address without /api/v3",
    "Habitica-Server": "Habitica server",
    "Haus-Karte in Heute": "House card on Today",
    "Haussteuerung: Schreibfreigabe": "House controls: write access",
    "In Mealie: Profil → API-Tokens → neues Token": "In Mealie: Profile → API tokens → new token",
    "Je Kalender „Name | https://…/kalender.ics“, mehrere durch ; getrennt":
        "One per calendar “Name | https://…/calendar.ics”, several separated by ;",
    "Land": "Country",
    "Langlebiges Zugangstoken": "Long-lived access token",
    "Leer = die erste Liste in Mealie": "Empty = the first list in Mealie",
    "Name der Einkaufsliste": "Name of the shopping list",
    "Name des Familienkalenders": "Name of the family calendar",
    "Name des Hubs": "Name of the hub",
    "Nur Betreiber: erst nach Backup, verifiziertem Cron-/Prozessstop und Bestandsabgleich freigeben. Standard leer.":
        "Operators only: enable only after a backup, a verified cron/process stop and a data check. Empty by default.",
    "Nur nötig, wenn Benutzernamen abweichen (Seerr-Name, Jellyfin-Name oder E-Mail).":
        "Only needed if user names differ (Seerr name, Jellyfin name or email).",
    "Nur nötig, wenn Benutzernamen abweichen.": "Only needed if user names differ.",
    "Nur nötig, wenn der Server anonymes Senden verbietet (Token mit Schreibrecht auf fh_*)":
        "Only needed if the server forbids anonymous publishing (token with write access to fh_*)",
    "Nutzer-Zuordnung hub=seerr,…": "User mapping hub=seerr,…",
    "Nutzer-Zuordnung hub=shelfarr,…": "User mapping hub=shelfarr,…",
    "Optional. Fallback für Personen ohne eigenes Konto.": "Optional. Fallback for people without their own account.",
    "Ortsname": "Place name",
    "Passwort": "Password",
    "So heißt der geteilte Familienkalender in Nextcloud o. Ä. (mehrere mit Komma). Er wird beim Anlegen vorgeschlagen.":
        "The name of the shared family calendar in Nextcloud or similar (several separated by commas). It is suggested first when creating events.",
    "Sprache": "Language",
    "Standard: calendar.cookidoo_speiseplan": "Default: calendar.cookidoo_speiseplan",
    "Standard: de": "Default: de",
    "Standard: de-DE": "Default: de-DE",
    "Standard: todo.cookidoo_einkaufsliste": "Default: todo.cookidoo_einkaufsliste",
    "Standard: todo.einkaufsliste": "Default: todo.einkaufsliste",
    "Von unterwegs erreichbar, z. B. https://hub.example.org; leer = keine Knöpfe":
        "Reachable from outside, e.g. https://hub.example.org; empty = no buttons",
    "Zeitzone": "Time zone",
    "Zugangs-Token zum Senden": "Access token for publishing",
    "Zum Öffnen von Rezepten im Browser; leer = wie oben": "For opening recipes in the browser; empty = same as above",
    "ntfy-Server (vom Hub aus erreichbar)": "ntfy server (reachable from the hub)",
    "ntfy-Server für die Handys": "ntfy server for the phones",
    "Öffentliche/interne Adresse zum Öffnen im Browser; leer = wie oben": "Public/internal address for opening in the browser; empty = same as above",
    "z. B. http://homeassistant.local:8123": "e.g. http://homeassistant.local:8123",
    "z. B. http://mealie.lan:9000": "e.g. http://mealie.lan:9000",
    "z. B. http://paperless.lan:8000": "e.g. http://paperless.lan:8000",
    "z. B. http://seerr.lan:5055": "e.g. http://seerr.lan:5055",
    "z. B. https://ntfy.sh oder http://ntfy.lan:8093": "e.g. https://ntfy.sh or http://ntfy.lan:8093",
}

_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


@lru_cache(maxsize=1)
def _templates() -> List[Tuple[re.Pattern, str, str]]:
    """Catalog entries with placeholders as regexes; the most specific (longest literal part) first."""
    out = []
    for de, en in EN.items():
        if not _PLACEHOLDER.search(de):
            continue
        pattern, pos = "", 0
        for m in _PLACEHOLDER.finditer(de):
            pattern += re.escape(de[pos:m.start()]) + f"(?P<{m.group(1)}>.+?)"
            pos = m.end()
        pattern += re.escape(de[pos:])
        out.append((re.compile(f"^{pattern}$", re.S), en, de))
    out.sort(key=lambda t: -len(_PLACEHOLDER.sub("", t[2])))
    return out


def translate(text: Any, lang: Optional[str]) -> Any:
    """``text`` in ``lang``; unknown texts and other languages stay unchanged."""
    if lang != "en" or not isinstance(text, str) or not text:
        return text
    if text in EN:
        return EN[text]
    if "{" in text or len(text) > 2000:
        return text
    for regex, en, _de in _templates():
        m = regex.match(text)
        if m:
            return en.format(**{k: EN.get(v, v) for k, v in m.groupdict().items()})
    return text


def parse_accept_language(header: Optional[str]) -> Optional[str]:
    """First supported language of an ``Accept-Language`` header (q values respected), else None."""
    best: Tuple[float, Optional[str]] = (0.0, None)
    for part in (header or "").split(","):
        tag, _, q = part.strip().partition(";q=")
        code = tag.strip().lower()[:2]
        if code not in SUPPORTED:
            continue
        try:
            weight = float(q) if q else 1.0
        except ValueError:
            weight = 0.0
        if weight > best[0]:
            best = (weight, code)
    return best[1]


def request_language(request) -> str:
    """The app's own setting (``X-App-Language``) wins over the browser's ``Accept-Language``."""
    return (parse_accept_language(request.headers.get("x-app-language"))
            or parse_accept_language(request.headers.get("accept-language")) or DEFAULT)


# Responses whose generic text fields ("name", "description", "label", "help") come from plugin and
# theme definitions; everywhere else only "detail"/"error" are translated (user content stays as is).
_METADATA_PREFIXES = ("/api/admin", "/api/plugins", "/api/setup", "/api/themes", "/api/tasks/providers")
_ALWAYS = {"detail", "error", "msg", "message"}
_METADATA = {"name", "description", "label", "help"}


def translate_payload(data: Any, lang: str, metadata: bool = False, _depth: int = 0) -> Any:
    if lang != "en" or _depth > 8:
        return data
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if isinstance(v, str) and (k in _ALWAYS or (metadata and k in _METADATA)):
                out[k] = translate(_strip_value_error(v) if k == "msg" else v, lang)
            else:
                out[k] = translate_payload(v, lang, metadata, _depth + 1)
        return out
    if isinstance(data, list):
        return [translate_payload(v, lang, metadata, _depth + 1) for v in data]
    return data


def _strip_value_error(msg: str) -> str:
    return msg[len("Value error, "):] if msg.startswith("Value error, ") else msg


def install(app) -> None:
    """Translate JSON error and status texts for clients that ask for English."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import Response

    class TranslateMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            lang = request_language(request)
            if lang != "en" or "application/json" not in response.headers.get("content-type", ""):
                return response
            body = b"".join([chunk async for chunk in response.body_iterator])
            try:
                data = json.loads(body) if len(body) < 2_000_000 else None
            except ValueError:
                data = None
            if data is not None:
                metadata = request.url.path.startswith(_METADATA_PREFIXES)
                body = json.dumps(translate_payload(data, lang, metadata), ensure_ascii=False).encode()
            out = Response(body, status_code=response.status_code)
            # raw headers keep repeated ones (Set-Cookie); only the length changes
            out.raw_headers = [(k, v) for k, v in response.raw_headers if k.lower() != b"content-length"] + [
                (b"content-length", str(len(body)).encode())]
            return out

    app.add_middleware(TranslateMiddleware)
