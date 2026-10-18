"""SQLAlchemy-Modelle für Hermes Family OS."""

from app.models.habitica import HabiticaAccount, HabiticaSelection, HabiticaOperation
from app.models.task_completion import TaskCompletion
from app.models.api_token import ApiToken
from app.models.caldav import CalDAVAccount, TaskList
from app.models.notification_log import NotificationLog
from app.models.ntfy import NtfyTarget
from app.models.seerr_notice import SeerrNotice
from app.models.hub import HubEvent, HubShoppingItem, HubTask
from app.models.service_key import ServiceKey
from app.models.config import ConfigOverride
from app.models.push_device import PushDevice
from app.models.recipe import MealPlanEntry, Recipe
from app.models.paperless import PaperlessAccount
from app.models.invite import Invite
from app.models.feedback import Feedback
from app.models.reminder import Reminder
from app.models.theme import Theme
from app.models.user import LoginAttempt, RefreshToken, User, UserAvatar

__all__ = [
    "SeerrNotice",
    "HubEvent",
    "HubShoppingItem",
    "HubTask",
    "NtfyTarget",
    "Feedback",
    "Invite",
    "HabiticaAccount",
    "HabiticaSelection",
    "HabiticaOperation",
    "User",
    "UserAvatar",
    "RefreshToken",
    "LoginAttempt",
    "Reminder",
    "PushDevice",
    "Recipe",
    "MealPlanEntry",
    "ConfigOverride",
    "CalDAVAccount",
    "TaskList",
    "TaskCompletion",
    "ApiToken",
    "Theme",
    "PaperlessAccount",
    "NotificationLog",
    "ServiceKey",
]
