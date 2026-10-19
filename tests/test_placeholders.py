"""
.
Copyright (C) 2026  Christopher Abanilla

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

"""Unit tests for placeholder assignment (no spaCy or Presidio needed)."""

import importlib.util
from collections import namedtuple
from pathlib import Path

# Loaded by path: importing ``backend.components`` would pull in Presidio/spaCy.
_path = Path(__file__).resolve().parent.parent / "backend" / "components" / "placeholders.py"
_spec = importlib.util.spec_from_file_location("placeholders", _path)
placeholders = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(placeholders)

M = namedtuple("M", "start end entity_type")
PLACEHOLDERS = {"PERSON": "[NAME]", "EMAIL_ADDRESS": "[EMAIL]", "LOCATION": "[ORT]"}


def find(text, value, entity="PERSON"):
    """All occurrences of ``value`` as matches."""
    out, pos = [], 0
    while (i := text.find(value, pos)) != -1:
        out.append(M(i, i + len(value), entity))
        pos = i + len(value)
    return out


def test_index_placeholder_inserts_before_the_closing_bracket():
    assert placeholders.index_placeholder("[EMAIL]", 2) == "[EMAIL_2]"
    assert placeholders.index_placeholder("EMAIL", 3) == "EMAIL_3"


def test_default_gives_every_occurrence_its_own_placeholder():
    text = "Max Mustermann schreibt. Max Mustermann antwortet."
    out, mapping = placeholders.apply_matches(text, find(text, "Max Mustermann"), PLACEHOLDERS)
    assert out == "[NAME_1] schreibt. [NAME_2] antwortet."
    assert mapping == {"[NAME_1]": "Max Mustermann", "[NAME_2]": "Max Mustermann"}


def test_reuse_gives_the_same_value_the_same_placeholder():
    text = "Max Mustermann und Anna Schmidt. Danach Max Mustermann."
    matches = find(text, "Max Mustermann") + find(text, "Anna Schmidt")
    out, mapping = placeholders.apply_matches(text, matches, PLACEHOLDERS, reuse_placeholders=True)
    assert out == "[NAME_1] und [NAME_2]. Danach [NAME_1]."
    assert mapping == {"[NAME_1]": "Max Mustermann", "[NAME_2]": "Anna Schmidt"}  # one entry per value


def test_reuse_is_exact_and_per_entity_type():
    text = "Berlin, berlin, Berlin"
    matches = find(text, "Berlin", "LOCATION") + find(text, "berlin", "LOCATION")
    out, mapping = placeholders.apply_matches(text, matches, PLACEHOLDERS, reuse_placeholders=True)
    assert out == "[ORT_1], [ORT_2], [ORT_1]"  # different spelling = different value, never altered
    # the same text under different placeholders is never merged
    out, mapping = placeholders.apply_matches("Berlin Berlin", [M(0, 6, "LOCATION"), M(7, 13, "PERSON")], PLACEHOLDERS, True)
    assert out == "[ORT_1] [NAME_1]" and len(mapping) == 2


def test_round_trip_restores_the_original_text_in_both_modes():
    text = "Mail an max@firma.de, Max Mustermann, nochmal max@firma.de und Max Mustermann."
    matches = find(text, "max@firma.de", "EMAIL_ADDRESS") + find(text, "Max Mustermann")
    for reuse in (False, True):
        out, mapping = placeholders.apply_matches(text, matches, PLACEHOLDERS, reuse)
        for placeholder in sorted(mapping, key=len, reverse=True):
            out = out.replace(placeholder, mapping[placeholder])
        assert out == text


def test_text_between_matches_is_copied_unchanged():
    text = "  Zeile 1\n\n=====0=====\n\nMax Mustermann\t am Ende \n"
    out, _ = placeholders.apply_matches(text, find(text, "Max Mustermann"), PLACEHOLDERS)
    assert out == "  Zeile 1\n\n=====0=====\n\n[NAME_1]\t am Ende \n"


def test_overlaps_are_skipped_and_unknown_types_fall_back_to_sensitiv():
    text = "Dr. Max Mustermann"
    matches = [M(0, 18, "PERSON"), M(4, 18, "PERSON"), M(0, 3, "UNBEKANNT")]
    out, mapping = placeholders.apply_matches(text, matches, PLACEHOLDERS)
    assert out == "[NAME_1]" and mapping == {"[NAME_1]": "Dr. Max Mustermann"}
    out, mapping = placeholders.apply_matches("IBAN", [M(0, 4, "UNBEKANNT")], PLACEHOLDERS)
    assert out == "[SENSITIV_1]"


def test_no_matches_returns_the_text_untouched():
    assert placeholders.apply_matches("Hallo Welt", [], PLACEHOLDERS) == ("Hallo Welt", {})


def test_entity_types_that_share_a_placeholder_never_collide_in_the_mapping():
    # IBAN_CODE and an unknown type both end up as "[SENSITIV]": counting per entity type
    # produced "[SENSITIV_1]" twice and the second original overwrote the first in the mapping.
    text = "DE89 3704 0044 0532 0130 00 und Geheimnummer 42"
    matches = [M(0, 27, "IBAN_CODE"), M(45, 47, "GEHEIM")]
    shared = {"IBAN_CODE": "[SENSITIV]"}  # GEHEIM has no row -> fallback "[SENSITIV]"
    out, mapping = placeholders.apply_matches(text, matches, shared)
    assert out == "[SENSITIV_1] und Geheimnummer [SENSITIV_2]"
    assert mapping == {"[SENSITIV_1]": "DE89 3704 0044 0532 0130 00", "[SENSITIV_2]": "42"}
    for placeholder in mapping:
        out = out.replace(placeholder, mapping[placeholder])
    assert out == text
