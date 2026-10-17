"""Von Admins installierte Farbschemata. Mitgelieferte liegen als Dateien in ``app/themes``."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class Theme(Base):
    __tablename__ = "themes"

    id = Column(Integer, primary_key=True)
    name = Column(String(60), nullable=False, unique=True)
    source_url = Column(String(500), nullable=False)
    data = Column(Text, nullable=False)  # geprüftes JSON: {"name", "colors": {...}}
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
