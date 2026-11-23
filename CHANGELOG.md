# Changelog

All notable changes to Castbook. This project is pre-1.0; PRs land on `main` continuously.

## Unreleased — quality tier (PRs #6–#23)

- **TTS backends**: `kokoro` (default), `pocket` (fast CPU + voice cloning via `castbook clone`), `qwen` (VoiceDesign, GPU); switch from CLI or the UI backend dropdown.
- **Attribution**: heuristic engine (quote-run turn tracking, vocatives, pronoun-gender, action beats, multilingual tags/quote styles), `llamacpp` for full-LLM, `hybrid` (LLM only where heuristic is unsure). Eval average ~89% heuristic / ~92% hybrid over 12 gold books.
- **Import**: EPUB, TXT, MD, MOBI/AZW/AZW3, PDF, HTML, DOCX, FB2, URLs (SSRF-guarded), Gutenberg browser, content-hash dedupe, `--lang` override, watch-folder (`castbook watch`).
- **Voices**: shareable voicepacks, voice blending (`a:0.7+b:0.3`), cloned voices, voice memory across books, per-speaker speed, `[tts] emotion_strength`.
- **Render**: resumable unit cache, `--chapters`/`--limit`/`--workers`/`--dry-run`, preview-50, cancel, `?failed=1` retry, ETA + browser notifications.
- **Export**: M4B (chaptered, cover, loudnorm), MP3 dir, Audiobookshelf layout (+zip), `--split` hours, `--chapters` subsets, read-along EPUB (`--epub`), podcast RSS per book, OPDS catalog.
- **Transcripts**: per-chapter or merged SRT/VTT/TXT with speaker labels and `--speaker` filter.
- **Reader**: read-along page with karaoke (faster-whisper `castbook align`), position memory, bookmarks, sleep timer, speed, keyboard shortcuts, font-size + theme toggles, `?ch=` deep links.
- **UI**: dark mode, dark-aware dark/sepia/light reader themes, editable speaker names, one-click speaker merge suggestions, emotion editor per unit, chapter rename, meta edit, custom cover upload, model manager, search ("who said it"), lexicon editor (book + global, with audition), "▶ all" voice audition, PWA manifest + icons.
- **Ops**: `doctor` (encoders/machine/disk), `verify`, `clean`, `config`, `stats`, `estimate`, `books --json`, `run-all` batch pipeline, LAN `serve --host` behind token.
- **Quality gates**: ruff + mypy strict + pytest in CI, attribution eval gate (`--fail-under`), release workflow building PyInstaller binaries per OS.
