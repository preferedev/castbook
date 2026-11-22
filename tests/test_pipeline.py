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
