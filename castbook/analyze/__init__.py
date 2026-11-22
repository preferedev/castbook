"""Analyze stage — chapters.json → cast.json + attribution.json."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..artifacts import (
    RESERVED_AMBIGUOUS,
    RESERVED_NARRATOR,
    AttributionFile,
    CastFile,
    ChaptersFile,
    Unit,
    load_artifact,
    save_artifact,
)
from ..config import Settings
from ..workdir import BookPaths
from .attributor import Attributor
from .heuristic import HeuristicAttributor
from .reconcile import reconcile_cast, speaker_id


def make_attributor(cfg: Settings, log: Callable[[str], None] = print) -> Attributor:
    if cfg.llm.backend == "heuristic":
        return HeuristicAttributor()
    if cfg.llm.backend in ("llamacpp", "hybrid"):
        from ..models import resolve_model

        path = resolve_model(cfg.models_dir, cfg.llm.model)
        if path is None:
            log(
                f"[analyze] model {cfg.llm.model!r} not downloaded "
                f"(`castbook models pull {cfg.llm.model}`) — using heuristic"
            )
            return HeuristicAttributor()
        from .llm import LlamaCppAttributor

        llm = LlamaCppAttributor(path, cfg.llm)
        if cfg.llm.backend == "hybrid":
            from .hybrid import HybridAttributor

            return HybridAttributor(HeuristicAttributor(), llm)
        return llm
    raise ValueError(f"unknown llm backend {cfg.llm.backend!r}")


def run(book: BookPaths, cfg: Settings, log: Callable[[str], None] = print) -> Path:
    chapters_file = load_artifact(ChaptersFile, book.dir)
    if chapters_file is None:
        raise FileNotFoundError(f"{book.dir}/chapters.json — run `castbook import` first")

    attributor = make_attributor(cfg, log)
    input_hash = chapters_file.input_hash

    prior = load_artifact(AttributionFile, book.dir)
    same_engine_prior = (
        prior is not None and prior.input_hash == input_hash and prior.attributor == attributor.name
    )

    prior_cast = load_artifact(CastFile, book.dir)
    cast_matches = (
        prior_cast is not None
        and prior_cast.input_hash == input_hash
        and (
            prior_cast.attributor == attributor.name
            # pre-field artifacts: reuse when the attribution they fed was this engine's
            or (prior_cast.attributor is None and same_engine_prior)
        )
    )
    if cast_matches:
        assert prior_cast is not None
        cast = prior_cast.characters
        if prior_cast.attributor is None:
            prior_cast.attributor = attributor.name
            save_artifact(prior_cast, book.dir)
        log(f"[analyze] reusing cast: {len(cast)} characters")
    else:
        log(f"[analyze] extracting cast with {attributor.name}")
        cast = reconcile_cast(attributor.extract_cast(chapters_file.chapters))
        save_artifact(
            CastFile(
                book_id=book.book_id,
                characters=cast,
                input_hash=input_hash,
                attributor=attributor.name,
            ),
            book.dir,
        )
        log(f"[analyze] {len(cast)} characters")

    done_chapters: dict[int, list[Unit]] = {}
    if same_engine_prior:
        assert prior is not None
        for u in prior.units:
            done_chapters.setdefault(u.chapter, []).append(u)
        if done_chapters:
            log(f"[analyze] resuming: {len(done_chapters)} chapters already attributed")

    all_units: list[Unit] = []
    for i, ch in enumerate(chapters_file.chapters):
        units = done_chapters.get(i) or attributor.attribute(ch, cast)
        all_units.extend(units)
        if i not in done_chapters and (i + 1) % 5 == 0:
            save_artifact(
                AttributionFile(
                    book_id=book.book_id,
                    attributor=attributor.name,
                    units=all_units,
                    input_hash=input_hash,
                ),
                book.dir,
            )
            log(f"[analyze] attributed {i + 1}/{len(chapters_file.chapters)} chapters (checkpoint)")

    new_names: set[str] = set()
    for u in all_units:
        if u.speaker in (RESERVED_NARRATOR, RESERVED_AMBIGUOUS, ""):
            continue
        resolved = speaker_id(u.speaker, cast)
        if resolved:
            u.speaker = resolved
        else:
            new_names.add(u.speaker)
            u.speaker = RESERVED_AMBIGUOUS
    if new_names:
        log(f"[analyze] {len(new_names)} unattributed speaker names → ambiguous")

    needs_review = [u.id for u in all_units if u.speaker == RESERVED_AMBIGUOUS or u.guess]
    save_artifact(
        AttributionFile(
            book_id=book.book_id,
            attributor=attributor.name,
            units=all_units,
            needs_review=needs_review,
            input_hash=input_hash,
        ),
        book.dir,
    )
    log(f"[analyze] {len(all_units)} units, {len(needs_review)} need review")
    return book.dir / "attribution.json"
