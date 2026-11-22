def test_gutenberg_boilerplate_stripped(tmp_path) -> None:
    from castbook.parse import parse

    src = tmp_path / "book.txt"
    src.write_text(
        "The Project Gutenberg eBook of X\nlicense header\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK X ***\n\n"
        "CHAPTER I\n\nChapter one text.\n\nMore of chapter one.\n\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK X ***\n"
        "license tail\n"
    )
    _, chapters = parse(src)
    joined = " ".join(c.title + " " + c.text for c in chapters).lower()
    assert "chapter one text" in joined
    assert "GUTENBERG" not in joined
    assert "license" not in joined
