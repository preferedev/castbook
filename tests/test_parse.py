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


def test_gutenberg_separate_license_chapters_and_renumber() -> None:
    from castbook.artifacts import Chapter
    from castbook.parse import _strip_gutenberg

    chs = [
        Chapter(index=0, title="license", text="Project Gutenberg license header", word_count=4),
        Chapter(
            index=1,
            title="start",
            text="*** START OF THE PROJECT GUTENBERG EBOOK X ***\n\nBody.",
            word_count=10,
        ),
        Chapter(index=2, title="middle", text="Real chapter.", word_count=2),
        Chapter(
            index=3,
            title="end",
            text="Fin.\n\n*** END OF THE PROJECT GUTENBERG EBOOK X ***",
            word_count=6,
        ),
        Chapter(index=4, title="license2", text="Full license text chapter.", word_count=4),
    ]
    out = _strip_gutenberg(chs)
    assert [c.index for c in out] == [0, 1, 2]
    joined = " ".join(c.text for c in out)
    assert "Body." in joined and "Real chapter." in joined and "Fin." in joined
    assert "license" not in joined.lower()


def test_gutenberg_marker_glued_to_story_text() -> None:
    from castbook.artifacts import Chapter
    from castbook.parse import _strip_gutenberg

    # PDF-style: newline after the marker was flattened to a space
    c = Chapter(
        index=0,
        title="ch",
        text="*** START OF THE PROJECT GUTENBERG EBOOK X *** Chapter one begins here.",
        word_count=12,
    )
    out = _strip_gutenberg([c])
    assert "Chapter one begins here." in out[0].text
