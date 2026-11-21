# Castbook

Turn any ebook into a full-cast audiobook — every character gets a consistent
voice, a narrator reads the rest. Free, open-source, local-first.

EPUB, PDF and TXT in, chaptered M4B out. Python CLI plus a minimal local web UI.

## Quickstart

```bash
uv venv && uv pip install -e '.[dev]'
castbook models pull kokoro-v1 kokoro-voices-v1   # ~350 MB, required
castbook models pull qwen3-4b-q4                  # ~2.5 GB, optional — better attribution
castbook run book.epub          # parse → analyze → cast → generate → export
```

Output lands in `books/<book-id>/export/`. Stages resume where they left off;
re-run `castbook generate` after a crash or a casting change and only
un-rendered units are synthesized.

## Commands

| command | what it does |
|---|---|
| `castbook import <file>` | parse EPUB/PDF/TXT into `chapters.json` |
| `castbook analyze <book>` | attribute every line to a speaker (LLM or heuristic fallback) |
| `castbook cast <book>` | auto-assign voices; `--map name=voice` to override |
| `castbook generate <book>` | synthesize audio (resumable; `--chapters 1-3,7` for partial) |
| `castbook export <book>` | mux chaptered M4B (+ `--format mp3`) |
| `castbook review <book>` | list ambiguous units; `--set unit=speaker` to fix |
| `castbook run <file>` | all of the above |
| `castbook books` | list imported books |
| `castbook models list\|pull` | model management |
| `castbook serve -p 8484` | local web UI |

## Docker

```bash
docker build -t castbook .
docker run -v $PWD/data:/data castbook doctor
```

## Web UI

`castbook serve` then open `http://localhost:8484`: import a file, audition voices
with the ▶ button, review and
override voice casting, generate, download the M4B.

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
