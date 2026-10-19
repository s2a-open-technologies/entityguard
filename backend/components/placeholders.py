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

"""
Placeholder assignment for detected entities (pure logic, no NLP imports).

Kept apart from ``cstm_analyzer`` so it can be unit-tested without spaCy or Presidio.
"""

from typing import Iterable, Mapping, Protocol


class Match(Protocol):
    """Minimal shape of a Presidio ``RecognizerResult`` that is needed here."""

    start: int
    end: int
    entity_type: str


def index_placeholder(base_placeholder: str, index: int) -> str:
    """
    Turn a static placeholder into a unique, indexed one.

    Inserts the index before the closing bracket if present
    (e.g. "[EMAIL]" -> "[EMAIL_1]"), otherwise appends it as a suffix
    (e.g. "EMAIL" -> "EMAIL_1").

    Args:
        base_placeholder (str): The static placeholder (e.g. "[EMAIL]").
        index (int): The 1-based index.

    Returns:
        str: The indexed placeholder.
    """
    if base_placeholder.endswith("]"):
        return f"{base_placeholder[:-1]}_{index}]"
    return f"{base_placeholder}_{index}"


def apply_matches(
    text: str,
    matches: Iterable[Match],
    entity_placeholders: Mapping[str, str],
    reuse_placeholders: bool = False,
) -> tuple[str, dict[str, str]]:
    """
    Replace each match with an indexed placeholder and build the mapping.

    Matches are applied left-to-right; a match that overlaps one already
    placed is skipped. The text between matches is copied unchanged
    (whitespace, line breaks and markers survive byte for byte).

    Args:
        text (str): The original text.
        matches: Detected spans (``start``, ``end``, ``entity_type``).
        entity_placeholders: Entity name -> static placeholder (e.g. "[NAME]");
            unknown entity types fall back to ``[SENSITIV]``.
        reuse_placeholders (bool): When True, the same original value of the
            placeholder gets the *same* placeholder every time it occurs
            (``[NAME_1]`` for every "Max Mustermann"), so a language model can
            tell that it is one person. The mapping then has one entry per
            distinct value. Default False: one unique placeholder per
            occurrence.

    Returns:
        tuple[str, dict[str, str]]: The masked text and placeholder -> original.
    """
    mapping: dict[str, str] = {}
    # Counters are keyed by the *static placeholder*, not the entity type: two
    # entity types that share a placeholder (e.g. IBAN and an unknown type both
    # map to "[SENSITIV]") would otherwise both produce "[SENSITIV_1]" and
    # overwrite each other in the mapping, so de-anonymization would restore
    # the wrong value.
    counters: dict[str, int] = {}
    seen: dict[tuple[str, str], str] = {}
    output_parts: list[str] = []
    last_end = 0

    for match in sorted(matches, key=lambda r: (r.start, r.start - r.end)):
        if match.start < last_end:
            continue

        original = text[match.start:match.end]
        base_placeholder = entity_placeholders.get(match.entity_type, "[SENSITIV]")
        key = (base_placeholder, original)
        if reuse_placeholders and key in seen:
            placeholder = seen[key]
        else:
            counters[base_placeholder] = counters.get(base_placeholder, 0) + 1
            placeholder = index_placeholder(base_placeholder, counters[base_placeholder])
            mapping[placeholder] = original
            seen[key] = placeholder

        output_parts.append(text[last_end:match.start])
        output_parts.append(placeholder)
        last_end = match.end

    output_parts.append(text[last_end:])
    return "".join(output_parts), mapping
