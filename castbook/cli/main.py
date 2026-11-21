"""castbook CLI — every web-UI action routes through these commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .. import models as models_mod
from ..artifacts import (
    AttributionFile,
    AudioManifest,
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
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Copy a book into the library and parse it into chapters."""
    cfg = _cfg(config)
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
) -> None:
    """Synthesize units and assemble chapter audio (resumable)."""
    cfg = _cfg(config)
    generate_book(_book(cfg, book), cfg, _chapter_range(chapters))


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


@app.command("run")
def run_cmd(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Full pipeline: import → analyze → cast → generate → export."""
    cfg = _cfg(config)
    book = run_book(file, cfg)
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
