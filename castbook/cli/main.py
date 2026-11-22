"""castbook CLI — every web-UI action routes through these commands."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from .. import models as models_mod
from ..artifacts import (
    AttributionFile,
    AudioManifest,
    CastingFile,
    ChaptersFile,
    ChapterStatus,
    UnitStatus,
    load_artifact,
    save_artifact,
)
from ..config import Settings
from ..pipeline import (
    analyze_book,
    cast_book,
    export_book,
    generate_book,
    import_book,
    run_book,
    search_units,
    set_cover,
)
from ..workdir import BookPaths

app = typer.Typer(help="Turn an ebook into a full-cast audiobook.", no_args_is_help=True)


def _version(value: bool) -> None:
    if value:
        from .. import __version__

        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def _main(
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True)] = False,
) -> None:
    pass


models_app = typer.Typer(help="Download and list model weights.")
app.add_typer(models_app, name="models")


def _cfg(config: Path | None) -> Settings:
    return Settings.load(config)


def _chapter_range(spec: str | None) -> set[int] | None:
    if not spec:
        return None
    out: set[int] = set()
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        out.update(range(int(lo), int(hi) + 1) if hi else [int(lo)])
    return out


def _book(cfg: Settings, book: str) -> BookPaths:
    root = cfg.data_dir.resolve()
    b = BookPaths(cfg.data_dir, book)
    if b.dir.resolve() == root or root not in b.dir.resolve().parents:
        typer.echo(f"bad book id {book!r}")
        raise typer.Exit(1)
    return b


@app.command("import")
def import_cmd(
    files: Annotated[
        list[str],
        typer.Argument(help="local files (.epub/.txt/.pdf/…) or http(s) ebook URLs"),
    ],
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    chain: Annotated[
        bool, typer.Option("--chain", help="also run analyze + cast after each import")
    ] = False,
    lang: Annotated[
        str | None, typer.Option("--lang", help="override detected language (e.g. fr, de)")
    ] = None,
) -> None:
    """Copy books into the library and parse them into chapters."""
    cfg = _cfg(config)
    paths, tmp_dirs = _resolve_sources(files)
    try:
        for path in paths:
            book = import_book(path, cfg, lang=lang)
            typer.echo(f"book id: {book.book_id}")
            if chain:
                analyze_book(book, cfg)
                cast_book(book, cfg)
    finally:
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)


def _resolve_sources(sources: list[str]) -> tuple[list[Path], list[Path]]:
    """Expand files/dirs/URLs into local ebook paths + temp dirs to clean up."""
    from .. import net

    out: list[str] = []
    for src in sources:
        p = Path(src)
        if p.is_dir():
            found = sorted(
                f
                for f in p.rglob("*")
                if f.is_file() and f.suffix.lower() in net.supported_suffixes()
            )
            if not found:
                typer.echo(f"no supported books in {src}")
                raise typer.Exit(1)
            out.extend(str(f) for f in found)
        else:
            out.append(src)
    paths: list[Path] = []
    tmp_dirs: list[Path] = []
    for src in out:
        path = Path(src)
        if src.lower().startswith(("http://", "https://")):
            tmp = Path(tempfile.mkdtemp())
            tmp_dirs.append(tmp)
            try:
                path = net.fetch_book_url(src, tmp)
            except net.FetchError as e:
                typer.echo(f"fetch failed: {e}")
                raise typer.Exit(1) from e
        if not path.exists() or path.is_dir():
            typer.echo(f"no such file: {src}")
            raise typer.Exit(1)
        if path.suffix.lower() not in net.supported_suffixes():
            typer.echo(f"unsupported format {path.suffix or '(none)'} — {path.name}")
            raise typer.Exit(1)
        paths.append(path)
    return paths, tmp_dirs


@app.command()
def analyze(
    book: str,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    backend: Annotated[
        str | None, typer.Option("--backend", help="attributor: heuristic|llamacpp|hybrid")
    ] = None,
) -> None:
    """Extract the cast and attribute speakers (cast.json + attribution.json)."""
    cfg = _cfg(config)
    if backend is not None:
        cfg.llm.backend = backend
    analyze_book(_book(cfg, book), cfg)


@app.command()
def cast(
    book: str,
    map: Annotated[
        list[str] | None, typer.Option("--map", help="speaker=voice_id overrides")
    ] = None,
    speed: Annotated[
        list[str] | None,
        typer.Option("--speed", help="speaker=rate overrides, e.g. narrator=0.9"),
    ] = None,
    flat: Annotated[
        bool, typer.Option("--flat", help="single-voice: everyone reads as the narrator")
    ] = False,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Auto-assign voices to characters (casting.json)."""
    cfg = _cfg(config)
    overrides = {}
    for pair in map or []:
        if "=" not in pair:
            raise typer.BadParameter("--map takes speaker=voice_id")
        k, v = pair.split("=", 1)
        overrides[k.strip()] = v.strip()
    speeds = {}
    for pair in speed or []:
        if "=" not in pair:
            raise typer.BadParameter("--speed takes speaker=rate")
        k, v = pair.split("=", 1)
        speeds[k.strip()] = float(v)
    cast_book(_book(cfg, book), cfg, overrides, speeds, flat=flat)


