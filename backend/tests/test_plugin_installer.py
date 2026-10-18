"""Plugin installer: manifest, GitHub access, safe extraction, install / update / remove with a real
plugin package (extract + ``pip install --target`` + hot-load), security rules, i18n coverage.

GitHub, codeload and raw.githubusercontent.com are simulated with respx. The plugin package is real: a tiny
tarball with an in-tree build backend, installed offline (``--no-index --no-build-isolation``).
"""

import ast
import importlib.util
import io
import json
import pathlib
import re
import shutil
import sys
import tarfile
import textwrap

import httpx
import pytest
import respx
from fastapi import APIRouter, FastAPI

from app.config import settings
from app.core import log_buffer
from app.core.crypto import decrypt
from app.core.database import SessionLocal
from app.core.i18n import translate
from app.core.security import get_password_hash
from app.main import app
from app.models.config import ConfigOverride
from app.models.installed_plugin import InstalledPlugin
from app.models.user import User
from app.plugins import archive, github, installer
from app.plugins.manifest import (MAX_MANIFEST_BYTES, form_spec, is_reserved_id, parse_manifest, validate_manifest)
from app.plugins.registry import plugin_registry
from app.services import config_store

APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"
SHA1, SHA2 = "a" * 40, "b" * 40
URL = "https://github.com/acme/demo"
TOKEN = "tok-secret-123"


# --- A real, tiny plugin package ---

BACKEND = '''
import base64, hashlib, os, zipfile

NAME, VERSION, PKG = "{dist}", "{version}", "{pkg}"


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    wheel = f"{{NAME}}-{{VERSION}}-py3-none-any.whl"
    dist = f"{{NAME}}-{{VERSION}}.dist-info"
    entries = {{}}
    for root, _, files in os.walk(PKG):
        if "__pycache__" in root:
            continue
        for f in files:
            path = os.path.join(root, f)
            entries[path.replace(os.sep, "/")] = open(path, "rb").read()
    entries[dist + "/METADATA"] = f"Metadata-Version: 2.1\\nName: {{NAME}}\\nVersion: {{VERSION}}\\n".encode()
    entries[dist + "/WHEEL"] = b"Wheel-Version: 1.0\\nGenerator: tiny\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n"
    record = []
    with zipfile.ZipFile(os.path.join(wheel_directory, wheel), "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            record.append(f"{{name}},sha256={{digest}},{{len(data)}}")
        record.append(dist + "/RECORD,,")
        z.writestr(dist + "/RECORD", "\\n".join(record) + "\\n")
    return wheel
'''


def plugin_code(pid="demo_hub", *, version="1.0.0", router_path=None, code_id=None, caps="frozenset()", extra=""):
    key = pid.upper()
    return textwrap.dedent(f'''
        from fastapi import APIRouter
        from app.plugins import Plugin, Setting, get_setting

        router = APIRouter(prefix="{router_path or '/api/plugins/' + pid}", tags=["{pid}"])


        @router.get("/items")
        async def items():
            url = get_setting("{key}_URL")
            if not url:
                return {{"status": "not_configured", "error": None, "items": []}}
            return {{"status": "ok", "error": None, "version": "{version}",
                     "items": [{{"url": url, "token_set": bool(get_setting("{key}_TOKEN"))}}]}}


        class DemoPlugin(Plugin):
            def __init__(self):
                super().__init__(id="{code_id or pid}", name="Demo", capabilities={caps},
                                 settings=(Setting("{key}_URL", "Adresse"),
                                           Setting("{key}_TOKEN", "Token", secret=True, required=False){extra}))

            def routers(self):
                return [router]
    ''')


def manifest_dict(pid="demo_hub", version="1.0.0", **extra):
    key = pid.upper()
    return {
        "id": pid,
        "name": {"de": "Demo-Plugin", "en": "Demo plugin"},
        "version": version,
        "description": {"de": "Zeigt ein Beispiel", "en": "Shows an example"},
        "author": "Acme",
        "homepage": "https://github.com/acme/demo",
        "license": "MIT",
        "entry_point": "fh_plugin_demo.plugin:DemoPlugin",
        "settings": [
            {"key": f"{key}_URL", "label": {"de": "Adresse", "en": "Address"}, "type": "url", "required": True,
             "example": "https://demo.example.org"},
            {"key": f"{key}_TOKEN", "label": "Token", "type": "password", "required": False},
        ],
        "hosts": ["demo.example.org"],
        "capabilities": [],
        **extra,
    }


def repo_files(pid="demo_hub", version="1.0.0", *, manifest=None, code=None, pyproject=None, extra_files=None):
    files = {
        "familienhub-plugin.json": json.dumps(manifest or manifest_dict(pid, version)),
        "pyproject.toml": pyproject or textwrap.dedent('''
            [build-system]
            requires = []
            build-backend = "tiny_backend"
            backend-path = ["."]

            [project]
            name = "familienhub-plugin-demo"
            version = "1.0.0"
        '''),
        "tiny_backend.py": BACKEND.format(dist="familienhub_plugin_demo", version=version, pkg="fh_plugin_demo"),
        "fh_plugin_demo/__init__.py": "",
        "fh_plugin_demo/plugin.py": code or plugin_code(pid, version=version),
    }
    files.update(extra_files or {})
    return files


