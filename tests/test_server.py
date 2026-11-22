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
