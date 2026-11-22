"""LlamaCppAttributor — local GGUF attribution via llama-cpp-python.

Structured output via json_object response format; Qwen3 runs with /no_think
for throughput. All model I/O lives here — nothing upstream sees raw text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from typing import cast as tcast

from ..artifacts import Chapter, Character, Emotion, Unit
from ..config import LlmSettings
from . import prompts
from .heuristic import slugify
from .units import split_units

BATCH = 12
EXCERPT_CHARS = 1800
MAX_EXCERPT_TOTAL = 24000


class LlamaCppAttributor:
    def __init__(self, model_path: Path, cfg: LlmSettings) -> None:
        from llama_cpp import Llama

        self._llm = Llama(
            model_path=str(model_path),
            n_ctx=cfg.context,
            n_gpu_layers=cfg.gpu_layers,
            verbose=False,
        )
        self._max_tokens = cfg.max_tokens_per_unit
        self._temperature = cfg.temperature
        self.name = f"llamacpp:{model_path.stem}"

    def _chat(self, prompt: str, max_tokens: int) -> dict[str, Any]:
        out: Any = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": "/no_think"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=self._temperature,
            max_tokens=max_tokens,
        )
        text = out["choices"][0]["message"]["content"] or "{}"
        return tcast(dict[str, Any], json.loads(_first_json(text)))

    def extract_cast(self, chapters: list[Chapter]) -> list[Character]:
        excerpts = []
        total = 0
        for ch in chapters:
            piece = ch.text[:EXCERPT_CHARS]
            if total + len(piece) > MAX_EXCERPT_TOTAL:
                break
            excerpts.append(f"[{ch.title}]\n{piece}")
            total += len(piece)
        data = self._chat(prompts.EXTRACT_CAST.format(excerpts="\n\n".join(excerpts)), 2048)
        characters: list[Character] = []
        for raw in data.get("characters", []):
            name = str(raw.get("name", "")).strip()
            if not name:
                continue
            characters.append(
                Character(
                    id=slugify(name),
                    name=name,
                    aliases=[str(a) for a in raw.get("aliases", [])],
                    gender=_gender(raw.get("gender")),
                    age=str(raw.get("age", "unknown")),
                    role=_role(raw.get("role")),
                    vibe=str(raw.get("vibe", "")),
                )
            )
        return characters

    def attribute(self, chapter: Chapter, cast: list[Character]) -> list[Unit]:
        units = split_units(chapter)
        cast_names = (
            ", ".join(
                c.name + (f" (aka {', '.join(c.aliases[:3])})" if c.aliases else "") for c in cast
            )
            or "(none yet)"
        )
        prev_speaker, prev_text = "narrator", ""
        for start in range(0, len(units), BATCH):
            batch = units[start : start + BATCH]
            passages = "\n\n".join(
                f'<{i + 1}> [prev: {prev}: "{_tail(ptext)}"] {u.text}'
                for i, u in enumerate(batch)
                for prev, ptext in [
                    (prev_speaker, prev_text)
                    if i == 0
                    else (batch[i - 1].speaker, batch[i - 1].text)
                ]
            )
            try:
                data = self._chat(
                    prompts.ATTRIBUTE.format(cast_names=cast_names, passages=passages),
                    self._max_tokens * len(batch),
                )
            except (json.JSONDecodeError, KeyError, ValueError):
                for u in batch:
                    u.speaker = "ambiguous"
                continue
            tagged = {int(t["i"]): t for t in data.get("units", []) if _valid_tag(t)}
            for i, u in enumerate(batch):
                tag = tagged.get(i + 1)
                if tag is None:
                    u.speaker = "ambiguous" if u.kind == "dialogue" else "narrator"
                else:
                    u.speaker = str(tag.get("speaker") or "ambiguous").strip().lower()
                    if u.speaker not in ("narrator", "ambiguous"):
                        u.kind = "dialogue"
                    emotion = str(tag.get("emotion", "neutral")).lower()
                    u.emotion = tcast(Emotion, emotion if emotion in _EMOTIONS else "neutral")
            prev_speaker, prev_text = batch[-1].speaker, batch[-1].text
        for u in units:  # rescue: '"quote," X said' mislabeled as narration
            if u.speaker in ("narrator", "ambiguous"):
                rescue = _said_speaker(u.text, cast)
                if rescue:
                    u.speaker = rescue
                    u.kind = "dialogue"
        return units


def _tail(text: str, n: int = 160) -> str:
    return text[-n:].replace("\n", " ")


_VERBS = "said|asked|replied|cried|exclaimed|answered|whispered|added|observed|continued|returned"
_NAME = r"(?:[A-Z][a-z]+\.?\s+){0,2}[A-Z][a-z]+\.?"
_SAID = re.compile(
    rf"[\"“”].{{0,400}}[\"“”]\s*,?\s*(?:{_VERBS})\s+"
    rf"({_NAME})(?:[.,;!?:)\"“”]|\s+to\s|$)"
    rf"|\b({_NAME})\s+(?:{_VERBS})\b.{{0,80}}[\"“]"
)


def _said_speaker(text: str, cast: list[Character]) -> str | None:
    if '"' not in text and "\u201c" not in text:
        return None
    for m in _SAID.finditer(text):
        name = (m.group(1) or m.group(2) or "").strip().rstrip(".").lower()
        if not name:
            continue
        found = _exact_speaker(name, cast) or _surname_speaker(name, cast)
        if found:
            return found
    return None


def _exact_speaker(name: str, cast: list[Character]) -> str | None:
    for c in cast:
        if any(name == str(o).lower() for o in {c.name, *c.aliases}):
            return c.name.lower()
    return None


def _surname_speaker(name: str, cast: list[Character]) -> str | None:
    for c in cast:
        for o in {c.name, *c.aliases}:
            surname = str(o).split()[-1].lower()
            if name.endswith(" " + surname):
                return c.name.lower()
    return None


_EMOTIONS = {"neutral", "angry", "sad", "joyful", "fearful", "whispered", "shouted", "sarcastic"}


def _valid_tag(t: object) -> bool:
    return isinstance(t, dict) and isinstance(t.get("i"), int)


def _gender(v: object) -> str:
    v = str(v).lower()[:2]
    return {"m": "m", "f": "f", "nb": "nb"}.get(v, "unknown")


def _role(v: object) -> str:
    v = str(v).lower()
    return v if v in ("protagonist", "major", "minor", "one_off") else "minor"


def _first_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return "{}"
    return text[start : end + 1]
