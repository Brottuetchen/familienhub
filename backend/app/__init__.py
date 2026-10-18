"""Familienhub backend package.

A layer over existing self-hosted services (Nextcloud, Home Assistant, Paperless, ...): connectors and
plugins bundle them into one family dashboard and app.
"""

import os

# Release images set FH_VERSION at build time (see backend/Dockerfile and .github/workflows/docker.yml)
__version__ = os.environ.get("FH_VERSION") or "0.1.0"
__app_name__ = "Hermes Family OS"