@app.command()
def generate(
    book: str,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    chapters: Annotated[str | None, typer.Option("--chapters")] = None,
    speed: Annotated[float, typer.Option("--speed", min=0.5, max=2.0)] = 1.0,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="render only the first N units (no assembly)"),
    ] = None,
    workers: Annotated[int, typer.Option("--workers", min=1, max=16)] = 1,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Synthesize units and assemble chapter audio (resumable)."""
    cfg = _cfg(config)
    generate_book(
        _book(cfg, book),
        cfg,
        _chapter_range(chapters),
        speed=speed,
        limit=limit,
        workers=workers,
        dry_run=dry_run,
    )


@app.command()
def export(
    book: str,
    format: Annotated[str, typer.Option("--format", "-f")] = "m4b",
    layout: Annotated[str | None, typer.Option("--layout", help="abs for Audiobookshelf")] = None,
    chapters: Annotated[str | None, typer.Option("--chapters", help="subset, e.g. 1-3,7")] = None,
    epub: Annotated[
        bool, typer.Option("--epub", help="also write a read-aloud EPUB3 (media overlay)")
    ] = False,
    split: Annotated[
        float | None,
        typer.Option("--split", help="split the M4B into parts of at most N hours"),
    ] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Mux finished chapters to M4B or MP3."""
    cfg = _cfg(config)
    book_paths = _book(cfg, book)
    export_book(
        book_paths,
        cfg,
        format=format,
        layout=layout,
        only=_chapter_range(chapters),
        split_hours=split,
    )
    if epub:
        from ..epubout import build_media_epub

        ch = load_artifact(ChaptersFile, book_paths.dir)
        title = (ch.meta.title if ch else book_paths.book_id) or book_paths.book_id
        out = build_media_epub(book_paths, book_paths.export / f"{title}-read-along.epub")
        typer.echo(f"wrote {out}")


