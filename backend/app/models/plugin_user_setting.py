"""Settings a person fills in for one plugin (their own account, token …), see ``Plugin.personal_settings``."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class PluginUserSetting(Base):
    __tablename__ = "plugin_user_settings"

    plugin_id = Column(String(31), primary_key=True)  # the manifest's plugin id
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    key = Column(String(64), primary_key=True)
    # Plain text, or Fernet-encrypted (``secret``), like ``config_overrides``
    value = Column(Text, nullable=False, default="")
    secret = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
