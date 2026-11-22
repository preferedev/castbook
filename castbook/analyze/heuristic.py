"""Heuristic attributor — deterministic, no model required.

Used for tests, CI, weak-CPU fallback, and as the unit splitter's oracle for
golden-file testing. Accuracy is far below a real LLM; it exists so the whole
pipeline is exercisable without weights.
"""

from __future__ import annotations

import re
from collections import Counter

from ..artifacts import Chapter, Character, Unit
from .units import _apostrophe, _inside_quote, _quote_step, quoted_spans, split_units

SAID_VERBS = (
    "said|asked|replied|cried|whispered|shouted|exclaimed|answered|continued|"
    "added|murmured|muttered|observed|remarked|returned|began|repeated|declared|"
    "protested|agreed|admitted|suggested|insisted|demanded|inquired|responded|"
    "called|laughed|sighed|smiled|frowned|nodded|interrupted|promised|urged|"
    "wondered|thought|told|spoke|went on|put in|burst out|pleaded|explained|"
    "begged|sobbed|stammered|gasped|growled|screamed|yelled|mumbled|drawled|"
    "wailed|moaned|grumbled|snarled|sneered|blurted|snapped|roared|bellowed|"
    "choked|hissed|rasped|whined|croaked|queried|ventured|offered|confessed|"
    "mused|retorted|drawled|howled|stuttered|resumed|rejoined|ejaculated|"
    "assented|reiterated"
)
_NAME_PLAIN = r"[A-Z][a-z]+(?:\s+(?:(?:de|van|von|of|the|al|bin)\s+)?[A-Z][a-z]+){0,2}"
_NAME_TITLED = r"(?:Mr\.?|Mrs\.?|Miss|Dr\.?|Lady|Lord|Sir|Captain)\s+[A-Z][a-z]+"
NAME = rf"(?-i:((?:the\s+)?(?:{_NAME_TITLED}|{_NAME_PLAIN})))"

