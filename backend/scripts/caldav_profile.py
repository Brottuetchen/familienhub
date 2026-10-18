"""Create an Apple configuration profile (.mobileconfig) for a CalDAV/CardDAV account.

Opening the file on an iPhone, iPad or Mac adds the account to Calendar, Reminders and
(optionally) Contacts. The profile contains no password: the device asks for it while
installing, so the file can be passed around safely. Use an app password where the
server offers one (Nextcloud: Settings → Security → Devices & sessions).

    python -m scripts.caldav_profile --host cloud.example.org --user anna --contacts -o anna.mobileconfig

Standard library only, so it also runs outside the container (python3 caldav_profile.py …).
"""

from __future__ import annotations

import argparse
import plistlib
import sys
import uuid

NEXTCLOUD_DAV = "/remote.php/dav"


def build_profile(host: str, user: str, *, name: str = "Nextcloud", dav_path: str = NEXTCLOUD_DAV,
                  port: int = 443, contacts: bool = False, identifier: str = "familienhub.caldav") -> bytes:
    """Return the profile as XML plist bytes."""
    path = "/" + dav_path.strip("/")
    ssl = port != 80
    payloads = [{
        "PayloadType": "com.apple.caldav.account",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"{identifier}.{user}.caldav",
        "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadDisplayName": f"{name} calendars",
        "CalDAVAccountDescription": name,
        "CalDAVHostName": host,
        "CalDAVPort": port,
        "CalDAVUseSSL": ssl,
        "CalDAVUsername": user,
        "CalDAVPrincipalURL": f"{path}/principals/users/{user}/",
    }]
    if contacts:
        payloads.append({
            "PayloadType": "com.apple.carddav.account",
            "PayloadVersion": 1,
            "PayloadIdentifier": f"{identifier}.{user}.carddav",
            "PayloadUUID": str(uuid.uuid4()).upper(),
            "PayloadDisplayName": f"{name} contacts",
            "CardDAVAccountDescription": name,
            "CardDAVHostName": host,
            "CardDAVPort": port,
            "CardDAVUseSSL": ssl,
            "CardDAVUsername": user,
            "CardDAVPrincipalURL": f"{path}/principals/users/{user}/",
        })
    profile = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"{identifier}.{user}",
        "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadDisplayName": f"{name} ({user})",
        "PayloadDescription": f"Calendars and reminders{' and contacts' if contacts else ''} from {host}. "
                              "The password (app password) is asked for during installation.",
        "PayloadRemovalDisallowed": False,
        "PayloadContent": payloads,
    }
    return plistlib.dumps(profile)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", required=True, help="server name, e.g. cloud.example.org")
    ap.add_argument("--user", required=True, help="user name on the server")
    ap.add_argument("--name", default="Nextcloud", help="account name shown on the device")
    ap.add_argument("--dav-path", default=NEXTCLOUD_DAV, help=f"DAV root path (default {NEXTCLOUD_DAV})")
    ap.add_argument("--port", type=int, default=443)
    ap.add_argument("--contacts", action="store_true", help="also add the address books (CardDAV)")
    ap.add_argument("-o", "--output", help="file to write (default: stdout)")
    args = ap.parse_args(argv)
    data = build_profile(args.host, args.user, name=args.name, dav_path=args.dav_path,
                         port=args.port, contacts=args.contacts)
    if args.output:
        with open(args.output, "wb") as fh:
            fh.write(data)
    else:
        sys.stdout.buffer.write(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
