---
objective: Castbook MVP — T1 through T8 at production level
status: ACTIVE
planning_level: executing
current_phase: 0
phases_total: 9
iteration: 0
max_iterations: 200
active_step: "phase-0"
created: 2026-11-22
---

# Goal — Castbook MVP (T1–T8)

Build the Castbook MVP per PLAN.md: repo skeleton + schemas, EPUB/TXT parser,
LLM speaker attribution (llama.cpp, Qwen3-4B GGUF) with a heuristic fallback,
voice casting, Kokoro TTS synthesis, M4B/MP3 export, minimal web UI, and an
eval harness — verified end to end.

## Done criteria (all must pass with evidence, not claims)

1. `castbook run <book.epub>` on a public-domain novel produces a chaptered M4B
   with ≥3 distinct character voices + narrator (measured: audio manifest +
   ffprobe chapter count).
2. `pytest -q` — all tests green.
3. `ruff check . && ruff format --check .` — clean.
4. `mypy castbook` — clean (strict where practical).
5. `python -m eval.run` writes `eval/report.md` with speaker-accuracy,
   narrator F1, and ambiguous-rate for the labeled fixture books.
6. Resume works: killing synthesis mid-chapter and re-running completes without
   re-rendering finished units (test or demonstrated).
7. Web UI serves import → cast table → generate → download on localhost.
8. README quickstart works from a clean checkout (fresh venv, documented steps).

## Evidence commands

- `cd ~/repos/castbook && ruff check . && ruff format --check .`
- `cd ~/repos/castbook && mypy castbook`
- `cd ~/repos/castbook && pytest -q`
- `cd ~/repos/castbook && python -m eval.run`
- `castbook run <fixture>` then `ffprobe -v quiet -print_format json -show_chapters export/*.m4b`

## Standing constraints

- pstack skills apply per stage (architect before new modules, laziness /
  subtract-before-add while writing, boundary-discipline at edges,
  prove-it-works before done, no-comments final pass).
- File-backed stages only: chapters.json, cast.json, attribution.json,
  casting.json, audio/ + manifest.json. No stage imports another's internals.
- Default bundle licenses stay Apache-2.0/MIT only; every model manifest
  carries its license string.
- No DRM handling anywhere; legally-acquired DRM-free inputs only.
- Branch + PR workflow; never push/merge main directly; no deploys or external
  messages without the owner's go-ahead.

## Time budget

Session-length; phases advance on verified exit criteria, not elapsed time.

## Verified results (2026-11-22)

- e2e `castbook run` on Pride & Prejudice EPUB: 67 chapters, 2,247 units,
  0 failed → `books/pp/export/pride-and-prejudice.m4b` (491 MB, 10.7 h,
  ffprobe: 67 chapters, aac + attached cover).
- 15 distinct voices across 24 speakers (`castbook stats pp`).
- `pytest`: 31 tests green; `ruff check` + `mypy` strict clean.
- Eval report: `eval/report.md` — heuristic 81% (Alice) / 50% (P&P excerpt).
- Resume verified: per-unit TTS hash + per-chapter analyze checkpoints.
- LLM path verified with real Qwen3-4B Q4_K_M GGUF (llama.cpp).
