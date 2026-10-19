"""Small, stable endpoints for voice assistants (Home Assistant Assist, see docs/voice-assistant.md).

Every answer is JSON with structured data **and** a short ``speech`` text in the language of the key's owner
(``lang`` query parameter or ``Accept-Language`` override it). The endpoints reuse the normal routers, so
sources, roles and routing behave exactly as in the app.

Soft failures (source down, nothing understood, role too low) answer HTTP 200 with ``ok: false``, a
``status`` and a spoken ``speech`` text: the assistant can always read something out. Only authentication
and missing scopes are real HTTP errors (a misconfigured token should be loud).

Scopes (API tokens with scopes only reach ``/api/voice``): ``shopping:read``, ``shopping:write``,
``tasks:write``, ``meals:read``, ``calendar:read``, ``reminders:write``.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.i18n import DEFAULT, SUPPORTED, parse_accept_language
from app.core.security import ROLE_LEVEL, require_scope
from app.core.timeutil import local_tz, to_utc_naive
from app.models.user import ROLE_ADMIN, ROLE_PARTNER, User
from app.services.voice_time import parse_when

router = APIRouter(prefix="/api/voice", tags=["voice"])
logger = logging.getLogger("hermes.voice")

MAX_ITEMS = 20
SPOKEN_LIMIT = 8  # items read out loud before "and N more"

# --- spoken texts ---------------------------------------------------------------------------------------

TEXTS: Dict[str, Dict[str, str]] = {
    "en": {
        "and": "and",
        "today": "today", "tomorrow": "tomorrow", "all_day": "all day",
        "more": "and {n} more",
        "shop_added_one": "Added {items} to the shopping list.",
        "shop_added_many": "Added {items} to the shopping list.",
        "shop_none": "What should I put on the shopping list?",
        "shop_partial": "I could only add {added} of {total} items to the shopping list.",
        "shop_unavailable": "The shopping list is not reachable right now.",
        "shop_empty": "The shopping list is empty.",
        "shop_open": "{n} on the shopping list: {items}.",
        "shop_open_one": "One item on the shopping list: {items}.",
        "task_none": "What should the task be?",
        "task_added": "Okay, I added the task {title}.",
        "task_added_for": "Okay, I added the task {title} for {name}.",
        "task_unknown_person": "I do not know anyone called {name}.",
        "task_ambiguous_person": "More than one person matches {name}. Please say the full name.",
        "task_forbidden": "Only adults can add tasks.",
        "task_unavailable": "I could not save the task right now.",
        "meal_none": "Nothing is planned {day}.",
        "meal_some": "On the menu {day}: {items}.",
        "meal_unavailable": "The meal plan is not reachable right now.",
        "event_none": "No events {day}.",
        "event_one": "One event {day}: {items}.",
        "event_some": "{n} events {day}: {items}.",
        "event_unavailable": "The calendar is not reachable right now.",
        "event_at": "{title} at {time}",
        "event_allday": "{title}, all day",
        "day_invalid": "I did not understand which day you mean.",
        "rem_none": "What should I remind you of?",
        "rem_no_time": "I did not understand the time. Please say it again, for example at 6 PM or in 20 minutes.",
        "rem_past": "That time has already passed.",
        "rem_ok": "Okay, I will remind you {when} to {title}.",
        "rem_unavailable": "I could not save the reminder right now.",
        "meal_breakfast": "breakfast", "meal_lunch": "lunch", "meal_dinner": "dinner",
        "weekdays": "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday",
    },
    "de": {
        "and": "und",
        "today": "heute", "tomorrow": "morgen", "all_day": "ganztägig",
        "more": "und {n} weitere",
        "shop_added_one": "{items} steht auf der Einkaufsliste.",
        "shop_added_many": "{items} stehen auf der Einkaufsliste.",
        "shop_none": "Was soll auf die Einkaufsliste?",
        "shop_partial": "Ich konnte nur {added} von {total} Artikeln auf die Einkaufsliste setzen.",
        "shop_unavailable": "Die Einkaufsliste ist gerade nicht erreichbar.",
        "shop_empty": "Die Einkaufsliste ist leer.",
        "shop_open": "{n} Einträge auf der Einkaufsliste: {items}.",
        "shop_open_one": "Ein Eintrag auf der Einkaufsliste: {items}.",
        "task_none": "Wie soll die Aufgabe heißen?",
        "task_added": "Okay, ich habe die Aufgabe {title} angelegt.",
        "task_added_for": "Okay, ich habe die Aufgabe {title} für {name} angelegt.",
        "task_unknown_person": "Ich kenne niemanden mit dem Namen {name}.",
        "task_ambiguous_person": "Der Name {name} passt auf mehrere Personen. Bitte sag den vollen Namen.",
        "task_forbidden": "Aufgaben legen nur Erwachsene an.",
        "task_unavailable": "Ich konnte die Aufgabe gerade nicht speichern.",
        "meal_none": "{day} ist nichts geplant.",
        "meal_some": "Es gibt {day}: {items}.",
        "meal_unavailable": "Der Essensplan ist gerade nicht erreichbar.",
        "event_none": "{day} keine Termine.",
        "event_one": "{day} ein Termin: {items}.",
        "event_some": "{day} {n} Termine: {items}.",
        "event_unavailable": "Der Kalender ist gerade nicht erreichbar.",
        "event_at": "{title} um {time}",
        "event_allday": "{title}, ganztägig",
        "day_invalid": "Ich habe nicht verstanden, welchen Tag du meinst.",
        "rem_none": "Woran soll ich dich erinnern?",
        "rem_no_time": "Die Uhrzeit habe ich nicht verstanden. Sag sie bitte noch einmal, zum Beispiel um 18 Uhr oder in 20 Minuten.",
        "rem_past": "Diese Uhrzeit ist schon vorbei.",
        "rem_ok": "Okay, ich erinnere dich {when}: {title}.",
        "rem_unavailable": "Ich konnte die Erinnerung gerade nicht speichern.",
        "meal_breakfast": "Frühstück", "meal_lunch": "Mittagessen", "meal_dinner": "Abendessen",
        "weekdays": "Montag,Dienstag,Mittwoch,Donnerstag,Freitag,Samstag,Sonntag",
    },
}


class Voice:
    """Language-aware helpers for one request."""

    def __init__(self, lang: str):
        self.lang = lang if lang in SUPPORTED else DEFAULT
        self._t = TEXTS[self.lang]

    def t(self, key: str, **kw: Any) -> str:
        return self._t[key].format(**kw)

    def day_word(self, day: date, today: date) -> str:
        if day == today:
            return self._t["today"]
        if day == today + timedelta(days=1):
            return self._t["tomorrow"]
        names = self._t["weekdays"].split(",")
        return ("am " if self.lang == "de" else "on ") + names[day.weekday()]

    def clock(self, dt: datetime) -> str:
        if self.lang == "de":
            return f"{dt.hour} Uhr" if dt.minute == 0 else f"{dt.hour}:{dt.minute:02d} Uhr"
        h = dt.hour % 12 or 12
        suffix = "AM" if dt.hour < 12 else "PM"
        return f"{h} {suffix}" if dt.minute == 0 else f"{h}:{dt.minute:02d} {suffix}"

    def join(self, items: List[str]) -> str:
        if len(items) <= 1:
            return "".join(items)
        return ", ".join(items[:-1]) + f" {self._t['and']} " + items[-1]

    def listing(self, items: List[str]) -> str:
        """Items for reading aloud, capped so a long list does not run for a minute."""
        shown = items[:SPOKEN_LIMIT]
        if len(items) > SPOKEN_LIMIT:
            return ", ".join(shown) + ", " + self.t("more", n=len(items) - SPOKEN_LIMIT)
        return self.join(shown)


def voice_for(request: Request, user: User, lang: Optional[str]) -> Voice:
    """``lang`` parameter, then the request's language headers, then the owner's language, then German."""
    chosen = None
    if lang:
        chosen = parse_accept_language(lang)
    chosen = chosen or parse_accept_language(request.headers.get("x-app-language")) \
        or parse_accept_language(request.headers.get("accept-language")) \
        or (user.language if user.language in SUPPORTED else None)
    return Voice(chosen or DEFAULT)


def answer(v: Voice, ok: bool, status: str, speech: str, **data: Any) -> Dict[str, Any]:
    # never the keys "detail"/"error": the generic error translation would touch them
    return {"ok": ok, "status": status, "lang": v.lang, "speech": speech, **data}


def _level(user: User) -> int:
    if user.is_admin:
        return ROLE_LEVEL[ROLE_ADMIN]
    return ROLE_LEVEL.get(user.role or ROLE_PARTNER, 0)


def _capitalise(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:]


def _today() -> date:
    return datetime.now(local_tz()).date()


# --- shopping -------------------------------------------------------------------------------------------

_SPLIT = re.compile(r"\s*(?:,|;|\n|\s&\s|\s+(?:and|und|sowie|plus)\s+)\s*", re.I)
_CONJUNCTIONS = {"and", "und", "&", "plus", "sowie"}
_ARTICLE = re.compile(r"^(?:a|an|some|the|ein|eine|einen|einem|einer|etwas|noch)\s+", re.I)


def split_items(text: Union[str, List[str], None]) -> List[str]:
    """"milk, bread and eggs" -> ["Milk", "Bread", "Eggs"] (also a list of such texts)."""
    parts: List[str] = []
    for chunk in ([text] if isinstance(text, str) else (text or [])):
        parts.extend(_SPLIT.split(str(chunk)))
    out: List[str] = []
    seen = set()
    for p in parts:
        p = _ARTICLE.sub("", p.strip().strip(".!?"))[:100].strip()
        if p and p.lower() not in seen and p.lower() not in _CONJUNCTIONS:
            seen.add(p.lower())
            out.append(_capitalise(p))
    return out[:MAX_ITEMS]


class ShoppingAdd(BaseModel):
    items: Union[str, List[str]] = ""


@router.post("/shopping/items")
async def add_shopping_items(data: ShoppingAdd, request: Request, lang: Optional[str] = None,
                             user: User = Depends(require_scope("shopping:write"))):
    """Put one or more items on the shopping list ("milk, bread and eggs")."""
    from app.routers import shopping

    v = voice_for(request, user, lang)
    items = split_items(data.items)
    if not items:
        return answer(v, False, "invalid", v.t("shop_none"), added=[], failed=[])
    added, failed = [], []
    for item in items:
        try:
            await shopping.add_item(shopping.AddItemRequest(item=item), user, None)
            added.append(item)
        except Exception as exc:  # noqa: BLE001 - the assistant must always get something to say
            logger.warning("Voice: could not add %r to the shopping list: %s", item, exc)
            failed.append(item)
    if not added:
        return answer(v, False, "unavailable", v.t("shop_unavailable"), added=[], failed=failed)
    if failed:
        return answer(v, False, "partial", v.t("shop_partial", added=len(added), total=len(items)),
                      added=added, failed=failed)
    key = "shop_added_one" if len(added) == 1 else "shop_added_many"
    return answer(v, True, "ok", v.t(key, items=v.join(added)), added=added, failed=[])


@router.get("/shopping")
async def open_shopping_items(request: Request, lang: Optional[str] = None,
                              user: User = Depends(require_scope("shopping:read"))):
    """What is still open on the shopping list."""
    from app.routers import shopping

    v = voice_for(request, user, lang)
    try:
        result = await shopping.list_items(user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Voice: shopping list failed: %s", exc)
        result = {"status": "unavailable", "groups": []}
    if result.get("status") != "ok":
        return answer(v, False, "unavailable", v.t("shop_unavailable"), items=[], count=0)
    items: List[str] = []
    for group in result.get("groups", []):
        for it in group.get("items", []):
            name = str(it.get("summary") or "").strip()
            if name and it.get("status") != "completed":
                items.append(name)
    if not items:
        return answer(v, True, "ok", v.t("shop_empty"), items=[], count=0)
    key = "shop_open_one" if len(items) == 1 else "shop_open"
    return answer(v, True, "ok", v.t(key, n=len(items), items=v.listing(items)), items=items, count=len(items))


# --- tasks ----------------------------------------------------------------------------------------------

_ME = {"", "me", "myself", "i", "mich", "mir", "ich", "selbst"}


class TaskAdd(BaseModel):
    title: str = ""
    assignee: Optional[str] = None  # a first name, display name or username


def resolve_person(db: Session, spoken: Optional[str], me: User):
    """(user, error) - error is ``"unknown"`` or ``"ambiguous"``. Active family members only, no guests."""
    name = (spoken or "").strip().strip(".!?").casefold()
    if name in _ME:
        return me, None
    people = db.query(User).filter(User.is_active == True, User.role != "guest").all()  # noqa: E712

    def names(u: User) -> List[str]:
        full = [n for n in (u.display_name, u.full_name, u.username) if n]
        return [n.casefold() for n in full]

    exact = [u for u in people if name in names(u)]
    if len(exact) == 1:
        return exact[0], None
    if not exact:
        first = [u for u in people if any(n.split()[0] == name for n in names(u) if n.split())]
        if len(first) == 1:
            return first[0], None
        exact = first
    return None, ("ambiguous" if exact else "unknown")


@router.post("/tasks")
async def add_task(data: TaskAdd, request: Request, lang: Optional[str] = None, db: Session = Depends(get_db),
                   user: User = Depends(require_scope("tasks:write"))):
    """Create a task, for yourself or for a named family member (their own task place applies)."""
    from app.routers import tasks

    v = voice_for(request, user, lang)
    title = _capitalise(data.title)[:200]
    if not title:
        return answer(v, False, "invalid", v.t("task_none"))
    if _level(user) < ROLE_LEVEL[ROLE_PARTNER]:
        return answer(v, False, "forbidden", v.t("task_forbidden"))
    person, problem = resolve_person(db, data.assignee, user)
    if problem:
        spoken = (data.assignee or "").strip()
        return answer(v, False, "not_found" if problem == "unknown" else "ambiguous",
                      v.t("task_unknown_person" if problem == "unknown" else "task_ambiguous_person", name=spoken))
    try:
        request_body = tasks.TaskCreateRequest(title=title, assignee_id=person.id if person.id != user.id else None)
        created = await tasks._create_task(request_body, "auto", None, user, db)
    except HTTPException as exc:
        logger.warning("Voice: task not created (%s): %s", exc.status_code, exc.detail)
        return answer(v, False, "unavailable", v.t("task_unavailable"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Voice: task not created: %s", exc)
        return answer(v, False, "unavailable", v.t("task_unavailable"))
    other = person.id != user.id
    speech = v.t("task_added_for", title=title, name=person.effective_name) if other else v.t("task_added", title=title)
    return answer(v, True, "ok", speech, title=title, assignee=person.effective_name if other else None,
                  uid=created.get("uid") if isinstance(created, dict) else None)


# --- meals ----------------------------------------------------------------------------------------------

def _day(spoken: Optional[str], today: date) -> Optional[date]:
    s = (spoken or "today").strip().lower()
    if s in ("today", "heute", ""):
        return today
    if s in ("tomorrow", "morgen"):
        return today + timedelta(days=1)
    if s in ("day_after_tomorrow", "übermorgen", "uebermorgen"):
        return today + timedelta(days=2)
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


@router.get("/meals")
async def meals(request: Request, day: Optional[str] = "today", lang: Optional[str] = None,
                db: Session = Depends(get_db), user: User = Depends(require_scope("meals:read"))):
    """What is for dinner (all meals of the day): ``day`` = today | tomorrow | YYYY-MM-DD."""
    from app.routers import meals as meals_router

    v = voice_for(request, user, lang)
    today = _today()
    target = _day(day, today)
    if target is None:
        return answer(v, False, "invalid", v.t("day_invalid"), meals=[])
    iso = target.isocalendar()
    try:
        result = await meals_router.get_meals(week=f"{iso[0]}-W{iso[1]:02d}", db=db, current_user=user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Voice: meal plan failed: %s", exc)
        result = {"status": "unavailable", "days": []}
    entries = next((d.get("entries", []) for d in result.get("days", []) if d.get("date") == target.isoformat()), [])
    found = [{"title": str(e.get("title") or "").strip(), "meal_type": e.get("meal_type")} for e in entries
             if str(e.get("title") or "").strip()]
    word = v.day_word(target, today)
    if not found and result.get("status") != "ok":
        return answer(v, False, "unavailable", v.t("meal_unavailable"), date=target.isoformat(), meals=[])
    if not found:
        return answer(v, True, "ok", v.t("meal_none", day=word[:1].upper() + word[1:] if v.lang == "de" else word),
                      date=target.isoformat(), meals=[])
    spoken = []
    for m in found:
        label = v.t(f"meal_{m['meal_type']}") if m["meal_type"] in ("breakfast", "lunch", "dinner") else None
        spoken.append(f"{label}: {m['title']}" if label and len(found) > 1 else m["title"])
    return answer(v, True, "ok", v.t("meal_some", day=word, items=v.join(spoken)), date=target.isoformat(), meals=found)


# --- calendar -------------------------------------------------------------------------------------------

def _naive(raw: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


@router.get("/events")
async def events(request: Request, day: Optional[str] = "today", lang: Optional[str] = None,
                 db: Session = Depends(get_db), user: User = Depends(require_scope("calendar:read"))):
    """Events of one day: ``day`` = today | tomorrow | YYYY-MM-DD."""
    from app.routers.calendar import collect_events
    from app.routers.today import _occurs_on

    v = voice_for(request, user, lang)
    today = _today()
    target = _day(day, today)
    if target is None:
        return answer(v, False, "invalid", v.t("day_invalid"), events=[])
    try:
        raw = await collect_events(db, user, 2, start=datetime.combine(target, datetime.min.time()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Voice: calendar failed: %s", exc)
        return answer(v, False, "unavailable", v.t("event_unavailable"), date=target.isoformat(), events=[])
    out, spoken = [], []
    for e in raw or []:
        if not _occurs_on(e, target):
            continue
        title = str(e.get("title") or "").strip() or "?"
        start = _naive(e.get("start"))
        all_day = bool(e.get("all_day")) or start is None
        out.append({"title": title, "start": e.get("start"), "end": e.get("end"), "all_day": all_day})
        spoken.append(v.t("event_allday", title=title) if all_day
                      else v.t("event_at", title=title, time=v.clock(start)))
    word = v.day_word(target, today)
    word = word[:1].upper() + word[1:] if v.lang == "de" else word
    if not out:
        return answer(v, True, "ok", v.t("event_none", day=word), date=target.isoformat(), events=[])
    key = "event_one" if len(out) == 1 else "event_some"
    return answer(v, True, "ok", v.t(key, day=word, n=len(out), items=v.listing(spoken)),
                  date=target.isoformat(), events=out)


# --- reminders ------------------------------------------------------------------------------------------

class ReminderAdd(BaseModel):
    text: str = ""
    when: str = ""  # spoken: "at 6", "18:30", "in 20 minutes", "tomorrow at 8", "um halb sieben"


@router.post("/reminders")
async def add_reminder(data: ReminderAdd, request: Request, lang: Optional[str] = None,
                       db: Session = Depends(get_db), user: User = Depends(require_scope("reminders:write"))):
    """A reminder for the key's owner at a spoken time (hub time zone)."""
    from app.models.reminder import Reminder

    v = voice_for(request, user, lang)
    title = _capitalise(data.text)[:200]
    if not title:
        return answer(v, False, "invalid", v.t("rem_none"))
    now = datetime.now(local_tz())
    due = parse_when(data.when, now)
    if due is None:
        return answer(v, False, "invalid", v.t("rem_no_time"))
    if due <= now:
        return answer(v, False, "invalid", v.t("rem_past"))
    try:
        reminder = Reminder(title=title, due_at=to_utc_naive(due), priority="info",
                            recurrence="none", for_family=False, fire_on="time", source="user",
                            created_by=user.id)
        db.add(reminder)
        db.commit()
        db.refresh(reminder)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("Voice: reminder not saved: %s", exc)
        return answer(v, False, "unavailable", v.t("rem_unavailable"))
    day = v.day_word(due.date(), now.date())
    when = f"{day} {'um' if v.lang == 'de' else 'at'} {v.clock(due)}"
    return answer(v, True, "ok", v.t("rem_ok", when=when, title=data.text.strip()[:200]), id=reminder.id, title=title,
                  due_at=due.astimezone(local_tz()).isoformat())
