"""Hub-side record of a task one person assigned to another (#38).

The task itself lives in the recipient's own task place (Nextcloud, Habitica or the hub). This row only
links creator, recipient and the remote object, so "Von mir" can list it and show open/done. It holds
no notes and never a copy of the recipient's lists.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class TaskAssignment(Base):
    __tablename__ = "task_assignments"

    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)  # where the task landed (plugin id)
    account_ref = Column(String(100), nullable=False, default="")
    remote_uid = Column(String(200), nullable=False)
    title = Column(String(200), nullable=False)
    due = Column(String(32), nullable=True)
    fallback = Column(Boolean, nullable=False, default=False)  # landed in the hub because the preferred place failed
    done = Column(Boolean, nullable=False, default=False)
    sync_ok = Column(Boolean, nullable=False, default=True)  # last status read from the recipient's provider worked
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    synced_at = Column(DateTime, nullable=True)