def tarball(files, sha=SHA1):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(f"demo-{sha}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeGitHub:
    """api.github.com + raw.githubusercontent.com + codeload.github.com in one handler; records every URL."""

    def __init__(self):
        self.head = SHA1
        self.manifests = {}  # sha -> bytes
        self.tarballs = {}  # sha -> bytes
        self.calls = []
        self.override = None  # callable(request) -> Response | None

    def publish(self, sha, files, *, head=True):
        self.manifests[sha] = files["familienhub-plugin.json"].encode()
        self.tarballs[sha] = tarball(files, sha)
        if head:
            self.head = sha

    def handle(self, request: httpx.Request):
        self.calls.append(str(request.url))
        if self.override and (resp := self.override(request)):
            return resp
        host, path = request.url.host, request.url.path
        if host == "api.github.com":
            m = re.match(r"^/repos/[^/]+/[^/]+/commits/(.+)$", path)
            if m and m.group(1) in ("HEAD", "main"):
                return httpx.Response(200, text=self.head)
            if m and m.group(1) in self.manifests:
                return httpx.Response(200, text=m.group(1))
            return httpx.Response(422, json={"message": "No commit found"})
        if host == "raw.githubusercontent.com":
            m = re.match(r"^/[^/]+/[^/]+/([0-9a-f]{40})/(.+)$", path)
            if m and m.group(1) in self.manifests and m.group(2) == "familienhub-plugin.json":
                return httpx.Response(200, content=self.manifests[m.group(1)])
            return httpx.Response(404)
        if host == "codeload.github.com":
            m = re.match(r"^/[^/]+/[^/]+/tar.gz/([0-9a-f]{40})$", path)
            if m and m.group(1) in self.tarballs:
                return httpx.Response(200, content=self.tarballs[m.group(1)])
            return httpx.Response(404)
        return httpx.Response(500, text="host not expected")

    def hosts(self):
        return {httpx.URL(u).host for u in self.calls}

    def count(self, host):
        return sum(1 for u in self.calls if httpx.URL(u).host == host)


def offline_pip(package_dir, target):
    """pip (or uv, where the environment has no pip) without network and without build isolation."""
    if importlib.util.find_spec("pip"):
        base = [sys.executable, "-m", "pip", "install"]
    else:
        uv = shutil.which("uv") or str(pathlib.Path.home() / ".local" / "bin" / "uv")
        if not pathlib.Path(uv).exists():
            pytest.skip("neither pip nor uv available to install the test package")
        base = [uv, "pip", "install", "--python", sys.executable]
    return base + ["--no-deps", "--no-index", "--no-build-isolation", "--target", str(target), str(package_dir)]


# --- Fixtures ---

def _login(client, name, role):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role=role))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def partner(client):
    return _login(client, "pi_partner", "partner")


