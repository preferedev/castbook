"""Local web UI — FastAPI shell over the same pipeline the CLI drives.

Long stages run in a thread pool; progress is read back from the on-disk
artifacts, so the UI survives a server restart.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.parse
from collections import Counter
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .. import net
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
from ..pipeline import (
    analyze_book,
    cast_book,
    export_book,
    generate_book,
    import_book,
    search_units,
    set_cover,
)
from ..reader import MAX_READ_CHARS, article_text, split_for_reading
from ..tts.backend import Backend
from ..workdir import BookPaths

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = net.MAX_UPLOAD
SUPPORTED_SUFFIXES = net.SUPPORTED_SUFFIXES


def _http(e: net.FetchError) -> HTTPException:
    return HTTPException(e.status, str(e))


_jobs: dict[str, threading.Thread] = {}
_cancels: dict[str, threading.Event] = {}
_run_all_current: str | None = None
_jobs_lock = threading.Lock()
_import_lock = threading.Lock()


def _log_to(path: Path) -> Callable[[str], None]:
    lock = threading.Lock()
    path.parent.mkdir(parents=True, exist_ok=True)

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


def create_app(cfg: Settings, token: str | None = None) -> FastAPI:
    app = FastAPI(title="Castbook")

    if token:
        from fastapi import Request
        from fastapi.responses import JSONResponse

        @app.middleware("http")
        async def _auth(request: Request, call_next):  # type: ignore[no-untyped-def]
            if not request.url.path.startswith("/favicon"):
                given = request.headers.get("x-castbook-token") or request.query_params.get("token")
                if given != token:
                    return JSONResponse({"detail": "missing token"}, status_code=401)
            return await call_next(request)

    def _page(name: str) -> str:
        html = (STATIC / name).read_text()
        if token:
            html = html.replace("</head>", f'<meta name="cb-token" content="{token}"></head>')
        return html

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _page("index.html")

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

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return cfg.model_dump(mode="json")

    @app.put("/api/config")
    def put_config(patch: dict[str, Any]) -> dict[str, Any]:
        tts = patch.get("tts") or {}
        backend = tts.get("backend")
        if backend is not None:
            if backend not in ("kokoro", "pocket", "qwen"):
                raise HTTPException(422, f"unknown tts backend: {backend}")
            cfg.tts.backend = backend
            recast = _drop_mismatched_casting(cfg)
            global _backend
            with _backend_lock:
                _backend = None
        else:
            recast = []
        cfg.save()
        out = cfg.model_dump(mode="json")
        out["recast"] = recast
        return out

    @app.get("/api/voices")
    def voices() -> list[dict[str, Any]]:
        from ..cast.library import POCKET_LIBRARY

        lib = {"kokoro": LIBRARY, "pocket": POCKET_LIBRARY}.get(cfg.tts.backend, [])
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

    def _save_upload(file: UploadFile, tmp_dir: Path) -> Path:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise HTTPException(400, f"unsupported format {suffix}")
        tmp_path = tmp_dir / Path(file.filename or f"book{suffix}").name
        size = 0
        with tmp_path.open("wb") as out:
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "file too large")
                out.write(chunk)
        return tmp_path

    def _save_url(url: str, tmp_dir: Path) -> Path:
        try:
            return net.fetch_book_url(url, tmp_dir)
        except net.FetchError as e:
            raise _http(e) from e

    @app.get("/api/gutenberg")
    def gutenberg(q: str = "", page: int = 1) -> dict[str, Any]:
        import json

        params = {"page": str(page)}
        if q.strip():
            params["search"] = q.strip()
        url = "https://gutendex.com/books/?" + urllib.parse.urlencode(params)
        for attempt in range(2):
            try:
                with net.open_url(url, timeout=30) as resp:
                    data = json.loads(resp.read())
                break
            except TimeoutError:
                if attempt:
                    raise HTTPException(502, "gutendex timed out — retry") from None
            except net.FetchError as e:
                raise HTTPException(502, f"gutendex failed: {e}") from e
        results = []
        for r in data.get("results", []):
            fmts = r.get("formats") or {}
            epub = next((u for k, u in fmts.items() if "epub" in k), None)
            if not epub:
                continue
            results.append(
                {
                    "id": r.get("id"),
                    "title": r.get("title", "?"),
                    "author": ((r.get("authors") or [{}])[0] or {}).get("name", ""),
                    "downloads": r.get("download_count", 0),
                    "url": epub,
                }
            )
        return {"results": results, "next": bool(data.get("next"))}

    @app.post("/api/import")
    def upload(
        file: Annotated[UploadFile | None, File()] = None,
        url: Annotated[str | None, Form()] = None,
    ) -> dict[str, Any]:
        if (file is None) == (not url):
            raise HTTPException(400, "pass exactly one of file or url")
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            if url:
                tmp_path = _save_url(url, tmp_dir)
            else:
                tmp_path = _save_upload(file or UploadFile(BytesIO(), filename=None), tmp_dir)
            if tmp_path.stat().st_size == 0:
                raise HTTPException(400, "empty file")
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
        stats: dict[str, dict[str, float | int]] = {}
        for u in attrib.units if attrib else []:
            s = stats.setdefault(u.speaker, {"units": 0, "words": 0, "minutes": 0.0})
            s["units"] += 1
            s["words"] += len(u.text.split())
            s["minutes"] += len(u.text) / 15 / 60
        for s in stats.values():
            s["minutes"] = round(s["minutes"], 1)
        return {
            "book_id": book_id,
            "characters": [c.model_dump() for c in cast_f.characters] if cast_f else [],
            "casting": {k: v.model_dump() for k, v in casting.map.items()} if casting else {},
            "needs_review": attrib.needs_review if attrib else [],
            "units": len(attrib.units) if attrib else 0,
            "unit_counts": (dict(Counter(u.speaker for u in attrib.units)) if attrib else {}),
            "speaker_stats": stats,
        }

    @app.get("/api/books/{book_id}/estimate")
    def estimate(book_id: str) -> dict[str, Any]:
        from ..tts import estimate_render

        book = _require_book(cfg, book_id)
        try:
            return estimate_render(book, cfg)
        except FileNotFoundError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/books/{book_id}/cover")
    def cover(book_id: str) -> FileResponse:
        book = _require_book(cfg, book_id)
        for base in (book.dir, book.source):
            for f in sorted(base.glob("cover.*")):
                if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                    return FileResponse(f)
        raise HTTPException(404, "no cover")

    @app.post("/api/books/{book_id}/cover")
    async def set_book_cover(book_id: str, file: Annotated[UploadFile, File()]) -> dict[str, str]:
        book = _require_book(cfg, book_id)
        data = await file.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "cover image too large")
        tmp = book.dir / ".cover-upload"
        tmp.write_bytes(data)
        try:
            name = set_cover(book, tmp)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        finally:
            tmp.unlink(missing_ok=True)
        return {"cover": name}

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
        if _run_all_current == book_id:
            raise HTTPException(409, "run-all is processing this book")
        with _jobs_lock:
            busy = [k for k, t in _jobs.items() if k.endswith(f":{book_id}") and t.is_alive()]
        if busy:
            raise HTTPException(409, f"job still running: {busy[0].split(':')[0]}")
        shutil.rmtree(book.dir)
        return {"ok": True}

    @app.post("/api/books/{book_id}/cast")
    def set_cast(book_id: str, spec: dict[str, Any], flat: bool = Query(False)) -> dict[str, Any]:
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
        cast_book(book, cfg, overrides=voices, speeds=speeds, flat=flat)
        return {"ok": True}

    @app.get("/api/books/{book_id}/voicepack")
    def get_voicepack(book_id: str) -> dict[str, Any]:
        from ..cast.voicepack import export_pack

        book = _require_book(cfg, book_id)
        try:
            return export_pack(book)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/books/{book_id}/voicepack")
    def put_voicepack(book_id: str, pack: dict[str, Any]) -> dict[str, Any]:
        from ..cast.voicepack import apply_pack

        book = _require_book(cfg, book_id)
        try:
            return apply_pack(book, pack, cfg.tts.backend)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/books/{book_id}/clone")
    def clone_voice(
        book_id: str,
        speaker: str,
        file: Annotated[UploadFile | None, File()] = None,
    ) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        if cfg.tts.backend != "pocket":
            raise HTTPException(422, "cloning needs tts.backend = 'pocket'")
        if file is None or not file.filename:
            raise HTTPException(400, "no clip uploaded")
        suffix = Path(file.filename).suffix.lower()
        if suffix not in {".wav", ".mp3", ".flac"}:
            raise HTTPException(400, "clip must be .wav, .mp3 or .flac")
        safe = re.sub(r"[^a-z0-9_-]", "", speaker.lower())
        if not safe:
            raise HTTPException(422, f"bad speaker id {speaker!r}")
        dest_dir = book.dir / "voices"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{safe}-{int(time.time())}{suffix}"
        size = 0
        with dest.open("wb") as out:
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, "file too large")
                out.write(chunk)
        casting = load_artifact(CastingFile, book.dir)
        overrides = {sp: spec.voice for sp, spec in casting.map.items()} if casting else {}
        speeds = {sp: spec.speed for sp, spec in casting.map.items()} if casting else {}
        overrides[safe] = str(dest)
        cast_book(book, cfg, overrides=overrides, speeds=speeds)
        return {"ok": True, "clip": str(dest)}

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

    @app.post("/api/books/{book_id}/run")
    def run(book_id: str, quality: str | None = None) -> dict[str, Any]:
        """Full pipeline in one job: analyze → cast → generate → export."""
        book = _require_book(cfg, book_id)
        log = _log_to(book.dir / "job.log")
        job_cfg = cfg
        if quality is not None:
            from ..config import QUALITY_PRESETS

            preset = QUALITY_PRESETS.get(quality)
            if preset is None:
                raise HTTPException(422, f"unknown quality: {quality}")
            job_cfg = cfg.model_copy(deep=True)
            job_cfg.llm.backend, job_cfg.tts.backend = preset
            log(f"[quality] {quality}: llm={preset[0]} tts={preset[1]}")

        def work() -> None:
            cancel = _cancels[f"job:{book_id}"]
            analyze_book(book, job_cfg, log)
            cast_book(book, job_cfg, log=log)
            if cancel.is_set():
                return
            generate_book(book, job_cfg, log=log, cancel=cancel)
            if not cancel.is_set():
                log("[export] started")
                outs = export_book(book, job_cfg, log=log)
                log(f"[export] wrote {', '.join(p.name for p in outs)}")

        _spawn(f"job:{book_id}", work, log)
        return {"ok": True}

    @app.post("/api/run-all")
    def run_all(quality: str | None = None) -> dict[str, Any]:
        """Every book through the pipeline in one job — resumable per book."""
        job_cfg = cfg
        if quality is not None:
            from ..config import QUALITY_PRESETS

            preset = QUALITY_PRESETS.get(quality)
            if preset is None:
                raise HTTPException(422, f"unknown quality: {quality}")
            job_cfg = cfg.model_copy(deep=True)
            job_cfg.llm.backend, job_cfg.tts.backend = preset

        log = _log_to(cfg.data_dir / "run-all.log")
        book_ids = (
            [
                d.name
                for d in sorted(cfg.data_dir.iterdir())
                if d.is_dir() and load_artifact(ChaptersFile, d) is not None
            ]
            if cfg.data_dir.is_dir()
            else []
        )
        if not book_ids:
            raise HTTPException(404, "no imported books")
        if any(k.startswith("job:") and t.is_alive() for k, t in _jobs.items()):
            raise HTTPException(409, "a per-book job is running — cancel it first")

        def work() -> None:
            global _run_all_current
            cancel = _cancels["run-all"]
            for bid in book_ids:
                if cancel.is_set():
                    return
                if not (cfg.data_dir / bid).is_dir():
                    continue  # deleted mid-run
                if (t := _jobs.get(f"job:{bid}")) is not None and t.is_alive():
                    log(f"[run-all] {bid} has its own job running — skipped")
                    continue
                book = BookPaths(cfg.data_dir, bid)
                log(f"[run-all] === {bid} ===")
                _run_all_current = bid
                try:
                    analyze_book(book, job_cfg, log)
                    cast_book(book, job_cfg, log=log)
                    if cancel.is_set():
                        return
                    generate_book(book, job_cfg, log=log, cancel=cancel)
                    if not cancel.is_set():
                        outs = export_book(book, job_cfg, log=log)
                        log(f"[run-all] {bid}: {', '.join(p.name for p in outs)}")
                finally:
                    _run_all_current = None
            log("[run-all] library complete")

        _spawn("run-all", work, log)
        return {"ok": True, "books": book_ids}

    @app.get("/api/run-all/log")
    def run_all_log(lines: int = 40) -> dict[str, Any]:
        text = ""
        path = cfg.data_dir / "run-all.log"
        if path.exists():
            text = path.read_text(errors="replace")
        t = _jobs.get("run-all")
        return {
            "lines": text.splitlines()[-lines:],
            "running": t is not None and t.is_alive(),
        }

    @app.post("/api/run-all/cancel")
    def run_all_cancel() -> dict[str, Any]:
        t = _jobs.get("run-all")
        if t is None or not t.is_alive():
            raise HTTPException(409, "no run-all job running")
        ev = _cancels.get("run-all")
        if ev:
            ev.set()
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

    @app.get("/api/books/{book_id}/chapters")
    def chapters(book_id: str) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        ch = load_artifact(ChaptersFile, book.dir)
        if ch is None:
            raise HTTPException(404, "not imported")
        manifest = load_artifact(AudioManifest, book.dir)
        attrib = load_artifact(AttributionFile, book.dir)
        rendered: Counter[int] = Counter()
        if manifest and attrib:
            ch_by_id = {u.id: u.chapter for u in attrib.units}
            for uid, e in manifest.units.items():
                if e.status == UnitStatus.done and (c := ch_by_id.get(uid)) is not None:
                    rendered[c] += 1
        return {
            "chapters": [
                {
                    "index": c.index,
                    "title": c.title,
                    "words": c.word_count,
                    "rendered": rendered.get(c.index, 0) > 0,
                }
                for c in ch.chapters
            ]
        }

    @app.get("/api/books/{book_id}/chapters/{chapter}/audio")
    def chapter_audio(book_id: str, chapter: int) -> FileResponse:
        book = _require_book(cfg, book_id)
        wav = book.dir / "audio" / f"ch{chapter:03d}.wav"
        if not wav.exists():
            raise HTTPException(404, "chapter not rendered")
        return FileResponse(wav, media_type="audio/wav")

    @app.get("/api/books/{book_id}/chapters/{chapter}/transcript")
    def chapter_transcript(book_id: str, chapter: int, fmt: str | None = None) -> FileResponse:
        book = _require_book(cfg, book_id)
        tr_dir = book.dir / "transcript"
        for ext in [fmt] if fmt else ["srt", "vtt", "txt"]:
            f = tr_dir / f"ch{chapter:03d}.{ext}"
            if f.exists():
                return FileResponse(f)
        raise HTTPException(404, "no transcript — run `castbook transcript`")

    @app.post("/api/books/{book_id}/transcript")
    def make_transcript(book_id: str, fmt: str = "srt") -> dict[str, Any]:
        from ..transcript import write_transcript

        book = _require_book(cfg, book_id)
        if fmt not in ("srt", "vtt", "txt"):
            raise HTTPException(400, "fmt must be srt, vtt or txt")
        try:
            written = write_transcript(book, book.dir / "transcript", fmt)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        first = int(written[0].stem[2:]) if written else None
        return {"ok": True, "count": len(written), "first_chapter": first}

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

    @app.post("/api/read")
    def read_now(spec: dict[str, Any]) -> dict[str, Any]:
        """Speechify-style: paste text or a URL, hear it now (single voice)."""
        text = str(spec.get("text") or "").strip()
        url = str(spec.get("url") or "").strip()
        if url:
            try:
                with net.open_url(url, timeout=30) as resp:
                    net.assert_public_peer(resp, resp.geturl())
                    raw = resp.read(MAX_READ_CHARS + 1)
            except net.FetchError as e:
                raise _http(e) from e
            if len(raw) > MAX_READ_CHARS:
                raise HTTPException(413, "page too large")
            body = raw.decode("utf-8", "replace")
            text = article_text(body) if "<" in body[:200] else body
        text = text[:MAX_READ_CHARS].strip()
        chunks = split_for_reading(text)
        if not chunks:
            raise HTTPException(400, "nothing to read")
        if len(chunks) > 400:
            raise HTTPException(413, "too long")
        voice = str(spec.get("voice") or "af_sarah")
        speed = float(spec.get("speed") or 1.0)
        speed = speed if 0 < speed <= 2 else 1.0
        read_id = secrets.token_hex(6)
        reads_root = cfg.data_dir / "_reads"
        reads_root.mkdir(parents=True, exist_ok=True)
        stale = sorted(reads_root.iterdir(), key=lambda p: p.stat().st_mtime)
        for old in stale[:-31]:  # keep the newest 32 reads
            job = _jobs.get(f"read:{old.name}")
            if job is not None and job.is_alive():
                continue
            shutil.rmtree(old, ignore_errors=True)
        d = reads_root / read_id
        d.mkdir(parents=True)
        status: dict[str, Any] = {"done": 0, "total": len(chunks)}

        def save_status() -> None:
            tmp = d / "status.json.tmp"
            tmp.write_text(json.dumps(status))
            tmp.replace(d / "status.json")

        save_status()

        def work() -> None:
            try:
                backend = _preview_backend(cfg)
                vspec = VoiceSpec(backend=cfg.tts.backend, voice=voice, speed=speed)
                cancel = _cancels.get(f"read:{read_id}")
                for i, chunk in enumerate(chunks):
                    if cancel is not None and cancel.is_set():
                        break
                    backend.synthesize(chunk, vspec, d / f"{i:04}.wav")
                    status["done"] = i + 1
                    save_status()
            except Exception as e:
                status["error"] = str(e)
                save_status()
                raise

        _spawn(f"read:{read_id}", work, _log_to(d / "read.log"))
        return {"id": read_id, "total": len(chunks)}

    @app.get("/api/read/{read_id}/status")
    def read_status(read_id: str) -> dict[str, Any]:
        f = _read_dir(cfg, read_id) / "status.json"
        if not f.exists():
            raise HTTPException(404, "no such read")
        try:
            return json.loads(f.read_text())  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            raise HTTPException(503, "status updating") from None

    @app.get("/api/read/{read_id}/audio/{i}")
    def read_audio(read_id: str, i: int) -> FileResponse:
        f = _read_dir(cfg, read_id) / f"{i:04}.wav"
        if not f.exists():
            raise HTTPException(404)
        return FileResponse(f, media_type="audio/wav")

    @app.post("/api/read/{read_id}/cancel")
    def read_cancel(read_id: str) -> dict[str, Any]:
        _read_dir(cfg, read_id)
        _cancels.setdefault(f"read:{read_id}", threading.Event()).set()
        return {"ok": True}

    @app.get("/api/books/{book_id}/review")
    def review(book_id: str) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        attrib = load_artifact(AttributionFile, book.dir)
        if attrib is None:
            raise HTTPException(404, "run analyze first")
        return {
            "units": [
                {
                    "id": u.id,
                    "chapter": u.chapter,
                    "text": u.text[:300],
                    "guess": u.guess and u.speaker != "ambiguous",
                }
                for u in attrib.units
                if u.speaker == "ambiguous" or u.guess
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
                u.guess = False
                fixed += 1
        attrib.needs_review = [u.id for u in attrib.units if u.speaker == "ambiguous" or u.guess]
        save_artifact(attrib, book.dir)
        manifest = load_artifact(AudioManifest, book.dir)
        if manifest is not None:
            for uid in fixes:
                manifest.units.pop(uid, None)
            save_artifact(manifest, book.dir)
        return {"ok": True, "fixed": fixed}

    @app.get("/api/books/{book_id}/search")
    def search(book_id: str, q: str = Query(min_length=1)) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        return {"matches": search_units(book.dir, q)}

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
        import json as _json

        return HTMLResponse(_page("reader.html").replace('"__BOOK_ID__"', _json.dumps(book_id)))

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
        audio_dir = d / "audio"
        chapters_ready = (
            sorted(int(p.stem[2:]) for p in audio_dir.glob("ch*.wav") if p.stem[2:].isdigit())
            if audio_dir.is_dir()
            else []
        )
        return {
            "total": total,
            "done": done,
            "failed": failed,
            "busy": busy,
            "eta_s": eta_s,
            "log": log_tail,
            "audio_chapters": chapters_ready,
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
    def export(
        book_id: str,
        format: str | None = None,
        layout: str | None = None,
        chapters: str | None = None,
    ) -> dict[str, Any]:
        book = _require_book(cfg, book_id)
        if format is not None and format not in ("m4b", "mp3", "both"):
            raise HTTPException(422, f"bad format {format!r}")
        if layout is not None and layout not in ("abs",):
            raise HTTPException(422, f"bad layout {layout!r}")
        only: set[int] | None = None
        if chapters:
            try:
                only = set()
                for part in chapters.split(","):
                    lo, _, hi = part.strip().partition("-")
                    only.update(range(int(lo), int(hi) + 1) if hi else [int(lo)])
            except ValueError:
                raise HTTPException(422, f"bad chapters {chapters!r}") from None
        log = _log_to(book.dir / "job.log")
        log(f"[export] started ({format or cfg.export.format})")

        def work() -> None:
            outs = export_book(book, cfg, format=format, layout=layout, only=only, log=log)
            log(f"[export] wrote {', '.join(p.name for p in outs)}")

        _spawn(f"job:{book_id}", work, log)
        return {"started": True}

    @app.get("/api/books/{book_id}/download/{name:path}")
    def download(book_id: str, name: str) -> FileResponse:
        export_dir = (cfg.data_dir / book_id / "export").resolve()
        path = (export_dir / name).resolve()
        if not path.is_file() or export_dir not in path.parents:
            raise HTTPException(404, "no such export")
        return FileResponse(path, filename=path.name)

    return app


_backend: Backend | None = None
_backend_lock = threading.Lock()


def _read_dir(cfg: Settings, read_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}", read_id):
        raise HTTPException(404, "no such read")
    return cfg.data_dir / "_reads" / read_id


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
        "exports": [
            str(p.relative_to(d / "export")) for p in (d / "export").rglob("*") if p.is_file()
        ]
        if (d / "export").exists()
        else [],
    }


def _drop_mismatched_casting(cfg: Settings) -> list[str]:
    """Backend switch invalidates saved voice specs from the previous backend."""
    recast: list[str] = []
    if not cfg.data_dir.is_dir():
        return recast
    for d in sorted(cfg.data_dir.iterdir()):
        casting = load_artifact(CastingFile, d)
        if not casting:
            continue
        stale = [k for k, v in casting.map.items() if v.backend != cfg.tts.backend]
        if stale:
            for k in stale:
                del casting.map[k]
            save_artifact(casting, d)
            recast.append(d.name)
    return recast
