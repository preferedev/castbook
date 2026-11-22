from castbook.reader import article_text, split_for_reading


def test_article_text_keeps_article_paragraphs() -> None:
    html = (
        "<html><body><nav>menu junk</nav><article>"
        "<p>First paragraph of real article content, long enough to keep.</p>"
        "<p>Second paragraph, also comfortably long enough to survive.</p>"
        "</article><footer>foot junk</footer></body></html>"
    )
    text = article_text(html)
    assert "First paragraph" in text and "Second paragraph" in text
    assert "menu junk" not in text and "foot junk" not in text


def test_article_text_falls_back_to_body() -> None:
    text = article_text("<html><body>plain text page</body></html>")
    assert "plain text" in text


def test_split_for_reading_bounds_and_preserves_text() -> None:
    text = " ".join(f"Sentence number {i}." for i in range(400))
    chunks = split_for_reading(text)
    assert all(len(c) <= 1600 for c in chunks)
    joined = " ".join(chunks)
    for i in (0, 200, 399):
        assert f"Sentence number {i}." in joined


def test_split_for_reading_empty() -> None:
    assert split_for_reading("  \n\n  ") == []
