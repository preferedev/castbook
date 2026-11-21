"""Deterministic character → voice matching.

Same cast + same library ⇒ same casting.json. Voices are dealt from a
gendered pool with a stride so adjacent characters rarely collide.
"""

from __future__ import annotations

import hashlib

from ..artifacts import Character, VoiceSpec
from .library import DEFAULT_AMBIGUOUS, DEFAULT_NARRATOR, pool


def auto_cast(characters: list[Character], book_id: str) -> dict[str, VoiceSpec]:
    order = sorted(characters, key=lambda c: (_role_rank(c.role), c.name))
    used: set[str] = set()
    out: dict[str, VoiceSpec] = {}
    for c in order:
        choices = pool(c.gender, c.age)
        pick = _pick(choices, used, f"{book_id}:{c.id}")
        used.add(pick.id)
        out[c.id] = VoiceSpec(backend=pick.backend, voice=pick.id, seed=_seed(f"{book_id}:{c.id}"))
    out["narrator"] = VoiceSpec(backend="kokoro", voice=DEFAULT_NARRATOR, seed=_seed(book_id))
    out["ambiguous"] = VoiceSpec(
        backend="kokoro", voice=DEFAULT_AMBIGUOUS, seed=_seed(book_id + "?")
    )
    return out


def _role_rank(role: str) -> int:
    return {"protagonist": 0, "major": 1, "minor": 2, "one_off": 3}.get(role, 4)


def _pick(choices, used, key: str):
    free = [v for v in choices if v.id not in used] or choices
    idx = _seed(key) % len(free)
    return free[idx]


def _seed(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
