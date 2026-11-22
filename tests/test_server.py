"""Web API: import, review list, speaker overrides, voice preview."""

from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from castbook.app.server import create_app
from castbook.artifacts import VoiceSpec
from castbook.config import Settings
from castbook.pipeline import analyze_book
from castbook.tts.backend import SAMPLE_RATE
from castbook.tts.backend import Backend as TTSBackend
from castbook.workdir import BookPaths


class FakeBackend(TTSBackend):
    def capabilities(self):  # type: ignore[no-untyped-def]
        from castbook.tts.backend import Capabilities

        return Capabilities()

    def synthesize(self, text: str, voice: VoiceSpec, out_wav: Path) -> float:
        sf.write(out_wav, np.ones(SAMPLE_RATE // 10, dtype=np.float32), SAMPLE_RATE)
        return 0.1


def _client(tmp_path: Path, monkeypatch) -> TestClient:  # type: ignore[no-untyped-def]
    cfg = Settings(data_dir=tmp_path / "books", models_dir=tmp_path / "models")
    fake = FakeBackend()
    monkeypatch.setattr("castbook.app.server._preview_backend", lambda c: fake)
    return TestClient(create_app(cfg))


def _import_txt(client: TestClient, tmp_path: Path) -> str:
    src = tmp_path / "book.txt"
    src.write_text("CHAPTER I\n\nHello, said Alice. The cat grinned.\n" * 5)
    r = client.post("/api/import", files={"file": ("book.txt", src.read_bytes())})
    assert r.status_code == 200
    return r.json()["book_id"]


def test_import_and_detail(client_setup) -> None:  # type: ignore[no-untyped-def]
    client, tmp_path = client_setup
    book_id = _import_txt(client, tmp_path)
    assert client.get("/api/books").status_code == 200
    d = client.get(f"/api/books/{book_id}")
    assert d.status_code == 200
    assert d.json()["book_id"] == book_id


def test_review_and_speakers(client_setup) -> None:  # type: ignore[no-untyped-def]
    client, tmp_path = client_setup
    book_id = _import_txt(client, tmp_path)
    assert client.get(f"/api/books/{book_id}/review").status_code == 404
    analyze_book(BookPaths(tmp_path / "books", book_id), Settings(data_dir=tmp_path / "books"))
    r = client.get(f"/api/books/{book_id}/review")
    assert r.status_code == 200
    units = r.json()["units"]
    fix = {u["id"]: "narrator" for u in units[:2]}
    r = client.post(f"/api/books/{book_id}/speakers", json=fix)
    assert r.status_code == 200 and r.json()["fixed"] == len(fix)


def test_preview_serves_audio(client_setup) -> None:  # type: ignore[no-untyped-def]
    client, _ = client_setup
    r = client.post("/api/preview", json={"voice": "af_sarah", "text": "hi"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert len(r.content) > 100


def test_unknown_book_404(client_setup) -> None:  # type: ignore[no-untyped-def]
    client, _ = client_setup
    assert client.get("/api/books/nope").status_code == 404


def test_regenerate_pops_chapter_units(client_setup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, tmp_path = client_setup
    book_id = _import_txt(client, tmp_path)
    book = BookPaths(tmp_path / "books", book_id)
    cfg = Settings(data_dir=tmp_path / "books")
    analyze_book(book, cfg)
    from castbook.artifacts import (
        AttributionFile,
        AudioEntry,
        AudioManifest,
        load_artifact,
        save_artifact,
    )

    attrib = load_artifact(AttributionFile, book.dir)
    assert attrib is not None
    manifest = AudioManifest(book_id=book_id, input_hash=attrib.input_hash)
    for u in attrib.units:
        manifest.units[u.id] = AudioEntry(
            path=f"{u.id}.wav", duration_s=0.1, status="done", unit_hash=f"h-{u.id}"
        )
    save_artifact(manifest, book.dir)
    spawned = []
    monkeypatch.setattr("castbook.app.server.generate_book", lambda *a, **k: spawned.append(k))
    r = client.post(f"/api/books/{book_id}/regenerate?chapters=1")
    assert r.status_code == 200
    assert r.json()["popped"] == len([u for u in attrib.units if u.chapter == 1])
    import time

    for _ in range(50):
        if spawned:
            break
        time.sleep(0.1)
    m2 = load_artifact(AudioManifest, book.dir)
    assert all(u.chapter != 1 or u.id not in m2.units for u in attrib.units)
    assert spawned and spawned[0]["chapters"] == {1}
    r = client.post(f"/api/books/{book_id}/regenerate?chapters=")
    assert r.status_code in (409, 422)


def test_models_endpoints(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    models = {m["id"]: m for m in client.get("/api/models").json()}
    assert "kokoro-v1" in models and "qwen3-4b-q4" in models
    assert all("license" in m and "downloaded" in m for m in models.values())
    assert client.post("/api/models/pull?ids=kokoro-v1").json() == {"ok": True}
    log = client.get("/api/models/log").json()["lines"]
    assert any("kokoro-v1" in line for line in log)


def test_config_backend_switch(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    cfg_file = tmp_path / "config.toml"
    monkeypatch.setenv("CASTBOOK_CONFIG", str(cfg_file))
    client = _client(tmp_path, monkeypatch)
    r = client.put("/api/config", json={"tts": {"backend": "nope"}})
    assert r.status_code == 422
    r = client.put("/api/config", json={"tts": {"backend": "pocket"}})
    assert r.status_code == 200 and r.json()["tts"]["backend"] == "pocket"
    assert 'backend = "pocket"' in cfg_file.read_text()


def test_token_gate(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    cfg = Settings(data_dir=tmp_path / "books", models_dir=tmp_path / "models")
    client = TestClient(create_app(cfg, token="sekret"))
    assert client.get("/api/books").status_code == 401
    assert client.get("/").status_code == 401
    assert client.get("/reader/x").status_code == 401
    assert client.get("/api/books", headers={"x-castbook-token": "sekret"}).status_code == 200
    assert client.get("/api/books?token=sekret").status_code == 200
    assert "cb-token" in client.get("/?token=sekret").text


def test_backend_switch_drops_stale_casting(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from castbook.artifacts import CastingFile, load_artifact, save_artifact

    monkeypatch.setenv("CASTBOOK_CONFIG", str(tmp_path / "config.toml"))
    client = _client(tmp_path, monkeypatch)
    d = tmp_path / "books" / "b1"
    d.mkdir(parents=True)
    save_artifact(
        CastingFile(
            book_id="b1",
            input_hash="x",
            map={
                "a": VoiceSpec(backend="kokoro", voice="af_heart"),
                "b": VoiceSpec(backend="pocket", voice="paul"),
            },
        ),
        d,
    )
    r = client.put("/api/config", json={"tts": {"backend": "pocket"}}).json()
    assert r["recast"] == ["b1"]
    assert list(load_artifact(CastingFile, d).map) == ["b"]


def test_import_from_url(client_setup) -> None:  # type: ignore[no-untyped-def]
    import functools
    import http.server
    import threading

    client, tmp_path = client_setup
    srv = http.server.HTTPServer(
        ("127.0.0.1", 0),
        functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path)),
    )
    (tmp_path / "book.txt").write_text("CHAPTER I\n\nHello, said Alice.\n" * 5)
    monkeypatch2 = __import__("pytest").MonkeyPatch()
    monkeypatch2.setattr("castbook.app.server._public_host", lambda url: None)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        port = srv.server_address[1]
        r = client.post("/api/import", data={"url": f"http://127.0.0.1:{port}/book.txt"})
        assert r.status_code == 200, r.text
        assert r.json()["book_id"]
        assert client.post("/api/import", data={"url": "ftp://x/book.txt"}).status_code == 400
        assert client.post("/api/import").status_code == 400
        assert (
            client.post(
                "/api/import",
                data={"url": f"http://127.0.0.1:{port}/missing.epub"},
            ).status_code
            == 502
        )
    finally:
        srv.shutdown()
        monkeypatch2.undo()


def test_url_import_rejects_private_hosts() -> None:
    from castbook.app.server import _public_host

    for bad in (
        "http://127.0.0.1/x.epub",
        "http://localhost/x.epub",
        "http://10.0.0.1/x.epub",
        "http://169.254.169.254/latest",
    ):
        try:
            _public_host(bad)
        except Exception as e:
            assert getattr(e, "status_code", None) in (400, 502), bad
        else:
            raise AssertionError(f"{bad} not rejected")
    _public_host("http://93.184.216.34/book.epub")  # public IP literal passes


def test_transcript_endpoints(client_setup) -> None:  # type: ignore[no-untyped-def]
    client, tmp_path = client_setup
    book_id = _import_txt(client, tmp_path)
    r = client.post(f"/api/books/{book_id}/transcript")
    assert r.status_code == 422  # needs analyze + generate
    assert client.post(f"/api/books/{book_id}/transcript?fmt=docx").status_code == 400
    assert client.get(f"/api/books/{book_id}/chapters/1/transcript").status_code == 404
