"""Local web UI — FastAPI shell over the same pipeline the CLI drives.

Long stages run in a thread pool; progress is read back from the on-disk
artifacts, so the UI survives a server restart.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from ..artifacts import (
    AttributionFile,
    AudioManifest,
    CastFile,
    CastingFile,
    ChaptersFile,
    UnitStatus,
    load_artifact,
)
from ..cast.library import LIBRARY
from ..config import Settings
from ..pipeline import analyze_book, cast_book, export_book, generate_book, import_book
from ..workdir import BookPaths

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 200 * 1024 * 1024

_jobs: dict[str, threading.Thread] = {}
_jobs_lock = threading.Lock()


def _log_to(path: Path) -> Callable[[str], None]:
    lock = threading.Lock()

    def log(msg: str) -> None:
        with lock, path.open("a") as f:
            f.write(msg + "\n")

    return log


def _spawn(key: str, target: Callable[[], object]) -> None:
    with _jobs_lock:
        if key in _jobs and _jobs[key].is_alive():
            raise HTTPException(409, f"{key} already running")
        t = threading.Thread(target=target, daemon=True)
        _jobs[key] = t
        t.start()


def create_app(cfg: Settings) -> FastAPI:
    app = FastAPI(title="Castbook")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text()

    @app.get("/api/voices")
    def voices() -> list[dict[str, Any]]:
        return [v.model_dump() for v in LIBRARY]

    @app.get("/api/books")
    def books() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not cfg.data_dir.exists():
            return out
        for d in sorted(cfg.data_dir.iterdir()):
            if not d.is_dir():
                continue
            ch = load_artifact(ChaptersFile, d)
            if ch is None:
                continue
            out.append(_status(d, ch))
        return out

    @app.post("/api/import")
    def upload(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in (".epub", ".txt", ".md"):
            raise HTTPException(400, f"unsupported format {suffix}")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            shutil.copyfileobj(file.file, tmp, 1 << 20)
            tmp_path = Path(tmp.name)
        if tmp_path.stat().st_size > MAX_UPLOAD:
            tmp_path.unlink()
            raise HTTPException(413, "file too large")
        try:
            book = import_book(tmp_path, cfg)
        finally:
            tmp_path.unlink(missing_ok=True)
        return {"book_id": book.book_id}

    @app.get("/api/books/{book_id}")
    def book_detail(book_id: str) -> dict[str, Any]:
        d = cfg.data_dir / book_id
        if not d.is_dir():
            raise HTTPException(404, "unknown book")
        cast_f = load_artifact(CastFile, d)
        casting = load_artifact(CastingFile, d)
        attrib = load_artifact(AttributionFile, d)
        return {
            "book_id": book_id,
            "characters": [c.model_dump() for c in cast_f.characters] if cast_f else [],
            "casting": {k: v.model_dump() for k, v in casting.map.items()} if casting else {},
            "needs_review": attrib.needs_review if attrib else [],
            "units": len(attrib.units) if attrib else 0,
        }

    @app.post("/api/books/{book_id}/cast")
    def set_cast(book_id: str, overrides: dict[str, str]) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        cast_book(book, cfg, overrides=overrides)
        return {"ok": True}

    @app.post("/api/books/{book_id}/analyze")
    def analyze(book_id: str) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        log = _log_to(book.dir / "job.log")

        def work() -> None:
            analyze_book(book, cfg, log)
            cast_book(book, cfg, log=log)

        _spawn(f"analyze:{book_id}", work)
        return {"ok": True}

    @app.post("/api/books/{book_id}/generate")
    def generate(book_id: str) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        log = _log_to(book.dir / "job.log")
        _spawn(f"generate:{book_id}", lambda: generate_book(book, cfg, log))
        return {"ok": True}

    @app.get("/api/books/{book_id}/progress")
    def progress(book_id: str) -> dict[str, Any]:
        d = cfg.data_dir / book_id
        manifest = load_artifact(AudioManifest, d)
        attrib = load_artifact(AttributionFile, d)
        total = len(attrib.units) if attrib else 0
        done = failed = 0
        if manifest:
            done = sum(1 for u in manifest.units.values() if u.status == UnitStatus.done)
            failed = sum(1 for u in manifest.units.values() if u.status == UnitStatus.failed)
        busy = any(k.endswith(book_id) and t.is_alive() for k, t in _jobs.items())
        log_tail = (d / "job.log").read_text()[-2000:] if (d / "job.log").exists() else ""
        return {
            "total": total,
            "done": done,
            "failed": failed,
            "busy": busy,
            "log": log_tail,
        }

    @app.post("/api/books/{book_id}/export")
    def export(book_id: str) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        outs = export_book(book, cfg)
        files = [p.name if p.is_file() else f"{p.name}/" for p in outs]
        return {"files": files}

    @app.get("/api/books/{book_id}/download/{name}")
    def download(book_id: str, name: str) -> FileResponse:
        path = (cfg.data_dir / book_id / "export" / name).resolve()
        if not path.is_file() or path.parent != (cfg.data_dir / book_id / "export").resolve():
            raise HTTPException(404, "no such export")
        return FileResponse(path, filename=path.name)

    return app


def _require_book(cfg: Settings, book_id: str) -> BookPaths:
    book = BookPaths(cfg.data_dir, book_id)
    if not book.dir.is_dir():
        raise HTTPException(404, "unknown book")
    return book


def _status(d: Path, ch: ChaptersFile) -> dict[str, Any]:
    manifest = load_artifact(AudioManifest, d)
    done = sum(1 for c in manifest.chapters.values() if c.status.value == "done") if manifest else 0
    stages = [
        n for n in ("cast", "attribution", "casting", "manifest") if (d / f"{n}.json").exists()
    ]
    return {
        "book_id": ch.book_id,
        "title": ch.meta.title,
        "author": ch.meta.author,
        "chapters": len(ch.chapters),
        "chapters_rendered": done,
        "stages": stages,
        "exports": [p.name for p in (d / "export").glob("*") if p.is_file()]
        if (d / "export").exists()
        else [],
    }
