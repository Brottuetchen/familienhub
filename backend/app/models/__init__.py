"""SQLAlchemy-Modelle für Hermes Family OS."""

from app.models.habitica import HabiticaAccount, HabiticaSelection, HabiticaOperation
from app.models.task_completion import TaskCompletion
from app.models.task_assignment import TaskAssignment
from app.models.stars import StarAccount, StarLedger, StarRequest, StarReward, StarTask
from app.models.api_token import ApiToken
from app.models.caldav import CalDAVAccount, TaskList
from app.models.notification_log import NotificationLog
from app.models.ntfy import NtfyTarget
from app.models.seerr_notice import SeerrNotice
from app.models.hub import HubEvent, HubShoppingItem, HubTask
from app.models.list_template import ListTemplate, ListTemplateItem
from app.models.event_alarm import EventAlarmSent
from app.models.birthday import Birthday, GiftIdea
from app.models.service_key import ServiceKey
from app.models.config import ConfigOverride
from app.models.today_layout import TodayLayout
from app.models.timetable import TimetableEntry
from app.models.push_device import PushDevice
from app.models.recipe import MealPlanEntry, Recipe
from app.models.paperless import PaperlessAccount
from app.models.invite import Invite
from app.models.feedback import Feedback
from app.models.reminder import Reminder
from app.models.theme import Theme
from app.models.store_source import StoreSource
from app.models.installed_plugin import InstalledPlugin
from app.models.user import LoginAttempt, RefreshToken, User, UserAvatar

__all__ = [
    "Birthday",
    "GiftIdea",
    "EventAlarmSent",
    "ListTemplate",
    "ListTemplateItem",
    "SeerrNotice",
    "TaskAssignment",
    "StarTask",
    "StarAccount",
    "StarLedger",
    "StarReward",
    "StarRequest",
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
    "TimetableEntry",
    "CalDAVAccount",
    "TaskList",
    "TaskCompletion",
    "ApiToken",
    "Theme",
    "StoreSource",
    "InstalledPlugin",
    "PaperlessAccount",
    "NotificationLog",
    "ServiceKey",
]
