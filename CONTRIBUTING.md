# Contributing

## Setup

```bash
uv venv .venv && uv pip install --python .venv/bin/python -e '.[dev]'
sudo apt-get install -y ffmpeg   # or brew install ffmpeg
```

Run everything before pushing:

```bash
.venv/bin/ruff format . && .venv/bin/ruff check .
.venv/bin/mypy castbook/
.venv/bin/pytest
```

## Rules that keep the codebase sane

- **File-backed stages**: every stage writes a JSON artifact (`chapters/attribution/casting/manifest`) so work is resumable. Don't pass state in memory between stages.
- **Attribution outputs speaker strings** — `narrator`, `ambiguous`, or a character id; `ambiguous` is honest uncertainty and lands in the needs-review queue. Never guess silently.
- **Apache-2.0/MIT-compatible deps only**; every new dependency needs a license check against LICENSE.
- **No blanket try/except** — guard at edges (CLI args, API input, network, subprocesses), trust data inside.
- **Tests assert behavior** (output files, endpoint responses, exported artifacts), not internals.
- `ruff format` is enforced by CI — run it before every push.

## Optional extras

`docx` (python-docx), `pocket` + `qwen` (GPU TTS tiers), `align` (faster-whisper karaoke), `qr` (LAN QR). Add extras under `[project.optional-dependencies]` and map the import to `ignore_missing_imports` in the mypy overrides.
