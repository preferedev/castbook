"""castbook CLI — every web-UI action routes through these commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .. import models as models_mod
from ..artifacts import (
    AttributionFile,
    AudioManifest,
    CastingFile,
    ChaptersFile,
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
    return BookPaths(cfg.data_dir, book)


@app.command("import")
def import_cmd(
    files: Annotated[list[Path], typer.Argument(exists=True, dir_okay=False)],
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Copy books into the library and parse them into chapters."""
    cfg = _cfg(config)
    for file in files:
        book = import_book(file, cfg)
        typer.echo(f"book id: {book.book_id}")


@app.command()
def analyze(
    book: str,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Extract the cast and attribute speakers (cast.json + attribution.json)."""
    cfg = _cfg(config)
    analyze_book(_book(cfg, book), cfg)


@app.command()
def cast(
    book: str,
    map: Annotated[
        list[str] | None, typer.Option("--map", help="speaker=voice_id overrides")
    ] = None,
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
    cast_book(_book(cfg, book), cfg, overrides)


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
) -> None:
    """Synthesize units and assemble chapter audio (resumable)."""
    cfg = _cfg(config)
    generate_book(_book(cfg, book), cfg, _chapter_range(chapters), speed=speed, limit=limit)


@app.command()
def export(
    book: str,
    format: Annotated[str, typer.Option("--format", "-f")] = "m4b",
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Mux finished chapters to M4B or MP3."""
    cfg = _cfg(config)
    cfg.export.format = format
    export_book(_book(cfg, book), cfg)


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
                fixed += 1
        attrib.needs_review = [u.id for u in attrib.units if u.speaker == "ambiguous"]
        save_artifact(attrib, b.dir)
        manifest = load_artifact(AudioManifest, b.dir)
        if manifest is not None:
            for uid in fixes:
                manifest.units.pop(uid, None)
            save_artifact(manifest, b.dir)
        typer.echo(f"fixed {fixed} units (re-run `castbook generate` to render them)")
        return
    ambiguous = [u for u in attrib.units if u.speaker == "ambiguous"]
    typer.echo(f"{len(ambiguous)} ambiguous units")
    for u in ambiguous[:50]:
        typer.echo(f"  {u.id}  ch{u.chapter}  {u.text[:80]!r}")


@app.command()
def voices(
    play: Annotated[str | None, typer.Option("--play", help="synthesize a sample")] = None,
    text: Annotated[str, typer.Option("--text")] = "A quick preview of this voice.",
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """List the voice library; --play writes a sample WAV for a voice id."""
    from ..cast.library import LIBRARY

    cfg = _cfg(config)
    if play:
        from ..artifacts import VoiceSpec
        from ..tts import make_backend

        if play not in {v.id for v in LIBRARY}:
            raise typer.BadParameter(f"unknown voice {play!r}")
        out = cfg.data_dir / "previews" / f"{play}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        make_backend(cfg).synthesize(text, VoiceSpec(backend="kokoro", voice=play), out)
        typer.echo(str(out))
        return
    for v in LIBRARY:
        typer.echo(f"{v.id:16} {v.gender or '?':3} {v.description}")


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
    raise typer.Exit(0 if ok else 1)


@app.command()
def stats(
    book: str,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Print book metrics: words, units, voices, rendered audio time."""
    cfg = _cfg(config)
    b = _book(cfg, book)
    chapters = load_artifact(ChaptersFile, b.dir)
    attrib = load_artifact(AttributionFile, b.dir)
    casting = load_artifact(CastingFile, b.dir)
    manifest = load_artifact(AudioManifest, b.dir)
    if chapters:
        typer.echo(f"chapters:  {len(chapters.chapters)}")
        typer.echo(f"words:     {sum(c.word_count for c in chapters.chapters):,}")
    if attrib:
        ambiguous = sum(1 for u in attrib.units if u.speaker == "ambiguous")
        typer.echo(f"units:     {len(attrib.units):,} ({ambiguous} ambiguous)")
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
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    speed: Annotated[float, typer.Option("--speed", min=0.5, max=2.0)] = 1.0,
) -> None:
    """Full pipeline: import → analyze → cast → generate → export."""
    cfg = _cfg(config)
    book = run_book(file, cfg, speed=speed)
    typer.echo(f"done: {book.export}")


@app.command()
def books(
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """List imported books."""
    cfg = _cfg(config)
    if not cfg.data_dir.exists():
        typer.echo("(no books yet)")
        return
    for d in sorted(cfg.data_dir.iterdir()):
        if d.is_dir() and (d / "chapters.json").exists():
            typer.echo(d.name)


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
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Run the local web UI."""
    import uvicorn

    from ..app.server import create_app

    cfg = _cfg(config)
    uvicorn.run(create_app(cfg), host="127.0.0.1", port=port, log_level="info")


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
