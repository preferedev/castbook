"""Reconcile speakers → canonical cast ids, and merge duplicate characters.

"Elizabeth" / "Lizzy" / "Miss Bennet" collapse onto one Character; free-form
LLM speaker strings map back to character ids by alias and surname overlap.
"""

from __future__ import annotations

import re

from ..artifacts import Character
from .heuristic import canonical


def normalize(name: str) -> str:
    name = canonical(name.strip())
    name = re.sub(r"^(the|a|an)\s+", "", name.lower())
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def reconcile_cast(characters: list[Character]) -> list[Character]:
    """Merge entries whose canonical names collide or nest."""
    out: list[Character] = []
    for c in characters:
        hit = _find(out, c.name)
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
    hit = _find(cast, target)
    if hit:
        return hit.id
    surname = target.split()[-1]
    candidates = [
        c for c in cast if surname in {normalize(n).split()[-1] for n in [c.name, *c.aliases]}
    ]
    return candidates[0].id if len(candidates) == 1 else None


def _find(cast: list[Character], name: str) -> Character | None:
    target = normalize(name)
    for c in cast:
        options = [c.name, *c.aliases, *c.name.split()]
        if target in {normalize(o) for o in options if o}:
            return c
    return None
