# Castbook

Turn any ebook into a full-cast audiobook — every character gets a consistent
voice, a narrator reads the rest. Free, open-source, local-first.

EPUB and TXT in, M4B out. Python CLI plus a minimal local web UI.

## Quickstart

```bash
uv venv && uv pip install -e .
castbook models pull            # downloads TTS + attribution models
castbook run book.epub          # parse → analyze → cast → generate → export
```

Output lands in `books/<title>/export/`. See `docs/` and `ARCHITECTURE.md`.

## Legality

For legally acquired, DRM-free books only. Castbook removes no DRM and uploads
nothing — everything runs on your machine. Output is for personal use.
