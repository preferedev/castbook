"""Attributor protocol — every attribution engine implements this surface."""

from __future__ import annotations

from typing import Protocol

from ..artifacts import Chapter, Character, Unit


class Attributor(Protocol):
    name: str

    def extract_cast(self, chapters: list[Chapter]) -> list[Character]: ...

    def attribute(self, chapter: Chapter, cast: list[Character]) -> list[Unit]: ...
