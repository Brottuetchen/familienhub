"""Habitica-Integration für Gamification.

Aktuell nur Score-Up bei Task-Completion.
"""

from __future__ import annotations



from app.core.logging_config import get_logger

logger = get_logger("service.habitica")


async def score_up(user_id: int, task_uid: str) -> bool:
    """Erhöht Score in Habitica für erledigte Aufgabe.

    Args:
        user_id: Hub-User-ID
        task_uid: UID der erledigten Aufgabe

    Returns:
        True bei Erfolg, False bei Fehler

    Note:
        Fehler werden geloggt, blockieren aber nicht die Task-Completion.
        Habitica-Account-Daten kommen später aus user_settings.
    """
    try:
        # TODO: Habitica-API-Key aus verschlüsselten User-Settings holen
        # Aktuell: keine Implementierung, nur Platzhalter
        logger.debug("habitica score_up: user_id=%s, task_uid=%s", user_id, task_uid)
        return True
    except Exception as exc:
        logger.warning("habitica score_up failed: %s", exc, exc_info=True)
        return False
