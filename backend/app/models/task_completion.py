"""Dauerhafter Abschlussbeleg für rotierende CalDAV-Aufgaben."""
from sqlalchemy import Column, String

from app.core.database import Base


class TaskCompletion(Base):
    __tablename__ = "task_completions"

    uid = Column(String, primary_key=True)
