"""Heuristic attributor — deterministic, no model required.

Used for tests, CI, weak-CPU fallback, and as the unit splitter's oracle for
golden-file testing. Accuracy is far below a real LLM; it exists so the whole
pipeline is exercisable without weights.
"""

from __future__ import annotations

import re
from collections import Counter

from ..artifacts import Chapter, Character, Unit
from .units import _apostrophe, _inside_quote, _quote_step, split_units

SAID_VERBS = (
    "said|asked|replied|cried|whispered|shouted|exclaimed|answered|continued|"
    "added|murmured|muttered|observed|remarked|returned|began|repeated|declared|"
    "protested|agreed|admitted|suggested|insisted|demanded|inquired|responded|"
    "called|laughed|sighed|smiled|frowned|nodded|interrupted|promised|urged|"
    "wondered|thought|told|spoke|went on|put in|burst out|pleaded|explained|"
    "begged|sobbed|stammered|gasped|growled|screamed|yelled|mumbled|drawled|"
    "wailed|moaned|grumbled|snarled|sneered|blurted|snapped|roared|bellowed|"
    "choked|hissed|rasped|whined|croaked|queried|ventured|offered|confessed|"
    "mused|retorted|drawled|howled|stuttered|resumed|rejoined|ejaculated|says|"
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
        pending: str | None = None
        for u in units:
            if u.kind != "dialogue":
                u.speaker = "narrator"
                in_quote = False
                narr_break = True
                pending = _trailing_says(u.text, names)
                if pending is None and "I" in names:
                    others = [c.id for c in cast if c.id != names["I"]]
                    if len(others) == 1 and re.search(
                        r"\b(?:he|she)\b[^.!?]*\b(?:me|us)\b", u.text, re.IGNORECASE
                    ):
                        pending = others[0]
                continue
            if u.paragraph != cur_para:
                in_quote = False
                cur_para = u.paragraph
            hit = self._speaker_for(u.text, names, in_quote)
            if in_quote and runs:
                runs[-1].append((u, hit))
            else:
                if hit is None and pending is not None:
                    hit = pending
                runs.append([(u, hit)])
                run_after_narration.append(narr_break)
            narr_break = False
            pending = None
            in_quote = _inside_quote(u.text, in_quote)
        resolved: list[str | None] = [next((s for _, s in run if s), None) for run in runs]

        segs: list[list[int]] = [[]]
        for i, flag in enumerate(run_after_narration):
            if flag and segs[-1]:
                segs.append([])
            segs[-1].append(i)

        first_person = "I" in names
        cast_ids = [c.id for c in cast]
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
            for pos, i in enumerate(seg):
                if resolved[i] is not None:
                    continue
                run = runs[i]
                stack: list[str] = []
                quoted = 0
                for u, _ in run:
                    for idx, c in enumerate(u.text):
                        deep = bool(stack)
                        _quote_step(stack, c, u.text, idx)
                        if deep and stack:
                            quoted += 1
                total = sum(len(u.text) for u, _ in run)
                zone = " ".join(_tag_zone(u.text) for u, _ in run)
                tagged = re.search(SAID_VERBS, zone) is not None
                left = next(
                    (resolved[j] for j in reversed(seg[:pos]) if resolved[j] in parties),
                    None,
                )
                if not left and not tagged and total and quoted / total < 0.3:
                    resolved[i] = "narrator"
                    continue
                spans = [
                    m.group(1).strip() for m in _QUOTED.finditer(" ".join(u.text for u, _ in run))
                ]
                named = {
                    _lookup(
                        re.sub(
                            r"\b(?:sir|ma'am|miss|madam)\b",
                            "",
                            sp,
                            flags=re.IGNORECASE,
                        ).strip(" .,!?'\u2019"),
                        names,
                    )
                    for sp in spans
                    if sp
                }
                named.discard(None)
                honorific = any(
                    re.search(r"\b(?:sir|ma'am|miss|madam)\b", sp, re.IGNORECASE) for sp in spans
                )
                self_id = (
                    len(named) == 1
                    and len(named) == len([sp for sp in spans if sp])
                    and (honorific or len([sp for sp in spans if sp]) > 1)
                )
                if self_id:
                    resolved[i] = named.pop()
                    continue
                pool = parties or cast_ids
                cands = [p for p in pool if p not in _addressed(run, names)]
                if len(cands) == 1:
                    resolved[i] = cands[0]
                    continue
                if len(cands) > 1 and _pronoun_tag(run):
                    g = {c.id: c.gender for c in cast}
                    zone_text = " ".join(_tag_zone(u.text) for u, _ in run)
                    want = "m" if re.search(r"\bhe\b", zone_text, re.IGNORECASE) else "f"
                    gendered = [p for p in cands if (g.get(p) or "").lower().startswith(want)]
                    if len(gendered) == 1:
                        resolved[i] = gendered[0]
                        for u, _ in run:
                            u.guess = True
                        continue
                if len(cands) != 2:
                    continue
                if first_person and re.search(
                    r"(?:^|[.!?]\s+)[“”\"']*\s*(?:he|she)\b[^.!?]*\b(?:me|us)\b",
                    zone,
                    re.IGNORECASE,
                ):
                    resolved[i] = next((p for p in cands if p != names["I"]), None)
                    continue
                if first_person and _pronoun_tag(run):
                    resolved[i] = next((p for p in cands if p != names["I"]), None)
                    continue
                qtext = " ".join(u.text for u, _ in run)
                if (
                    left in cands
                    and quoted >= 15 * 6
                    and not re.search(r'[!?]["\u201d\'\u2019]*\s*$', qtext.strip())
                ):
                    resolved[i] = left
                    for u, _ in run:
                        u.guess = True
                    continue
                anchor = (
                    left
                    if left in cands
                    else next(
                        (resolved[j] for j in seg[pos + 1 :] if resolved[j] in cands),
                        None,
                    )
                )
                if anchor:
                    resolved[i] = cands[1] if anchor == cands[0] else cands[0]
                    for u, _ in run:
                        u.guess = True
            if len(parties) == 2:
                head = next(
                    (pos for pos, i in enumerate(seg) if resolved[i] in parties),
                    len(seg),
                )
                for pos in range(min(head, len(seg) - 2), -1, -1):
                    i = seg[pos]
                    right = resolved[seg[pos + 1]]
                    if resolved[i] is not None or right not in parties:
                        continue
                    resolved[i] = parties[1] if right == parties[0] else parties[0]
                    for u, _ in runs[i]:
                        u.guess = True
            last_speaker = ""
            prev_speaker = ""
            for i in seg:
                if resolved[i] is None:
                    speaker = prev_speaker or last_speaker or "ambiguous"
                    resolved[i] = speaker
                    if speaker != "ambiguous":
                        for u, _ in runs[i]:
                            u.guess = True
                final = resolved[i] or "ambiguous"
                if final not in ("ambiguous", "narrator") and final != last_speaker:
                    prev_speaker = last_speaker or prev_speaker
                    last_speaker = final

        for run, final_speaker in zip(runs, resolved, strict=True):
            for u, _ in run:
                u.speaker = final_speaker or "ambiguous"
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
        hit = _beat_speaker(zone, names)
        if hit:
            return hit
        if re.search(
            r"\b(?:score of \w+\s+voices|clubbed\s+voices|chorus|all hands|the voices)\b",
            zone,
            re.IGNORECASE,
        ):
            for collective in ("crew", "the crew", "chorus", "crowd", "seamen", "mariners", "men"):
                hit = _lookup(collective, names) or _lookup(collective.title(), names)
                if hit:
                    return hit
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


_TRAILING_SAYS = re.compile(
    rf"({NAME}|he|she|I)\s+(?:{SAID_VERBS})\s*[:\u2014\u2013,-]?\s*$",
    re.IGNORECASE,
)


def _trailing_says(text: str, names: dict[str, str]) -> str | None:
    m = _TRAILING_SAYS.search(text.strip())
    return _lookup(m.group(1), names) if m else None


_QUOTED = re.compile("[\u201c\"']([^\u201d\"']+)[\u201d\"']")


def _addressed(run: list[tuple[Unit, str | None]], names: dict[str, str]) -> set[str]:
    out: set[str] = set()
    for u, _ in run:
        for m in _QUOTED.finditer(u.text):
            span = m.group(1)
            lone = re.sub(
                r"\b(?:sir|ma'am|miss|madam)\b", "", span.strip(), flags=re.IGNORECASE
            ).strip(" .,!?'\u2019")
            lone_is_name = lone in names or (
                len(lone) > 3
                and any(
                    re.fullmatch(re.escape(raw).replace(r"\ ", r"\s+"), lone, re.IGNORECASE)
                    for raw in names
                )
            )
            for raw, cid in names.items():
                pat = re.escape(raw).replace(r"\ ", r"\s+")
                if lone_is_name and re.fullmatch(pat, lone, re.IGNORECASE):
                    continue
                if re.search(
                    rf"(?:^|[,.!?;\u2014\u2013]\s*)(?:my\s+(?:dear|dearest|love)\s+)?{pat}\s*(?=[,.!?;\u2014\u2013]|$)",
                    span,
                ) or re.search(rf"\b{pat}\s+\w*\s*(?:{SAID_VERBS})\b", span):
                    out.add(cid)
            for collective in ("crew", "crowd", "chorus", "seamen", "mariners"):
                group_id = _lookup(collective, names) or _lookup(collective.title(), names)
                if group_id and re.search(
                    r"(?:^|[,.!?;\u2014\u2013]\s*)(?:my\s+)?(?:men|lads|mates|hearties|boys|friends)\s*(?=[,.!?;\u2014\u2013]|$)",
                    span,
                    re.IGNORECASE,
                ):
                    out.add(group_id)
    return out


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _subject_name(sent: str, names: dict[str, str]) -> str | None:
    head = re.sub(
        r"^(?:And|But|So|Then|Well|Why|Now)\s+",
        "",
        sent.lstrip().lstrip("“”\"'").lstrip(),
    )
    for raw, cid in names.items():
        if len(raw) <= 3 or raw in ("I", "he", "she", "they"):
            continue
        pat = re.escape(raw).replace(r"\ ", r"\s+")
        if re.match(rf"{pat}\b", head, re.IGNORECASE):
            return cid
    return None


def _beat_speaker(zone: str, names: dict[str, str]) -> str | None:
    tail = zone.strip().rstrip(",:;\u2014\u2013-").strip()
    if not tail:
        return None
    sents = [s for s in _SENT_SPLIT.split(tail) if re.search(r"[^\W\d_]", s)]
    if not sents:
        return None
    last = sents[-1]
    head = last.lstrip("“”\"', ")
    pronoun_subject = re.match(r"(?:he|she|they)\b", head, re.IGNORECASE) or re.search(
        rf"\b(?:{SAID_VERBS})\s+(?:he|she|they)\b", last, re.IGNORECASE
    )
    if pronoun_subject:
        if not re.search(rf"\b(?:{SAID_VERBS})\b", last):
            return None
        for prev in reversed(sents[:-1]):
            hit = _subject_name(prev, names) or _any_name(prev, names)
            if hit:
                return hit
            if not re.match(r"(?:he|she|they)\b", prev.lstrip("“”\"', "), re.IGNORECASE):
                return None
        return None
    return _subject_name(last, names)


def _any_name(sent: str, names: dict[str, str]) -> str | None:
    best: tuple[int, str] | None = None
    for raw, cid in names.items():
        if len(raw) <= 3 or raw in ("I", "he", "she", "they"):
            continue
        pat = re.escape(raw).replace(r"\ ", r"\s+")
        m = re.search(rf"\b{pat}\b", sent, re.IGNORECASE)
        if m and (best is None or m.start() > best[0]):
            best = (m.start(), cid)
    return best[1] if best else None


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
