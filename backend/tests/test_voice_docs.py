"""docs/voice-assistant.md: the Home Assistant YAML is valid and wired to endpoints that exist (#21)."""

import pathlib
import re

import pytest
import yaml

from app.main import app
from app.services.voice_time import parse_when

DOC = pathlib.Path(__file__).resolve().parents[2] / "docs" / "voice-assistant.md"


class _HaLoader(yaml.SafeLoader):
    """Home Assistant's own YAML tag."""


_HaLoader.add_constructor("!secret", lambda loader, node: f"<secret:{loader.construct_scalar(node)}>")


def _blocks():
    """{file name from the first comment line: parsed yaml}"""
    out = {}
    for body in re.findall(r"```yaml\n(.*?)```", DOC.read_text(), re.S):
        first = body.splitlines()[0]
        assert first.startswith("# "), f"every yaml block starts with a '# file' comment: {first!r}"
        out[first[2:].strip()] = yaml.load(body, Loader=_HaLoader)  # raises on invalid YAML
    return out


def test_all_yaml_blocks_parse():
    blocks = _blocks()
    assert set(blocks) == {"secrets.yaml", "configuration.yaml", "custom_sentences/en/familienhub.yaml",
                           "custom_sentences/de/familienhub.yaml"}


def test_secret_is_used_and_no_real_token_or_domain_in_the_doc():
    text = DOC.read_text()
    cfg = _blocks()["configuration.yaml"]
    for cmd in cfg["rest_command"].values():
        assert cmd["headers"]["authorization"] == "<secret:familienhub_auth>"
    assert re.search(r"fhp_[A-Za-z0-9_-]{20,}", text) is None
    hosts = set(re.findall(r"https://([a-z0-9.-]+)", text))
    assert hosts == {"hub.example.org"}


def _routes():
    return {(m.upper(), path) for path, ops in app.openapi()["paths"].items() for m in ops}


def test_rest_commands_call_existing_voice_endpoints():
    routes = _routes()
    for name, cmd in _blocks()["configuration.yaml"]["rest_command"].items():
        path = re.sub(r"^https://hub\.example\.org", "", cmd["url"]).split("?")[0]
        assert (cmd["method"].upper(), path) in routes, f"{name}: {cmd['method']} {path}"
        assert path.startswith("/api/voice/")


def test_intents_sentences_and_scripts_belong_together():
    cfg = _blocks()["configuration.yaml"]
    scripts, commands = cfg["intent_script"], cfg["rest_command"]
    for lang in ("en", "de"):
        doc = _blocks()[f"custom_sentences/{lang}/familienhub.yaml"]
        assert doc["language"] == lang
        assert set(doc["intents"]) == set(scripts), lang
        for intent, spec in doc["intents"].items():
            for group in spec["data"]:
                for sentence in group["sentences"]:
                    for slot in re.findall(r"\{(\w+)\}", sentence):
                        assert slot in doc["lists"], f"{lang}/{intent}: slot {slot} has no list"
                    # slots used by a sentence are the variables the script uses
                    used = set(re.findall(r"\{(\w+)\}", sentence))
                    needed = set(re.findall(r"\{\{\s*(\w+)", str(scripts[intent]["action"][0].get("data", {}))))
                    needed -= {"assignee", "day"}  # optional: the script has defaults
                    assert needed <= used, f"{lang}/{intent}: '{sentence}' lacks {needed - used}"
        for lst in doc["lists"].values():
            assert lst.get("wildcard") or lst["values"]
    for intent, script in scripts.items():
        first = script["action"][0]
        assert first["action"].split(".", 1)[1] in commands
        assert script["speech"]["text"] == "{{ action_response.speech }}"


def test_day_lists_map_to_words_the_endpoints_understand():
    for lang, spoken in (("en", {"today", "tomorrow"}), ("de", {"heute", "morgen"})):
        values = _blocks()[f"custom_sentences/{lang}/familienhub.yaml"]["lists"]["day"]["values"]
        assert {v["in"] for v in values} == spoken
        assert {v["out"] for v in values} == {"today", "tomorrow"}


@pytest.mark.parametrize("prefix,spoken", [
    ("at ", "6"), ("at ", "18:30"), ("at ", "18 Uhr"), ("at ", "halb sieben"), ("at ", "6 pm"),
    ("in ", "20 minutes"), ("in ", "20 Minuten"), ("in ", "einer Stunde"), ("in ", "half an hour"),
    ("tomorrow at ", "8"), ("tomorrow at ", "18 Uhr"), ("tomorrow at ", "halb sieben"),
])
def test_what_the_intents_send_is_understood_by_the_time_parser(prefix, spoken):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    assert parse_when(prefix + spoken, datetime(2026, 10, 19, 7, 0, tzinfo=ZoneInfo("Europe/Berlin"))) is not None


def test_prefixes_in_the_doc_are_the_ones_tested_above():
    scripts = _blocks()["configuration.yaml"]["intent_script"]
    sent = {k: v["action"][0]["data"]["when"] for k, v in scripts.items() if "Reminder" in k}
    assert sent == {"FamilienhubReminderAt": "at {{ when }}", "FamilienhubReminderIn": "in {{ when }}",
                    "FamilienhubReminderTomorrow": "tomorrow at {{ when }}"}
