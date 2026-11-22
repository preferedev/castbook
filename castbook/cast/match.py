"""Deterministic character → voice matching.

Same cast + same library ⇒ same casting.json. Voices are dealt from a
gendered pool with a stride so adjacent characters rarely collide.
"""

from __future__ import annotations

import hashlib

from ..artifacts import Character, VoiceSpec
from .library import DEFAULT_AMBIGUOUS, DEFAULT_NARRATOR, VoiceEntry, _norm, pool

_VALID = {v.id for v in pool("male") + pool("female") + pool("unknown")}


def auto_cast(
    characters: list[Character], book_id: str, memory: dict[str, str] | None = None
) -> dict[str, VoiceSpec]:
    memory = memory or {}
    order = sorted(characters, key=lambda c: (_role_rank(c.role), c.name))
    used: set[str] = {DEFAULT_NARRATOR, DEFAULT_AMBIGUOUS}
    out: dict[str, VoiceSpec] = {}
    for c in order:
        remembered = memory.get(_norm(c.name))
        if remembered in _VALID:
            out[c.id] = VoiceSpec(
                backend="kokoro", voice=remembered, seed=_seed(f"{book_id}:{c.id}")
            )
            used.add(remembered)
        else:
            choices = pool(c.gender, c.age)
            pick = _pick(choices, used, f"{book_id}:{c.id}")
            used.add(pick.id)
            out[c.id] = VoiceSpec(
                backend=pick.backend, voice=pick.id, seed=_seed(f"{book_id}:{c.id}")
            )
    out["narrator"] = VoiceSpec(backend="kokoro", voice=DEFAULT_NARRATOR, seed=_seed(book_id))
    out["ambiguous"] = VoiceSpec(
        backend="kokoro", voice=DEFAULT_AMBIGUOUS, seed=_seed(book_id + "?")
    )
    return out


def _role_rank(role: str) -> int:
    return {"protagonist": 0, "major": 1, "minor": 2, "one_off": 3}.get(role, 4)


def _pick(choices: list[VoiceEntry], used: set[str], key: str) -> VoiceEntry:
    free = [v for v in choices if v.id not in used]
    if not free:
        free = [v for v in choices if v.id not in {DEFAULT_NARRATOR, DEFAULT_AMBIGUOUS}]
    if not free:
        free = choices
    idx = _seed(key) % len(free)
    return free[idx]


def _seed(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
