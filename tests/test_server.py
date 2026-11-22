"""Web API: import, review list, speaker overrides, voice preview."""

import time
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
    monkeypatch2.setattr("castbook.net.assert_public_host", lambda url: None)
    monkeypatch2.setattr("castbook.net.assert_public_peer", lambda resp, url: None)
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
    from castbook.net import FetchError, assert_public_host

    for bad in (
        "http://127.0.0.1/x.epub",
        "http://localhost/x.epub",
        "http://10.0.0.1/x.epub",
        "http://169.254.169.254/latest",
    ):
        try:
            assert_public_host(bad)
        except FetchError as e:
            assert e.status == 400, bad
        else:
            raise AssertionError(f"{bad} not rejected")
    assert_public_host("http://93.184.216.34/book.epub")  # public IP literal passes


def test_transcript_endpoints(client_setup) -> None:  # type: ignore[no-untyped-def]
    client, tmp_path = client_setup
    book_id = _import_txt(client, tmp_path)
    r = client.post(f"/api/books/{book_id}/transcript")
    assert r.status_code == 422  # needs analyze + generate
    assert client.post(f"/api/books/{book_id}/transcript?fmt=docx").status_code == 400
    assert client.get(f"/api/books/{book_id}/chapters/0/transcript").status_code == 404
    assert client.get(f"/api/books/{book_id}/chapters/0/transcript?fmt=vtt").status_code == 404


def test_gutenberg_endpoint(client_setup) -> None:  # type: ignore[no-untyped-def]
    import io
    import json

    client, _ = client_setup
    body = json.dumps(
        {
            "next": None,
            "results": [
                {
                    "id": 1342,
                    "title": "Pride and Prejudice",
                    "authors": [{"name": "Austen, Jane"}],
                    "download_count": 50000,
                    "formats": {
                        "text/html": "https://gutenberg.org/ebooks/1342.html",
                        "application/epub+zip": "https://gutenberg.org/ebooks/1342.epub3.images",
                    },
                },
                {"id": 1, "title": "No EPUB", "formats": {"text/html": "x"}},
            ],
        }
    ).encode()

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    mp = __import__("pytest").MonkeyPatch()
    mp.setattr("castbook.net.assert_public_host", lambda url: None)
    mp.setattr(
        "castbook.net._opener",
        type("O", (), {"open": lambda self, req, timeout=0: _Resp(body)})(),
    )
    try:
        r = client.get("/api/gutenberg?q=pride")
        assert r.status_code == 200, r.text
        rows = r.json()["results"]
        assert len(rows) == 1 and rows[0]["title"] == "Pride and Prejudice"
        assert rows[0]["author"] == "Austen, Jane" and rows[0]["url"].endswith("epub3.images")
        assert r.json()["next"] is False
    finally:
        mp.undo()


def test_download_nested_and_traversal(client_setup) -> None:  # type: ignore[no-untyped-def]
    client, tmp_path = client_setup
    book_id = _import_txt(client, tmp_path)
    book_dir = tmp_path / "books" / book_id
    sub = book_dir / "export" / "Some Title-1-2"
    sub.mkdir(parents=True)
    (sub / "01 - One.mp3").write_bytes(b"mp3")
    (book_dir / "export" / "book.m4b").write_bytes(b"m4b")

    r = client.get("/api/books")
    assert r.status_code == 200
    exports = next(b for b in r.json() if b["book_id"] == book_id)["exports"]
    assert "Some Title-1-2/01 - One.mp3" in exports and "book.m4b" in exports

    from urllib.parse import quote

    r = client.get(f"/api/books/{book_id}/download/{quote('Some Title-1-2/01 - One.mp3')}")
    assert r.status_code == 200 and r.content == b"mp3"
    r = client.get(f"/api/books/{book_id}/download/..%2F..%2Fsecret.txt")
    assert r.status_code == 404


def test_read_now_flow(client_setup) -> None:  # type: ignore[no-untyped-def]
    client, _tmp_path = client_setup
    r = client.post("/api/read", json={"text": "Hello world. " * 30})
    assert r.status_code == 200
    read_id, total = r.json()["id"], r.json()["total"]
    for _ in range(100):
        s = client.get(f"/api/read/{read_id}/status").json()
        if s["done"] >= total:
            break
        time.sleep(0.05)
    assert s["done"] == total
    a = client.get(f"/api/read/{read_id}/audio/0")
    assert a.status_code == 200 and len(a.content) > 100
    assert client.get("/api/read/deadbeef/status").status_code == 404
    assert client.post("/api/read", json={}).status_code == 400


def test_read_rejects_nonpublic_url(client_setup) -> None:  # type: ignore[no-untyped-def]
    client, _ = client_setup
    r = client.post("/api/read", json={"url": "http://169.254.169.254/latest"})
    assert r.status_code == 400


def test_run_quality_param(client_setup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, tmp_path = client_setup
    monkeypatch.setattr("castbook.app.server.generate_book", lambda *a, **k: None)
    monkeypatch.setattr("castbook.app.server.export_book", lambda *a, **k: [])
    book_id = _import_txt(client, tmp_path)
    assert client.post(f"/api/books/{book_id}/run?quality=bogus").status_code == 422
    r = client.post(f"/api/books/{book_id}/run?quality=fast")
    assert r.status_code == 200


def test_custom_cover(client_setup) -> None:  # type: ignore[no-untyped-def]
    client, tmp_path = client_setup
    book_id = _import_txt(client, tmp_path)
    assert client.get(f"/api/books/{book_id}/cover").status_code == 404
    r = client.post(f"/api/books/{book_id}/cover", files={"file": ("x.txt", b"hello")})
    assert r.status_code == 422
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    r = client.post(f"/api/books/{book_id}/cover", files={"file": ("c.png", png)})
    assert r.status_code == 200
    assert r.json()["cover"] == "cover.png"
    got = client.get(f"/api/books/{book_id}/cover")
    assert got.status_code == 200
    assert got.content == png
