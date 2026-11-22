def test_reimport_same_content_dedupes(tmp_path, monkeypatch) -> None:
    from castbook.config import Settings
    from castbook.pipeline import import_book

    cfg = Settings(data_dir=tmp_path / "data")
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("CHAPTER I\n\nSame text.\n\nMore text.")
    b.write_text(a.read_text())
    first = import_book(a, cfg, log=lambda s: None)
    second = import_book(b, cfg, log=lambda s: None)
    assert second.book_id == first.book_id
    again = import_book(a, cfg, log=lambda s: None)
    assert again.book_id == first.book_id
    n_books = sum(1 for d in cfg.data_dir.iterdir() if (d / "chapters.json").exists())
    assert n_books == 1


def test_search_units(tmp_path) -> None:
    from castbook.artifacts import AttributionFile, CastFile, Character, Unit, save_artifact
    from castbook.pipeline import search_units

    d = tmp_path / "b"
    d.mkdir()
    save_artifact(
        AttributionFile(
            book_id="b",
            attributor="t",
            input_hash="h",
            units=[
                Unit(id="u1", chapter=2, text="Hello there, said the cat.", speaker="cat"),
                Unit(id="u2", chapter=5, text="Nothing here.", speaker="narrator"),
            ],
        ),
        d,
    )
    save_artifact(
        CastFile(
            book_id="b",
            input_hash="h",
            characters=[
                Character(id="cat", name="Cheshire Cat", kind="character"),
            ],
        ),
        d,
    )
    hits = search_units(d, "hello")
    assert hits[0]["chapter"] == 2 and hits[0]["speaker"] == "Cheshire Cat"
    assert "Hello there" in hits[0]["excerpt"]
    assert search_units(d, "zzz") == []


def test_rename_speaker(tmp_path) -> None:
    from castbook.analyze.reconcile import rename_speaker
    from castbook.artifacts import CastFile, Character, load_artifact, save_artifact

    d = tmp_path / "b"
    d.mkdir()
    save_artifact(
        CastFile(
            book_id="b",
            input_hash="h",
            characters=[
                Character(id="q", name="the red queen", kind="character"),
            ],
        ),
        d,
    )
    assert rename_speaker(d, "q", "Queen of Hearts") == "Queen of Hearts"
    c = load_artifact(CastFile, d).characters[0]
    assert c.name == "Queen of Hearts" and "the red queen" in c.aliases
    import pytest

    with pytest.raises(ValueError):
        rename_speaker(d, "nope", "X")


def test_build_feed(tmp_path) -> None:
    from castbook.artifacts import (
        AttributionFile,
        AudioEntry,
        AudioManifest,
        BookMeta,
        Chapter,
        ChaptersFile,
        Unit,
        save_artifact,
    )
    from castbook.rss import build_feed

    d = tmp_path / "b"
    (d / "audio").mkdir(parents=True)
    (d / "audio" / "ch001.wav").write_bytes(b"RIFF")
    save_artifact(
        ChaptersFile(
            book_id="b",
            meta=BookMeta(title="T", author="A"),
            chapters=[Chapter(index=1, title="I", text="x", word_count=1)],
            input_hash="h",
        ),
        d,
    )
    save_artifact(
        AttributionFile(
            book_id="b",
            attributor="t",
            input_hash="h",
            units=[
                Unit(id="u1", chapter=1, text="x", speaker="narrator"),
            ],
        ),
        d,
    )
    save_artifact(
        AudioManifest(
            book_id="b",
            input_hash="h",
            units={
                "u1": AudioEntry(path="u1.wav", duration_s=1, status="done", unit_hash="h"),
            },
        ),
        d,
    )
    xml = build_feed(d, "http://localhost:3000/")
    assert xml is not None
    assert "<enclosure" in xml and "chapters/1/audio" in xml
    assert build_feed(tmp_path / "empty", "http://x/") is None
