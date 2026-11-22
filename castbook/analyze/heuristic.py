"""Heuristic attributor — deterministic, no model required.

Used for tests, CI, weak-CPU fallback, and as the unit splitter's oracle for
golden-file testing. Accuracy is far below a real LLM; it exists so the whole
pipeline is exercisable without weights.
"""

from __future__ import annotations

import re
from collections import Counter

from ..artifacts import Chapter, Character, Unit
from .units import _inside_quote, quoted_spans, split_units

SAID_VERBS = (
    "said|asked|replied|cried|whispered|shouted|exclaimed|answered|continued|"
    "added|murmured|muttered|observed|remarked|returned|began|repeated|declared|"
    "protested|agreed|admitted|suggested|insisted|demanded|inquired|responded|"
    "called|laughed|sighed|smiled|frowned|nodded|interrupted|promised|urged|"
    "wondered|thought|told|spoke|went on|put in|burst out"
)
_NAME_PLAIN = r"[A-Z][a-z]+(?:\s+(?:(?:de|van|von|of|the|al|bin)\s+)?[A-Z][a-z]+){0,2}"
_NAME_TITLED = r"(?:Mr\.?|Mrs\.?|Miss|Dr\.?|Lady|Lord|Sir|Captain)\s+[A-Z][a-z]+"
NAME = rf"(?-i:((?:the\s+)?(?:{_NAME_TITLED}|{_NAME_PLAIN})))"

TAG_AFTER = re.compile(rf"[”\"']\s*,?\s*({SAID_VERBS})\s+{NAME}", re.IGNORECASE)
FIRST_PERSON = re.compile(
    rf"[”\"']\s*,?\s*(?:I\s+(?:{SAID_VERBS})|(?:{SAID_VERBS})\s+I)\b",
    re.IGNORECASE,
)
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
    "Everybody",
    "Somebody",
    "Nobody",
    "Anyone",
    "Someone",
    "Everyone",
    "Many",
    "Most",
    "Some",
    "All",
    "None",
    "One",
    "Two",
    "Several",
    "Mr",
    "Mrs",
    "Miss",
    "Dr",
    "Lady",
    "Lord",
    "Sir",
    "Captain",
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
            canon = identity(name)
            if canon in STOP_NAMES or len(canon) < 2:
                continue
            characters.append(
                Character(
                    id=slugify(canon),
                    name=canon,
                    aliases=[name] if name != canon else [],
                    gender=_gender_of(name),
                    role="major" if n >= 10 else "minor",
                )
            )
        return _dedupe(characters)

    def attribute(self, chapter: Chapter, cast: list[Character]) -> list[Unit]:
        units = split_units(chapter)
        names = _name_index(cast)
        last_speaker = ""
        prev_speaker = ""
        prev_text = ""
        for u in units:
            if u.kind != "dialogue":
                u.speaker = "narrator"
                last_speaker = prev_speaker = prev_text = ""
                continue
            speaker = self._speaker_for(u.text, names)
            if speaker is None:
                if last_speaker and _inside_quote(prev_text):
                    speaker = last_speaker
                else:
                    speaker = prev_speaker or last_speaker
            u.speaker = speaker if speaker else "ambiguous"
            if speaker and speaker != last_speaker:
                prev_speaker = last_speaker or prev_speaker
                last_speaker = speaker
            prev_text = u.text
        return units

    def _speaker_for(self, text: str, names: dict[str, str]) -> str | None:
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
        if FIRST_PERSON.search(text):
            hit = _lookup("I", names)
            if hit:
                return hit
        residual = quoted_free(text)
        for raw, cid in names.items():
            if len(raw) <= 3:
                continue
            pat = re.escape(raw)
            if re.search(
                rf"\b({SAID_VERBS})\s+(?!to\b|with\b|for\b|of\b)(?:his|her|their|the)?\s*{pat}",
                residual,
                re.IGNORECASE,
            ):
                return cid
            if re.search(rf"\b{pat}\s+\w*\s*({SAID_VERBS})", residual, re.IGNORECASE):
                return cid
        return None


TITLE_GENDER = {
    "mrs.": "f",
    "miss": "f",
    "lady": "f",
    "mr.": "m",
    "lord": "m",
    "sir": "m",
    "captain": "m",
    "dr.": "m",
}
FIRST_NAME_GENDER = {
    "elizabeth": "f",
    "jane": "f",
    "lydia": "f",
    "kitty": "f",
    "mary": "f",
    "maria": "f",
    "charlotte": "f",
    "catherine": "f",
    "emma": "f",
    "anne": "f",
    "caroline": "f",
    "georgiana": "f",
    "harriet": "f",
    "isabella": "f",
    "louisa": "f",
    "margaret": "f",
    "eleanor": "f",
    "marianne": "f",
    "fanny": "f",
    "julia": "f",
    "susan": "f",
    "john": "m",
    "charles": "m",
    "george": "m",
    "edward": "m",
    "william": "m",
    "henry": "m",
    "james": "m",
    "robert": "m",
    "frederick": "m",
    "frank": "m",
    "edmund": "m",
    "philip": "m",
    "colonel": "m",
}


def _gender_of(raw: str) -> str:
    low = raw.lower().strip(",.;:!?")
    for prefix, g in TITLE_GENDER.items():
        if low.startswith(prefix + " "):
            return g
    first = re.sub(r"^[^a-z]+", "", low).split()[0] if low.split() else ""
    return FIRST_NAME_GENDER.get(first, "unknown")


def quoted_free(text: str) -> str:
    """Text with quoted spans blanked — the zone where speech tags live."""
    out = text
    for span in quoted_spans(text):
        out = out.replace(span, " ", 1)
    return out


def identity(name: str) -> str:
    """Surface form → display name; strips articles, keeps honorifics."""
    name = name.strip().strip(",.;:!?")
    return re.sub(r"^(the|a|an)\s+", "", name, flags=re.IGNORECASE)


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
