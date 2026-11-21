"""Heuristic attributor — deterministic, no model required.

Used for tests, CI, weak-CPU fallback, and as the unit splitter's oracle for
golden-file testing. Accuracy is far below a real LLM; it exists so the whole
pipeline is exercisable without weights.
"""

from __future__ import annotations

import re
from collections import Counter

from ..artifacts import Chapter, Character, Unit
from .units import quoted_spans, split_units

SAID_VERBS = (
    "said|asked|replied|cried|whispered|shouted|exclaimed|answered|continued|"
    "added|murmured|muttered|observed|remarked|returned|began|repeated|declared|"
    "protested|agreed|admitted|suggested|insisted|demanded|inquired|responded|"
    "called|laughed|sighed|smiled|frowned|nodded|interrupted|promised|urged|"
    "wondered|thought|told|spoke|went on|put in|burst out"
)
_NAME_PLAIN = r"[A-Z][a-z]+(?:\s+(?:de|van|von|of|the)?\s*[A-Z]?[a-z]*){0,3}"
_NAME_TITLED = r"(?:Mr\.?|Mrs\.?|Miss|Dr\.?|Lady|Lord|Sir|Captain)\s+[A-Z][a-z]+"
NAME = rf"({_NAME_PLAIN}|{_NAME_TITLED})"

TAG_AFTER = re.compile(rf"[”\"']\s*,?\s*({SAID_VERBS})\s+{NAME}", re.IGNORECASE)
NAME_SAYS = re.compile(rf"{NAME}\s+({SAID_VERBS})", re.IGNORECASE)
VOCATIVE = re.compile(rf"\b({SAID_VERBS})\b[^.!?]*,\s*{NAME}\s*[.!?]", re.IGNORECASE)

TITLE_PREFIXES = ("mr.", "mrs.", "miss", "dr.", "lady", "lord", "sir", "captain")
STOP_NAMES = {
    "The",
    "A",
    "An",
    "It",
    "He",
    "She",
    "They",
    "I",
    "You",
    "We",
    "But",
    "And",
    "Chapter",
    "Part",
    "What",
    "When",
    "Where",
    "Why",
    "How",
    "This",
    "That",
    "Oh",
    "Ah",
    "Yes",
    "No",
    "Well",
    "Now",
    "Then",
    "So",
    "For",
    "In",
    "On",
    "My",
    "Your",
    "His",
    "Her",
    "Their",
    "Our",
    "Dear",
    "Good",
    "Come",
    "Pray",
}


class HeuristicAttributor:
    name = "heuristic"

    def extract_cast(self, chapters: list[Chapter]) -> list[Character]:
        counts: Counter[str] = Counter()
        for ch in chapters:
            for m in TAG_AFTER.finditer(ch.text):
                counts[m.group(2)] += 1
            for m in NAME_SAYS.finditer(ch.text):
                counts[m.group(1)] += 1
            for m in VOCATIVE.finditer(ch.text):
                counts[m.group(2)] += 1
        characters = []
        for name, n in counts.most_common(40):
            canon = canonical(name)
            if canon in STOP_NAMES or len(canon) < 2:
                continue
            characters.append(
                Character(
                    id=slugify(canon),
                    name=canon,
                    aliases=[name] if name != canon else [],
                    role="major" if n >= 10 else "minor",
                )
            )
        return _dedupe(characters)

    def attribute(self, chapter: Chapter, cast: list[Character]) -> list[Unit]:
        units = split_units(chapter)
        names = _name_index(cast)
        last_speaker = ""
        for u in units:
            if u.kind != "dialogue":
                u.speaker = "narrator"
                last_speaker = ""
                continue
            speaker = self._speaker_for(u.text, names) or last_speaker
            u.speaker = speaker if speaker else "ambiguous"
            if speaker:
                last_speaker = speaker
        return units

    def _speaker_for(self, text: str, names: dict[str, str]) -> str | None:
        lowered = text.lower()
        if not quoted_spans(text):
            return None
        for m in TAG_AFTER.finditer(text):
            hit = _lookup(m.group(2), names)
            if hit:
                return hit
        for m in NAME_SAYS.finditer(text):
            hit = _lookup(m.group(1), names)
            if hit:
                return hit
        for raw, cid in names.items():
            if f" {raw.lower()}" in lowered and len(raw) > 3:
                return cid
        return None


def canonical(name: str) -> str:
    name = name.strip().strip(",.;:!?")
    low = name.lower()
    for p in TITLE_PREFIXES:
        if low.startswith(p + " "):
            return name[len(p) + 1 :]
    return name


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _dedupe(characters: list[Character]) -> list[Character]:
    """Merge same-last-token names (Elizabeth / Elizabeth Bennet) and slug collisions."""
    out: list[Character] = []
    by_last: dict[str, Character] = {}
    for c in characters:
        last = c.name.split()[-1].lower()
        existing = by_last.get(last)
        if existing and existing.id != c.id:
            if c.name not in existing.aliases and c.name != existing.name:
                existing.aliases.append(c.name)
            continue
        dup = next((x for x in out if x.id == c.id), None)
        if dup:
            if c.name not in dup.aliases and c.name != dup.name:
                dup.aliases.append(c.name)
            continue
        by_last[last] = c
        out.append(c)
    return out


def _name_index(cast: list[Character]) -> dict[str, str]:
    index: dict[str, str] = {}
    for c in cast:
        for n in [c.name, *c.aliases]:
            index[n] = c.id
            parts = n.split()
            if len(parts) > 1:
                index[parts[0]] = c.id
                index[parts[-1]] = c.id
    return index


def _lookup(raw: str, names: dict[str, str]) -> str | None:
    canon = canonical(raw)
    for candidate in (raw, canon):
        if candidate in names:
            return names[candidate]
        for part in candidate.split():
            if part in names:
                return names[part]
    return None
