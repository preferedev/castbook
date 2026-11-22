from castbook.analyze.units import split_units
from castbook.artifacts import Chapter


def ch(text: str) -> Chapter:
    return Chapter(index=0, title="One", text=text, word_count=len(text.split()))


def test_dialogue_paragraph_marks_dialogue() -> None:
    units = split_units(ch('She turned. "I will not go," she said.\n\nPlain narration only.'))
    assert len(units) == 2
    assert units[0].kind == "dialogue"
    assert units[1].kind == "narration"


def test_long_paragraph_splits_on_sentence_boundaries() -> None:
    text = " ".join(["Word word word word word word."] * 80)
    units = split_units(ch(text))
    assert len(units) > 1
    for u in units:
        assert u.text.rstrip().endswith("."), u.text[-40:]


def test_unit_ids_are_stable() -> None:
    a = split_units(ch("Same text."))
    b = split_units(ch("Same text."))
    assert [u.id for u in a] == [u.id for u in b]