TAG_AFTER = re.compile(rf"[”\"'\u2019]\s*,?\s*({SAID_VERBS})\s+{NAME}", re.IGNORECASE)
_QUOTE_CHAR = re.compile(r"[\"\u201c\u201d\u2018\u2019']")
FIRST_PERSON = re.compile(
    rf"[”\"']\s*,?\s*(?:I\s+(?:\w+\s+)?(?:{SAID_VERBS})|(?:{SAID_VERBS})\s+I)\b",
    re.IGNORECASE,
)
NAME_SAYS = re.compile(rf"{NAME}\s+({SAID_VERBS})", re.IGNORECASE)
_FP_TAGS = re.compile(
    rf"[”\"'\u2019]\s*,?\s*I\s+(?:{SAID_VERBS})|\b(?:{SAID_VERBS})\s+I\b",
    re.IGNORECASE,
)
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
        fp = sum(len(_FP_TAGS.findall(ch.text)) for ch in chapters)
        if fp >= 5:
            characters.insert(
                0,
                Character(
                    id="protagonist",
                    name="Protagonist",
                    aliases=["I"],
                    gender="unknown",
                    role="major",
                ),
            )
        return _dedupe(characters)

    def attribute(self, chapter: Chapter, cast: list[Character]) -> list[Unit]:
        units = split_units(chapter)
        names = _name_index(cast)
        runs: list[list[tuple[Unit, str | None]]] = []
        run_after_narration: list[bool] = []
        in_quote = False
        cur_para = -1
        narr_break = True
        for u in units:
            if u.kind != "dialogue":
                u.speaker = "narrator"
                in_quote = False
                narr_break = True
                continue
            if u.paragraph != cur_para:
                in_quote = False
                cur_para = u.paragraph
            hit = self._speaker_for(u.text, names, in_quote)
            if in_quote and runs:
                runs[-1].append((u, hit))
            else:
                runs.append([(u, hit)])
                run_after_narration.append(narr_break)
            narr_break = False
            in_quote = _inside_quote(u.text, in_quote)
        resolved: list[str | None] = [next((s for _, s in run if s), None) for run in runs]

        segs: list[list[int]] = [[]]
        for i, flag in enumerate(run_after_narration):
            if flag and segs[-1]:
                segs.append([])
            segs[-1].append(i)

        first_person = "I" in names
        cast_ids = [c.id for c in cast]
        last_speaker = ""
        prev_speaker = ""
        for seg in segs:
            parties: list[str] = []
            for i in seg:
                s = resolved[i]
                if s and s != "narrator" and s not in parties:
                    parties.append(s)
            if len(cast_ids) == 2:
                for cid in cast_ids:
                    if cid not in parties:
                        parties.append(cid)
                parties = parties[:2]
            last_speaker = prev_speaker = ""
            for pos, i in enumerate(seg):
                run = runs[i]
                speaker = resolved[i]
                if speaker is None:
                    quoted = sum(len(q) for u, _ in run for q in quoted_spans(u.text))
                    total = sum(len(u.text) for u, _ in run)
                    zone = " ".join(_tag_zone(u.text) for u, _ in run)
                    tagged = re.search(SAID_VERBS, zone) is not None
                    left = next(
                        (resolved[j] for j in seg[pos - 1 :: -1] if resolved[j] in parties),
                        None,
                    )
                    if not left and not tagged and total and quoted / total < 0.3:
                        speaker = "narrator"
                    elif len(parties) == 2:
                        if first_person and _pronoun_tag(run):
                            speaker = next((p for p in parties if p != names["I"]), None)
                        if speaker is None:
                            anchor = left or next(
                                (resolved[j] for j in seg[pos + 1 :] if resolved[j] in parties),
                                None,
                            )
                            if anchor:
                                speaker = parties[1] if anchor == parties[0] else parties[0]
                                for u, _ in run:
                                    u.guess = True
                    if speaker is None:
                        speaker = prev_speaker or last_speaker or "ambiguous"
                        if speaker not in ("ambiguous",):
                            for u, _ in run:
                                u.guess = True
                    resolved[i] = speaker
                for u, _ in run:
                    u.speaker = speaker
                if speaker not in ("ambiguous", "narrator") and speaker != last_speaker:
                    prev_speaker = last_speaker or prev_speaker
                    last_speaker = speaker

        for run, speaker in zip(runs, resolved, strict=True):
            for u, _ in run:
                u.speaker = speaker or "ambiguous"
        return units

    def _speaker_for(self, text: str, names: dict[str, str], in_quote: bool = False) -> str | None:
        zone = _tag_zone(text, in_quote)
        if not _QUOTE_CHAR.search(zone):
            return None
        for m in TAG_AFTER.finditer(zone):
            hit = _lookup(m.group(2), names)
            if hit:
                return hit
        for m in NAME_SAYS.finditer(zone):
            hit = _lookup(m.group(1), names)
            if hit:
                return hit
        if FIRST_PERSON.search(zone):
            hit = _lookup("I", names)
            if hit:
                return hit
        residual = zone
        for raw, cid in names.items():
            if len(raw) <= 3:
                continue
            pat = re.escape(raw).replace(r"\ ", r"\s+")
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


def _tag_zone(text: str, inside: bool = False) -> str:
    """Text outside quoted speech — where speaker tags live. Quote marks stay
    as regex anchors; everything said inside a quote is dropped."""
    stack: list[str] = ["d"] if inside else []
    out: list[str] = []
    for i, ch in enumerate(text):
        if ch in '"\u201c\u201d\u2018' or (ch == "\u2019" and not _apostrophe(text, i)):
            _quote_step(stack, ch, text, i)
            out.append(ch)
        elif not stack:
            out.append(ch)
    return "".join(out)


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
                for part in (parts[0], parts[-1]):
                    if part.lower() not in _NAME_PART_STOP:
                        index[part] = c.id
    return index


_PRONOUN_TAG = re.compile(
    rf"\b(?:he|she)\s+(?:{SAID_VERBS})\b|\b(?:{SAID_VERBS})\s+(?:he|she)\b",
    re.IGNORECASE,
)


def _pronoun_tag(run: list[tuple[Unit, str | None]]) -> bool:
    return any(_PRONOUN_TAG.search(_tag_zone(u.text)) for u, _ in run)


_NAME_PART_STOP = {
    "the",
    "a",
    "an",
    "his",
    "her",
    "their",
    "mr.",
    "mr",
    "mrs.",
    "mrs",
    "miss",
    "dr.",
    "dr",
    "sir",
    "lady",
    "lord",
    "captain",
    "madam",
    "old",
}


def _lookup(raw: str, names: dict[str, str]) -> str | None:
    canon = canonical(raw)
    for candidate in (raw, canon):
        if candidate in names:
            return names[candidate]
        for part in candidate.split():
            if part in names:
                return names[part]
    return None
