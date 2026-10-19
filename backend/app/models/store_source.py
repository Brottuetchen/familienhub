"""Extra store sources an admin added: a GitHub repository with an ``index.json`` (``docs/store.md``)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class StoreSource(Base):
    __tablename__ = "store_sources"

    id = Column(Integer, primary_key=True)
    repo_url = Column(String(300), nullable=False, unique=True)  # https://github.com/<owner>/<repo>[/tree/<branch>]
    name = Column(String(80), nullable=False, default="")  # name from the index at the time it was added
    added_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)
