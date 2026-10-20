# Home Assistant sidebar (ingress) and sub-paths

Familienhub can run below a path prefix. This is what makes the Home Assistant add-on appear in the sidebar
(**ingress**), and it also works behind any reverse proxy that serves the hub under a path such as `/hub`.

Direct access on the port (`http://<host>:8000`) is not affected and keeps working as before.

## How it works

Home Assistant proxies `/api/hassio_ingress/<token>/...` to the add-on, **strips that prefix** and tells the add-on
the original one in the `X-Ingress-Path` header. Requests arrive only from Home Assistant's ingress gateway
(`172.30.32.2`). The hub therefore routes as usual and uses the prefix only where it writes absolute URLs:

| What | Under a prefix |
|---|---|
| `index.html` | `<base href="<prefix>/">`; the Flutter assets and `push-sw.js` are relative to it |
| Web app to API | the app takes its server address from the page's base URL, so `/api/...` calls go through the prefix |
| Web manifest | `id`, `start_url`, `scope`, share target and shortcuts move below the prefix |
| Push service worker | registered as `push-sw.js` (relative), its icons and action requests use its own location |
| Login cookies | `Path=<prefix>` instead of `/`, so they are not sent to Home Assistant or other add-ons |
| OIDC web login | redirects back to `<prefix>/` |
| Framing | `X-Frame-Options: SAMEORIGIN` / `frame-ancestors 'self'` so Home Assistant can show the page in its iframe, **only** for requests that came in through the trusted ingress header (everything else stays `DENY`) |

## Where the prefix comes from

1. `X-Ingress-Path`, if `TRUST_INGRESS_HEADER=true`, the connection comes from `INGRESS_PROXY_IPS`
   (default `172.30.32.2`) and the value is exactly `/api/hassio_ingress/<token>` (letters, digits, `-`, `_`).
2. Otherwise `ROOT_PATH` (for example `/hub`; plain path segments only, no trailing slash).
3. Otherwise no prefix.

The value is written into HTML, so anything else (a scheme or host, quotes, `<`, `..`, extra segments) is ignored.
`TRUST_INGRESS_HEADER` is **off by default**: a hub that is reachable directly never lets a client choose the
prefix. The add-on switches it on; because of the peer check it stays harmless even when port 8000 is also exposed.

## Home Assistant add-on

The add-on enables `ingress: true` (port 8000, `panel_icon`, `panel_title`) and sets `TRUST_INGRESS_HEADER=true`.
Then **Familienhub** appears in the sidebar.

Home Assistant authenticates *you* at the panel, but Familienhub keeps its own accounts: log in to Familienhub
once inside the panel (the session is stored in the browser and kept like on any other address). The port-8000
address and the Android/iOS app continue to work with the same accounts.

Notes:

- Use the HTTPS address of Home Assistant if you use it that way; `SECURE_COOKIES=true` then also works in the panel.
- Web push needs a secure context; it works in the panel only when Home Assistant itself is opened over HTTPS.
- Links that the hub puts into notifications (`HUB_PUBLIC_URL`) should point to an address that works outside of
  Home Assistant, such as the port-8000 address.

## Other reverse proxies

Serve the hub below a path, strip the prefix before forwarding and set `ROOT_PATH` to that prefix:

```nginx
location /hub/ { proxy_pass http://familienhub:8000/; }   # strips /hub
```

```env
ROOT_PATH=/hub
```
