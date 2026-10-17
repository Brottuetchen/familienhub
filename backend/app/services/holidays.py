"""Deutsche Feiertage (bundesweit) – ohne externe Abhängigkeit.

Berechnet bewegliche Feiertage über den Osteralgorithmus (Gauß/Butcher).
Bundeslandspezifische Feiertage sind bewusst nicht enthalten (bundesweite Auswahl).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional


def _easter_sunday(year: int) -> date:
    """Ostersonntag nach dem anonymen gregorianischen Algorithmus."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def german_holidays(year: int) -> Dict[date, str]:
    """Bundesweite Feiertage eines Jahres als {Datum: Name}."""
    easter = _easter_sunday(year)
    holidays = {
        date(year, 1, 1): "Neujahr",
        easter - timedelta(days=2): "Karfreitag",
        easter + timedelta(days=1): "Ostermontag",
        date(year, 5, 1): "Tag der Arbeit",
        easter + timedelta(days=39): "Christi Himmelfahrt",
        easter + timedelta(days=50): "Pfingstmontag",
        date(year, 10, 3): "Tag der Deutschen Einheit",
        date(year, 12, 25): "1. Weihnachtstag",
        date(year, 12, 26): "2. Weihnachtstag",
    }
    return holidays


def holiday_on(day: date) -> Optional[str]:
    return german_holidays(day.year).get(day)


def upcoming_holidays(reference: Optional[date] = None, days: int = 30) -> List[Dict[str, str]]:
    """Feiertage in den nächsten ``days`` Tagen."""
    ref = reference or date.today()
    end = ref + timedelta(days=days)
    result: List[Dict[str, str]] = []
    for year in {ref.year, end.year}:
        for d, name in german_holidays(year).items():
            if ref <= d <= end:
                result.append({"date": d.isoformat(), "name": name})
    result.sort(key=lambda h: h["date"])
    return result
