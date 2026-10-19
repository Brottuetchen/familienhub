"""Usernames are stored lowercase; sign-in ignores case (the create dialog used to block capitals silently)."""


def test_admin_creates_mixed_case_username_and_person_signs_in_with_capitals(client, auth):
    r = client.post("/api/auth/users", headers=auth, json={
        "username": " Allie ", "email": "allie@example.org", "password": "lang-genug-123", "role": "child"})
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "allie"
    for typed in ("Allie", "allie", "ALLIE "):
        login = client.post("/api/auth/login", json={"username": typed, "password": "lang-genug-123"})
        assert login.status_code == 200, (typed, login.text)
    assert client.post("/api/auth/login", json={"username": "Allie", "password": "falsch-falsch"}).status_code == 401
    dup = client.post("/api/auth/users", headers=auth, json={
        "username": "ALLIE", "email": "other@example.org", "password": "lang-genug-123", "role": "child"})
    assert dup.status_code == 400
