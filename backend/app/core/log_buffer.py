"""Letzte Warnungen und Fehler im Speicher, für das Protokoll in der Verwaltung (nur Admins).

Kein Ersatz für echte Logs: höchstens 200 Einträge, nach einem Neustart leer. Tokens und lange
Zufallswerte werden geschwärzt, damit das Protokoll gefahrlos angezeigt werden kann.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, List

MAX_ENTRIES = 200
_entries: Deque[Dict[str, str]] = deque(maxlen=MAX_ENTRIES)

_SECRETS = [
    (re.compile(r"(?i)(bearer|token|api[_-]?key|password|passwort|secret)([\"'=: ]+)[^\s\"',;]+"), r"\1\2•••"),
    (re.compile(r"\b(fh[a-z]?_[A-Za-z0-9_\-]{8,})"), "•••"),
    (re.compile(r"\b[A-Za-z0-9_\-]{32,}\b"), "•••"),
]


def redact(text: str) -> str:
    for pattern, repl in _SECRETS:
        text = pattern.sub(repl, text)
    return text


class BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        if record.exc_info and record.exc_info[1] is not None:
            message = f"{message} ({type(record.exc_info[1]).__name__})"
        _entries.append({
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "source": record.name,
            "message": redact(message)[:500],
        })


def install() -> None:
    root = logging.getLogger()
    if not any(isinstance(h, BufferHandler) for h in root.handlers):
        handler = BufferHandler(level=logging.WARNING)
        root.addHandler(handler)


def entries() -> List[Dict[str, str]]:
    return list(reversed(_entries))  # neueste zuerst


def clear() -> None:
    _entries.clear()
