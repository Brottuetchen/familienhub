#!/usr/bin/env python3
"""Validate the ARB translation files (Python stdlib only).

Fails on: invalid JSON, duplicate keys, keys that are missing from the template, placeholder
mismatches against the template, and a wrong or missing ``@@locale``. Missing *translations* are
allowed (the generated code falls back to the template), they are only reported as a summary.

Usage: python tools/check_arb.py [arb_dir]     (default: app/lib/l10n)
       python tools/check_arb.py --self-test
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

TEMPLATE = "app_de.arb"


def _load(path: Path, errors: list[str]):
    dups: list[str] = []

    def hook(pairs):
        seen, out = set(), {}
        for k, v in pairs:
            if k in seen:
                dups.append(k)
            seen.add(k)
            out[k] = v
        return out

    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=hook)
    except (ValueError, OSError) as exc:
        errors.append(f"{path.name}: invalid JSON: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{path.name}: top level must be a JSON object")
        return None
    for k in sorted(set(dups)):
        errors.append(f"{path.name}: duplicate key {k!r}")
    return data


def _used(message: str, declared) -> set[str]:
    return {n for n in declared if re.search(r"\{\s*" + re.escape(n) + r"\s*[,}]", message)}


def check(arb_dir: Path) -> tuple[list[str], str]:
    errors: list[str] = []
    template = _load(arb_dir / TEMPLATE, errors)
    if template is None:
        return errors, ""
    tkeys = {k for k in template if not k.startswith("@")}
    meta = {k[1:]: v for k, v in template.items() if k.startswith("@") and not k.startswith("@@")}
    for k in meta:
        if k not in tkeys:
            errors.append(f"{TEMPLATE}: metadata @{k} has no message")
    declared = {k: set((m.get("placeholders") or {})) for k, m in meta.items() if isinstance(m, dict)}
    for k in tkeys:
        if isinstance(template[k], str) and k in declared or not isinstance(template[k], str):
            continue
        if re.search(r"\{\s*\w+\s*[,}]", template[k]):
            errors.append(f"{TEMPLATE}: {k!r} uses placeholders but has no @{k} metadata")
    summary = []
    for path in sorted(arb_dir.glob("app_*.arb")):
        if path.name == TEMPLATE:
            continue
        data = _load(path, errors)
        if data is None:
            continue
        code = path.stem[len("app_"):]
        loc = data.get("@@locale")
        if loc is not None and loc != code:
            errors.append(f"{path.name}: @@locale is {loc!r}, expected {code!r}")
        keys = {k for k in data if not k.startswith("@")}
        if "languageName" not in keys:
            errors.append(f"{path.name}: 'languageName' (the language's own name) is required for the picker")
        for k in sorted(keys - tkeys):
            errors.append(f"{path.name}: key {k!r} does not exist in {TEMPLATE}")
        for k in sorted(k[1:] for k in data if k.startswith("@") and not k.startswith("@@")):
            if k not in tkeys:
                errors.append(f"{path.name}: metadata @{k} does not exist in {TEMPLATE}")
            elif isinstance(data["@" + k], dict) and "placeholders" in data["@" + k]:
                if set(data["@" + k]["placeholders"] or {}) != declared.get(k, set()):
                    errors.append(f"{path.name}: placeholder metadata of @{k} differs from the template")
        for k in sorted(keys & tkeys):
            if not isinstance(data[k], str):
                errors.append(f"{path.name}: {k!r} must be a string")
                continue
            names = declared.get(k, set())
            if _used(data[k], names) != _used(template[k], names):
                errors.append(
                    f"{path.name}: {k!r} placeholders {sorted(_used(data[k], names))} "
                    f"!= template {sorted(_used(template[k], names))}"
                )
        summary.append(f"{code}: {len(keys & tkeys)}/{len(tkeys)} translated")
    return errors, ", ".join(summary)


def self_test() -> int:
    def run(files: dict[str, str]):
        with tempfile.TemporaryDirectory() as d:
            for name, text in files.items():
                (Path(d) / name).write_text(text, encoding="utf-8")
            return check(Path(d))[0]

    base = '{"@@locale":"de","languageName":"Deutsch","hi":"Hallo {name}","@hi":{"placeholders":{"name":{}}},"bye":"Tschüss"}'
    cases = [
        ("ok", {"app_de.arb": base, "app_en.arb": '{"@@locale":"en","languageName":"English","hi":"Hi {name}"}'}, 0),
        ("partial ok", {"app_de.arb": base, "app_fr.arb": '{"languageName":"Fr","bye":"Salut"}'}, 0),
        ("duplicate", {"app_de.arb": '{"a":"1","a":"1"}'}, 1),
        ("bad json", {"app_de.arb": '{"a":'}, 1),
        ("extra key", {"app_de.arb": base, "app_en.arb": '{"languageName":"E","zzz":"x"}'}, 1),
        ("placeholder", {"app_de.arb": base, "app_en.arb": '{"languageName":"E","hi":"Hi"}'}, 1),
        ("no languageName", {"app_de.arb": base, "app_en.arb": '{"bye":"x"}'}, 1),
        ("locale", {"app_de.arb": base, "app_en.arb": '{"@@locale":"fr","languageName":"F"}'}, 1),
    ]
    bad = 0
    for name, files, want in cases:
        got = len(run(files))
        if bool(got) != bool(want):
            print(f"self-test FAILED: {name} (errors={got})")
            bad += 1
    print("self-test ok" if not bad else "self-test failed")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--self-test"]:
        return self_test()
    arb_dir = Path(argv[0]) if argv else Path(__file__).resolve().parents[1] / "app/lib/l10n"
    errors, summary = check(arb_dir)
    for e in errors:
        print("ERROR", e)
    if errors:
        print(f"{len(errors)} problem(s) found")
        return 1
    print(f"ARB files ok ({summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
