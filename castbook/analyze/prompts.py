"""LLM prompt templates — kept minimal, structured output does the constraining."""

from __future__ import annotations

EXTRACT_CAST = """\
You are analyzing a novel to build its character cast for audiobook narration.

Below are excerpts from the book. List every named character who speaks or is
spoken about more than once. For each: canonical name, all aliases/nicknames/
titles used for them, gender ("m","f","nb","unknown"), rough age, role
("protagonist","major","minor","one_off"), and a one-line voice/vibe note
(e.g. "warm middle-aged female, measured, gentle").

Return ONLY JSON: {{"characters": [{{"name","aliases","gender","age","role","vibe"}}]}}

EXCERPTS:
{excerpts}
"""

ATTRIBUTE = """\
You are tagging a novel for multi-voice audiobook narration.

CAST (use these names exactly — aliases are listed in parentheses): {cast_names}

Each passage is prefixed by the previous passage's speaker and a snippet, so you
can resolve pronouns like "she replied" in alternating dialogue.

For each numbered passage, decide who should speak it:
- If it contains dialogue, name the character speaking (from CAST, or a new
  name if the speaker is real but missing from the list). Narration that embeds
  a quote after "X said/cried/asked" belongs to X, not the narrator.
- If it is narration, answer "narrator".
- If you cannot tell, answer "ambiguous".
Optionally add an emotion from: neutral, angry, sad, joyful, fearful,
whispered, shouted, sarcastic.

Return ONLY JSON: {{"units": [{{"i": <number>, "speaker": "...", "emotion": "neutral"}}]}}

PASSAGES:
{passages}
"""
