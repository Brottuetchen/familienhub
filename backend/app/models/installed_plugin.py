"""Plugins installed from GitHub by an admin (``docs/plugins.md``). The code lives in ``<DATA_DIR>/plugins``."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class InstalledPlugin(Base):
    __tablename__ = "installed_plugins"

    id = Column(String(31), primary_key=True)  # the manifest's plugin id
    repo_url = Column(String(300), nullable=False)
    sha = Column(String(40), nullable=False)  # the exact commit that is installed
    version = Column(String(32), nullable=False)
    manifest = Column(Text, nullable=False)  # validated manifest JSON as installed
    installed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    installed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    store_source = Column(String(32), nullable=True)  # "official" / "custom-<id>" if installed from the store
