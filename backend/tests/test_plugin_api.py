"""proxy_image: images from an internal server through a plugin route (mocked server)."""

import httpx
import pytest
import respx
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient

from app.plugins.api import proxy_image, sniff_image_type

SRC = "http://immich.internal:2283/api/assets/abc/thumbnail"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64


@pytest.fixture
def api():
    app = FastAPI()
    router = APIRouter(prefix="/api/plugins/photos")

    @router.get("/img")
    async def img(request: Request, big: int = 0, types: int = 0, verify_key: int = 0):
        kwargs = {"max_bytes": 100} if big else {}
        if types:
            kwargs["allowed_types"] = ("image/png",)
        return await proxy_image(SRC, {"x-api-key": "SECRET-KEY"}, request=request, **kwargs)

    app.include_router(router)
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        yield TestClient(app), http


def test_magic_bytes():
    assert sniff_image_type(JPEG) == "image/jpeg" and sniff_image_type(PNG) == "image/png"
    assert sniff_image_type(WEBP) == "image/webp" and sniff_image_type(b"GIF89a....") == "image/gif"
    assert sniff_image_type(b"<html>") is None and sniff_image_type(b"") is None


@pytest.mark.parametrize("body,media", [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp")])
def test_serves_image_with_cache_headers_and_key_stays_server_side(api, body, media):
    client, http = api
    route = http.get(SRC).mock(return_value=httpx.Response(200, content=body, headers={"content-type": "text/plain"}))
    r = client.get("/api/plugins/photos/img")
    assert r.status_code == 200 and r.content == body
    assert r.headers["content-type"] == media  # sniffed, not what the server claimed
    assert r.headers["cache-control"] == "private, max-age=86400" and r.headers["x-content-type-options"] == "nosniff"
    assert route.calls.last.request.headers["x-api-key"] == "SECRET-KEY"
    assert "SECRET-KEY" not in str(r.headers) and "immich" not in str(r.headers)


def test_etag_gives_304(api):
    client, http = api
    http.get(SRC).mock(return_value=httpx.Response(200, content=JPEG))
    first = client.get("/api/plugins/photos/img")
    again = client.get("/api/plugins/photos/img", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.content == b""


def test_html_disguised_as_image_is_refused(api):
    client, http = api
    http.get(SRC).mock(return_value=httpx.Response(200, content=b"<html><script>x</script></html>",
                                                   headers={"content-type": "image/jpeg"}))
    assert client.get("/api/plugins/photos/img").status_code == 415


def test_type_not_allowed(api):
    client, http = api
    http.get(SRC).mock(return_value=httpx.Response(200, content=JPEG))
    assert client.get("/api/plugins/photos/img", params={"types": 1}).status_code == 415


def test_size_limit_declared_and_streamed(api):
    client, http = api
    http.get(SRC).mock(return_value=httpx.Response(200, content=JPEG + b"\x00" * 500))
    assert client.get("/api/plugins/photos/img", params={"big": 1}).status_code == 413
    assert client.get("/api/plugins/photos/img").status_code == 200


@pytest.mark.parametrize("upstream,expected", [(404, 404), (401, 502), (500, 502)])
def test_upstream_errors(api, upstream, expected):
    client, http = api
    http.get(SRC).mock(return_value=httpx.Response(upstream))
    r = client.get("/api/plugins/photos/img")
    assert r.status_code == expected
    assert "immich" not in r.text and "SECRET" not in r.text


def test_unreachable_and_timeout_and_redirect(api):
    client, http = api
    route = http.get(SRC)
    route.mock(side_effect=httpx.ConnectError("boom http://immich.internal SECRET-KEY"))
    r = client.get("/api/plugins/photos/img")
    assert r.status_code == 502 and "SECRET" not in r.text and "immich" not in r.text
    route.mock(side_effect=httpx.ReadTimeout("slow"))
    assert client.get("/api/plugins/photos/img").status_code == 502
    route.mock(return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/"}))
    assert client.get("/api/plugins/photos/img").status_code == 502  # redirects are not followed


def test_only_http_urls():
    import asyncio

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        asyncio.run(proxy_image("file:///etc/passwd"))
    assert exc.value.status_code == 502
