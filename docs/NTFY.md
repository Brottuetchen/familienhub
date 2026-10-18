# Push via ntfy

[ntfy](https://ntfy.sh) delivers real push notifications to phones without a Familienhub app, especially iPhones: a sideloaded iOS app cannot receive Apple push without a paid developer account.

## How it works
- The **admin** enables the `ntfy` plugin under *Administration → Plugins & access*:
  - `NTFY_URL`: the ntfy server, e.g. `https://ntfy.sh` or your own server.
  - `NTFY_TOKEN` (optional): token the hub uses to publish. Needed if the server denies anonymous publishing.
  - `HUB_PUBLIC_URL` (optional): address of the hub that phones can reach. It enables tap-to-open and the reminder buttons (*Done*, *In 1 hr*, *Tomorrow*).
- **Each person** turns on *Notifications via ntfy* under *More → Notifications & devices*:
  - The hub creates a random secret topic (`fh_…`).
  - The person subscribes to it in the ntfy app.
- Every notification goes to the person's devices (Firebase, Web Push) **and** to their ntfy topic. Quiet hours and category switches apply as usual.
- The server address is set only by the admin, so nobody can make the hub send requests to arbitrary addresses. The publish token never leaves the server.

## Privacy
- **The topic is the password.** Anyone who knows it can read the messages if the server allows reading it. *New topic* replaces a leaked topic.
- On the public `ntfy.sh`, title and text pass through a third-party server. A self-hosted ntfy is recommended.
- Reminder buttons contain a short-lived token signed by the hub. It is valid only for that one reminder and person.

## Self-hosted ntfy with `auth-default-access: deny-all`
Let the hub publish, let anyone read only the secret `fh_*` topics:

```sh
ntfy user add familienhub                      # publisher account
ntfy access familienhub 'fh_*' write-only
ntfy token add familienhub                      # → NTFY_TOKEN
ntfy access everyone 'fh_*' read-only           # subscribe by secret topic, no account per person
```

For instant delivery on iOS, set `upstream-base-url: "https://ntfy.sh"` in the server config. The iOS app must use exactly the server's `base-url`.
