"""Read a schema.org Recipe from a web page (JSON-LD first, microdata as fallback).

`parse_recipe(html, page_url)` is pure and returns a draft in the shape of the hub's recipe request,
or None if the page carries no recipe. Nothing is saved here.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

_DURATION = re.compile(
    r"^P(?:(\d+(?:[.,]\d+)?)W)?(?:(\d+(?:[.,]\d+)?)D)?(?:T(?:(\d+(?:[.,]\d+)?)H)?(?:(\d+(?:[.,]\d+)?)M)?(?:(\d+(?:[.,]\d+)?)S)?)?$",
    re.I)


def parse_duration(value: Any) -> Optional[int]:
    """ISO 8601 duration (PT1H30M, P0DT45M, P1DT2H) to whole minutes; None if unusable or zero."""
    if not isinstance(value, str):
        return None
    m = _DURATION.match(value.strip())
    if not m or not any(m.groups()):
        return None
    w, d, h, mi, s = (float(g.replace(",", ".")) if g else 0.0 for g in m.groups())
    minutes = round(w * 7 * 1440 + d * 1440 + h * 60 + mi + s / 60)
    return minutes if minutes > 0 else None


def _text(value: Any) -> str:
    """Plain text from a string with possible HTML; <br>, <li>, <p> become line breaks."""
    if not isinstance(value, str):
        return ""
    value = re.sub(r"(?i)<\s*(br\s*/?|/p|/li|/div)\s*>", "\n", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = html_lib.unescape(value).replace("\xa0", " ")
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in value.split("\n")]
    return "\n".join(line for line in lines if line)


def _line(value: Any) -> str:
    return " ".join(_text(value).split())


def _types(node: Dict[str, Any]) -> List[str]:
    t = node.get("@type")
    items = t if isinstance(t, list) else [t]
    return [str(i).rsplit("/", 1)[-1].rsplit(":", 1)[-1].lower() for i in items if i]


def _walk(data: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(data, list):
        for item in data:
            yield from _walk(item)
    elif isinstance(data, dict):
        yield data
        for key, value in data.items():
            if key != "@context" and isinstance(value, (list, dict)):
                yield from _walk(value)


def _image(value: Any, base: str) -> Optional[str]:
    if isinstance(value, str):
        url = value.strip()
    elif isinstance(value, list):
        for item in value:
            url = _image(item, base)
            if url:
                return url
        return None
    elif isinstance(value, dict):
        return _image(value.get("url") or value.get("contentUrl") or value.get("@id"), base)
    else:
        return None
    if not url:
        return None
    url = urljoin(base, url)
    return url if url.lower().startswith(("http://", "https://")) and len(url) <= 500 else None


def _servings(value: Any) -> Optional[int]:
    if isinstance(value, list):
        for item in value:
            found = _servings(item)
            if found:
                return found
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        n = int(value)
    elif isinstance(value, str):
        m = re.search(r"\d+", value)
        n = int(m.group()) if m else 0
    else:
        return None
    return n if 1 <= n <= 50 else None


def _steps(value: Any) -> List[str]:
    """Instructions as a flat list; HowToSection headings become their own line."""
    if isinstance(value, str):
        return [line for line in _text(value).split("\n") if line]
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            out.extend(_steps(item))
        return out
    if isinstance(value, dict):
        kinds = _types(value)
        if "howtosection" in kinds or ("itemlistelement" in value and "howtostep" not in kinds):
            out = []
            heading = _line(value.get("name"))
            if heading:
                out.append(heading + ":")
            out.extend(_steps(value.get("itemListElement")))
            return out
        return _steps(value.get("text") or value.get("name") or "")
    return []


def _ingredients(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        line = _line(item if isinstance(item, str) else (item.get("name") if isinstance(item, dict) else ""))
        if line:
            out.append(line[:200])
    return out[:100]


def _keywords(node: Dict[str, Any]) -> Optional[str]:
    parts: List[str] = []
    for key in ("recipeCategory", "keywords"):
        value = node.get(key)
        values = value if isinstance(value, list) else str(value or "").split(",") if value else []
        parts.extend(_line(v) for v in values)
    seen, tags = set(), []
    for p in parts:
        if p and p.lower() not in seen:
            seen.add(p.lower())
            tags.append(p)
    joined = ""
    for t in tags:
        if len(joined) + len(t) + 2 > 200:
            break
        joined = f"{joined}, {t}" if joined else t
    return joined or None


def _from_node(node: Dict[str, Any], page_url: str) -> Optional[Dict[str, Any]]:
    title = _line(node.get("name") or node.get("headline"))
    ingredients = _ingredients(node.get("recipeIngredient") or node.get("ingredients"))
    steps = _steps(node.get("recipeInstructions"))
    if not title or not (ingredients or steps):
        return None
    total = parse_duration(node.get("totalTime"))
    if total is None:
        prep, cook = parse_duration(node.get("prepTime")), parse_duration(node.get("cookTime"))
        total = (prep or 0) + (cook or 0) or None
    description = _text(node.get("description")).replace("\n", " ")
    return {
        "title": title[:200],
        "description": description[:2000] or None,
        "ingredients": ingredients,
        "instructions": "\n".join(steps)[:20000] or None,
        "servings": _servings(node.get("recipeYield")) or 2,
        "prep_minutes": min(total, 6000) if total else None,
        "tags": _keywords(node),
        "source_url": page_url[:500],
        "image_url": _image(node.get("image"), page_url),
    }


class _Scanner(HTMLParser):
    """Collects JSON-LD blocks, og:image and the first microdata Recipe."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.jsonld: List[str] = []
        self.og_image: Optional[str] = None
        self._in_ld = False
        self._buf: List[str] = []
        # microdata: stack of (tag, is_recipe_root, prop_name or None, collected text)
        self._stack: List[List[Any]] = []
        self.micro: Dict[str, List[str]] = {}
        self._has_micro = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "script" and "ld+json" in a.get("type", "").lower():
            self._in_ld, self._buf = True, []
            return
        if tag == "meta" and a.get("property", "").lower() == "og:image" and not self.og_image:
            self.og_image = a.get("content") or None
        void = tag in ("meta", "link", "img", "br", "hr", "input", "source")
        in_recipe = any(e[1] for e in self._stack)
        is_root = "itemscope" in a and a.get("itemtype", "").lower().rstrip("/").endswith("/recipe") and not in_recipe
        prop = a.get("itemprop") if in_recipe else None
        if is_root:
            self._has_micro = True
        value: Optional[str] = None
        if prop:
            if tag == "meta":
                value = a.get("content")
            elif tag in ("img", "source"):
                value = a.get("src")
            elif tag in ("link", "a") and a.get("href") and prop in ("image", "url"):
                value = a.get("href")
            elif tag == "time" and a.get("datetime"):
                value = a.get("datetime")
            elif a.get("content"):
                value = a["content"]
        if prop and value is not None:
            for name in prop.split():
                self.micro.setdefault(name, []).append(value)
        if not void:
            self._stack.append([tag, is_root, prop if (prop and value is None) else None, []])

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_ld:
            self.jsonld.append("".join(self._buf))
            self._in_ld = False
            return
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                _, _, prop, text = self._stack[i]
                del self._stack[i:]
                if prop:
                    joined = "".join(text).strip()
                    if joined:
                        for name in prop.split():
                            self.micro.setdefault(name, []).append(joined)
                break

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self._buf.append(data)
            return
        for entry in self._stack:
            if entry[2]:
                entry[3].append(data)