@app.command()
def transcript(
    book: str,
    fmt: Annotated[str, typer.Option("--fmt", help="srt | vtt | txt")] = "srt",
    out: Annotated[Path | None, typer.Option("--out", "-o")] = None,
    speaker: Annotated[
        str | None, typer.Option("--speaker", help="only this speaker's lines (id or name)")
    ] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Write per-chapter speaker-labeled transcripts (needs analyze + generate)."""
    from ..transcript import write_transcript

    cfg = _cfg(config)
    book_paths = _book(cfg, book)
    if fmt not in ("srt", "vtt", "txt"):
        raise typer.BadParameter("fmt must be srt, vtt or txt")
    written = write_transcript(
        book_paths, out or book_paths.dir / "transcript", fmt, speaker=speaker
    )
    typer.echo(
        f"wrote {len(written)} transcript file(s) to {written[0].parent if written else out}"
    )


@app.command()
def review(
    book: str,
    set_speaker: Annotated[
        list[str] | None, typer.Option("--set", help="unit_id=speaker overrides")
    ] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """List ambiguous units and apply speaker overrides."""
    cfg = _cfg(config)
    b = _book(cfg, book)
    attrib = load_artifact(AttributionFile, b.dir)
    if attrib is None:
        typer.echo("run `castbook analyze` first")
        raise typer.Exit(1)
    fixes = {}
    for spec in set_speaker or []:
        uid, _, speaker = spec.partition("=")
        if not speaker:
            raise typer.BadParameter("--set takes unit_id=speaker")
        fixes[uid] = speaker
    if fixes:
        fixed = 0
        for u in attrib.units:
            if u.id in fixes:
                u.speaker = fixes[u.id]
                u.guess = False
                fixed += 1
        attrib.needs_review = [u.id for u in attrib.units if u.speaker == "ambiguous" or u.guess]
        save_artifact(attrib, b.dir)
        manifest = load_artifact(AudioManifest, b.dir)
        if manifest is not None:
            for uid in fixes:
                manifest.units.pop(uid, None)
            save_artifact(manifest, b.dir)
        typer.echo(f"fixed {fixed} units (re-run `castbook generate` to render them)")
        return
    flagged = [u for u in attrib.units if u.speaker == "ambiguous" or u.guess]
    typer.echo(f"{len(flagged)} units need review (ambiguous + guessed)")
    for u in flagged[:50]:
        tag = "?" if u.speaker == "ambiguous" else f"~{u.speaker}"
        typer.echo(f"  {u.id}  ch{u.chapter}  {tag}  {u.text[:80]!r}")


@app.command()
def voices(
    play: Annotated[str | None, typer.Option("--play", help="synthesize a sample")] = None,
    text: Annotated[str, typer.Option("--text")] = "A quick preview of this voice.",
    backend: Annotated[
        str | None, typer.Option("--backend", help="kokoro|pocket|qwen — default: config")
    ] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """List the voice library; --play writes a sample WAV for a voice id."""
    from ..cast.library import LIBRARY, POCKET_LIBRARY

    cfg = _cfg(config)
    if backend is not None:
        if backend not in ("kokoro", "pocket", "qwen"):
            raise typer.BadParameter(f"unknown backend {backend!r}")
        cfg.tts.backend = backend
    lib = {"kokoro": LIBRARY, "pocket": POCKET_LIBRARY}.get(cfg.tts.backend, [])
    if play:
        from ..artifacts import VoiceSpec
        from ..tts import make_backend

        if play not in {v.id for v in lib}:
            raise typer.BadParameter(f"unknown voice {play!r} for backend {cfg.tts.backend}")
        out = cfg.data_dir / "previews" / f"{play}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        make_backend(cfg).synthesize(text, VoiceSpec(backend=cfg.tts.backend, voice=play), out)
        typer.echo(str(out))
        return
    for v in lib:
        typer.echo(f"{v.id:16} {v.gender or '?':3} {v.description}")


@app.command()
def estimate(
    book: str,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Estimate render time for the configured backend (rough, CPU-measured)."""
    from ..tts import estimate_render

    cfg = _cfg(config)
    try:
        e = estimate_render(_book(cfg, book), cfg)
    except FileNotFoundError as err:
        typer.echo(str(err))
        raise typer.Exit(1) from err
    typer.echo(
        f"{e['pending']}/{e['total']} units pending"
        f" · ~{e['est_audio_min']:.0f} min audio"
        f" · ~{e['est_render_min']:.0f} min render on {e['backend']}"
    )


@app.command()
def meta(
    book: str,
    title: Annotated[str | None, typer.Option("--title")] = None,
    author: Annotated[str | None, typer.Option("--author")] = None,
    language: Annotated[str | None, typer.Option("--lang")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Show or edit a book's title/author/language."""
    cfg = _cfg(config)
    b = _book(cfg, book)
    ch = load_artifact(ChaptersFile, b.dir)
    if ch is None:
        typer.echo("not imported")
        raise typer.Exit(1)
    if title is not None:
        ch.meta.title = title
    if author is not None:
        ch.meta.author = author
    if language is not None:
        if ch.meta.language != language:
            manifest = load_artifact(AudioManifest, b.dir)
            if manifest is not None:
                manifest.units.clear()
                save_artifact(manifest, b.dir)
                typer.echo("audio invalidated — re-render with `castbook generate`")
        ch.meta.language = language
    if title is not None or author is not None or language is not None:
        save_artifact(ch, b.dir)
    typer.echo(f"title:    {ch.meta.title}")
    typer.echo(f"author:   {ch.meta.author}")
    typer.echo(f"language: {ch.meta.language}")


@app.command()
def clean(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="skip confirmation")] = False,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Remove junk book dirs: tmp leftovers and dirs with no parsed book."""
    cfg = _cfg(config)
    if not cfg.data_dir.is_dir():
        typer.echo("nothing to clean")
        return
    junk = [
        d
        for d in cfg.data_dir.iterdir()
        if d.is_dir() and d.name not in ("_reads",) and not (d / "chapters.json").exists()
    ]
    for d in junk:
        typer.echo(f"  {d.name}")
    if not junk:
        typer.echo("clean — nothing to remove")
        return
    if not yes and not typer.confirm(f"remove {len(junk)} dir(s)?"):
        raise typer.Abort()
    for d in junk:
        shutil.rmtree(d, ignore_errors=True)
    typer.echo(f"removed {len(junk)}")


@app.command()
def verify(
    book: str,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Health-check a book: coverage, failed units, chapter gaps, stale export."""
    cfg = _cfg(config)
    b = _book(cfg, book)
    attrib = load_artifact(AttributionFile, b.dir)
    manifest = load_artifact(AudioManifest, b.dir)
    problems: list[str] = []
    if attrib is None:
        problems.append("no attribution — run analyze")
    elif manifest is None:
        problems.append("not rendered — run generate")
    else:
        failed = [
            u.id
            for u in attrib.units
            if manifest.units.get(u.id) is not None
            and manifest.units[u.id].status == UnitStatus.failed
        ]
        missing = [
            u.id
            for u in attrib.units
            if manifest.units.get(u.id) is None or manifest.units[u.id].status != UnitStatus.done
        ]
        if missing:
            problems.append(f"{len(missing)} units unrendered")
        if failed:
            problems.append(f"{len(failed)} units failed (rerun generate to retry)")
        expected = {str(u.chapter) for u in attrib.units}
        gaps = sorted(
            c
            for c in expected
            if manifest.chapters.get(c) is None
            or manifest.chapters[c].status != ChapterStatus.done
            or not (b.audio / manifest.chapters[c].path).exists()
        )
        if gaps:
            problems.append(f"missing chapter wavs: {','.join(sorted(gaps, key=int)[:10])}")
        export_dir = b.dir / "export"
        if not export_dir.is_dir() or not any(export_dir.iterdir()):
            problems.append("no exports — run export")
        else:
            mpath = b.dir / "manifest.json"
            if not mpath.exists():
                mpath = next(b.dir.glob("*manifest*.json"))
            newest = max(f.stat().st_mtime for f in export_dir.iterdir() if f.is_file())
            if mpath.stat().st_mtime > newest:
                problems.append("audio changed after last export — re-export")
    for msg in problems:
        typer.echo(f"✗ {msg}")
    if not problems:
        typer.echo("✓ book is healthy: fully rendered and exported")
    else:
        raise typer.Exit(1)


@app.command()
def doctor(
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Check the environment: ffmpeg, models, data dir."""
    import shutil

    cfg = _cfg(config)
    ok = True
    for name, found in [
        ("ffmpeg", shutil.which("ffmpeg")),
        ("ffprobe", shutil.which("ffprobe")),
        ("data dir", cfg.data_dir.is_dir() and str(cfg.data_dir)),
    ]:
        status = "ok" if found else "MISSING"
        ok &= bool(found)
        typer.echo(f"{name:12} {status}")
    for m in models_mod.MANIFEST:
        present = (cfg.models_dir / m.filename).exists()
        typer.echo(f"{m.id:22} {'ok' if present else 'not downloaded'}")
    import importlib.util

    for pkg, extra in [("pocket_tts", "pocket"), ("qwen_tts", "qwen"), ("faster_whisper", "align")]:
        installed = importlib.util.find_spec(pkg) is not None
        typer.echo(f"extra {extra:10} {'installed' if installed else 'not installed'}")
    typer.echo(f"tts backend  {cfg.tts.backend}")
    from ..probe import detect

    mi = detect()
    typer.echo(f"machine:     {mi.tier} · {mi.cores} cores · {mi.ram_gb} GB RAM")
    typer.echo(mi.verdict)
    if cfg.data_dir.is_dir():
        junk = sum(
            1
            for d in cfg.data_dir.iterdir()
            if d.is_dir() and d.name != "_reads" and not (d / "chapters.json").exists()
        )
        if junk:
            typer.echo(f"junk dirs:   {junk} — run `castbook clean`")
    raise typer.Exit(0 if ok else 1)


@app.command()
def stats(
    book: Annotated[str | None, typer.Argument()] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Print book metrics: words, units, voices, rendered audio time."""
    cfg = _cfg(config)
    if book is None:
        n_books = n_units = n_rendered = 0
        chars = 0.0
        for d in cfg.data_dir.iterdir() if cfg.data_dir.is_dir() else ():
            if not d.is_dir():
                continue
            if load_artifact(ChaptersFile, d) is None:
                continue
            n_books += 1
            attrib_f = load_artifact(AttributionFile, d)
            manifest_f = load_artifact(AudioManifest, d)
            if attrib_f is None:
                continue
            n_units += len(attrib_f.units)
            done_ids = (
                {k for k, e in manifest_f.units.items() if e.status == "done"}
                if manifest_f
                else set()
            )
            for u in attrib_f.units:
                if u.id in done_ids:
                    n_rendered += 1
                    chars += len(u.text)
        typer.echo(f"books:     {n_books}")
        typer.echo(f"units:     {n_units:,} ({n_rendered:,} rendered)")
        typer.echo(f"audio:     ~{chars / 15 / 60:.0f} min rendered")
        return
    b = _book(cfg, book)
    chapters = load_artifact(ChaptersFile, b.dir)
    attrib = load_artifact(AttributionFile, b.dir)
    casting = load_artifact(CastingFile, b.dir)
    manifest = load_artifact(AudioManifest, b.dir)
    if chapters:
        words = sum(c.word_count for c in chapters.chapters)
        typer.echo(f"chapters:  {len(chapters.chapters)}")
        typer.echo(f"words:     {words:,} (est. ~{words / 165 / 60:.1f} h narration)")
    if attrib:
        ambiguous = sum(1 for u in attrib.units if u.speaker == "ambiguous")
        typer.echo(f"units:     {len(attrib.units):,} ({ambiguous} ambiguous)")
        agg: dict[str, list[float]] = {}
        for u in attrib.units:
            a = agg.setdefault(u.speaker, [0, 0, 0.0])
            a[0] += 1
            a[1] += len(u.text.split())
            a[2] += len(u.text) / 15 / 60
        typer.echo(f"\n{'speaker':24} {'units':>6} {'words':>7} {'~min':>7}")
        for sp, (u_cnt, w_cnt, mins) in sorted(agg.items(), key=lambda kv: -kv[1][2]):
            typer.echo(f"{sp:24} {int(u_cnt):>6} {int(w_cnt):>7} {mins:>7.1f}")
    if casting:
        voices = {v.voice for v in casting.map.values()}
        typer.echo(f"speakers:  {len(casting.map)} on {len(voices)} voices")
    if manifest:
        done = [e for e in manifest.units.values() if e.status == "done"]
        typer.echo(
            f"rendered:  {len(done):,} units, {sum(e.duration_s for e in done) / 3600:.1f} h"
        )


@app.command("run")
def run_cmd(
    files: Annotated[
        list[str],
        typer.Argument(help="local files (.epub/.txt/.pdf/…), a directory, or http(s) ebook URLs"),
    ],
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    speed: Annotated[float, typer.Option("--speed", min=0.5, max=2.0)] = 1.0,
    workers: Annotated[int, typer.Option("--workers", min=1, max=16)] = 1,
    layout: Annotated[str | None, typer.Option("--layout", help="abs for Audiobookshelf")] = None,
    quality: Annotated[
        str | None,
        typer.Option("--quality", "-q", help="fast|balanced|studio — preset llm+tts backends"),
    ] = None,
) -> None:
    """Full pipeline: import → analyze → cast → generate → export."""
    cfg = _cfg(config)
    if quality is not None:
        from ..config import QUALITY_PRESETS

        preset = QUALITY_PRESETS.get(quality)
        if preset is None:
            raise typer.BadParameter(f"unknown quality {quality!r} (fast|balanced|studio)")
        cfg.llm.backend, cfg.tts.backend = preset
    paths, tmp_dirs = _resolve_sources(files)
    try:
        for path in paths:
            book = run_book(path, cfg, speed=speed, workers=workers, layout=layout)
            typer.echo(f"done: {book.export}")
    finally:
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)


@app.command()
def books(
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """List imported books."""
    cfg = _cfg(config)
    if not cfg.data_dir.exists():
        typer.echo("(no books yet)")
        return
    from ..artifacts import load_artifact

    for d in sorted(cfg.data_dir.iterdir()):
        if not d.is_dir() or not (d / "chapters.json").exists():
            continue
        chapters = load_artifact(ChaptersFile, d)
        attrib = load_artifact(AttributionFile, d)
        manifest = load_artifact(AudioManifest, d)
        title = chapters.meta.title if chapters else "?"
        done = (
            sum(1 for e in manifest.units.values() if e.status == UnitStatus.done)
            if manifest
            else 0
        )
        failed = (
            sum(1 for e in manifest.units.values() if e.status == UnitStatus.failed)
            if manifest
            else 0
        )
        total = len(attrib.units) if attrib else 0
        rendered = f" · {done}/{total} rendered" if manifest else " · not rendered"
        rendered += f" · {failed} failed" if failed else ""
        review = (
            f" · {len(attrib.needs_review)} to review" if attrib and attrib.needs_review else ""
        )
        typer.echo(f"{d.name:30} {title}{rendered}{review}")


@models_app.command("list")
def models_list() -> None:
    """Show the model manifest with licenses."""
    for m in models_mod.MANIFEST:
        typer.echo(f"{m.id:22} {m.kind:4} {m.size_bytes / 1e6:7.0f} MB  {m.license:12} {m.url}")


@models_app.command("pull")
def models_pull(
    ids: Annotated[list[str] | None, typer.Argument()] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Download models (all, or the named ones)."""
    cfg = _cfg(config)
    for path in models_mod.pull(cfg.models_dir, ids or None):
        typer.echo(f"  → {path}")


@app.command()
def serve(
    port: Annotated[int, typer.Option("--port", "-p")] = 8484,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    open_browser: Annotated[
        bool, typer.Option("--open", help="open the UI in your browser")
    ] = False,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Run the local web UI (--host 0.0.0.0 to share on the LAN)."""
    import uvicorn

    from ..app.server import create_app

    cfg = _cfg(config)
    token = None
    if host not in ("127.0.0.1", "localhost", "::1"):
        import secrets

        token = secrets.token_urlsafe(16)
        typer.echo(f"LAN mode — share as ?token= or header x-castbook-token:\n  {token}")
    if open_browser:
        import threading
        import webbrowser

        shown = f"[{host}]" if ":" in host else host
        url = f"http://{shown}:{port}" + (f"?token={token}" if token else "")
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    shown = f"[{host}]" if ":" in host else host
    tqs = f"?token={token}" if token else ""
    typer.echo(f"OPDS catalog (e-reader apps): http://{shown}:{port}/api/opds{tqs}")
    uvicorn.run(create_app(cfg, token=token), host=host, port=port, log_level="info")


@app.command()
def align(
    book: str,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Word-level timestamps via faster-whisper (needs castbook[align])."""
    from ..audio import align as align_mod

    cfg = _cfg(config)
    align_mod.run(_book(cfg, book), cfg)


@app.command()
def merge(
    book: str,
    src: Annotated[str, typer.Argument(help="speaker id to fold away")],
    dst: Annotated[str, typer.Argument(help="speaker id that survives")],
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Merge one speaker into another (aliases, units, casting)."""
    from ..analyze.reconcile import merge_speakers

    b = _book(_cfg(config), book)
    try:
        n = merge_speakers(b.dir, src, dst)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(str(e))
        raise typer.Exit(1) from e
    typer.echo(f"merged {src} → {dst} ({n} units re-attributed)")


@app.command()
def rename(
    book: str,
    speaker: Annotated[str, typer.Argument(help="speaker id")],
    name: Annotated[str, typer.Argument(help="new display name")],
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Rename a character's display name (old name kept as an alias)."""
    from ..analyze.reconcile import rename_speaker

    b = _book(_cfg(config), book)
    try:
        typer.echo(f"{speaker} → {rename_speaker(b.dir, speaker, name)}")
    except (FileNotFoundError, ValueError) as e:
        typer.echo(str(e))
        raise typer.Exit(1) from e


@app.command()
def chapters(
    book: str,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """List chapter indexes, titles and word counts (for --chapters ranges)."""
    cfg = _cfg(config)
    b = _book(cfg, book)
    ch = load_artifact(ChaptersFile, b.dir)
    if ch is None:
        typer.echo("not imported yet")
        raise typer.Exit(1)
    for c in ch.chapters:
        typer.echo(f"{c.index:<5} {c.word_count:>7}  {c.title}")


@app.command()
def search(
    book: str,
    text: Annotated[str, typer.Argument(help="substring to find in unit text")],
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Who said it: list (chapter, speaker, excerpt) for every unit containing text."""
    cfg = _cfg(config)
    b = _book(cfg, book)
    hits = search_units(b.dir, text)
    if not hits:
        typer.echo("no matches")
        raise typer.Exit(1)
    for h in hits:
        typer.echo(f"ch{h['chapter']:<4} {h['speaker']:24} {h['excerpt']}")


@app.command()
def clone(
    book: str,
    speaker: Annotated[str, typer.Argument(help="speaker id to give the cloned voice")],
    clip: Annotated[Path, typer.Argument(help="voice clip (wav/mp3/flac) to clone from")],
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Clone a voice from an audio clip onto a speaker (pocket backend).

    Only clone voices you have the right to use — see the consent notice in
    the README. The clip is copied into the book so paths stay stable.
    """
    import shutil

    if clip.suffix.lower() not in {".wav", ".mp3", ".flac"}:
        typer.echo("clip must be .wav, .mp3 or .flac")
        raise typer.Exit(1)
    if not clip.exists():
        typer.echo(f"no such file: {clip}")
        raise typer.Exit(1)
    cfg = _cfg(config)
    if cfg.tts.backend != "pocket":
        typer.echo('cloning needs the pocket backend — set tts.backend = "pocket"')
        raise typer.Exit(1)
    b = _book(cfg, book)
    dest_dir = b.dir / "voices"
    dest_dir.mkdir(parents=True, exist_ok=True)
    import time as _time

    dest = dest_dir / f"{speaker}-{int(_time.time())}{clip.suffix.lower()}"
    shutil.copy2(clip, dest)
    casting = load_artifact(CastingFile, b.dir)
    overrides = {sp: spec.voice for sp, spec in casting.map.items()} if casting else {}
    speeds = {sp: spec.speed for sp, spec in casting.map.items()} if casting else {}
    overrides[speaker] = str(dest)
    cast_book(b, cfg, overrides=overrides, speeds=speeds)
    typer.echo(f"cloned {clip.name} → {speaker} ({dest})")


@app.command()
def reset(
    book: str,
    keep_source: Annotated[
        bool, typer.Option("--keep-source", help="keep the imported source file")
    ] = True,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Delete a book's artifacts (chapters/attribution/casting/audio/export)."""
    import shutil

    b = _book(_cfg(config), book)
    if not b.dir.is_dir():
        typer.echo(f"unknown book {book!r}")
        raise typer.Exit(1)
    for stem in ("chapters", "attribution", "cast", "casting", "manifest"):
        (b.dir / f"{stem}.json").unlink(missing_ok=True)
    for d in (b.dir / "audio", b.dir / "export"):
        shutil.rmtree(d, ignore_errors=True)
    if not keep_source:
        shutil.rmtree(b.dir / "source", ignore_errors=True)
    typer.echo(f"reset {book}")


@app.command()
def cover(
    book: str,
    image: Annotated[Path, typer.Argument(help="png/jpg/webp image")],
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Set a custom cover image used in the exported audiobook."""
    b = _book(_cfg(config), book)
    if not b.dir.is_dir():
        typer.echo(f"unknown book {book!r}")
        raise typer.Exit(1)
    if not image.is_file():
        typer.echo(f"no such file: {image}")
        raise typer.Exit(1)
    try:
        name = set_cover(b, image)
    except ValueError as e:
        typer.echo(str(e))
        raise typer.Exit(1) from e
    typer.echo(f"cover → {name}")


@app.command()
def rm(
    book: str,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="skip confirmation")] = False,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Delete a book entirely (source, artifacts, audio, exports)."""
    b = _book(_cfg(config), book)
    if not b.dir.is_dir():
        typer.echo(f"unknown book {book!r}")
        raise typer.Exit(1)
    if not yes and not typer.confirm(f"delete {b.dir} entirely?"):
        raise typer.Abort
    shutil.rmtree(b.dir)
    typer.echo(f"deleted {book}")


voicepack_app = typer.Typer(help="Export/import shareable voice packs (casting presets).")
app.add_typer(voicepack_app, name="voicepack")


@voicepack_app.command("export")
def voicepack_export(
    book: str,
    out: Annotated[Path | None, typer.Option("--out", "-o")] = None,
    name: Annotated[str | None, typer.Option("--name")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Export the book's casting as a shareable voice pack JSON."""
    import json as _json

    from ..cast.voicepack import export_pack

    b = _book(_cfg(config), book)
    try:
        pack = export_pack(b, name)
    except ValueError as e:
        typer.echo(str(e))
        raise typer.Exit(1) from e
    dest = out or b.dir / f"{book}.voicepack.json"
    dest.write_text(_json.dumps(pack, indent=2))
    typer.echo(f"wrote {dest} ({len(pack['speakers'])} voices)")


@voicepack_app.command("import")
def voicepack_import(
    book: str,
    pack_file: Path,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Apply a voice pack to a book's casting."""
    import json as _json

    from ..cast.voicepack import apply_pack

    cfg = _cfg(config)
    b = _book(cfg, book)
    try:
        pack = _json.loads(pack_file.read_text())
        res = apply_pack(b, pack, cfg.tts.backend)
    except (ValueError, _json.JSONDecodeError) as e:
        typer.echo(str(e))
        raise typer.Exit(1) from e
    typer.echo(f"applied {len(res['applied'])} voices: {', '.join(res['applied'])}")
    if res["skipped"]:
        typer.echo(f"skipped (no match): {', '.join(res['skipped'])}")
    if res["mismatched"]:
        typer.echo(f"skipped (other backend): {', '.join(res['mismatched'])}")
