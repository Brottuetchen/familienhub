"""Reusable template lists (packing lists, the weekly shopping, ...), shared within the family."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class ListTemplate(Base):
    __tablename__ = "list_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    items = relationship("ListTemplateItem", cascade="all, delete-orphan", order_by="ListTemplateItem.position",
                         passive_deletes=True)


class ListTemplateItem(Base):
    __tablename__ = "list_template_items"

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("list_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False, default=0)
    name = Column(String(200), nullable=False)
    note = Column(String(200), nullable=False, default="")  # optional quantity / note, e.g. "2 l"
