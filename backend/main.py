"""Kompatibilitäts-Einstiegspunkt für Hermes Family OS.

Die eigentliche Anwendung liegt in ``app/main.py``. Diese Datei erlaubt
weiterhin ``python main.py`` sowie ``uvicorn main:app`` aus dem Verzeichnis
``backend/``.
"""

from app.main import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn

    from app.config import settings

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, log_level=settings.log_level)
