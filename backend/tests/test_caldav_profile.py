"""Apple configuration profile for CalDAV/CardDAV accounts (scripts/caldav_profile.py)."""

import plistlib

from scripts.caldav_profile import build_profile, main


def test_profile_has_caldav_account_without_password():
    p = plistlib.loads(build_profile("cloud.example.org", "anna"))
    assert p["PayloadType"] == "Configuration"
    (cal,) = p["PayloadContent"]
    assert cal["PayloadType"] == "com.apple.caldav.account"
    assert cal["CalDAVHostName"] == "cloud.example.org" and cal["CalDAVUsername"] == "anna"
    assert cal["CalDAVPrincipalURL"] == "/remote.php/dav/principals/users/anna/"
    assert cal["CalDAVUseSSL"] is True and cal["CalDAVPort"] == 443
    assert not any("Password" in k for payload in p["PayloadContent"] for k in payload)


def test_contacts_and_custom_path(tmp_path):
    out = tmp_path / "anna.mobileconfig"
    assert main(["--host", "dav.example.org", "--user", "anna", "--dav-path", "dav/", "--contacts", "-o", str(out)]) == 0
    p = plistlib.loads(out.read_bytes())
    types = [c["PayloadType"] for c in p["PayloadContent"]]
    assert types == ["com.apple.caldav.account", "com.apple.carddav.account"]
    assert p["PayloadContent"][1]["CardDAVPrincipalURL"] == "/dav/principals/users/anna/"
    assert len({c["PayloadUUID"] for c in p["PayloadContent"]} | {p["PayloadUUID"]}) == 3
