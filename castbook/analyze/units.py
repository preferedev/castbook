"""Split chapter text into attribution units — shared by every attributor.

A unit is a paragraph or a quote-group; dialogue detection is by typographic
quotes, which holds for the English-language books the MVP targets.
"""

from __future__ import annotations

import itertools
import re

from ..artifacts import Chapter, Unit

QUOTE_RE = re.compile("[\u201c\u0022\u2018']([^\u201d\u0022\u2019']+)[\u201d\u0022\u2019']")

MAX_UNIT_WORDS = 180


def split_units(chapter: Chapter) -> list[Unit]:
    units: list[Unit] = []
    seq = 0
    for p_index, para in enumerate(_paragraphs(chapter.text)):
        inside = False
        for piece in (p for block in _speech_blocks(para) for p in _cap(block)):
            seq += 1
            after = _inside_quote(piece, inside)
            kind = "dialogue" if inside or after or QUOTE_RE.search(piece) else "narration"
            units.append(
                Unit(
                    id=f"ch{chapter.index:03d}-u{seq:04d}",
                    chapter=chapter.index,
                    text=piece,
                    speaker="",
                    kind=kind,
                    paragraph=p_index,
                )
            )
            inside = after
    return units


def _quote_step(stack: list[str], ch: str, text: str, i: int) -> None:
    """One char of quote tracking: 'd'/'s' levels so nested quotes of the other
    kind can't close the enclosing speech."""
    if ch == '"':
        if stack and stack[-1] == "d":
            stack.pop()
        else:
            stack.append("d")
    elif ch == "\u201c":
        stack.append("d")
    elif ch == "\u2018":
        stack.append("s")
    elif stack and (
        (ch == "\u201d" and stack[-1] == "d")
        or (ch == "\u2019" and stack[-1] == "s" and not _apostrophe(text, i))
    ):
        stack.pop()


def _inside_quote(text: str, inside: bool = False) -> bool:
    stack: list[str] = ["d"] if inside else []
    for i, ch in enumerate(text):
        _quote_step(stack, ch, text, i)
    return bool(stack)


def _apostrophe(text: str, i: int) -> bool:
    return i > 0 and i + 1 < len(text) and text[i - 1].isalnum() and text[i + 1].isalnum()


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]


_GAP_SENT_END = re.compile(
    r"(?:[.!?](?<!Mr\.)(?<!Mrs\.)(?<!Dr\.)(?<!St\.)(?<!Ms\.)(?<!Jr\.)(?<!Sr\.))+[\"'\\u201d\\u2019\\)]*\\s+"
)


def _spans(text: str) -> list[tuple[int, int]]:
    """Top-level quote spans via the same stack tracking used for kind checks."""
    stack: list[str] = []
    start = -1
    out: list[tuple[int, int]] = []
    for i, ch in enumerate(text):
        deep = bool(stack)
        _quote_step(stack, ch, text, i)
        if not deep and stack:
            start = i
        elif deep and not stack:
            out.append((start, i + 1))
            start = -1
    if start >= 0:
        out.append((start, len(text)))
    return out


def _speech_blocks(para: str) -> list[str]:
    """Cut a paragraph between separate speeches: narration stays glued to its
    speech, while '...,' said X, '...' continuations count as one speech."""
    spans = _spans(para)
    if len(spans) < 2:
        return [para]
    cuts: list[int] = []
    for (as_, ae), (bs, _be) in itertools.pairwise(spans):
        gap = para[ae:bs]
        if not re.search(r"[^\W\d_]", gap):
            continue
        inner_a = para[as_ + 1 : ae - 1].rstrip()
        if inner_a.endswith(",") and gap.rstrip().endswith(","):
            continue
        ends = list(_GAP_SENT_END.finditer(gap))
        cuts.append(ae + ends[-1].end() if ends else bs)
    if not cuts:
        return [para]
    out = []
    prev = 0
    for c in cuts:
        out.append(para[prev:c])
        prev = c
    out.append(para[prev:])
    return [p.strip() for p in out if p.strip()]


def _cap(para: str) -> list[str]:
    """Split a paragraph that exceeds the unit cap on sentence boundaries."""
    if len(para.split()) <= MAX_UNIT_WORDS:
        return [para]
    sentences = re.split(r"(?<=[.!?])\s+", para)
    out: list[str] = []
    buf: list[str] = []
    n = 0
    for s in sentences:
        w = len(s.split())
        if n + w > MAX_UNIT_WORDS and buf:
            out.append(" ".join(buf))
            buf, n = [], 0
        buf.append(s)
        n += w
    if buf:
        out.append(" ".join(buf))
    return out


def quoted_spans(text: str) -> list[str]:
    return [m.group(1).strip() for m in QUOTE_RE.finditer(text) if m.group(1).strip()]
