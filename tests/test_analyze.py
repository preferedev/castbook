def test_normalize_speaker() -> None:
    from castbook.analyze.llm import _normalize_speaker
    from castbook.artifacts import Character

    cast = [
        Character(id="a", name="Elizabeth Bennet", aliases=["Lizzy", "Eliza"]),
        Character(id="b", name="March Hare", aliases=[]),
    ]
    assert _normalize_speaker("lizzy", cast) == "elizabeth bennet"
    assert _normalize_speaker("miss elizabeth bennet", cast) == "elizabeth bennet"
    assert _normalize_speaker("the march hare", cast) == "march hare"
    assert _normalize_speaker("narrator", cast) == "narrator"
    assert _normalize_speaker("unknown stranger", cast) == "unknown stranger"


def test_normalize_speaker_shared_surname() -> None:
    from castbook.analyze.llm import _normalize_speaker
    from castbook.artifacts import Character

    cast = [
        Character(id="a", name="Mr Bennet", aliases=[]),
        Character(id="b", name="Mrs Bennet", aliases=[]),
    ]
    # exact match misses on the period; surname match must not grab Mr. Bennet
    assert _normalize_speaker("mrs. bennet", cast) == "mrs bennet"
    assert _normalize_speaker("mr. bennet", cast) == "mr bennet"
    cast2 = [
        Character(id="a", name="Mr. Bennet", aliases=[]),
        Character(id="b", name="Lady Catherine", aliases=["Lady Catherine de Bourgh"]),
    ]
    assert _normalize_speaker("elder mr. bennet", cast2) == "mr. bennet"


def test_split_units_keeps_long_quote_dialogue() -> None:
    from castbook.analyze.units import split_units
    from castbook.artifacts import Chapter

    speech = "“" + " ".join(" ".join(["word"] * 20) + "." for _ in range(20)) + "”"
    ch = Chapter(index=0, title="t", text=speech, word_count=len(speech.split()))
    kinds = [u.kind for u in split_units(ch)]
    assert len(kinds) > 1 and all(k == "dialogue" for k in kinds), kinds


def test_split_units_apostrophe_does_not_close_quote() -> None:
    from castbook.analyze.units import split_units
    from castbook.artifacts import Chapter

    narration = " ".join(" ".join(["narration"] * 40) + "." for _ in range(6))
    text = '"I can\u2019t wait," he said. ' + narration
    ch = Chapter(index=0, title="t", text=text, word_count=len(text.split()))
    kinds = [u.kind for u in split_units(ch)]
    assert len(kinds) > 1 and kinds[-1] == "narration", kinds


def test_heuristic_long_speech_keeps_speaker_across_pieces() -> None:
    from castbook.analyze.heuristic import HeuristicAttributor
    from castbook.artifacts import Chapter, Character

    cast = [
        Character(id="alice", name="Alice", aliases=[]),
        Character(id="bob", name="Bob", aliases=[]),
    ]
    speech = "“" + " ".join(" ".join(["word"] * 20) + "." for _ in range(25)) + ",” said Bob."
    text = "“Hi,” said Alice.\n\n" + speech
    ch = Chapter(index=0, title="t", text=text, word_count=len(text.split()))
    units = HeuristicAttributor().attribute(ch, cast)
    assert len(units) > 3, len(units)
    assert units[0].speaker == "alice"
    assert all(u.speaker == "bob" for u in units[1:]), [u.speaker for u in units]


def test_heuristic_untagged_turn_alternates() -> None:
    from castbook.analyze.heuristic import HeuristicAttributor
    from castbook.artifacts import Chapter, Character

    cast = [
        Character(id="alice", name="Alice", aliases=[]),
        Character(id="bob", name="Bob", aliases=[]),
    ]
    text = "“First,” said Alice.\n\n“Second,” said Bob.\n\n“Third.”\n\n“Fourth.”"
    ch = Chapter(index=0, title="t", text=text, word_count=len(text.split()))
    units = HeuristicAttributor().attribute(ch, cast)
    assert [u.speaker for u in units] == ["alice", "bob", "alice", "bob"]


def test_heuristic_name_says_inside_quote_is_content_not_tag() -> None:
    from castbook.analyze.heuristic import HeuristicAttributor
    from castbook.artifacts import Chapter, Character

    cast = [
        Character(id="alice", name="Alice", aliases=[]),
        Character(id="bob", name="Bob", aliases=[]),
    ]
    ch = Chapter(
        index=0,
        title="t",
        text='"Alice said nothing," he noted. "All wrong," said Bob.',
        word_count=0,
    )
    assert [u.speaker for u in HeuristicAttributor().attribute(ch, cast)] == ["bob"]


