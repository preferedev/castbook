"""Voice packs — portable JSON casting presets shareable across books.

A pack maps speaker ids to VoiceSpecs plus alias hints so a pack exported from
one book can cast another book with a different cast (e.g. "the hero gets the
gravel voice" across a series).
"""

from __future__ import annotations

from typing import Any

from ..artifacts import CastFile, CastingFile, VoiceSpec, load_artifact, save_artifact
from ..workdir import BookPaths

PACK_SCHEMA = 1


def export_pack(book: BookPaths, name: str | None = None) -> dict[str, Any]:
    casting = load_artifact(CastingFile, book.dir)
    cast = load_artifact(CastFile, book.dir)
    if casting is None:
        raise ValueError("book has no casting to export")
    speakers: dict[str, Any] = {}
    aliases: dict[str, str] = {}
    names = {c.id: c for c in cast.characters} if cast else {}
    from ..analyze.heuristic import slugify

    for sid, spec in casting.map.items():
        entry: dict[str, Any] = spec.model_dump()
        character = names.get(sid)
        entry["name"] = character.name if character else sid
        speakers[sid] = entry
        for alias in (character.aliases if character else []) or []:
            aliases[slugify(alias)] = sid
    return {
        "schema": PACK_SCHEMA,
        "name": name or f"{casting.book_id} voices",
        "backend": next((s["backend"] for s in speakers.values()), "kokoro"),
        "speakers": speakers,
        "aliases": aliases,
    }


def apply_pack(book: BookPaths, pack: dict[str, Any], backend: str) -> dict[str, list[str]]:
    """Apply a pack's voices to the book's casting; returns applied/skipped ids."""
    if pack.get("schema") != PACK_SCHEMA:
        raise ValueError("unsupported voice pack schema")
    cast = load_artifact(CastFile, book.dir)
    casting = load_artifact(CastingFile, book.dir)
    if casting is None or cast is None:
        raise ValueError("book needs casting first (run cast)")
    from ..analyze.heuristic import slugify

    aliases: dict[str, str] = pack.get("aliases", {})
    book_aliases: dict[str, str] = {}
    for c in cast.characters:
        for a in c.aliases:
            book_aliases[slugify(a)] = c.id
    applied: list[str] = []
    skipped: list[str] = []
    mismatched: list[str] = []
    for sid, entry in (pack.get("speakers") or {}).items():
        if entry.get("backend") and entry["backend"] != backend:
            mismatched.append(sid)
            continue
        candidates = [sid] + [a for a, owner in aliases.items() if owner == sid]
        target = next(
            (c for c in candidates if c in casting.map),
            next((book_aliases[c] for c in candidates if c in book_aliases), None),
        )
        if target is None or target not in casting.map:
            skipped.append(sid)
            continue
        try:
            spec = VoiceSpec(
                backend=backend,
                voice=str(entry.get("voice", "")),
                seed=int(entry.get("seed", 0)),
                speed=float(entry.get("speed", 1.0)),
                emotion=str(entry.get("emotion", "neutral")),
            )
            if not spec.voice:
                raise ValueError("empty voice")
        except (TypeError, ValueError):
            skipped.append(sid)
            continue
        casting.map[target] = spec
        applied.append(target)
    save_artifact(casting, book.dir)
    return {"applied": applied, "skipped": skipped, "mismatched": mismatched}
