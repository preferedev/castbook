"""Local web UI — FastAPI shell over the same pipeline the CLI drives.

Long stages run in a thread pool; progress is read back from the on-disk
artifacts, so the UI survives a server restart.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from ..artifacts import (
    AttributionFile,
    AudioManifest,
    CastFile,
    CastingFile,
    ChaptersFile,
    UnitStatus,
    VoiceSpec,
    load_artifact,
    save_artifact,
)
from ..cast.library import LIBRARY
from ..config import Settings
from ..models import MANIFEST, resolve_model
from ..models import pull as models_pull
from ..pipeline import analyze_book, cast_book, export_book, generate_book, import_book
from ..tts.backend import Backend
from ..workdir import BookPaths

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 200 * 1024 * 1024

_jobs: dict[str, threading.Thread] = {}
_cancels: dict[str, threading.Event] = {}
_jobs_lock = threading.Lock()
_import_lock = threading.Lock()


def _log_to(path: Path) -> Callable[[str], None]:
    lock = threading.Lock()

    def log(msg: str) -> None:
        with lock, path.open("a") as f:
            f.write(msg + "\n")

    return log


def _spawn(key: str, target: Callable[[], object], log: Callable[[str], None]) -> None:
    def wrapped() -> None:
        try:
            target()
        except Exception as e:
            log(f"[{key.split(':')[0]}] failed: {e}")

    with _jobs_lock:
        if key in _jobs and _jobs[key].is_alive():
            raise HTTPException(409, f"{key} already running")
        cancel = _cancels.setdefault(key, threading.Event())
        cancel.clear()
        t = threading.Thread(target=wrapped, daemon=True)
        _jobs[key] = t
        t.start()


def create_app(cfg: Settings) -> FastAPI:
    app = FastAPI(title="Castbook")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text()

    @app.get("/api/machine")
    def machine() -> dict[str, Any]:
        from ..probe import detect

        mi = detect()
        return {
            "tier": mi.tier,
            "gpu": mi.gpu,
            "cores": mi.cores,
            "ram_gb": mi.ram_gb,
            "quality_capable": mi.quality_capable,
            "verdict": mi.verdict,
        }

    @app.get("/api/voices")
    def voices() -> list[dict[str, Any]]:
        from ..cast.library import POCKET_LIBRARY

        lib = POCKET_LIBRARY if cfg.tts.backend == "pocket" else LIBRARY
        return [v.model_dump() for v in lib]

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

    @app.get("/api/models")
    def models() -> list[dict[str, Any]]:
        busy = _jobs.get("models:pull")
        return [
            {
                "id": m.id,
                "kind": m.kind,
                "size_mb": round(m.size_bytes / 1e6),
                "license": m.license,
                "required": m.required,
                "downloaded": resolve_model(cfg.models_dir, m.id) is not None,
                "busy": busy is not None and busy.is_alive(),
            }
            for m in MANIFEST
        ]

    @app.get("/api/models/log")
    def models_log(lines: int = 100) -> dict[str, Any]:
        path = cfg.models_dir / "models.log"
        text = path.read_text(errors="replace") if path.exists() else ""
        return {"lines": text.splitlines()[-lines:]}

    @app.post("/api/models/pull")
    def pull_models(ids: str = "") -> dict[str, Any]:
        wanted = [i for i in ids.split(",") if i] or None
        log = _log_to(cfg.models_dir / "models.log")
        _spawn("models:pull", lambda: models_pull(cfg.models_dir, wanted, log=log), log)
        return {"ok": True}

    @app.post("/api/import")
    def upload(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in (".epub", ".txt", ".md", ".pdf"):
            raise HTTPException(400, f"unsupported format {suffix}")
        filename = Path(file.filename or f"book{suffix}").name
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_path = tmp_dir / filename
        size = 0
        try:
            with tmp_path.open("wb") as out:
                while chunk := file.file.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413, "file too large")
                    out.write(chunk)
            try:
                with _import_lock:
                    book = import_book(tmp_path, cfg)
            except ValueError as e:
                raise HTTPException(422, str(e)) from e
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
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

    @app.get("/api/books/{book_id}/lexicon")
    def get_lexicon(book_id: str) -> dict[str, Any]:
        import json

        book = _require_book(cfg, book_id)
        book_lex: dict[str, str] = {}
        f = book.dir / "lexicon.json"
        if f.exists():
            book_lex = json.loads(f.read_text())
        glob: dict[str, str] = {}
        g = cfg.data_dir / "lexicon.json"
        if g.exists():
            glob = json.loads(g.read_text())
        return {"book": book_lex, "global": glob}

    @app.put("/api/books/{book_id}/lexicon")
    def put_lexicon(book_id: str, body: dict[str, str]) -> dict[str, Any]:
        import json

        book = _require_book(cfg, book_id)
        for k, v in body.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise HTTPException(422, "lexicon entries must be word→replacement strings")
        fd, tmppath = tempfile.mkstemp(dir=book.dir, suffix=".tmp", prefix="lexicon-")
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(body, indent=2, ensure_ascii=False))
        Path(tmppath).replace(book.dir / "lexicon.json")
        return {"saved": len(body)}

    @app.get("/api/books/{book_id}/align")
    def alignment(book_id: str) -> Any:
        import json

        f = _require_book(cfg, book_id).dir / "align.json"
        return json.loads(f.read_text()) if f.exists() else {}

    @app.post("/api/books/{book_id}/merge")
    def merge(book_id: str, src: str, dst: str) -> dict[str, Any]:
        from ..analyze.reconcile import merge_speakers

        book = _require_book(cfg, book_id)
        try:
            n = merge_speakers(book.dir, src, dst)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(422, str(e)) from e
        return {"merged": n}

    @app.get("/api/books/{book_id}/log")
    def book_log(book_id: str, lines: int = 100) -> dict[str, Any]:
        f = _require_book(cfg, book_id).dir / "job.log"
        text = f.read_text() if f.exists() else ""
        return {"lines": text.splitlines()[-lines:]}

    @app.delete("/api/books/{book_id}")
    def delete_book(book_id: str) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        with _jobs_lock:
            busy = [k for k, t in _jobs.items() if k.endswith(f":{book_id}") and t.is_alive()]
        if busy:
            raise HTTPException(409, f"job still running: {busy[0].split(':')[0]}")
        shutil.rmtree(book.dir)
        return {"ok": True}

    @app.post("/api/books/{book_id}/cast")
    def set_cast(book_id: str, spec: dict[str, Any]) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        voices: dict[str, str] = {}
        speeds: dict[str, float] = {}
        for sp, v in spec.items():
            if isinstance(v, dict):
                if "voice" in v:
                    voices[sp] = str(v["voice"])
                if "speed" in v:
                    speeds[sp] = float(v["speed"])
            else:
                voices[sp] = str(v)
        cast_book(book, cfg, overrides=voices, speeds=speeds)
        return {"ok": True}

    @app.post("/api/books/{book_id}/analyze")
    def analyze(book_id: str, backend: str | None = None) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        if backend is not None and backend not in ("heuristic", "llamacpp"):
            raise HTTPException(422, f"bad backend {backend!r}")
        local_cfg = (
            cfg.model_copy(update={"llm": cfg.llm.model_copy(update={"backend": backend})})
            if backend is not None
            else cfg
        )
        log = _log_to(book.dir / "job.log")

        def work() -> None:
            analyze_book(book, local_cfg, log)
            cast_book(book, local_cfg, log=log)

        _spawn(f"job:{book_id}", work, log)
        return {"ok": True}

    @app.post("/api/books/{book_id}/generate")
    def generate(
        book_id: str,
        limit: Annotated[int | None, Query(ge=1)] = None,
        chapters: str | None = None,
        workers: Annotated[int, Query(ge=1, le=16)] = 1,
        export: bool = False,
    ) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        sel: set[int] | None = None
        if chapters:
            try:
                sel = set()
                for part in chapters.split(","):
                    part = part.strip()
                    if "-" in part:
                        a, b = (int(x) for x in part.split("-", 1))
                        sel.update(range(min(a, b), max(a, b) + 1))
                    elif part:
                        sel.add(int(part))
                if len(sel) > 2000:
                    raise ValueError("range too wide")
            except ValueError as e:
                raise HTTPException(422, f"bad chapters {chapters!r}") from e
        if export and limit is not None:
            raise HTTPException(422, "export needs chapter assembly — drop limit or export after")
        log = _log_to(book.dir / "job.log")

        def work() -> None:
            cancel = _cancels[f"job:{book_id}"]
            generate_book(
                book,
                cfg,
                log=log,
                chapters=sel,
                limit=limit,
                workers=workers,
                cancel=cancel,
            )
            if export and not cancel.is_set():
                log("[export] started")
                outs = export_book(book, cfg, log=log)
                log(f"[export] wrote {', '.join(p.name for p in outs)}")

        _spawn(f"job:{book_id}", work, log)
        return {"ok": True}

    @app.post("/api/books/{book_id}/regenerate")
    def regenerate(book_id: str, chapters: str) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        sel: set[int] = set()
        try:
            for part in chapters.split(","):
                part = part.strip()
                if "-" in part:
                    a, b = (int(x) for x in part.split("-", 1))
                    sel.update(range(min(a, b), max(a, b) + 1))
                elif part:
                    sel.add(int(part))
        except ValueError:
            raise HTTPException(422, f"bad chapters {chapters!r}") from None
        if not sel or len(sel) > 2000:
            raise HTTPException(422, f"bad chapters {chapters!r}")
        attribution = load_artifact(AttributionFile, book.dir)
        manifest = load_artifact(AudioManifest, book.dir)
        if attribution is None or manifest is None:
            raise HTTPException(409, "nothing to regenerate")
        unit_ids = {u.id for u in attribution.units if u.chapter in sel}
        popped = sum(1 for uid in unit_ids if uid in manifest.units)

        def work() -> None:
            for uid in unit_ids:
                manifest.units.pop(uid, None)
            for cid in [str(c) for c in sel]:
                manifest.chapters.pop(cid, None)
            save_artifact(manifest, book.dir)
            generate_book(book, cfg, log=log, chapters=sel, cancel=_cancels[f"job:{book_id}"])

        log = _log_to(book.dir / "job.log")
        _spawn(f"job:{book_id}", work, log)
        return {"ok": True, "popped": popped}

    @app.get("/api/books/{book_id}/chapters/{chapter}/audio")
    def chapter_audio(book_id: str, chapter: int) -> FileResponse:
        book = _require_book(cfg, book_id)
        wav = book.dir / "audio" / f"ch{chapter:03d}.wav"
        if not wav.exists():
            raise HTTPException(404, "chapter not rendered")
        return FileResponse(wav, media_type="audio/wav")

    @app.post("/api/preview")
    def preview(spec: dict[str, Any]) -> FileResponse:
        voice = str(spec.get("voice", "af_sarah"))
        speed = float(spec.get("speed") or 1.0)
        speed = speed if 0 < speed <= 2 else 1.0
        text = str(spec.get("text") or "A quick preview of this voice.")
        out = cfg.data_dir / ".previews" / f"{voice}-{speed}-{abs(hash(text))}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists():
            backend = _preview_backend(cfg)
            backend.synthesize(
                text[:300], VoiceSpec(backend=cfg.tts.backend, voice=voice, speed=speed), out
            )
        return FileResponse(out, media_type="audio/wav")

    @app.get("/api/books/{book_id}/review")
    def review(book_id: str) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        attrib = load_artifact(AttributionFile, book.dir)
        if attrib is None:
            raise HTTPException(404, "run analyze first")
        return {
            "units": [
                {"id": u.id, "chapter": u.chapter, "text": u.text[:300]}
                for u in attrib.units
                if u.speaker == "ambiguous"
            ]
        }

    @app.post("/api/books/{book_id}/speakers")
    def set_speakers(book_id: str, fixes: dict[str, str]) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        attrib = load_artifact(AttributionFile, book.dir)
        if attrib is None:
            raise HTTPException(404, "run analyze first")
        fixed = 0
        for u in attrib.units:
            if u.id in fixes:
                u.speaker = fixes[u.id]
                fixed += 1
        attrib.needs_review = [u.id for u in attrib.units if u.speaker == "ambiguous"]
        save_artifact(attrib, book.dir)
        manifest = load_artifact(AudioManifest, book.dir)
        if manifest is not None:
            for uid in fixes:
                manifest.units.pop(uid, None)
            save_artifact(manifest, book.dir)
        return {"ok": True, "fixed": fixed}

    @app.get("/api/books/{book_id}/units")
    def units(book_id: str) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        attrib = load_artifact(AttributionFile, book.dir)
        if attrib is None:
            raise HTTPException(404, "run analyze first")
        manifest = load_artifact(AudioManifest, book.dir)
        done = manifest.units if manifest else {}
        return {
            "units": [
                {
                    "id": u.id,
                    "chapter": u.chapter,
                    "text": u.text,
                    "speaker": u.speaker,
                    "has_audio": done.get(u.id) is not None
                    and done[u.id].status == UnitStatus.done,
                }
                for u in attrib.units
            ]
        }

    @app.get("/api/books/{book_id}/audio/{unit_id}")
    def unit_audio(book_id: str, unit_id: str) -> FileResponse:
        book = _require_book(cfg, book_id)
        wav = book.unit_wav(unit_id)
        if not wav.exists():
            raise HTTPException(404, "not rendered")
        return FileResponse(wav, media_type="audio/wav")

    @app.get("/reader/{book_id}", response_class=HTMLResponse)
    def reader(book_id: str) -> HTMLResponse:
        page = STATIC / "reader.html"
        import json as _json

        return HTMLResponse(page.read_text().replace('"__BOOK_ID__"', _json.dumps(book_id)))

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
        eta_s = None
        if manifest and manifest.started_at > 0 and total > done + failed:
            rendered_this_run = sum(
                1 for u in manifest.units.values() if u.done_at > manifest.started_at
            )
            if rendered_this_run > 0:
                rate = (time.time() - manifest.started_at) / rendered_this_run
                eta_s = round(rate * (total - done - failed))
        log_tail = (d / "job.log").read_text()[-2000:] if (d / "job.log").exists() else ""
        return {
            "total": total,
            "done": done,
            "failed": failed,
            "busy": busy,
            "eta_s": eta_s,
            "log": log_tail,
        }

    @app.post("/api/books/{book_id}/cancel")
    def cancel(book_id: str) -> dict[str, Any]:
        _require_book(cfg, book_id)
        key = f"job:{book_id}"
        ev = _cancels.get(key)
        t = _jobs.get(key)
        if t is None or not t.is_alive():
            raise HTTPException(409, "no job running")
        if ev:
            ev.set()
        return {"cancelled": True}

    @app.post("/api/books/{book_id}/align")
    def align_words(book_id: str) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        try:
            from ..audio import align as align_mod
        except ImportError:
            raise HTTPException(422, "install castbook[align] for word timestamps") from None
        log = _log_to(book.dir / "job.log")
        log("[align] started")
        _spawn(f"job:{book_id}", lambda: align_mod.run(book, cfg, log=log), log)
        return {"started": True}

    @app.post("/api/books/{book_id}/export")
    def export(book_id: str, format: str | None = None) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        if format is not None and format not in ("m4b", "mp3", "both"):
            raise HTTPException(422, f"bad format {format!r}")
        log = _log_to(book.dir / "job.log")
        log(f"[export] started ({format or cfg.export.format})")

        def work() -> None:
            outs = export_book(book, cfg, format=format, log=log)
            log(f"[export] wrote {', '.join(p.name for p in outs)}")

        _spawn(f"job:{book_id}", work, log)
        return {"started": True}

    @app.get("/api/books/{book_id}/download/{name}")
    def download(book_id: str, name: str) -> FileResponse:
        path = (cfg.data_dir / book_id / "export" / name).resolve()
        if not path.is_file() or path.parent != (cfg.data_dir / book_id / "export").resolve():
            raise HTTPException(404, "no such export")
        return FileResponse(path, filename=path.name)

    return app


_backend: Backend | None = None
_backend_lock = threading.Lock()


def _preview_backend(cfg: Settings) -> Backend:
    global _backend
    with _backend_lock:
        if _backend is None:
            from ..tts import make_backend

            _backend = make_backend(cfg)
        return _backend


def _require_book(cfg: Settings, book_id: str) -> BookPaths:
    root = cfg.data_dir.resolve()
    book = BookPaths(cfg.data_dir, book_id)
    d = book.dir.resolve()
    if d == root or root not in d.parents or not d.is_dir():
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
