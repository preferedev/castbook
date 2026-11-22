from castbook.analyze.heuristic import HeuristicAttributor, slugify
from castbook.artifacts import Chapter, Character


def ch(text: str) -> Chapter:
    return Chapter(index=0, title="One", text=text, word_count=len(text.split()))


CAST = [
    Character(id="mrs-bennet", name="Mrs. Bennet", gender="f", role="major"),
    Character(id="elizabeth", name="Elizabeth", gender="f", role="protagonist"),
]


def test_said_attribution() -> None:
    h = HeuristicAttributor()
    units = h.attribute(ch('"It is a truth," said Mrs. Bennet, "universally acknowledged."'), CAST)
    assert units[0].speaker == "mrs-bennet"


def test_name_says_pattern() -> None:
    h = HeuristicAttributor()
    units = h.attribute(ch('"Fine," Elizabeth said.\n\nShe turned away.'), CAST)
    assert units[0].speaker == "elizabeth"


def test_extract_cast_finds_named_speakers() -> None:
    text = "\n\n".join(
        f'"Line {i}," said Mrs. Bennet.\n\n"Lizzy!" cried Mr. Bennet.' for i in range(15)
    )
    h = HeuristicAttributor()
    cast = h.extract_cast([ch(text)])
    assert cast
    assert all(c.id for c in cast)
    assert sum(1 for c in cast if c.role == "major") >= 1


def test_unattributed_dialogue_is_ambiguous() -> None:
    h = HeuristicAttributor()
    units = h.attribute(ch('"Who said this?"\n\nIt floated, unattributed.'), [])
    assert units[0].speaker == "ambiguous"
    assert units[1].speaker == "narrator"


def test_narration_is_narrator() -> None:
    h = HeuristicAttributor()
    units = h.attribute(ch("Rain fell on the house all day."), CAST)
    assert units[0].speaker == "narrator"


def test_slugify() -> None:
    assert slugify("Mrs. Bennet") == "mrs-bennet"
    assert slugify("Mr Darcy") == "mr-darcy"
