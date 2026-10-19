"""Ingredient parser and merge rules (#70): tables of real German lines (Cookidoo/Mealie style)."""

import pytest

from app.services.ingredients import OpenItem, merge, parse_line, parse_summary, plan_merge, render


def _brief(line):
    ing = parse_line(line)
    parts = [(p.unit, str(p.lo), str(p.hi)) for p in ing.parts]
    return ing.key, parts


PARSE = [
    ("200 g Zwiebeln", ("zwiebel", [("g", "200", "200")])),
    ("1 Zwiebel", ("zwiebel", [(None, "1", "1")])),
    ("2 Stück Zwiebeln", ("zwiebel", [(None, "2", "2")])),
    ("1/2 TL Salz", ("salz", [("TL", "1/2", "1/2")])),
    ("½ Bund Petersilie", ("petersilie", [("Bund", "1/2", "1/2")])),
    ("1½ EL Olivenöl", ("olivenöl", [("EL", "3/2", "3/2")])),
    ("1,5 kg Kartoffeln", ("kartoffel", [("kg", "3/2", "3/2")])),
    ("1.5 l Milch", ("milch", [("l", "3/2", "3/2")])),
    ("2-3 Zwiebel(n)", ("zwiebel", [(None, "2", "3")])),
    ("2 – 3 Karotten", ("karotte", [(None, "2", "3")])),
    ("ca. 200g Mehl, fein gesiebt", ("mehl", [("g", "200", "200")])),
    ("500ml Brühe", ("brühe", [("ml", "500", "500")])),
    ("3 Knoblauchzehen", ("knoblauch", [("Zehe", "3", "3")])),
    ("2 Zehen Knoblauch", ("knoblauch", [("Zehe", "2", "2")])),
    ("1 Dose Tomaten (400 g)", ("tomate", [("Dose", "1", "1")])),
    ("1 Pck. Backpulver", ("backpulver", [("Packung", "1", "1")])),
    ("eine Prise Zucker", ("zucker", [("Prise", "1", "1")])),
    ("4 Eier (Größe M)", ("ei", [(None, "4", "4")])),
    ("1 große Zwiebel", ("zwiebel", [(None, "1", "1")])),
    ("Zwiebel, fein gehackt", ("zwiebel", [])),
    ("Salz", ("salz", [])),
    ("Tomaten, gehackt", ("tomaten, gehackt", [])),  # product-changing hint stays in the key
    ("3-Minuten-Ei", ("3-minuten-ei", [])),  # a number that is no amount
]


@pytest.mark.parametrize("line,expected", PARSE)
def test_parse(line, expected):
    assert _brief(line) == expected


def _m(a, b):
    merged = merge(parse_line(a), parse_line(b))
    return render(merged) if merged else None


MERGE = [
    # same unit: sum
    ("1 Zwiebel", "1 Zwiebel", "2 Zwiebeln"),
    ("200 g Zwiebeln", "300 g Zwiebel", "500 g Zwiebeln"),
    ("1 EL Öl", "2 EL Öl", "3 EL Öl"),
    ("1 Dose Tomaten", "2 Dosen Tomaten", "3 Dosen Tomaten"),
    ("1/2 TL Salz", "1/2 TL Salz", "1 TL Salz"),
    ("2-3 Karotten", "1 Karotte", "3-4 Karotten"),
    # convertible units
    ("500 g Mehl", "0,5 kg Mehl", "1 kg Mehl"),
    ("700 g Kartoffeln", "500 g Kartoffeln", "1,2 kg Kartoffeln"),
    ("500 ml Milch", "1 l Milch", "1½ l Milch"),
    ("2 dl Sahne", "100 ml Sahne", "300 ml Sahne"),
    # not convertible: listed together
    ("1 Zwiebel", "200 g Zwiebeln", "1 Zwiebel + 200 g"),
    ("2 Zwiebeln", "200 g Zwiebeln", "2 Zwiebeln + 200 g"),
    ("1 EL Öl", "1 TL Öl", "1 EL Öl + 1 TL"),
    ("2 Zehen Knoblauch", "1 Knolle Knoblauch", None),  # "1 Knolle Knoblauch" has no known unit: name differs
    # bare line next to an amount: the amount wins
    ("Salz", "1 Prise Salz", "1 Prise Salz"),
    # different ingredients never merge
    ("1 Zwiebel", "1 Frühlingszwiebel", None),
    ("200 g Tomaten", "Tomaten, gehackt", None),
    ("1 rote Zwiebel", "1 Zwiebel", None),
    ("Butter", "Margarine", None),
    ("1 Dose Mais", "1 Dose Mais", "2 Dosen Mais"),
]


@pytest.mark.parametrize("a,b,expected", MERGE)
def test_merge(a, b, expected):
    assert _m(a, b) == expected


def test_summary_of_merged_entry_parses_back():
    text = _m("2 Zwiebeln", "200 g Zwiebeln")
    ing = parse_summary(text)
    assert ing.key == "zwiebel" and len(ing.parts) == 2
    assert render(merge(ing, parse_line("300 g Zwiebeln"))) == "2 Zwiebeln + 500 g"
    assert parse_summary("Milch + Zucker") is None  # only amounts can follow a plus sign


def test_plan_merge_with_open_items_and_recipe_names():
    existing = [OpenItem("u1", "1 Zwiebel", ["Suppe"]), OpenItem("u2", "Brot", [])]
    ops, handled = plan_merge(existing, [("200 g Zwiebeln", "Bolognese"), ("1 Zwiebel", "Chili"),
                                         ("400 g Hackfleisch", "Bolognese"), ("Brot", "Chili")])
    by = {o.uid or o.summary: o for o in ops}
    assert handled == 4
    assert by["u1"].summary == "2 Zwiebeln + 200 g" and by["u1"].recipes == ["Suppe", "Bolognese", "Chili"]
    assert by["400 g Hackfleisch"].uid is None and by["400 g Hackfleisch"].recipes == ["Bolognese"]
    assert by["u2"].summary == "Brot" and by["u2"].recipes == ["Chili"] and not by["u2"].changed_text


def test_same_recipe_twice_does_not_double():
    existing = [OpenItem("u1", "2 Zwiebeln", ["Suppe"])]
    ops, handled = plan_merge(existing, [("2 Zwiebeln", "Suppe")])
    assert handled == 0 and ops == []


def test_unparsable_lines_are_kept_as_written():
    ops, _ = plan_merge([], [("Saft von 1 Zitrone", "A"), ("Saft von 1 Zitrone", "B"), ("3-Minuten-Ei", "A")])
    assert [(o.summary, o.recipes) for o in ops] == [("Saft von 1 Zitrone", ["A", "B"]), ("3-Minuten-Ei", ["A"])]
