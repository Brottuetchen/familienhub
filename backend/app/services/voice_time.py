"""Simple spoken times for the voice endpoints ("at 6", "18:30", "in 20 minutes", "morgen um halb sieben").

``parse_when`` works on text a speech-to-text engine hands over, in German and English, and rounds to whole
minutes. It never guesses wildly: anything it does not understand returns ``None`` and the caller asks again.

Rules for a bare hour without any marker ("at 6", "6:30"):
- without a day: the next time that hour comes round (at 07:00 "at 6" means 18:00, at 05:00 it means 06:00),
- with a day ("tomorrow at 6"): 1-6 are afternoon, 7-11 morning, 12 noon.
Markers that fix the hour: am/pm, "Uhr", a 24-hour value (0, 13-23, "07:30"), or a part of the day
(morning/evening/morgens/abends/...).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

_NUMBERS: Dict[str, int] = {
    # en
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45,
    "fifty": 50, "sixty": 60,
    # de
    "eins": 1, "ein": 1, "eine": 1, "einer": 1, "einem": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
    "fuenf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12, "zwoelf": 12,
    "fünfzehn": 15, "zwanzig": 20, "dreißig": 30, "dreissig": 30, "vierzig": 40, "fünfzig": 50, "sechzig": 60,
    "a": 1, "an": 1,
}
_NUM = r"\d{1,3}|" + "|".join(sorted((re.escape(k) for k in _NUMBERS), key=len, reverse=True))

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3, "freitag": 4, "samstag": 5, "sonnabend": 5,
    "sonntag": 6,
}

_AM_WORDS = r"morning|morgens|vormittags|früh|frueh|fruh"
_PM_WORDS = r"afternoon|evening|tonight|night|nachmittags|abends|abend|nachts"


def _num(token: str) -> int:
    return int(token) if token.isdigit() else _NUMBERS[token]


def _relative(text: str, now: datetime) -> Optional[datetime]:
    """"in 20 minutes", "in einer Stunde", "in half an hour", "in 2 hours", "in einer Viertelstunde"."""
    t = text.strip()
    if re.fullmatch(r"(?:in|nach)\s+(?:a\s+|an\s+)?(?:half an hour|half hour|einer halben stunde|einer halbe stunde)", t):
        return now + timedelta(minutes=30)
    if re.fullmatch(r"(?:in|nach)\s+(?:a\s+|an\s+|einer\s+)?(?:quarter of an hour|quarter hour|viertelstunde|viertel stunde)", t):
        return now + timedelta(minutes=15)
    m = re.fullmatch(
        rf"(?:in|nach)\s+(?P<n>{_NUM})\s*(?P<u>minutes?|mins?|minuten?|min|hours?|hrs?|h|stunden?|std)"
        rf"(?:\s+(?:and|und)\s+(?P<n2>{_NUM})\s*(?P<u2>minutes?|mins?|minuten?|min))?", t)
    if not m:
        m = re.fullmatch(rf"(?P<n>{_NUM})\s*(?P<u>minutes?|mins?|minuten?|hours?|stunden?)\s+(?:from now|ab jetzt)", t)
    if not m:
        return None
    unit_hours = m["u"].startswith(("h", "s"))
    minutes = _num(m["n"]) * (60 if unit_hours else 1)
    if m.groupdict().get("n2"):
        minutes += _num(m["n2"])
    if minutes <= 0 or minutes > 60 * 24 * 7:
        return None
    return now + timedelta(minutes=minutes)


def _clock(text: str) -> Optional[Tuple[int, int, bool, Optional[str]]]:
    """(hour, minute, fixed, meridiem) from the clock expression in ``text``; ``fixed`` = no am/pm guessing."""
    # quarter / half forms
    m = re.search(rf"\bhalb\s+(?P<h>{_NUM})\b", text)  # "halb sieben" = 6:30
    if m:
        h = (_num(m["h"]) - 1) % 24
        return h, 30, False, None, _num(m["h"])  # the spoken hour (7) decides morning/afternoon, not 6
    m = re.search(rf"\b(?:viertel|quarter)\s+(?P<k>nach|past|vor|to)\s+(?P<h>{_NUM})\b", text)
    if m:
        h = _num(m["h"])
        return ((h, 15) if m["k"] in ("nach", "past") else ((h - 1) % 24, 45)) + (False, None, h)
    m = re.search(rf"\bhalf past\s+(?P<h>{_NUM})\b", text)
    if m:
        return _num(m["h"]) % 24, 30, False, None
    # 18:30, 18.30, 6:30pm, 6.30 p.m.
    m = re.search(r"\b(?P<h>\d{1,2})[:.](?P<m>[0-5]\d)\s*(?P<ap>a\.?m\.?|p\.?m\.?|uhr)?(?!\d)", text)
    if m:
        return _finish(int(m["h"]), int(m["m"]), m["ap"], lead_zero=m["h"].startswith("0") and len(m["h"]) == 2,
                       colon=True)
    # 18 Uhr 30, 18 Uhr
    m = re.search(r"\b(?P<h>\d{1,2})\s*uhr(?:\s*(?P<m>[0-5]?\d)\b)?", text)
    if m:
        return _finish(int(m["h"]), int(m["m"] or 0), "uhr")
    # 6 pm, 6pm, 6 o'clock
    m = re.search(r"\b(?P<h>\d{1,2})\s*(?P<ap>a\.?m\.?|p\.?m\.?)", text)
    if m:
        return _finish(int(m["h"]), 0, m["ap"])
    m = re.search(rf"\b(?P<h>{_NUM})\s*(?P<ap>o'?clock|uhr)\b", text)
    if m:
        return _finish(_num(m["h"]), 0, "uhr")
    # bare "at 6", "um 6", "um sechs"
    m = re.search(rf"\b(?:at|um|gegen|@)\s+(?P<h>{_NUM})\b(?!\s*(?:minutes?|minuten|hours?|stunden?))", text)
    if m:
        return _finish(_num(m["h"]), 0, None)
    m = re.fullmatch(rf"(?P<h>{_NUM})", text.strip())  # just "6"
    if m:
        return _finish(_num(m["h"]), 0, None)
    return None


def _finish(hour: int, minute: int, marker: Optional[str], lead_zero: bool = False, colon: bool = False):
    if hour > 24 or minute > 59:
        return None
    if marker and marker.replace(".", "").startswith(("a", "p")):
        pm = marker.startswith("p")
        if hour < 1 or hour > 12:
            return None
        return hour % 12 + (12 if pm else 0), minute, True, "pm" if pm else "am"
    if marker == "uhr":
        return hour % 24, minute, True, None
    if hour == 0 or hour > 12 or lead_zero:
        return hour % 24, minute, True, None
    return hour, minute, False, None


def parse_when(text: str, now: datetime) -> Optional[datetime]:
    """Local, timezone-aware moment for the spoken ``text`` (``now`` must be timezone-aware local time).

    Returns ``None`` when nothing usable was said. The result may lie in the past when the person named
    today and a time that is over; the caller decides what to say.
    """
    t = re.sub(r"\s+", " ", (text or "").lower().strip().strip(".!?,"))
    if not t or len(t) > 120:
        return None
    t = t.replace("o clock", "o'clock").replace("uhr.", "uhr")

    rel = _relative(t, now)
    if rel is not None:
        return rel.replace(second=0, microsecond=0)

    # --- day ---
    day_offset: Optional[int] = None
    rest = t
    for pattern, offset in ((r"\b(?:day after tomorrow|übermorgen|uebermorgen)\b", 2),
                            (r"\b(?:tomorrow|morgen)\b", 1), (r"\b(?:today|heute)\b", 0)):
        if re.search(pattern, rest):
            day_offset, rest = offset, re.sub(pattern, " ", rest, count=1)
            break
    if day_offset is None:
        m = re.search(rf"\b(?:on |am |next |nächsten |naechsten )?(?P<d>{'|'.join(_WEEKDAYS)})\b", rest)
        if m:
            ahead = (_WEEKDAYS[m["d"]] - now.weekday()) % 7
            day_offset, rest = ahead, rest.replace(m.group(0), " ", 1)

    # --- part of the day ---
    part: Optional[str] = None
    if re.search(rf"\b(?:{_AM_WORDS})\b", rest) and not re.search(r"\bmorgen\b", rest):
        part = "am"
    if re.search(rf"\b(?:{_PM_WORDS})\b", rest):
        part = "pm"
    if re.search(r"\b(?:noon|mittags?|midday)\b", rest):
        clock: Optional[tuple] = (12, 0, True, None)
    elif re.search(r"\b(?:midnight|mitternacht)\b", rest):
        clock = (0, 0, True, None)
    else:
        clock = _clock(rest)
    if clock is None:
        if day_offset is None:
            return None
        clock = (9, 0, True, None)  # only a day was said: 09:00
    hour, minute, fixed = clock[0], clock[1], clock[2]
    ref = clock[4] if len(clock) > 4 else hour  # hour used to guess morning/afternoon

    if part and not fixed and 1 <= hour <= 12:
        hour, fixed = (hour % 12 + 12 if part == "pm" else hour % 12), True

    base = now.replace(second=0, microsecond=0)
    if day_offset is not None:
        day = base + timedelta(days=day_offset)
        if not fixed and 1 <= hour <= 12:
            hour = hour if ref >= 7 else hour + 12 if hour < 12 else hour
        return day.replace(hour=hour % 24, minute=minute)

    candidates: List[int] = [hour % 24] if fixed else sorted({hour % 12, hour % 12 + 12})
    options = []
    for h in candidates:
        moment = base.replace(hour=h, minute=minute)
        if moment <= now:
            moment += timedelta(days=1)
        options.append(moment)
    return min(options)
