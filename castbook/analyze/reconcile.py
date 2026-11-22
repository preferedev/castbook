"""Reconcile speakers → canonical cast ids, and merge duplicate characters.

"Elizabeth" / "Lizzy" / "Miss Bennet" collapse onto one Character; free-form
LLM speaker strings map back to character ids by alias and surname overlap.
"""

from __future__ import annotations

import re

from ..artifacts import Character
from .heuristic import TITLE_PREFIXES

_TITLE = re.compile(r"^(?:" + "|".join(p.rstrip(".") for p in TITLE_PREFIXES) + r")\.?\s+")


def normalize(name: str) -> str:
    """Surface form → match key. Articles drop; honorifics stay — Mr. Bennet
    and Mrs. Bennet are different people."""
    name = name.strip().strip(",.;:!?").lower()
    name = re.sub(r"^(the|a|an)\s+", "", name)
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def _bare(key: str) -> str:
    return _TITLE.sub("", key)


def reconcile_cast(characters: list[Character]) -> list[Character]:
    """Merge entries whose canonical names collide or nest."""
    from collections import Counter

    titled = Counter(
        _bare(normalize(c.name))
        for c in characters
        if normalize(c.name) != _bare(normalize(c.name))
    )
    out: list[Character] = []
    for c in characters:
        hit = _find(out, c.name, titled)
        if hit is None:
            out.append(c)
            continue
        if hit is not c:
            for a in (c.name, *c.aliases):
                if a not in hit.aliases and normalize(a) != normalize(hit.name):
                    hit.aliases.append(a)
            if c.role == "protagonist":
                hit.role = "protagonist"
    return out


def speaker_id(name: str, cast: list[Character]) -> str | None:
    """Free-form speaker string → character id, or None when unresolved."""
    target = normalize(name)
    if not target:
        return None
    hit = _find(cast, target, None)
    if hit:
        return hit.id
    surname = target.split()[-1]
    candidates = [
        c for c in cast if surname in {normalize(n).split()[-1] for n in [c.name, *c.aliases]}
    ]
    return candidates[0].id if len(candidates) == 1 else None


def _find(cast: list[Character], name: str, titled: dict[str, int] | None) -> Character | None:
    target = normalize(name)
    for c in cast:
        if target in {normalize(o) for o in [c.name, *c.aliases] if o}:
            return c
    bare = _bare(target)
    if titled is not None and titled.get(bare, 0) > 1:
        return None
    hits = [
        c
        for c in cast
        if bare
        and bare in {_bare(normalize(o)) for o in [c.name, *c.aliases, *c.name.split()] if o}
    ]
    return hits[0] if len(hits) == 1 else None
