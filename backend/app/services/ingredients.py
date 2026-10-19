"""Ingredient lines: parse ("200 g Zwiebeln"), merge equal ingredients, render again.

Used when ingredients of several recipes go onto the shopping list (#70). The rule is *conservative*: two lines only
merge when the normalised ingredient name is equal. Amounts are summed per unit family (count, g/kg, ml/l, EL, TL, Dose
...); families that cannot be converted are listed together ("2 Zwiebeln + 200 g"). A line that cannot be parsed is
never changed; at most it is dropped as an exact duplicate.

Pure functions, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional, Sequence, Tuple

# --- units ---------------------------------------------------------------------------------------------------------

# canonical unit -> spellings (lower case, without trailing dot)
_UNIT_SPELLINGS: Dict[str, Tuple[str, ...]] = {
    "g": ("g", "gr", "gramm"),
    "kg": ("kg", "kilo", "kilogramm"),
    "ml": ("ml", "milliliter"),
    "cl": ("cl", "centiliter"),
    "dl": ("dl", "deziliter"),
    "l": ("l", "liter"),
    "EL": ("el", "essl", "esslöffel", "essloeffel"),
    "TL": ("tl", "teel", "teelöffel", "teeloeffel"),
    "Prise": ("prise", "prisen"),
    "Msp.": ("msp", "messerspitze", "messerspitzen"),
    "Dose": ("dose", "dosen"),
    "Bund": ("bund", "bünde", "buende"),
    "Zehe": ("zehe", "zehen"),
    "Packung": ("packung", "packungen", "pck", "pckg", "pkg", "pk", "pkt", "paket", "pakete"),
    "Päckchen": ("päckchen", "paeckchen"),
    "Scheibe": ("scheibe", "scheiben"),
    "Stange": ("stange", "stangen"),
    "Becher": ("becher",),
    "Glas": ("glas", "gläser", "glaeser"),
    "Zweig": ("zweig", "zweige"),
    "Stängel": ("stängel", "staengel"),
    "Stiel": ("stiel", "stiele"),
    "Blatt": ("blatt", "blätter", "blaetter"),
    "Handvoll": ("handvoll", "handvoll"),
    "Tasse": ("tasse", "tassen"),
    "Flasche": ("flasche", "flaschen"),
    "Stück": ("stück", "stueck", "stk", "st", "stücke", "stuecke"),
}
_UNIT_LOOKUP = {s: u for u, spellings in _UNIT_SPELLINGS.items() for s in spellings}
# unit -> (family, factor into the family's base unit). Units without conversion are their own family.
_FAMILY = {"g": ("g", Fraction(1)), "kg": ("g", Fraction(1000)),
           "ml": ("ml", Fraction(1)), "cl": ("ml", Fraction(10)), "dl": ("ml", Fraction(100)), "l": ("ml", Fraction(1000))}
_PLURAL_UNIT = {"Prise": "Prisen", "Dose": "Dosen", "Zehe": "Zehen", "Packung": "Packungen", "Päckchen": "Päckchen",
                "Scheibe": "Scheiben", "Stange": "Stangen", "Glas": "Gläser", "Zweig": "Zweige", "Blatt": "Blätter",
                "Tasse": "Tassen", "Flasche": "Flaschen"}

# --- name normalisation --------------------------------------------------------------------------------------------

# Irregular plural -> singular (the regular "-n" plural is handled by rule).
_IRREGULAR_SINGULAR = {
    "eier": "ei", "äpfel": "apfel", "nüsse": "nuss", "pilze": "pilz", "champignons": "champignon", "kiwis": "kiwi",
    "zucchinis": "zucchini", "mandeln": "mandel", "birnen": "birne", "möhren": "möhre", "tomatos": "tomato",
    "kräuter": "kraut", "brötchen": "brötchen", "paprikas": "paprika", "lauchstangen": "lauchstange",
}
_IRREGULAR_PLURAL = {"ei": "Eier", "apfel": "Äpfel", "nuss": "Nüsse", "pilz": "Pilze", "champignon": "Champignons",
                     "kiwi": "Kiwis", "zucchini": "Zucchini", "paprika": "Paprika"}
# Countable nouns in -el that take "-n" (others such as Fenchel or Kümmel stay as they are).
_EL_NOUNS = ("zwiebel", "kartoffel", "nudel", "semmel", "mandel", "gurkenscheibel")
# Words that look like a plural but are not (singular-looking words ending in -n after e/el/er).
_NOT_PLURAL = {"margarine", "sahne", "kokosmilch"}

# Preparation words: a comma/parenthesis part made only of these does not change the product.
_PREP_WORDS = {
    "fein", "grob", "klein", "in", "scheiben", "würfel", "würfeln", "streifen", "ringe", "ringen", "spalten", "stücke",
    "stücken", "gewürfelt", "geschält", "gerieben", "geraspelt", "zerkleinert", "gewaschen", "geputzt", "frisch",
    "optional", "entkernt", "halbiert", "geviertelt", "geschnitten", "gehobelt", "zimmerwarm", "nach", "belieben",
    "zum", "bestreuen", "braten", "anbraten", "garnieren", "dekorieren", "und", "geschnittene", "gehackt_fein", "etwas",
    "bei", "bedarf", "ca", "je", "nach", "geschmack", "abgetropft", "abgespült", "gepresst", "zerdrückt", "zerrieben",
    "gesiebt", "gesalzen", "weich", "kalt",
}
# Adjectives in front of the noun that do not change the product ("große Zwiebel").
_SIZE_ADJ = re.compile(r"^(gro(ß|ss)e[nrms]?|kleine[nrms]?|mittelgro(ß|ss)e[nrms]?|frische[nrms]?|frisch)\s+", re.I)

# --- amounts -------------------------------------------------------------------------------------------------------

_VULGAR = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8"}
_NUM = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)"
_AMOUNT_RE = re.compile(
    rf"^\s*(?:(?:ca\.?|etwa|ungefähr|circa|zirka|~)\s*)?(?P<lo>{_NUM})(?:\s*(?:-|–|—|bis)\s*(?P<hi>{_NUM}))?\s*",
    re.I)
_ONE_RE = re.compile(r"^\s*(ein|eine|einen|einem|einer)\s+", re.I)
_WORD_RE = re.compile(r"^([A-Za-zÄÖÜäöüß]+)\.?(?=$|[\s,;])")


def _frac(text: str) -> Fraction:
    text = text.strip().replace(",", ".")
    if " " in text:  # "1 1/2"
        whole, rest = text.split(None, 1)
        return Fraction(whole) + Fraction(rest)
    return Fraction(text)


def _prepare(text: str) -> str:
    """Normalise vulgar fractions ("1½" -> "1 1/2"), whitespace and parentheticals."""
    for sign, plain in _VULGAR.items():
        text = re.sub(rf"(\d)\s*{sign}", rf"\1 {plain}", text)
        text = text.replace(sign, plain)
    text = re.sub(r"\(n\)|\(en\)|\(e\)|\(s\)", "", text)  # "Zwiebel(n)"
    text = re.sub(r"\([^)]*\)", " ", text)  # "(400 g)", "(Größe M)"
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Part:
    unit: Optional[str]  # canonical unit or None for a plain count
    lo: Fraction
    hi: Fraction

    def family(self) -> str:
        return _FAMILY[self.unit][0] if self.unit in _FAMILY else (self.unit or "")


@dataclass
class Ingredient:
    key: str  # normalised name used to compare
    singular: str  # display name, singular
    plural: str  # display name, plural
    parts: List[Part] = field(default_factory=list)  # empty: no amount known
    shown: str = ""  # name as written in the line, used after a unit ("3 Dosen Tomaten")


def _singular(word: str) -> str:
    low = word.lower()
    if low in _IRREGULAR_SINGULAR:
        return _IRREGULAR_SINGULAR[low]
    if low in _NOT_PLURAL or len(low) < 5 or not low.endswith("n"):
        return low
    stem = low[:-1]
    if stem.endswith(("e", "el", "er")) and not low.endswith(("ein", "ren")) or low.endswith("eln"):
        return stem
    return low


def _plural_of(word: str) -> str:
    """Plural for a display singular; unknown words stay as they are."""
    low = word.lower()
    if low in _IRREGULAR_PLURAL:
        return _match_case(word, _IRREGULAR_PLURAL[low])
    if (low.endswith("e") or low.endswith(_EL_NOUNS)) and len(low) >= 4 and low not in _NOT_PLURAL:
        return word + "n"
    return word


def _match_case(model: str, text: str) -> str:
    return text[:1].upper() + text[1:] if model[:1].isupper() else text[:1].lower() + text[1:]


def _clean_name(name: str) -> Optional[str]:
    """Drop preparation hints after a comma ("Zwiebel, fein gehackt"); keep product-changing ones."""
    head, _, tail = name.partition(",")
    tail_words = re.findall(r"[a-zäöüß]+", re.sub(r"\b(fein|klein|grob)\s+gehackte?", r"\1", tail.lower()))
    if tail and tail_words and all(w in _PREP_WORDS for w in tail_words):
        name = head
    elif tail and not tail_words:
        name = head
    name = _SIZE_ADJ.sub("", name.strip())
    name = re.sub(r"\s+", " ", name).strip(" ,;.-")
    return name or None


def _name_forms(name: str) -> Tuple[str, str, str]:
    """(key, singular display, plural display). Only the last word takes the plural."""
    words = name.split(" ")
    last = words[-1]
    sing_low = _singular(last)
    plural_given = sing_low != last.lower()
    sing_disp = _match_case(last, sing_low)
    plural_disp = last if plural_given else _plural_of(last)
    head = " ".join(words[:-1])
    join = lambda tail: (head + " " + tail).strip()  # noqa: E731
    key = join(sing_low).lower()
    return key, join(sing_disp), join(plural_disp)


def _take_unit(rest: str) -> Tuple[Optional[str], str]:
    m = _WORD_RE.match(rest)
    if not m:
        # "200g" and "1EL" are handled by the caller (digits glued to letters); other text has no unit.
        return None, rest
    word = m.group(1)
    unit = _UNIT_LOOKUP.get(word.lower())
    if unit is None or (len(word) == 1 and word not in ("g", "l")) or word in ("St", "Pk"):
        return None, rest
    return unit, rest[m.end():].lstrip(" ,;")


def _unit_from_compound(name: str) -> Tuple[Optional[str], str]:
    """"Knoblauchzehen" -> (Zehe, "Knoblauch"); "Knoblauchzehe" as well."""
    m = re.match(r"^(?P<head>[A-Za-zÄÖÜäöüß]{3,}?)zehen?$", name)
    return ("Zehe", m.group("head")) if m else (None, name)


def parse_line(text: str) -> Optional[Ingredient]:
    """Parse one ingredient line, or None when it is empty. Lines without a recognisable amount get no parts."""
    text = _prepare(text or "")
    if not text:
        return None
    parts: List[Part] = []
    rest = text
    m = _AMOUNT_RE.match(text)
    if m:
        lo = _frac(m.group("lo"))
        hi = _frac(m.group("hi")) if m.group("hi") else lo
        if hi < lo:
            lo, hi = hi, lo
        rest = text[m.end():]
        if rest and not rest[:1].isalpha():
            return _unparsed(text)  # "3-Minuten-Ei": numbers that are no amount
        unit, rest = _take_unit(rest)
        parts.append(Part(None if unit == "Stück" else unit, lo, hi))
        if unit is None:
            stueck, after = _take_unit(rest)  # "2 Stück Zwiebeln" handled above; keep symmetrical
            if stueck == "Stück":
                rest = after
    else:
        one = _ONE_RE.match(text)
        if one:
            unit, after = _take_unit(text[one.end():])
            if unit is not None:
                parts.append(Part(None if unit == "Stück" else unit, Fraction(1), Fraction(1)))
                rest = after
    name = _clean_name(rest) if rest else None
    if name is None:
        return Ingredient("", "", "", parts) if parts else _unparsed(text)
    if parts and parts[0].unit is None:
        zehe, head = _unit_from_compound(name)
        if zehe:
            parts[0].unit, name = zehe, head
    key, sing, plural = _name_forms(name)
    return Ingredient(key, sing, plural, parts, shown=name)


def _unparsed(text: str) -> Ingredient:
    key, sing, plural = _name_forms(text)
    return Ingredient(key, sing, plural, [])


def parse_summary(text: str) -> Optional[Ingredient]:
    """Parse a list entry that may be a merged one ("2 Zwiebeln + 200 g"). None when not understood."""
    pieces = [p.strip() for p in re.split(r"\s+\+\s+", text or "")]
    first = parse_line(pieces[0]) if pieces else None
    if first is None or len(pieces) == 1:
        return first
    if not first.key:
        return None
    for piece in pieces[1:]:
        extra = _parse_amount_only(piece)
        if extra is None:
            return None
        first.parts.append(extra)
    return first


def _parse_amount_only(text: str) -> Optional[Part]:
    text = _prepare(text)
    m = _AMOUNT_RE.match(text)
    if not m:
        return None
    rest = text[m.end():]
    unit, after = _take_unit(rest)
    if rest and unit is None or after:
        return None
    lo = _frac(m.group("lo"))
    hi = _frac(m.group("hi")) if m.group("hi") else lo
    return Part(unit, lo, hi)


# --- merging -------------------------------------------------------------------------------------------------------


def merge(a: Ingredient, b: Ingredient) -> Optional[Ingredient]:
    """Merge two ingredients with the same name, or None when they must stay separate."""
    if not a.key or a.key != b.key:
        return None
    if not a.parts or not b.parts:
        # "Salz" next to "1 Prise Salz": the bare line has no quantity to add, the amount one wins.
        winner = a if a.parts else b
        return Ingredient(winner.key, winner.singular, winner.plural, [Part(p.unit, p.lo, p.hi) for p in winner.parts],
                          winner.shown)
    totals: Dict[str, Part] = {}
    order: List[str] = []
    for part in a.parts + b.parts:
        if part.unit in _FAMILY:
            fam, factor = _FAMILY[part.unit]
            base = Part(fam, part.lo * factor, part.hi * factor)
        else:
            fam, base = part.unit or "", Part(part.unit, part.lo, part.hi)
        if fam in totals:
            totals[fam].lo += base.lo
            totals[fam].hi += base.hi
        else:
            totals[fam] = base
            order.append(fam)
    return Ingredient(a.key, a.singular, a.plural, [totals[f] for f in order], a.shown or b.shown)


# --- rendering -----------------------------------------------------------------------------------------------------


def _num(value: Fraction) -> str:
    whole, rem = divmod(value, 1)
    glyph = {Fraction(1, 2): "½", Fraction(1, 4): "¼", Fraction(3, 4): "¾"}.get(rem)
    if rem == 0:
        return str(int(whole))
    if glyph:
        return f"{int(whole)}{glyph}" if whole else glyph
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _amount(part: Part) -> Tuple[str, bool]:
    """Amount text and whether it means more than one."""
    lo, hi, unit = part.lo, part.hi, part.unit
    if unit in ("g", "ml") and hi >= 1000:  # back to kg / l
        lo, hi, unit = lo / 1000, hi / 1000, "kg" if unit == "g" else "l"
    text = _num(lo) if lo == hi else f"{_num(lo)}-{_num(hi)}"
    return text, hi > 1


def _unit_text(unit: Optional[str], many: bool) -> str:
    if not unit:
        return ""
    return _PLURAL_UNIT.get(unit, unit) if many else unit


def render(ing: Ingredient) -> str:
    """Text for the list: "2 Zwiebeln", "400 g Mehl", "2 Zwiebeln + 200 g"."""
    if not ing.parts:
        return ing.singular
    parts = sorted(ing.parts, key=lambda p: p.unit is not None)  # plain count first, it carries the name
    chunks: List[str] = []
    for i, part in enumerate(parts):
        amount, many = _amount(part)
        unit = _unit_text(_display_unit(part), many)
        if i == 0:
            if part.unit is None:
                name = ing.plural if many else ing.singular
            else:
                name = ing.shown or ing.singular
            chunks.append(" ".join(x for x in (amount, unit, name) if x))
        else:
            chunks.append(" ".join(x for x in (amount, unit) if x))
    return " + ".join(chunks)


def _display_unit(part: Part) -> Optional[str]:
    if part.unit in ("g", "ml") and part.hi >= 1000:
        return "kg" if part.unit == "g" else "l"
    return part.unit


# --- merging into a list -------------------------------------------------------------------------------------------


@dataclass
class OpenItem:
    uid: str
    summary: str
    recipes: List[str] = field(default_factory=list)


@dataclass
class Op:
    """A change for the list: ``uid`` set -> replace the entry, None -> add a new one."""

    summary: str
    recipes: List[str]
    uid: Optional[str] = None
    changed_text: bool = False
    absorbed: List[Tuple[str, str]] = field(default_factory=list)  # (raw line, recipe) merged into this op


def plan_merge(existing: Sequence[OpenItem], new: Sequence[Tuple[str, str]]) -> Tuple[List[Op], int]:
    """Merge ``new`` lines ``(raw line, recipe name)`` into the open list entries.

    Returns the operations and how many lines were taken in. A recipe that already stands on an entry (its name is in
    the entry's recipes from before this call) is not added again, so pressing the button twice never doubles amounts.
    """
    slots: List[dict] = []
    for item in existing:
        slots.append({"op": Op(item.summary, list(item.recipes), uid=item.uid), "ing": parse_summary(item.summary),
                      "before": set(item.recipes), "raw": item.summary})
    handled = 0
    for raw, recipe in new:
        raw = raw.strip()
        ing = parse_line(raw)
        if not raw:
            continue
        match = None
        if ing is not None and ing.key:
            match = next((s for s in slots if s["ing"] is not None and s["ing"].key == ing.key), None)
        if match is None:
            same_text = next((s for s in slots if s["raw"].lower() == raw.lower()), None)  # unparsable duplicates
            match = same_text
        if match is None:
            op = Op(raw, [recipe] if recipe else [])
            slots.append({"op": op, "ing": ing, "before": set(), "raw": raw})
            handled += 1
            continue
        op: Op = match["op"]
        if recipe and recipe in match["before"]:
            continue  # this recipe's ingredient is already on the list
        merged = merge(match["ing"], ing) if ing is not None and match["ing"] is not None else None
        if merged is None and match["raw"].lower() != raw.lower():
            # same key but no merge possible cannot happen for parsed lines; unparsable lines stay separate
            op = Op(raw, [recipe] if recipe else [])
            slots.append({"op": op, "ing": ing, "before": set(), "raw": raw})
            handled += 1
            continue
        if merged is not None and merged.parts:
            text = render(merged)
            if text != op.summary:
                op.summary, op.changed_text = text, True
            match["ing"] = merged
        if recipe and recipe not in op.recipes:
            op.recipes.append(recipe)
        op.absorbed.append((raw, recipe))
        handled += 1
    ops = [s["op"] for s in slots
           if s["op"].uid is None or s["op"].absorbed]
    return ops, handled


# --- read-only lists (Cookidoo's own list via Home Assistant) ------------------------------------------------------

MERGED_PREFIX = "m~"  # uid of a merged row: "m~<uid1>~<uid2>…"; ticking it ticks every entry behind it


def merged_uids(uid: str) -> List[str]:
    """The entries behind a merged row (or just ``uid``)."""
    if uid.startswith(MERGED_PREFIX):
        return [u for u in uid[len(MERGED_PREFIX):].split("~") if u]
    return [uid]


def merge_open_items(items: Sequence[Dict]) -> List[Dict]:
    """Show equal open entries of a list we cannot rewrite as one row ("Butter" 50 g + 40 g → "90 g Butter").

    Entries are Home Assistant to-do items (``summary``, ``description`` = amount, ``uid``, ``status``). Done and
    unparsable entries stay as they are; the merged row lists every uid behind it (see ``merged_uids``).
    """
    out: List[Dict] = []
    groups: Dict[str, Dict] = {}
    for item in items:
        if item.get("status") != "needs_action" or not item.get("uid"):
            out.append(item)
            continue
        text = " ".join(x for x in ((item.get("description") or "").strip(), (item.get("summary") or "").strip()) if x)
        ing = parse_line(text)
        if ing is None or not ing.key:
            out.append(item)
            continue
        group = groups.get(ing.key)
        merged = merge(group["ing"], ing) if group else None
        if group and merged is not None:
            group["ing"] = merged
            group["uids"].append(item["uid"])
            continue
        if group:  # same name, but cannot be merged: keep it on its own
            out.append(item)
            continue
        groups[ing.key] = {"ing": ing, "uids": [item["uid"]], "row": dict(item)}
        out.append(groups[ing.key]["row"])
    for group in groups.values():
        if len(group["uids"]) > 1:
            group["row"].update(uid=MERGED_PREFIX + "~".join(group["uids"]), summary=render(group["ing"]),
                                description=None, merged=len(group["uids"]))
    return out