def test_heuristic_speaker_history_resets_at_narration() -> None:
    from castbook.analyze.heuristic import HeuristicAttributor
    from castbook.artifacts import Chapter, Character

    cast = [
        Character(id="alice", name="Alice", aliases=[]),
        Character(id="bob", name="Bob", aliases=[]),
    ]
    ch = Chapter(
        index=0,
        title="t",
        text='"Hi," said Alice.\n\nThe sun set.\n\n"Okay?"',
        word_count=0,
    )
    assert [u.speaker for u in HeuristicAttributor().attribute(ch, cast)] == [
        "alice",
        "narrator",
        "ambiguous",
    ]


def test_heuristic_nested_single_quotes_keep_outer_tag() -> None:
    from castbook.analyze.heuristic import HeuristicAttributor
    from castbook.artifacts import Chapter, Character

    cast = [
        Character(id="alice", name="Alice", aliases=[]),
        Character(id="bob", name="Bob", aliases=[]),
    ]
    ch = Chapter(
        index=0,
        title="t",
        text='"He said \u2018hello\u2019 to me," said Bob.',
        word_count=0,
    )
    assert [u.speaker for u in HeuristicAttributor().attribute(ch, cast)] == ["bob"]


def test_heuristic_double_quote_inside_single_speech() -> None:
    from castbook.analyze.heuristic import HeuristicAttributor
    from castbook.artifacts import Chapter, Character

    cast = [
        Character(id="alice", name="Alice", aliases=[]),
        Character(id="bob", name="Bob", aliases=[]),
    ]
    ch = Chapter(
        index=0,
        title="t",
        text='\u2018Alice quietly said, "hi" to me,\u2019 said Bob.',
        word_count=0,
    )
    assert [u.speaker for u in HeuristicAttributor().attribute(ch, cast)] == ["bob"]


def test_heuristic_extract_cast_synthesizes_first_person_protagonist() -> None:
    from castbook.analyze.heuristic import HeuristicAttributor
    from castbook.artifacts import Chapter

    text = "\n\n".join(f'"Line {i}," said I.' for i in range(6))
    ch = Chapter(index=0, title="t", text=text, word_count=0)
    cast = HeuristicAttributor().extract_cast([ch])
    assert cast[0].name == "Protagonist" and "I" in cast[0].aliases
    units = HeuristicAttributor().attribute(ch, cast)
    assert all(u.speaker == "protagonist" for u in units)


def test_heuristic_no_protagonist_in_third_person() -> None:
    from castbook.analyze.heuristic import HeuristicAttributor
    from castbook.artifacts import Chapter

    text = "\n\n".join(f'"Line {i}," said Alice.' for i in range(6))
    ch = Chapter(index=0, title="t", text=text, word_count=0)
    cast = HeuristicAttributor().extract_cast([ch])
    assert all(c.name != "Protagonist" for c in cast)


def test_heuristic_narration_dominant_quote_is_narrator() -> None:
    from castbook.analyze.heuristic import HeuristicAttributor
    from castbook.artifacts import Chapter, Character

    cast = [Character(id="alice", name="Alice", aliases=[])]
    ch = Chapter(
        index=0,
        title="t",
        text='She walked to the stone and read aloud the words carved there, '
        '"REST IN PEACE," before turning slowly toward the empty fields beyond.',
        word_count=0,
    )
    assert HeuristicAttributor().attribute(ch, cast)[0].speaker == "narrator"


def test_heuristic_narrator_does_not_enter_turn_history() -> None:
    from castbook.analyze.heuristic import HeuristicAttributor
    from castbook.artifacts import Chapter, Character

    cast = [
        Character(id="alice", name="Alice", aliases=[]),
        Character(id="bob", name="Bob", aliases=[]),
    ]
    ch = Chapter(
        index=0,
        title="t",
        text='"Hi," said Alice.\n\n'
        "The afternoon wore on.\n\n"
        'She stared at the stone that read "RIP" beneath her breath for a while.\n\n'
        '"Okay then."',
        word_count=0,
    )
    # the inscription unit is narrator and must not seed turn-taking history;
    # the trailing untagged line stays honestly ambiguous
    assert [u.speaker for u in HeuristicAttributor().attribute(ch, cast)] == [
        "alice",
        "narrator",
        "narrator",
        "ambiguous",
    ]
