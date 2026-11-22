"""HybridAttributor — heuristic pass, LLM second opinion on low-confidence units.

Units the heuristic marks guess=True or resolves to a non-cast speaker get a
second look from the LLM; everything else keeps the cheap deterministic answer.
"""

from __future__ import annotations

from ..artifacts import Chapter, Character, Unit
from .attributor import Attributor
from .reconcile import speaker_id


class HybridAttributor:
    def __init__(self, heuristic: Attributor, llm: Attributor) -> None:
        self._heuristic = heuristic
        self._llm = llm
        self.name = f"hybrid:{llm.name}"

    def extract_cast(self, chapters: list[Chapter]) -> list[Character]:
        return self._llm.extract_cast(chapters)

    def attribute(self, chapter: Chapter, cast: list[Character]) -> list[Unit]:
        units = self._heuristic.attribute(chapter, cast)
        unsure = {
            u.id
            for u in units
            if u.kind == "dialogue"
            and (
                u.guess or u.speaker in (None, "ambiguous") or u.speaker not in {c.id for c in cast}
            )
        }
        if not unsure:
            return units
        llm_units = {u.id: u for u in self._llm.attribute(chapter, cast)}
        cast_ids = {c.id for c in cast}
        for u in units:
            if u.id not in unsure:
                continue
            alt = llm_units.get(u.id)
            if alt is None or alt.speaker in (None, "ambiguous"):
                continue
            alt_id = speaker_id(alt.speaker, cast) if alt.speaker not in cast_ids else alt.speaker
            if alt_id and alt_id in cast_ids:
                u.speaker = alt_id
                u.guess = False
        return units
