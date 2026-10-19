"""Hintergrund-Scheduler.

Prüft periodisch fällige Erinnerungen und verschickt dafür Web-Push-
Benachrichtigungen (einmalig, danach als ``notified`` markiert). Läuft als
asyncio-Task im App-Lifespan.
"""

from __future__ import annotations

import asyncio

from app.core.database import SessionLocal
from app.core.logging_config import get_logger
from app.models.reminder import Reminder
from app.models.user import User
from app.services.notify import notify
from app.core.security import create_reminder_action_token
from app.core.timeutil import utcnow
from app.services.recurrence import advance_utc

logger = get_logger("service.scheduler")

# Prüfintervall in Sekunden.
CHECK_INTERVAL = 60
SEERR_EVERY = 10  # ticks: look for newly available Seerr requests every 10 minutes


async def _tick() -> None:
    """Ein Prüf-Durchlauf: fällige, nicht benachrichtigte Erinnerungen pushen."""
    db = SessionLocal()
    try:
        now = utcnow()  # due_at liegt als UTC vor
        due = (
            db.query(Reminder)
            .filter(
                Reminder.completed == False,  # noqa: E712
                Reminder.notified == False,  # noqa: E712
                Reminder.due_at != None,  # noqa: E711
                Reminder.due_at <= now,
            )
            .all()
        )
        if not due:
            return
        all_users = None
        for reminder in due:
            # Private Erinnerung → Ersteller; Familie (oder alte ohne Ersteller) → alle aktiven Nutzer.
            if reminder.for_family or reminder.created_by is None:
                if all_users is None:
                    all_users = [u.id for u in db.query(User).filter(User.is_active == True).all()]  # noqa: E712
                recipients = all_users
            else:
                recipients = [reminder.created_by]
            for user_id in recipients:
                try:
                    await notify(
                        user_id,
                        "⏰ Erinnerung",
                        reminder.title,
                        data={
                            "route": "/reminders",
                            "reminder_id": reminder.id,
                            # Knöpfe in der Mitteilung; Token gilt nur für diese Erinnerung/Person
                            "actions": "done,snooze_1h,tomorrow",
                            "action_token": create_reminder_action_token(reminder.id, user_id),
                        },
                        category="reminder",
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("reminder %s an Nutzer %s nicht zugestellt: %s", reminder.id, user_id, exc)
            # Wiederkehrende Erinnerung: nächste Fälligkeit planen statt abschließen.
            next_due = advance_utc(reminder.due_at, reminder.recurrence)
            if next_due:
                reminder.due_at = next_due
                reminder.notified = False
                reminder.completed = False
            else:
                reminder.notified = True
        db.commit()
        logger.info("scheduler: notified %d due reminder(s)", len(due))
    except Exception as exc:  # noqa: BLE001
        logger.warning("scheduler tick failed: %s", exc)
    finally:
        db.close()


async def run_scheduler() -> None:
    """Endlosschleife – wird beim Shutdown via CancelledError beendet."""
    logger.info("reminder scheduler started (interval=%ds)", CHECK_INTERVAL)
    try:
        ticks = 0
        while True:
            await asyncio.sleep(CHECK_INTERVAL)
            await _tick()
            try:
                from app.services.event_alarms import send_due

                await send_due()
            except Exception as exc:  # noqa: BLE001 - must never stop the reminder loop
                logger.warning("event alarms failed: %s", type(exc).__name__)
            try:
                from app.services.birthdays import send_due as send_birthdays

                await send_birthdays()
            except Exception as exc:  # noqa: BLE001 - must never stop the reminder loop
                logger.warning("birthday reminders failed: %s", type(exc).__name__)
            try:
                from app.services import backup

                if backup.auto_due():  # nightly backup: blocking work runs in a thread
                    await asyncio.to_thread(backup.run_auto_if_due)
            except Exception as exc:  # noqa: BLE001 - must never stop the reminder loop
                logger.warning("nightly backup failed: %s", type(exc).__name__)
            ticks += 1
            if ticks % SEERR_EVERY == 0:
                try:
                    from app.services.seerr_watch import check_available

                    await check_available()
                except Exception as exc:  # noqa: BLE001 - must never stop the reminder loop
                    logger.warning("seerr check failed: %s", type(exc).__name__)
    except asyncio.CancelledError:  # pragma: no cover
        logger.info("reminder scheduler stopped")
        raise
