"""Schreibbare native Habitica-Felder, keine Spielzustands-/Owner-Proxyfelder."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator


class ReminderFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    time: str
    startDate: str | None = None

    @field_validator("id")
    @classmethod
    def uuid(cls, value):
        if str(UUID(value)) != value:
            raise ValueError("Kanonische UUID erforderlich")
        return value

    @field_validator("time", "startDate")
    @classmethod
    def date(cls, value):
        if value is not None:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class NativeFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["todo", "daily", "habit", "reward"] | None = None
    text: str = Field(default=None, min_length=1, max_length=10000)
    notes: str | None = None
    alias: str | None = None
    attribute: Literal["str", "con", "int", "per"] | None = None
    priority: Literal[0.1, 1, 1.5, 2] | None = None
    tags: list[str] | None = None
    reminders: list[ReminderFields] | None = None
    up: StrictBool | None = None
    down: StrictBool | None = None
    frequency: Literal["daily", "weekly", "monthly", "yearly"] | None = None
    everyX: StrictInt = Field(default=None, ge=1, le=9999)
    startDate: str | None = None
    date: str | None = None
    repeat: dict[Literal["m", "t", "w", "th", "f", "s", "su"], StrictBool] | None = None
    daysOfMonth: list[StrictInt] | None = None
    weeksOfMonth: list[StrictInt] | None = None
    streak: StrictInt = Field(default=None, ge=0)
    collapseChecklist: StrictBool | None = None
    value: float = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("text")
    @classmethod
    def title(cls, value):
        if not value.strip():
            raise ValueError("Titel erforderlich")
        return value

    @field_validator("tags")
    @classmethod
    def tags_valid(cls, value):
        if value is None:
            raise ValueError("Zum Leeren [] verwenden")
        if len(value) != len(set(value)) or any(str(UUID(v)) != v for v in value):
            raise ValueError("Eindeutige kanonische Tag-UUIDs erforderlich")
        return value

    @field_validator("daysOfMonth", "weeksOfMonth")
    @classmethod
    def month(cls, value, info):
        bound = 31 if info.field_name == "daysOfMonth" else 5
        if value is None or len(value) != len(set(value)) or any(not 1 <= v <= bound for v in value):
            raise ValueError("Ungültiger Monatszeitplan")
        return value

    @field_validator("startDate", "date")
    @classmethod
    def dates(cls, value):
        if value:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @field_validator("priority", mode="before")
    @classmethod
    def difficulty(cls, value):
        if type(value) not in (int, float):
            raise ValueError("Native Schwierigkeit als Zahl erforderlich")
        return value
