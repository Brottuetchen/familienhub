"""``min_hub_version`` of plugins and store entries: pre-releases are compared, not ignored."""

import pytest

from app.plugins.manifest import hub_version_ok


@pytest.mark.parametrize("need, have, ok", [
    ("1.0.0-beta.3", "1.0.0-beta.2", False),   # the release without the calendar hook
    ("1.0.0-beta.3", "1.0.0-beta.3", True),
    ("1.0.0-beta.3", "1.0.0-beta.10", True),
    ("1.0.0-beta.3", "1.0.0-rc.1", True),
    ("1.0.0-beta.3", "1.0.0", True),
    ("1.0.0-beta.3", "1.0.1-beta.1", True),
    ("1.0.0-beta.3", "0.9.0", False),
    ("1.0.0-beta.3", "1.0.0-edge+412", True),   # edge builds come from main
    ("1.0.0", "1.0.0-beta.9", False),
    ("1.0.0", "1.0.0", True),
    ("1.0.0", "1.0.0-edge+412", True),
    ("1.2.0", "1.1.9", False),
    ("1.0.0-beta.3", "dev", True),               # not a number: the check is skipped
    ("", "1.0.0", True),
])
def test_min_hub_version(need, have, ok):
    assert hub_version_ok(need, have) is ok
