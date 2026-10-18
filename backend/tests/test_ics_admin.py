"""Calendar subscriptions in the admin UI and setup wizard: list, add with a check, remove."""

from datetime import date, timedelta

import httpx
import respx

FEED = "https://feeds.example.test/ferien.ics"


def _ics(n=3):
    events = "".join(
        f"BEGIN:VEVENT\r\nUID:{i}\r\nSUMMARY:Ferientag {i}\r\nDTSTART;VALUE=DATE:{(date.today() + timedelta(days=i + 1)).strftime('%Y%m%d')}\r\nEND:VEVENT\r\n"
        for i in range(n))
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n{events}END:VCALENDAR\r\n"


def test_save_and_list_feeds(client, auth):
    try:
        r = client.put("/api/admin/ics", headers=auth, json={"feeds": [
            {"name": "Schulferien", "url": FEED}, {"name": " Müll ", "url": "https://feeds.example.test/abfall.ics"}]})
        assert r.status_code == 200, r.text
        feeds = client.get("/api/admin/ics", headers=auth).json()["feeds"]
        assert feeds == [{"name": "Schulferien", "url": FEED}, {"name": "Müll", "url": "https://feeds.example.test/abfall.ics"}]
        from app.plugins.base import get_setting
        assert get_setting("ICS_FEEDS") == f"Schulferien | {FEED}\nMüll | https://feeds.example.test/abfall.ics"
        modules = client.get("/api/modules", headers=auth).json()["plugins"]
        assert next(p for p in modules if p["id"] == "ics")["active"] is True
    finally:
        client.put("/api/admin/ics", headers=auth, json={"feeds": []})


def test_validation(client, auth):
    for feed in ({"name": "", "url": FEED}, {"name": "A|B", "url": FEED}, {"name": "Ok", "url": "file:///etc/passwd"},
                 {"name": "Ok", "url": "https://x.test/a;b"}):
        assert client.put("/api/admin/ics", headers=auth, json={"feeds": [feed]}).status_code == 422, feed
    too_many = [{"name": f"K{i}", "url": f"https://x.test/{i}.ics"} for i in range(21)]
    assert client.put("/api/admin/ics", headers=auth, json={"feeds": too_many}).status_code == 422


def test_check_a_feed_before_adding(client, auth):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get(FEED).mock(return_value=httpx.Response(200, text=_ics(3)))
        http.get("https://feeds.example.test/kaputt.ics").mock(return_value=httpx.Response(404))
        http.get("https://feeds.example.test/kein-kalender").mock(return_value=httpx.Response(200, text="<html>hallo</html>"))
        ok = client.post("/api/admin/ics/test", headers=auth, json={"url": FEED}).json()
        assert ok["ok"] is True and ok["events"] == 3 and ok["sample"][0] == "Ferientag 0"
        bad = client.post("/api/admin/ics/test", headers=auth, json={"url": "https://feeds.example.test/kaputt.ics"}).json()
        assert bad["ok"] is False and "404" in bad["error"]
        html = client.post("/api/admin/ics/test", headers=auth, json={"url": "https://feeds.example.test/kein-kalender"}).json()
        assert html["ok"] is False


def test_admin_only(client):
    from app.core.database import SessionLocal
    from app.core.security import get_password_hash
    from app.models.user import User

    with SessionLocal() as db:
        if not db.query(User).filter(User.username == "ics_partner").first():
            db.add(User(username="ics_partner", email="icsp@test.de", hashed_password=get_password_hash("pw-12345"), role="partner"))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": "ics_partner", "password": "pw-12345"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/admin/ics", headers=h).status_code == 403
    assert client.post("/api/admin/ics/test", headers=h, json={"url": FEED}).status_code == 403
