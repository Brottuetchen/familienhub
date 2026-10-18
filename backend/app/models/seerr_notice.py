"""Seerr requests already reported as available (poller and webhook share it, so nobody is told twice)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer

from app.core.database import Base


class SeerrNotice(Base):
    __tablename__ = "seerr_notices"

    request_id = Column(Integer, primary_key=True)  # 0 = marker: first run done
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
