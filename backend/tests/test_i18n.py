"""Server texts in the reader's language (#24): catalog coverage, error texts, plugin texts, push texts."""

import ast
import pathlib
import re

from app.core.i18n import EN, parse_accept_language, translate

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

GERMAN = re.compile(
    r"[äöüßÄÖÜ„“]|\b(nicht|kein|keine|nur|bitte|oder|und|mit|für|gibt|wird|darf|kann|ist|sind|fehlt|ungültig|"
    r"gefunden|eingerichtet|erforderlich|erreichbar|unbekannte?r?s?|leer|Adresse|Aufgabe|Termin|Kalender|Liste|"
    r"Rolle|Konto|Zugang|Erinnerung|Gerät|Einstellung|Breitengrad|Längengrad|Zeitzone|Sprache|Passwort|Land|"
    r"Ortsname|Wetter|Einkauf|Termine|Aufgaben|Titel|Helligkeit|Standard|Name des|Haus)\b",
    re.I,
)


def _template(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "X1" for v in node.values)
    return None


def _messages():
    """Texts the server shows to people: HTTP details, "error" fields, forwarded errors, plugin texts."""
    found = {}
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for n in ast.walk(tree):
            texts = []
            if isinstance(n, ast.Call):
                func = getattr(n.func, "id", getattr(n.func, "attr", None))
                if func == "HTTPException":
                    texts += n.args[1:2] + [k.value for k in n.keywords if k.arg == "detail"]
                if func == "Setting":
                    texts += n.args[1:2] + [k.value for k in n.keywords if k.arg in ("help", "label")]
                if "plugins" in path.parts:
                    texts += [k.value for k in n.keywords if k.arg in ("name", "description")]
            if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call) and getattr(n.exc.func, "id", None) == "ValueError":
                texts += n.exc.args[:1]
            if isinstance(n, ast.Dict):
                texts += [v for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant) and k.value == "error"]
            for t in filter(None, map(_template, texts)):
                found.setdefault(t, f"{path.relative_to(APP)}:{n.lineno}")
    return found


def test_every_german_server_text_has_an_english_translation():
    missing = [f"{loc}: {text}" for text, loc in _messages().items()
               if GERMAN.search(text) and translate(text, "en") == text]
    assert not missing, "Add these to app/core/i18n.py EN:\n" + "\n".join(sorted(missing))


def test_catalog_placeholders_match():
    for de, en in EN.items():
        assert set(re.findall(r"\{(\w+)\}", de)) == set(re.findall(r"\{(\w+)\}", en)), de


def test_translate_exact_templates_and_fallbacks():
    assert translate("Kalender nicht gefunden", "en") == "Calendar not found"
    assert translate("Kalender nicht gefunden", "de") == "Kalender nicht gefunden"
    assert translate("Kalender nicht gefunden", None) == "Kalender nicht gefunden"
    assert translate("Etwas völlig Neues", "en") == "Etwas völlig Neues"  # unknown stays readable
    assert translate("Hörbuch von Astrid Lindgren liegt in der Bibliothek.", "en") == "Audiobook by Astrid Lindgren is in the library."
    assert translate("Hörbuch liegt in der Bibliothek.", "en") == "Audiobook is in the library."
    assert translate("🎬 „Dune“ ist da", "en") == "🎬 “Dune” is available"


def test_accept_language_parsing():
    assert parse_accept_language("en-US,en;q=0.9,de;q=0.8") == "en"
    assert parse_accept_language("fr-FR, de;q=0.7, en;q=0.5") == "de"
    assert parse_accept_language("fr") is None
    assert parse_accept_language(None) is None


def test_error_detail_follows_the_app_language(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "vapid_private_key", None)
    monkeypatch.setattr(settings, "vapid_public_key", None)
    de = client.get("/api/push/vapid-public-key")
    en = client.get("/api/push/vapid-public-key", headers={"Accept-Language": "en-GB,en;q=0.9"})
    app_wins = client.get("/api/push/vapid-public-key", headers={"Accept-Language": "en", "X-App-Language": "de"})
    assert de.status_code == en.status_code == 501
    assert de.json()["detail"] == "Web Push nicht eingerichtet (VAPID-Schlüssel fehlen)"
    assert en.json()["detail"] == "Web Push not set up (VAPID keys missing)"
    assert app_wins.json()["detail"] == de.json()["detail"]


def test_cookies_survive_translation(client, admin_token):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "secret123"},
                    headers={"Accept-Language": "en"})
    assert r.status_code == 200
    assert len(r.headers.get_list("set-cookie")) >= 2  # access + refresh cookie both kept


def test_plugin_texts_on_admin_endpoints(client, auth):
    de = client.get("/api/admin/sources", headers=auth).json()
    en = client.get("/api/admin/sources", headers={**auth, "Accept-Language": "en"}).json()
    names_de = {s["name"] for a in de["areas"] for s in a["sources"]}
    names_en = {s["name"] for a in en["areas"] for s in a["sources"]}
    assert "Aufgaben im Hub" in names_de and "Tasks in the hub" in names_en


def test_push_text_in_the_recipients_language(client, auth):
    import asyncio

    from app.core.database import SessionLocal
    from app.models.notification_log import NotificationLog
    from app.models.user import User
    from app.services.notify import notify

    client.get("/api/auth/me", headers={**auth, "X-App-Language": "en"})  # the app reports its language
    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin").one()
        assert admin.language == "en"
        uid = admin.id
    asyncio.run(notify(uid, "⏰ Erinnerung", "Zahnarzt", category="reminder"))
    with SessionLocal() as db:
        last = db.query(NotificationLog).filter(NotificationLog.user_id == uid).order_by(NotificationLog.id.desc()).first()
        assert (last.title, last.body) == ("⏰ Reminder", "Zahnarzt")  # user content stays as written
    client.get("/api/auth/me", headers={**auth, "X-App-Language": "de"})
