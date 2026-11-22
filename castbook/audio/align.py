"""Word-level alignment via faster-whisper (optional `[align]` extra).

Whisper returns timestamps for the words it heard; unit wavs are synthesized
from the unit's own text, so a left-to-right zip maps them back to the
source tokens the reader displays.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..artifacts import AttributionFile, AudioManifest, UnitStatus, load_artifact
from ..config import Settings
from ..workdir import BookPaths

_model: Any = None


def _whisper() -> Any:
    global _model
    if _model is None:
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]
        except ImportError as e:
            raise RuntimeError(
                "faster-whisper not installed — install with `castbook[align]`"
            ) from e
        _model = WhisperModel("tiny", device="cpu", compute_type="int8")
    return _model


def _tokens(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", word.lower())


def align_unit(wav: Path, text: str) -> list[list[float | str]]:
    """Zip source tokens to whisper word timestamps; unmatched tokens reuse
    the previous end so every displayed word still gets a highlight slot."""
    segs, _ = _whisper().transcribe(str(wav), word_timestamps=True)
    heard = [w for s in segs for w in s.words]
    out: list[list[float | str]] = []
    j = 0
    last = 0.0
    for tok in _tokens(text):
        want = _norm(tok)
        start, end = last, last
        for skip in range(j, min(j + 4, len(heard))):
            if _norm(heard[skip].word) == want:
                j = skip + 1
                start, end = float(heard[skip].start), float(heard[skip].end)
                break
        out.append([tok, round(start, 3), round(end, 3)])
        last = end
    return out


def run(book: BookPaths, cfg: Settings, log: Callable[[str], None] = print) -> Path:
    attrib = load_artifact(AttributionFile, book.dir)
    manifest = load_artifact(AudioManifest, book.dir)
    if attrib is None or manifest is None:
        raise FileNotFoundError(f"{book.dir} — run `castbook generate` first")

    path = book.dir / "align.json"
    done: dict[str, list[list[float | str]]] = json.loads(path.read_text()) if path.exists() else {}
    pending = [
        u
        for u in attrib.units
        if u.id not in done
        and u.id in manifest.units
        and manifest.units[u.id].status == UnitStatus.done
        and book.unit_wav(u.id).exists()
    ]
    for i, u in enumerate(pending):
        done[u.id] = align_unit(book.unit_wav(u.id), u.text)
        if (i + 1) % 25 == 0 or i + 1 == len(pending):
            path.write_text(json.dumps(done))
            log(f"[align] {i + 1}/{len(pending)} units")
    path.write_text(json.dumps(done))
    return path