@pytest.fixture
def gh(tmp_path, monkeypatch):
    """Fake GitHub, isolated data folder, offline pip; cleans up anything an install left behind."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    monkeypatch.setattr(settings, "plugin_install_enabled", True)
    monkeypatch.setattr(installer, "pip_command", offline_pip)
    fake = FakeGitHub()
    with respx.mock(using="httpx", assert_all_called=False, assert_all_mocked=True) as http:
        http.route(host="testserver").pass_through()  # the test client itself
        http.route().mock(side_effect=fake.handle)
        yield fake
    for pid in ("demo_hub", "other_demo"):
        installer.unload_plugin(app, pid)
    with SessionLocal() as db:
        db.query(InstalledPlugin).delete()
        db.query(ConfigOverride).filter(ConfigOverride.key.like("DEMO_HUB_%") | ConfigOverride.key.like("OTHER_DEMO_%")).delete(
            synchronize_session=False)
        db.commit()
    installer._errors.clear()  # noqa: SLF001
    for key in list(config_store._extra):  # noqa: SLF001
        if key.startswith(("DEMO_HUB_", "OTHER_DEMO_")):
            config_store._extra.pop(key)  # noqa: SLF001


def inspect(client, auth, url=URL, **headers):
    return client.post("/api/plugins/inspect", headers={**auth, **headers}, json={"url": url})


def install(client, auth, sha=SHA1, settings_=None, url=URL):
    body = {"url": url, "sha": sha,
            "settings": {"DEMO_HUB_URL": "https://demo.example.org", "DEMO_HUB_TOKEN": TOKEN} if settings_ is None else settings_}
    return client.post("/api/plugins/install", headers=auth, json=body)


# --- Manifest ---

def test_valid_manifest_gets_defaults_and_keeps_translations():
    m = validate_manifest(manifest_dict())
    assert validate_manifest(m) == m  # the stored form validates again (used at start-up and on update)
    assert m["package"] == "." and m["min_hub_version"] == "" and m["capabilities"] == []
    assert m["settings"][1]["secret"] is True  # type password implies secret
    assert m["settings"][0]["required"] is True and m["settings"][1]["required"] is False
    assert m["name"] == {"de": "Demo-Plugin", "en": "Demo plugin"}
    assert [f["label"] for f in form_spec(m, "en")] == ["Address", "Token"]
    assert [f["label"] for f in form_spec(m, "de")] == ["Adresse", "Token"]


@pytest.mark.parametrize("change, message", [
    ({"id": "Demo"}, "id muss"),
    ({"id": "x"}, "id muss"),
    ({"id": "weather"}, "reserviert"),
    ({"id": "hub_extra"}, "reserviert"),
    ({"id": "vapid"}, "reserviert"),
    ({"id": "caldav_x"}, "reserviert"),
    ({"id": "tasks"}, "reserviert"),
    ({"surprise": 1}, "unbekannte Felder"),
    ({"version": "latest"}, "version"),
    ({"entry_point": "no_colon"}, "entry_point"),
    ({"package": "../outside"}, "package"),
    ({"package": "/abs"}, "package"),
    ({"homepage": "http://insecure.example"}, "homepage"),
    ({"hosts": ["https://x.example"]}, "hosts"),
    ({"capabilities": ["root_access"]}, "capabilities"),
    ({"name": ""}, "name"),
    ({"name": {"fr": "Démo"}}, "de und en"),
    ({"description": "x" * 501}, "description"),
    ({"settings": [{"key": "OTHER_URL", "label": "x"}]}, "muss mit DEMO_HUB_ beginnen"),
    ({"settings": [{"key": "DEMO_HUB_", "label": "x"}]}, "muss mit DEMO_HUB_ beginnen"),
    ({"settings": [{"key": "SECRET_KEY", "label": "x"}]}, "muss mit DEMO_HUB_ beginnen"),
    ({"settings": [{"key": "DEMO_HUB_A", "label": "x", "color": "red"}]}, "unbekannte Felder"),
    ({"settings": [{"key": "DEMO_HUB_A", "label": "x", "type": "file"}]}, "type"),
    ({"settings": [{"key": "DEMO_HUB_A", "label": "x"}, {"key": "DEMO_HUB_A", "label": "y"}]}, "doppelt"),
    ({"settings": [{"key": "DEMO_HUB_A", "label": "x", "type": "password", "default": "abc"}]}, "Vorgabe"),
    ({"settings": [{"key": "DEMO_HUB_A", "label": "x", "type": "number", "default": "abc"}]}, "Vorgabe"),
    ({"settings": [{"key": "DEMO_HUB_A", "label": "x", "type": "url", "default": "ftp://x"}]}, "http"),
])
def test_manifest_rejects(change, message):
    with pytest.raises(ValueError) as exc:
        validate_manifest({**manifest_dict(), **change})
    assert message in str(exc.value)


def test_manifest_required_fields_and_shape():
    for field in ("id", "name", "version", "description", "author", "entry_point"):
        raw = manifest_dict()
        del raw[field]
        with pytest.raises(ValueError, match=field):
            validate_manifest(raw)
    with pytest.raises(ValueError):
        validate_manifest(["not", "an", "object"])
    with pytest.raises(ValueError, match="JSON"):
        parse_manifest(b"{nope")
    with pytest.raises(ValueError, match="64 KB"):
        parse_manifest(b" " * (MAX_MANIFEST_BYTES + 1))


def test_reserved_ids_cover_core_and_builtin_words():
    for word in ("nextcloud", "homeassistant", "hub_tasks", "weather", "plugins", "oidc", "database", "tasks", "calendar",
                 "paperless_extra"):
        assert is_reserved_id(word), word
    for free in ("demo_hub", "grocy", "mealplan_x"):
        assert not is_reserved_id(free), free


def test_no_installed_setting_key_can_reach_a_core_field():
    """Whatever id passes the check, its '<ID>_' keys never equal a core settings field."""
    from app.config import Settings

    for name in Settings.model_fields:
        key = name.upper()
        pid = key.lower().split("_")[0]
        assert is_reserved_id(pid), f"{key} could be claimed by id {pid}"


# --- GitHub link and archive ---

@pytest.mark.parametrize("url, expected", [
    ("https://github.com/acme/demo", ("acme", "demo", ())),
    ("https://github.com/acme/demo/", ("acme", "demo", ())),
    ("https://github.com/acme/demo.git", ("acme", "demo", ())),
    ("https://github.com/acme/demo/tree/main", ("acme", "demo", ("main",))),
    ("https://github.com/acme/demo/tree/feature/x/sub/dir", ("acme", "demo", ("feature", "x", "sub", "dir"))),
])
def test_parse_repo_url(url, expected):
    ref = github.parse_repo_url(url)
    assert (ref.owner, ref.repo, ref.rest) == expected


@pytest.mark.parametrize("url", [
    "http://github.com/acme/demo", "https://gitlab.com/acme/demo", "https://evil.example/github.com/acme/demo",
    "https://github.com/acme", "https://github.com/acme/demo?x=1", "https://github.com/acme/demo#frag",
    "https://user:pw@github.com/acme/demo", "https://github.com:444/acme/demo", "https://github.com/acme/demo/blob/main/x",
    "https://github.com/acme/demo/tree/../x", "https://github.com/-bad/demo", "https://raw.githubusercontent.com/acme/demo/main",
    "ftp://github.com/acme/demo", "", "not a url",
])
def test_parse_repo_url_rejects(url):
    with pytest.raises(github.GitHubError):
        github.parse_repo_url(url)


def test_only_three_hosts_are_allowed():
    for ok in ("https://api.github.com/x", "https://raw.githubusercontent.com/x", "https://codeload.github.com/x"):
        github._check(ok)  # noqa: SLF001
    for bad in ("https://github.com/x", "http://api.github.com/x", "https://evil.example/x", "https://api.github.com:8443/x"):
        with pytest.raises(github.GitHubError):
            github._check(bad)  # noqa: SLF001


def _tar(members):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for info, data in members:
            tar.addfile(info, io.BytesIO(data) if data is not None else None)
    return buf.getvalue()


def _file(name, data=b"x"):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    return info, data


def _special(name, kind, linkname=""):
    info = tarfile.TarInfo(name)
    info.type, info.linkname = kind, linkname
    return info, None


def test_extract_strips_top_folder_and_writes_regular_files(tmp_path):
    dest = tmp_path / "out"
    count = archive.safe_extract(_tar([_file("repo-abc/a.txt", b"A"), _file("repo-abc/sub/b.txt", b"B")]), dest)
    assert count == 2 and (dest / "a.txt").read_bytes() == b"A" and (dest / "sub" / "b.txt").read_bytes() == b"B"


@pytest.mark.parametrize("members, message", [
    ([_file("repo/../../evil.txt")], "ungültige Pfade"),
    ([_file("/abs/evil.txt")], "ungültige Pfade"),
    ([_file("repo/a\\b.txt")], "ungültige Pfade"),
    ([_special("repo/link", tarfile.SYMTYPE, "/etc/passwd")], "Verknüpfungen"),
    ([_special("repo/hard", tarfile.LNKTYPE, "repo/a")], "Verknüpfungen"),
    ([_special("repo/dev", tarfile.CHRTYPE)], "Verknüpfungen"),
    ([_special("repo/fifo", tarfile.FIFOTYPE)], "Verknüpfungen"),
    ([_special("repo/", tarfile.DIRTYPE)], "leer"),
])
def test_extract_rejects_dangerous_archives(tmp_path, members, message):
    with pytest.raises(archive.ArchiveError, match=message):
        archive.safe_extract(_tar(members), tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_extract_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "MAX_FILES", 3)
    with pytest.raises(archive.ArchiveError, match="mehr als 3"):
        archive.safe_extract(_tar([_file(f"r/{i}.txt") for i in range(4)]), tmp_path / "a")
    monkeypatch.setattr(archive, "MAX_FILE_BYTES", 10)
    with pytest.raises(archive.ArchiveError, match="10 MB"):
        archive.safe_extract(_tar([_file("r/big.bin", b"x" * 11)]), tmp_path / "b")
    monkeypatch.setattr(archive, "MAX_FILE_BYTES", 100)
    monkeypatch.setattr(archive, "MAX_TOTAL_BYTES", 15)
    with pytest.raises(archive.ArchiveError, match="50 MB"):
        archive.safe_extract(_tar([_file("r/a", b"x" * 10), _file("r/b", b"x" * 10)]), tmp_path / "c")
    with pytest.raises(archive.ArchiveError, match="beschädigt"):
        archive.safe_extract(b"this is not a tarball", tmp_path / "d")


# --- Inspect ---

def test_inspect_and_install_are_admin_only(client, auth, partner, gh):
    gh.publish(SHA1, repo_files())
    assert client.post("/api/plugins/inspect", json={"url": URL}).status_code == 401
    assert inspect(client, partner).status_code == 403
    assert install(client, partner).status_code == 403
    assert client.delete("/api/plugins/demo_hub", headers=partner).status_code == 403
    assert client.get("/api/plugins/installed", headers=partner).status_code == 403
    assert gh.calls == []  # a non-admin never makes the hub contact GitHub


def test_inspect_resolves_to_a_commit_and_describes_the_form(client, auth, gh):
    gh.publish(SHA1, repo_files())
    r = inspect(client, auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sha"] == SHA1 and body["short_sha"] == "aaaaaaa" and body["url"] == URL
    assert body["repo"] == {"url": URL, "owner": "acme", "repo": "demo", "folder": ""}
    m = body["manifest"]
    assert (m["id"], m["name"], m["version"], m["author"]) == ("demo_hub", "Demo-Plugin", "1.0.0", "Acme")
    assert m["description"] == "Zeigt ein Beispiel" and m["hosts"] == ["demo.example.org"]
    assert [(s["key"], s["label"], s["type"], s["secret"], s["required"]) for s in body["settings"]] == [
        ("DEMO_HUB_URL", "Adresse", "url", False, True), ("DEMO_HUB_TOKEN", "Token", "password", True, False)]
    assert body["installed"] is None and body["install_enabled"] is True
    # exactly the allow-listed hosts, nothing downloaded yet
    assert gh.hosts() == {"api.github.com", "raw.githubusercontent.com"}
    assert gh.calls[0] == "https://api.github.com/repos/acme/demo/commits/HEAD"
    assert gh.calls[1] == f"https://raw.githubusercontent.com/acme/demo/{SHA1}/familienhub-plugin.json"


def test_inspect_texts_follow_the_request_language(client, auth, gh):
    gh.publish(SHA1, repo_files())
    en = inspect(client, auth, **{"X-App-Language": "en"}).json()
    assert en["manifest"]["name"] == "Demo plugin" and en["manifest"]["description"] == "Shows an example"
    assert [s["label"] for s in en["settings"]] == ["Address", "Token"]
    de = inspect(client, auth, **{"Accept-Language": "de"}).json()
    assert de["manifest"]["name"] == "Demo-Plugin"
    en_err = client.post("/api/plugins/inspect", headers={**auth, "X-App-Language": "en"}, json={"url": "https://gitlab.com/a/b"})
    assert en_err.status_code == 422 and en_err.json()["detail"] == "Only plugins from GitHub (github.com)"


def test_inspect_with_branch_and_folder_and_slash_branch(client, auth, gh):
    gh.publish(SHA1, repo_files())
    r = inspect(client, auth, url=f"{URL}/tree/main")
    assert r.status_code == 200 and r.json()["url"] == f"{URL}/tree/main" and r.json()["repo"]["folder"] == ""
    # "feature" is no ref (422), "feature/x" is: the rest is the folder
    seen = []

    def override(request):
        seen.append(request.url.path)
        if request.url.host == "api.github.com" and request.url.path.endswith("/commits/feature/x"):
            return httpx.Response(200, text=SHA1)
        if request.url.host == "raw.githubusercontent.com":
            return httpx.Response(200, content=gh.manifests[SHA1]) if request.url.path.endswith("/sub/familienhub-plugin.json") \
                else httpx.Response(404)
        return None

    gh.override = override
    r = inspect(client, auth, url=f"{URL}/tree/feature/x/sub")
    assert r.status_code == 200, r.text
    assert r.json()["repo"]["folder"] == "sub"
    assert "/repos/acme/demo/commits/feature" in seen and "/repos/acme/demo/commits/feature/x" in seen


def test_inspect_errors_are_soft_and_never_follow_redirects(client, auth, gh):
    # a repository without a manifest
    r = inspect(client, auth)
    assert r.status_code == 422 and "familienhub-plugin.json" in r.json()["detail"]
    gh.publish(SHA1, repo_files())
    gh.manifests[SHA1] = b"{ definitely not json"
    r = inspect(client, auth)
    assert r.status_code == 422 and "JSON" in r.json()["detail"]
    # redirect (renamed repository): reported, the Location is never requested
    gh.override = lambda req: httpx.Response(301, headers={"Location": "https://evil.example/steal"}) \
        if req.url.host == "api.github.com" else None
    r = inspect(client, auth)
    assert r.status_code == 422 and "umbenannt" in r.json()["detail"]
    assert "evil.example" not in gh.hosts()
    # rate limit, outage, oversized manifest
    gh.override = lambda req: httpx.Response(403) if req.url.host == "api.github.com" else None
    assert "begrenzt" in inspect(client, auth).json()["detail"]
    gh.override = lambda req: (_ for _ in ()).throw(httpx.ConnectError("down"))
    assert inspect(client, auth).json()["detail"] == "GitHub nicht erreichbar"
    gh.override = lambda req: httpx.Response(200, content=b"x" * (MAX_MANIFEST_BYTES + 5)) \
        if req.url.host == "raw.githubusercontent.com" else None
    assert "64 KB" in inspect(client, auth).json()["detail"]


def test_inspect_refuses_taken_ids_and_old_hubs(client, auth, gh):
    gh.publish(SHA1, repo_files("weather", manifest=manifest_dict("weather")))
    r = inspect(client, auth)
    assert r.status_code == 422 and "reserviert" in r.json()["detail"]
    # an id that a plugin from an entry point already uses
    from app.plugins.base import Plugin

    plugin_registry.register(Plugin(id="demo_hub", name="From a docker image"))
    try:
        gh.publish(SHA1, repo_files())
        r = inspect(client, auth)
        assert r.status_code == 422 and "schon vergeben" in r.json()["detail"]
    finally:
        plugin_registry.unregister("demo_hub")
    gh.publish(SHA1, repo_files(manifest=manifest_dict(min_hub_version="99.0.0")))
    r = inspect(client, auth)
    assert r.status_code == 422 and "99.0.0" in r.json()["detail"]


def test_installer_can_be_switched_off(client, auth, gh, monkeypatch):
    gh.publish(SHA1, repo_files())
    monkeypatch.setattr(settings, "plugin_install_enabled", False)
    assert inspect(client, auth).status_code == 403
    assert install(client, auth).status_code == 403
    assert gh.calls == []
    listing = client.get("/api/plugins/installed", headers=auth).json()
    assert listing["enabled"] is False


# --- Install, use, update, remove ---

def test_install_hot_loads_a_real_plugin_and_stores_secrets_safely(client, auth, gh):
    gh.publish(SHA1, repo_files())
    assert client.get("/api/plugins/demo_hub/items", headers=auth).status_code == 404  # not there yet

    r = install(client, auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["id"], body["version"], body["sha"], body["updated"], body["restart_required"]) == (
        "demo_hub", "1.0.0", SHA1, False, False)
    assert body["active"] is True and body["plugin"]["loaded"] is True and body["plugin"]["error"] is None
    assert TOKEN not in r.text  # the secret is never echoed
    assert gh.hosts() == {"api.github.com", "raw.githubusercontent.com", "codeload.github.com"}
    assert f"https://codeload.github.com/acme/demo/tar.gz/{SHA1}" in gh.calls

    # files: source of exactly this commit, package installed with its own site folder
    base = pathlib.Path(settings.data_dir) / "plugins"
    assert (base / "src" / f"demo_hub-{SHA1}" / "familienhub-plugin.json").is_file()
    assert (base / "site" / "demo_hub" / "fh_plugin_demo" / "plugin.py").is_file()
    assert list((base / "tmp").iterdir()) == []

    # works without a restart: the route is live, namespaced, and needs a login
    assert client.get("/api/plugins/demo_hub/items").status_code == 401
    live = client.get("/api/plugins/demo_hub/items", headers=auth).json()
    assert live == {"status": "ok", "error": None, "version": "1.0.0",
                    "items": [{"url": "https://demo.example.org", "token_set": True}]}

    # the plugin shows up like any other: list, settings form (secret masked), modules
    plugin = plugin_registry.get("demo_hub")
    assert plugin.name == "Demo-Plugin" and plugin.version == "1.0.0" and plugin.builtin is False and plugin.active
    fields = {f["key"]: f for p in client.get("/api/admin/settings", headers=auth).json() if p["id"] == "demo_hub"
              for f in p["fields"]}
    assert fields["DEMO_HUB_TOKEN"]["value"] == "" and fields["DEMO_HUB_TOKEN"]["is_set"] is True
    assert fields["DEMO_HUB_URL"]["value"] == "https://demo.example.org"
    assert TOKEN not in client.get("/api/admin/settings", headers=auth).text
    en_name = next(p["name"] for p in client.get("/api/admin/settings", headers={**auth, "X-App-Language": "en"}).json()
                   if p["id"] == "demo_hub")
    assert en_name == "Demo plugin"

    # stored encrypted in the database, record complete
    with SessionLocal() as db:
        row = db.get(ConfigOverride, "DEMO_HUB_TOKEN")
        assert row.secret is True and TOKEN not in row.value and decrypt(row.value) == TOKEN
        assert db.get(ConfigOverride, "DEMO_HUB_URL").secret is False
        rec = db.get(InstalledPlugin, "demo_hub")
        assert (rec.repo_url, rec.sha, rec.version, rec.enabled) == (URL, SHA1, "1.0.0", True)
        assert rec.installed_by is not None and rec.installed_at is not None
        assert json.loads(rec.manifest)["entry_point"] == "fh_plugin_demo.plugin:DemoPlugin"
        assert TOKEN not in rec.manifest

    listing = client.get("/api/plugins/installed", headers=auth).json()
    assert listing["enabled"] is True and [i["id"] for i in listing["items"]] == ["demo_hub"]
    item = listing["items"][0]
    assert item["short_sha"] == "aaaaaaa" and item["loaded"] is True and item["name"] == "Demo-Plugin"
    assert TOKEN not in json.dumps(listing)

    # protocol: the install is in the admin log
    assert any("Plugin demo_hub 1.0.0 installiert" in e["message"] for e in log_buffer.entries())

    # inspect now says it is installed, current values prefilled, the secret only "set"
    again = inspect(client, auth).json()
    assert again["installed"] == {"version": "1.0.0", "sha": SHA1, "short_sha": "aaaaaaa", "same_sha": True}
    by_key = {s["key"]: s for s in again["settings"]}
    assert by_key["DEMO_HUB_URL"]["value"] == "https://demo.example.org" and by_key["DEMO_HUB_URL"]["is_set"] is True
    assert by_key["DEMO_HUB_TOKEN"]["value"] == "" and by_key["DEMO_HUB_TOKEN"]["is_set"] is True


def test_update_swaps_code_keeps_settings_and_asks_only_for_new_required_ones(client, auth, gh):
    gh.publish(SHA1, repo_files())
    assert install(client, auth).status_code == 200
    routes_with_plugin = len(app.router.routes)

    v2 = manifest_dict(version="1.1.0")
    v2["settings"].append({"key": "DEMO_HUB_ROOM", "label": {"de": "Raum", "en": "Room"}, "required": True})
    gh.publish(SHA2, repo_files(version="1.1.0", manifest=v2))
    info = inspect(client, auth).json()
    assert info["sha"] == SHA2 and info["installed"]["version"] == "1.0.0" and info["installed"]["same_sha"] is False

    # the new required setting is missing: refused before anything is downloaded
    codeload_before = gh.count("codeload.github.com")
    r = install(client, auth, sha=SHA2, settings_={})
    assert r.status_code == 422 and "DEMO_HUB_ROOM" in r.json()["detail"]
    assert gh.count("codeload.github.com") == codeload_before
    assert client.get("/api/plugins/demo_hub/items", headers=auth).json()["version"] == "1.0.0"

    r = install(client, auth, sha=SHA2, settings_={"DEMO_HUB_ROOM": "kitchen"})  # URL and token stay as they were
    assert r.status_code == 200, r.text
    assert r.json()["updated"] is True and r.json()["version"] == "1.1.0"
    live = client.get("/api/plugins/demo_hub/items", headers=auth).json()
    assert live["version"] == "1.1.0" and live["items"][0] == {"url": "https://demo.example.org", "token_set": True}
    assert plugin_registry.get("demo_hub").version == "1.1.0"
    assert len(app.router.routes) == routes_with_plugin  # the old version's routes were replaced, not added to
    base = pathlib.Path(settings.data_dir) / "plugins"
    assert not (base / "src" / f"demo_hub-{SHA1}").exists() and (base / "src" / f"demo_hub-{SHA2}").exists()
    assert [p.name for p in (base / "site").iterdir()] == ["demo_hub"]
    with SessionLocal() as db:
        assert db.get(InstalledPlugin, "demo_hub").sha == SHA2
        assert decrypt(db.get(ConfigOverride, "DEMO_HUB_TOKEN").value) == TOKEN


def test_a_failing_update_leaves_the_old_version_running(client, auth, gh):
    gh.publish(SHA1, repo_files())
    assert install(client, auth).status_code == 200
    broken = plugin_code(version="2.0.0").replace("class DemoPlugin", "raise RuntimeError('boom')\nclass DemoPlugin")
    gh.publish(SHA2, repo_files(version="2.0.0", code=broken))
    r = install(client, auth, sha=SHA2, settings_={})
    assert r.status_code == 422 and "RuntimeError: boom" in r.json()["detail"]
    live = client.get("/api/plugins/demo_hub/items", headers=auth)
    assert live.status_code == 200 and live.json()["version"] == "1.0.0"
    with SessionLocal() as db:
        assert db.get(InstalledPlugin, "demo_hub").sha == SHA1
    base = pathlib.Path(settings.data_dir) / "plugins"
    assert [p.name for p in (base / "site").iterdir()] == ["demo_hub"]
    assert not (base / "src" / f"demo_hub-{SHA2}").exists()


def test_remove_deletes_routes_files_record_and_settings(client, auth, gh):
    gh.publish(SHA1, repo_files())
    assert install(client, auth).status_code == 200
    r = client.delete("/api/plugins/demo_hub", headers=auth)
    assert r.status_code == 200 and r.json() == {"removed": True, "restart_required": False}
    assert client.get("/api/plugins/demo_hub/items", headers=auth).status_code == 404  # route gone at once
    assert plugin_registry.get("demo_hub") is None
    base = pathlib.Path(settings.data_dir) / "plugins"
    assert list((base / "site").iterdir()) == [] and list((base / "src").iterdir()) == []
    with SessionLocal() as db:
        assert db.get(InstalledPlugin, "demo_hub") is None
        assert db.get(ConfigOverride, "DEMO_HUB_URL") is None and db.get(ConfigOverride, "DEMO_HUB_TOKEN") is None
    assert "DEMO_HUB_TOKEN" not in config_store._extra  # noqa: SLF001
    assert any("Plugin demo_hub entfernt" in e["message"] for e in log_buffer.entries())
    assert client.delete("/api/plugins/demo_hub", headers=auth).status_code == 404
    assert client.delete("/api/plugins/Not-An-Id", headers=auth).status_code == 404
    # a reinstall after removal starts clean
    assert install(client, auth).status_code == 200


def test_removing_still_works_when_the_installer_is_off(client, auth, gh, monkeypatch):
    gh.publish(SHA1, repo_files())
    assert install(client, auth).status_code == 200
    monkeypatch.setattr(settings, "plugin_install_enabled", False)
    assert client.delete("/api/plugins/demo_hub", headers=auth).status_code == 200


def test_toggle_keeps_the_record_in_sync(client, auth, gh, monkeypatch):
    monkeypatch.setattr(settings, "plugins_disabled", "")  # restored afterwards
    gh.publish(SHA1, repo_files())
    assert install(client, auth).status_code == 200
    assert client.put("/api/admin/plugins/demo_hub", headers=auth, json={"enabled": False}).status_code == 200
    with SessionLocal() as db:
        assert db.get(InstalledPlugin, "demo_hub").enabled is False
    assert client.get("/api/plugins/installed", headers=auth).json()["items"][0]["active"] is False
    client.put("/api/admin/plugins/demo_hub", headers=auth, json={"enabled": True})
    with SessionLocal() as db:
        assert db.get(InstalledPlugin, "demo_hub").enabled is True


# --- Validation and rollback ---

def test_required_settings_and_values_are_validated_before_download(client, auth, gh):
    gh.publish(SHA1, repo_files())
    for values, text in (({}, "DEMO_HUB_URL"), ({"DEMO_HUB_URL": "not a url"}, "Adresse"),
                         ({"DEMO_HUB_URL": "https://x.example", "OTHER": "1"}, "Unbekannte Einstellung"),
                         ({"DEMO_HUB_URL": "https://x.example\nSECRET_KEY=1"}, "ungültig")):
        r = install(client, auth, settings_=values)
        assert r.status_code == 422 and text in r.json()["detail"], (values, r.text)
    assert gh.count("codeload.github.com") == 0
    with SessionLocal() as db:
        assert db.get(InstalledPlugin, "demo_hub") is None and db.get(ConfigOverride, "DEMO_HUB_URL") is None


def test_install_needs_a_valid_commit_and_a_matching_manifest(client, auth, gh):
    gh.publish(SHA1, repo_files())
    assert client.post("/api/plugins/install", headers=auth, json={"url": URL, "sha": "main", "settings": {}}).status_code == 422
    r = install(client, auth, sha="c" * 40)  # a commit without manifest
    assert r.status_code == 422 and "familienhub-plugin.json" in r.json()["detail"]
    assert gh.count("codeload.github.com") == 0


def test_boolean_number_and_default_values(client, auth, gh):
    m = manifest_dict()
    m["settings"] += [
        {"key": "DEMO_HUB_LIMIT", "label": "Limit", "type": "number", "default": 5, "required": False},
        {"key": "DEMO_HUB_DEBUG", "label": "Debug", "type": "bool", "required": True},
    ]
    gh.publish(SHA1, repo_files(manifest=m))
    r = install(client, auth, settings_={"DEMO_HUB_URL": "https://x.example", "DEMO_HUB_DEBUG": True})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.get(ConfigOverride, "DEMO_HUB_LIMIT").value == "5"
        assert db.get(ConfigOverride, "DEMO_HUB_DEBUG").value == "true"
    with pytest.raises(ValueError, match="keine Zahl"):
        installer.check_settings(validate_manifest(m), {"DEMO_HUB_URL": "https://x.example", "DEMO_HUB_LIMIT": "abc"})


def test_pip_failure_leaves_nothing_behind(client, auth, gh):
    files = repo_files(pyproject='[build-system]\nrequires = []\nbuild-backend = "does_not_exist"\nbackend-path = ["."]\n'
                                  '[project]\nname = "x"\nversion = "1"\n')
    gh.publish(SHA1, files)
    r = install(client, auth)
    assert r.status_code == 422 and "pip" in r.json()["detail"]
    base = pathlib.Path(settings.data_dir) / "plugins"
    assert list((base / "site").iterdir()) == [] and list((base / "src").iterdir()) == [] and list((base / "tmp").iterdir()) == []
    assert plugin_registry.get("demo_hub") is None
    with SessionLocal() as db:
        assert db.get(InstalledPlugin, "demo_hub") is None and db.get(ConfigOverride, "DEMO_HUB_URL") is None


def test_package_folder_must_exist_and_be_a_project(client, auth, gh):
    gh.publish(SHA1, repo_files(manifest=manifest_dict(package="missing/dir")))
    assert "Paketordner" in install(client, auth).json()["detail"]
    files = repo_files()
    del files["pyproject.toml"]
    gh.publish(SHA1, files)
    assert "pyproject.toml" in install(client, auth).json()["detail"]


@pytest.mark.parametrize("name, code_kwargs, message", [
    ("wrong_id", {"code_id": "someone_else"}, "weicht vom Manifest"),
    ("outside_prefix", {"router_path": "/api/auth"}, "liegt nicht unter /api/plugins/demo_hub/"),
    ("extra_setting", {"extra": ', Setting("SECRET_KEY", "Key")'}, "Einstellungen fehlen im Manifest: SECRET_KEY"),
    ("extra_cap", {"caps": 'frozenset({"tasks"})'}, "Fähigkeiten fehlen im Manifest: tasks"),
])
def test_plugin_must_match_its_manifest(client, auth, gh, name, code_kwargs, message):
    routes_before = len(app.router.routes)
    gh.publish(SHA1, repo_files(code=plugin_code(**code_kwargs)))
    r = install(client, auth)
    assert r.status_code == 422 and message in r.json()["detail"], r.text
    assert plugin_registry.get("demo_hub") is None and plugin_registry.get(code_kwargs.get("code_id", "x")) is None
    assert "fh_plugin_demo" not in sys.modules
    assert len(app.router.routes) == routes_before
    base = pathlib.Path(settings.data_dir) / "plugins"
    assert list((base / "site").iterdir()) == []
    with SessionLocal() as db:
        assert db.get(InstalledPlugin, "demo_hub") is None


def test_module_name_must_not_shadow_the_hub(client, auth, gh):
    m = manifest_dict(entry_point="app.plugin:DemoPlugin")
    gh.publish(SHA1, repo_files(manifest=m))
    assert "schon belegt" in install(client, auth).json()["detail"]
    m = manifest_dict(entry_point="json.plugin:DemoPlugin")
    gh.publish(SHA1, repo_files(manifest=m))
    assert "schon belegt" in install(client, auth).json()["detail"]


def test_an_installed_id_cannot_be_taken_over_from_another_repository(client, auth, gh):
    gh.publish(SHA1, repo_files())
    assert install(client, auth).status_code == 200
    r = client.post("/api/plugins/inspect", headers=auth, json={"url": "https://github.com/evil/demo"})
    assert r.status_code == 422 and "anderen Repository" in r.json()["detail"]
    r = install(client, auth, url="https://github.com/evil/demo")
    assert r.status_code == 422 and gh.count("codeload.github.com") == 1  # only the first install downloaded


def test_a_plugin_cannot_claim_settings_of_another(client, auth, gh):
    m = manifest_dict()
    m["settings"].append({"key": "DEMO_HUB_EXTRA_URL", "label": "Extra", "required": False})
    gh.publish(SHA1, repo_files(manifest=m))
    assert install(client, auth).status_code == 200
    # key belonging to another plugin's id is refused by the prefix rule
    wrong = manifest_dict("other_demo")
    wrong["settings"] = [{"key": "DEMO_HUB_URL", "label": "x"}]
    with pytest.raises(ValueError, match="muss mit OTHER_DEMO_ beginnen"):
        validate_manifest(wrong)
    # "demo_hub_extra" would own DEMO_HUB_EXTRA_*, which demo_hub already declares: refused
    clash = manifest_dict("demo_hub_extra")
    clash["settings"] = [{"key": "DEMO_HUB_EXTRA_URL", "label": "x"}]
    with SessionLocal() as db, pytest.raises(installer.InstallError, match="kollidieren.*DEMO_HUB_EXTRA_URL"):
        installer.check_installable(validate_manifest(clash), "https://github.com/acme/other", db)


# --- Start-up, mounting ---

def test_startup_loads_installed_plugins_and_skips_broken_ones(client, auth, gh):
    gh.publish(SHA1, repo_files())
    assert install(client, auth).status_code == 200
    # simulate a restart: nothing in memory, everything on disk and in the database
    installer.unload_plugin(app, "demo_hub")
    assert client.get("/api/plugins/demo_hub/items", headers=auth).status_code == 404
    routes_without = len(app.router.routes)
    installer.load_installed(app)
    assert client.get("/api/plugins/demo_hub/items", headers=auth).json()["status"] == "ok"
    routes_with = len(app.router.routes)
    assert routes_with == routes_without + 1
    installer.load_installed(app)  # idempotent
    assert len(app.router.routes) == routes_with

    # files vanished (e.g. no persistent volume): logged, skipped, visible in the list; the hub keeps running
    installer.unload_plugin(app, "demo_hub")
    shutil.rmtree(pathlib.Path(settings.data_dir) / "plugins" / "site" / "demo_hub")
    installer.load_installed(app)
    item = client.get("/api/plugins/installed", headers=auth).json()["items"][0]
    assert item["loaded"] is False and "fehlen" in item["error"]
    en = client.get("/api/plugins/installed", headers={**auth, "X-App-Language": "en"}).json()["items"][0]
    assert "missing" in en["error"]
    assert client.get("/api/health").status_code == 200
    # reinstalling the same commit repairs it
    assert install(client, auth, settings_={}).status_code == 200
    assert client.get("/api/plugins/installed", headers=auth).json()["items"][0]["error"] is None


def test_a_plugin_that_cannot_be_imported_at_startup_is_skipped(client, auth, gh):
    gh.publish(SHA1, repo_files())
    assert install(client, auth).status_code == 200
    installer.unload_plugin(app, "demo_hub")
    (pathlib.Path(settings.data_dir) / "plugins" / "site" / "demo_hub" / "fh_plugin_demo" / "plugin.py").write_text("raise ImportError('gone')")
    installer.load_installed(app)
    item = client.get("/api/plugins/installed", headers=auth).json()["items"][0]
    assert item["loaded"] is False and "ImportError: gone" in item["error"]
    assert plugin_registry.get("demo_hub") is None and "fh_plugin_demo" not in sys.modules


def test_plugin_routes_go_before_the_frontend_catch_all():
    from starlette.staticfiles import StaticFiles

    from app.plugins.base import Plugin

    router = APIRouter(prefix="/api/plugins/zz_demo")

    @router.get("/ping")
    async def ping():
        return {"pong": True}

    class Zz(Plugin):
        def routers(self):
            return [router]

    mini = FastAPI()
    mini.mount("/", StaticFiles(directory=str(pathlib.Path(__file__).parent), html=False), name="frontend")
    # authentication is part of the mount: without a login there is no answer, and no fall-through to the files
    from starlette.testclient import TestClient

    from app.core.security import get_current_user

    mini.dependency_overrides[get_current_user] = lambda: object()
    routes = installer._mount(mini, Zz(id="zz_demo", name="Zz"))  # noqa: SLF001
    from starlette.routing import Mount

    assert mini.router.routes.index(routes[0]) < next(i for i, r in enumerate(mini.router.routes) if isinstance(r, Mount))
    assert TestClient(mini).get("/api/plugins/zz_demo/ping").json() == {"pong": True}


def test_pip_command_and_build_environment(monkeypatch):
    monkeypatch.setattr(settings, "plugin_pip_args", "--index-url https://pypi.example.org/simple --quiet")
    cmd = installer.pip_command(pathlib.Path("/pkg"), pathlib.Path("/target"))
    assert cmd[1:4] == ["-m", "pip", "install"] and "--no-cache-dir" in cmd
    assert cmd[cmd.index("--target") + 1] == "/target" and cmd[-1] == "/pkg"
    assert "--index-url" in cmd and "https://pypi.example.org/simple" in cmd
    monkeypatch.setenv("SECRET_KEY", "must-not-leak")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/x")
    env = installer._build_env(pathlib.Path("/tmp/x"))  # noqa: SLF001
    assert "SECRET_KEY" not in env and "DATABASE_URL" not in env and env["HOME"] == "/tmp/x"


def test_install_runs_without_a_shell():
    source = (APP_DIR / "plugins" / "installer.py").read_text()
    assert "shell=True" not in source and "os.system" not in source and "create_subprocess_shell" not in source
    assert "create_subprocess_exec" in source


# --- Texts ---

def _german_messages():
    found = {}
    files = [APP_DIR / "plugins" / n for n in ("manifest.py", "github.py", "archive.py", "installer.py")]
    files.append(APP_DIR / "routers" / "plugins.py")
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", getattr(node.func, "attr", ""))
            if name == "HTTPException":
                args = node.args[1:2]
            elif name.endswith("Error") or name == "NotFound":
                args = node.args[:1]
            else:
                continue
            for arg in args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found[arg.value] = path.name
                elif isinstance(arg, ast.JoinedStr):
                    text = "".join(v.value if isinstance(v, ast.Constant) else "X1" for v in arg.values)
                    found[text] = path.name
    return found


def test_every_installer_message_has_an_english_translation():
    messages = _german_messages()
    assert len(messages) > 60
    missing = [f"{where}: {text}" for text, where in messages.items() if translate(text, "en") == text]
    assert not missing, "Add these to app/core/i18n.py EN:\n" + "\n".join(sorted(missing))


def test_capability_labels_and_warnings_are_translated():
    from app.plugins.base import CAPABILITIES

    for label in CAPABILITIES.values():
        assert translate(label, "en") != label, label


def test_untrusted_texts_cannot_override_the_catalog():
    from app.core.i18n import add_runtime_translations

    add_runtime_translations({"Passwort": "Hacked", "Meine Beschriftung": "My label"})
    assert translate("Passwort", "en") == "Password" and translate("Meine Beschriftung", "en") == "My label"


def test_default_compose_keeps_the_data_folder_in_a_volume():
    compose = (APP_DIR.parents[1] / "docker-compose.yml").read_text()
    assert "familienhub_data:/app/data" in compose


def test_env_example_documents_the_switch():
    assert "PLUGIN_INSTALL_ENABLED" in (APP_DIR.parents[1] / ".env.example").read_text()