def _json_blocks(blocks: List[str]) -> Iterable[Any]:
    for raw in blocks:
        raw = raw.strip()
        raw = re.sub(r"^\s*<!--|-->\s*$|^\s*//<!\[CDATA\[|//\]\]>\s*$", "", raw).strip()
        if not raw:
            continue
        try:
            yield json.loads(raw, strict=False)
        except ValueError:
            continue


def _from_microdata(micro: Dict[str, List[str]], page_url: str, og_image: Optional[str]) -> Optional[Dict[str, Any]]:
    node: Dict[str, Any] = {
        "name": (micro.get("name") or [None])[0],
        "description": (micro.get("description") or [None])[0],
        "image": (micro.get("image") or [og_image])[0],
        "recipeIngredient": micro.get("recipeIngredient") or micro.get("ingredients") or [],
        "recipeInstructions": micro.get("recipeInstructions") or [],
        "recipeYield": (micro.get("recipeYield") or [None])[0],
        "totalTime": (micro.get("totalTime") or [None])[0],
        "prepTime": (micro.get("prepTime") or [None])[0],
        "cookTime": (micro.get("cookTime") or [None])[0],
        "recipeCategory": micro.get("recipeCategory") or [],
        "keywords": micro.get("keywords") or [],
    }
    return _from_node(node, page_url)


def parse_recipe(page: str, page_url: str) -> Optional[Dict[str, Any]]:
    scanner = _Scanner()
    try:
        scanner.feed(page)
        scanner.close()
    except Exception:  # noqa: BLE001 - broken markup must never raise into the UI
        pass
    best: Optional[Dict[str, Any]] = None
    for data in _json_blocks(scanner.jsonld):
        for node in _walk(data):
            if "recipe" in _types(node):
                draft = _from_node(node, page_url)
                if draft and (best is None or len(draft["ingredients"]) + len((draft["instructions"] or "")) >
                              len(best["ingredients"]) + len((best["instructions"] or ""))):
                    best = draft
    if best is None and scanner._has_micro:
        best = _from_microdata(scanner.micro, page_url, scanner.og_image and urljoin(page_url, scanner.og_image))
    if best is not None and not best["image_url"] and scanner.og_image:
        best["image_url"] = _image(scanner.og_image, page_url)
    if best is not None and best["image_url"]:
        best["image_url"] = _image(best["image_url"], page_url)
    return best
