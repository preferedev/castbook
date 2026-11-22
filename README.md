# Castbook

Turn any ebook into a full-cast audiobook — every character gets a consistent
voice, a narrator reads the rest. Free, open-source, local-first.

EPUB, PDF and TXT in, chaptered M4B out. Python CLI plus a minimal local web UI.

## Quickstart

```bash
uv venv && uv pip install -e '.[dev]'
castbook models pull kokoro-v1 kokoro-voices-v1   # ~350 MB, required for the kokoro backend

# faster alternative on CPU (cloning + streaming), optional:
pip install -e '.[pocket]'   # torch CPU wheel first: pip install torch --index-url https://download.pytorch.org/whl/cpu
# then set backend = "pocket" under [tts] in config.toml — the model auto-downloads from HF.
# clone a voice: castbook cast <book> --map "<speaker>=/path/to/clip.wav" (requires HF terms
# accepted for kyutai/pocket-tts); catalog voices need no auth.

# quality tier (GPU only — check 'castbook doctor' for your tier):
pip install -e '.[qwen]'     # Qwen3-TTS VoiceDesign: every character gets a designed voice
# then backend = "qwen" under [tts]. Each character's vibe note becomes the voice description.
castbook models pull qwen3-4b-q4                  # ~2.5 GB, optional — better attribution
castbook run book.epub          # parse → analyze → cast → generate → export
castbook run examples/lighthouse.txt   # or try the bundled sample
```

Output lands in `books/<book-id>/export/`. Stages resume where they left off;
re-run `castbook generate` after a crash or a casting change and only
un-rendered units are synthesized.

## Commands

| command | what it does |
|---|---|
| `castbook import <file> [<file>…]` | import one or more ebooks (EPUB/PDF/TXT/MD) → `chapters.json` |
| `castbook analyze <book>` | attribute every line (`--backend heuristic\|llamacpp` to override config) |
| `castbook cast <book>` | auto-assign voices; `--map name=voice` (mix voices as `a:0.7+b:0.3`), `--speed name=rate` |
| `castbook generate <book>` | synthesize audio (resumable; `--chapters 1-3,7`, `--limit 50` preview, `--workers 4` parallel, `--align` word timestamps) |
| `castbook export <book>` | mux chaptered M4B (+ `--format mp3`/`both`) |
| `castbook review <book>` | list ambiguous units; `--set unit=speaker` to fix |
| `castbook merge <book> <a> <b>` | fold duplicate speaker `a` into `b` |
| `castbook align <book>` | word-level timestamps for reader karaoke (needs `[align]` extra) |
| `castbook reset <book>` | wipe a book's artifacts to start over |
| `castbook run <file>` | all of the above |
| `castbook books` | list books with render progress |
| `castbook models list\|pull` | model management |
| `castbook serve -p 8484` | local web UI |

## Docker

```bash
docker build -t castbook .
docker run -v $PWD/data:/data castbook doctor
```

## Web UI

`castbook serve` then open `http://localhost:8484`: import files (multi-select or drag-and-drop), audition voices
with the ▶ button, review and
override voice casting (including per-speaker speed, `voiceA:0.7+voiceB:0.3` mixes, and merging duplicate speakers), generate (or "Preview 50" for a quick sample), play any rendered chapter with ▶ audio, re-render just a range with ↻, and export in the background — download the M4B when it lands.
The reader view highlights the spoken word when `castbook align` has run, remembers
your position, and supports space/←/→/↑/↓ shortcuts.

Voice assignments persist across books (`data/voice-memory.json`) — a character
keeps their voice everywhere they appear. Pronunciation overrides live in
`data/lexicon.json` (global) and `<book>/lexicon.json` (per-book, wins on conflicts).

## Attribution

Without the LLM, a heuristic attributor tags explicit speech verbs
("said Elizabeth") and leaves the rest `ambiguous` — those units land in
`needs_review` in `attribution.json` rather than being guessed. With
`qwen3-4b-q4` downloaded, `analyze` uses it via llama.cpp (CPU) for
pronoun/context resolution.

## Eval

`python -m eval.run` scores attribution on labeled excerpts (Pride & Prejudice
ch. II, Alice's Mad Tea-Party) and writes `eval/report.md`.

## Legality

For legally acquired, DRM-free books only. Castbook removes no DRM and uploads
nothing — everything runs on your machine. Output is for personal use.
Bundled models: Kokoro (Apache-2.0), Qwen3 (Apache-2.0).
