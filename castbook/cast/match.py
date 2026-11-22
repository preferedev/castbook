"""Deterministic character → voice matching.

Same cast + same library ⇒ same casting.json. Voices are dealt from a
gendered pool with a stride so adjacent characters rarely collide.
"""

from __future__ import annotations

import hashlib

from ..artifacts import Character, VoiceSpec
from .library import VoiceEntry, _norm, defaults_for, pool


def _valid_ids(backend: str) -> set[str]:
    return {
        v.id
        for v in pool("male", backend=backend)
        + pool("female", backend=backend)
        + pool("unknown", backend=backend)
    }


def _valid_voice(name: str, valid: set[str], backend: str) -> bool:
    if not name:
        return False
    from pathlib import Path

    if Path(name).suffix.lower() in {".wav", ".mp3", ".flac"} and Path(name).exists():
        return backend == "pocket"  # voice clone clip — only pocket can consume one
    if "+" in name and backend != "kokoro":
        return False  # only kokoro can blend voice vectors
    for spec in name.split("+"):
        vname, _, w = spec.partition(":")
        if vname not in valid:
            return False
        try:
            if w and float(w) <= 0:
                return False
        except ValueError:
            return False
    return True


def auto_cast(
    characters: list[Character],
    book_id: str,
    memory: dict[str, str] | None = None,
    backend: str = "kokoro",
) -> dict[str, VoiceSpec]:
    memory = memory or {}
    valid = _valid_ids(backend)
    narrator, ambiguous = defaults_for(backend)
    order = sorted(characters, key=lambda c: (_role_rank(c.role), c.name))
    used: set[str] = {narrator, ambiguous}
    out: dict[str, VoiceSpec] = {}
    pending: list[Character] = []
    for c in order:
        remembered = memory.get(_norm(c.name))
        if remembered and _valid_voice(remembered, valid, backend):
            out[c.id] = VoiceSpec(
                backend=backend, voice=remembered, seed=_seed(f"{book_id}:{c.id}")
            )
            used.add(remembered)
        else:
            pending.append(c)
    for c in pending:
        choices = pool(c.gender, c.age, backend)
        pick = _pick(choices, used, f"{book_id}:{c.id}")
        used.add(pick.id)
        out[c.id] = VoiceSpec(backend=pick.backend, voice=pick.id, seed=_seed(f"{book_id}:{c.id}"))
    out["narrator"] = VoiceSpec(backend=backend, voice=narrator, seed=_seed(book_id))
    out["ambiguous"] = VoiceSpec(backend=backend, voice=ambiguous, seed=_seed(book_id + "?"))
    return out


def _role_rank(role: str) -> int:
    return {"protagonist": 0, "major": 1, "minor": 2, "one_off": 3}.get(role, 4)


def _pick(choices: list[VoiceEntry], used: set[str], key: str) -> VoiceEntry:
    free = [v for v in choices if v.id not in used]
    if not free:
        free = [
            v
            for v in choices
            if v.id not in set(defaults_for(choices[0].backend if choices else "kokoro"))
        ]
    if not free:
        free = choices
    idx = _seed(key) % len(free)
    return free[idx]


def _seed(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
