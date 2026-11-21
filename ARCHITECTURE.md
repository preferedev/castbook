# Castbook MVP — Architecture (T1–T8)

Chosen shape: **file-backed stage pipeline** (matches PLAN.md §3/§6).
Rejected: in-memory DAG of pipeline objects — loses resume/caching, which is a
core product property, and couples stages through Python objects instead of
versioned JSON artifacts.

## Modules and boundaries

```
castbook/
  artifacts.py   # schema models + JSON read/write + input-hash provenance
  config.py      # pydantic-settings: config.toml + per-book book.castbook.json
  workdir.py     # books/<id>/ layout; the ONLY module that knows paths
  parse/         # epub.py, txt.py → chapters.json     (boundary: file formats)
  analyze/       # prompts.py, llm.py, extract.py, attribute.py, reconcile.py,
                 #   heuristic.py → cast.json, attribution.json
  cast/          # library.py, match.py → casting.json
  tts/           # backend.py (ABC), kokoro.py → audio/ + manifest.json
  audio/         # pacing.py, loudnorm.py, mux.py → export/
  models.py      # download manager: manifest, hash, license, resume
  app/server.py  # FastAPI: import / cast table / generate / download
  app/static/    # single-page UI, no build step
  cli/main.py    # typer — every UI action is a CLI call
eval/            # fixture books, labels.json, run.py → report.md
tests/
goals/mvp/       # GOAL.md contract (goal-mode)
```

Each stage = one public `run(book: BookPaths, cfg: Settings) -> <artifact>`
that reads prior artifacts from disk and writes the next one. Stages never
import each other's internals — the artifacts ARE the interface.

## Core types (artifacts.py — single source of truth)

```python
class Chapter(BaseModel):
    index: int
    title: str
    text: str
    word_count: int
    source: dict  # format-specific offsets/href for provenance


class ChaptersFile(BaseModel):
    schema: Literal[1]
    book_id: str
    meta: BookMeta  # title, author, cover_path, source_file
    chapters: list[Chapter]
    input_hash: str  # sha256 of source file → stale detection


class Character(BaseModel):
    id: str  # slug, stable across re-runs
    name: str
    aliases: list[str]
    gender: Literal["m", "f", "nb", "unknown"]
    age: str
    role: Literal["protagonist", "major", "minor", "one_off"]
    vibe: str  # one-line persona for VoiceDesign prompts later


SpeakerId = str  # character id, or reserved: "narrator" | "ambiguous"


class Unit(BaseModel):  # one synthesis unit — the atomic work item
    id: str  # ch{chapter:03d}-u{seq:04d}
    chapter: int
    text: str
    speaker: SpeakerId
    emotion: Emotion  # neutral|angry|sad|joyful|fearful|whispered|shouted|sarcastic
    kind: Literal["dialogue", "narration", "mixed"]


class AttributionFile(BaseModel):
    schema: Literal[1]
    book_id: str
    attributor: str  # "llamacpp:qwen3-4b@Q4" | "heuristic"
    units: list[Unit]
    needs_review: list[str]  # unit ids marked ambiguous
    input_hash: str


class VoiceSpec(BaseModel):  # the consistency pin — same spec+seed = same voice
    backend: str  # "kokoro" (MVP); "qwen3"/"pocket" later
    voice: str  # library voice id OR design prompt OR ref clip path
    seed: int
    speed: float = 1.0


class CastingFile(BaseModel):
    schema: Literal[1]
    book_id: str
    map: dict[str, VoiceSpec]  # speaker id (incl. "narrator") → voice
    input_hash: str


class UnitStatus(str, Enum):
    pending | done | failed


class AudioManifest(BaseModel):
    schema: Literal[1]
    book_id: str
    units: dict[str, AudioEntry]  # id → {path, duration_s, status, unit_hash}
    chapters: dict[int, ChapterAudio]  # index → {path, duration_s, status}
    input_hash: str  # of casting+attribution → incremental re-render
```

## Key signatures

```python
# parse/
def parse(path: Path, workdir: BookPaths) -> ChaptersFile          # dispatch on suffix
def parse_epub(path: Path) -> tuple[BookMeta, list[Chapter]]
def parse_txt(path: Path) -> tuple[BookMeta, list[Chapter]]

# analyze/
class Attributor(Protocol):
    name: str
    def extract_cast(self, chapters: list[Chapter]) -> list[Character]: ...
    def attribute(self, ch: Chapter, cast: list[Character]) -> list[Unit]: ...
class LlamaCppAttributor / HeuristicAttributor        # boundary: model I/O
def reconcile(cast: list[Character]) -> list[Character]  # alias merge

# cast/
def auto_cast(cast: list[Character], library: VoiceLibrary) -> CastingFile
def audition(voice: VoiceSpec, text: str) -> Path     # sample wav for UI

# tts/
class Backend(ABC):
    def capabilities(self) -> Capabilities: ...
    def synthesize(self, units: list[Unit], voice: VoiceSpec,
                   out: Callable[[Unit, Path], None]) -> Iterator[Path]: ...

# audio/
def assemble_chapter(manifest, chapter) -> Path       # trims + pause schedule
def loudnorm(path: Path, target_lufs=-19.0) -> Path   # ffmpeg loudnorm, peak -1dBTP
def mux_m4b(chapters: list[Path], meta, cover, out) -> Path  # FFMETADATA+aac
def export_mp3(chapters: list[Path], out_dir) -> list[Path]  # + .m3u
```

## Domain model choices (model-the-domain)

- **Speaker** is one string slot with two reserved values — no parallel
  `is_narrator` flag that could contradict the id.
- **Emotion** is a closed Literal set every backend maps from — never raw
  LLM text leaking into TTS calls.
- **UnitStatus** is a real enum in the manifest; resume = "run units whose
  hash changed or status ≠ done". No scattered state booleans.
- Voice-vs-character mapping lives entirely in `casting.json` — synthesis
  never re-derives casting decisions.

## Boundary discipline

Guards live at: CLI args (typer validation), upload endpoint (extension +
size), config.toml + book.castbook.json (pydantic), LLM output (JSON-schema
constrained + pydantic parse → `ambiguous` on failure), ffmpeg subprocess
(checked return codes), model downloads (sha256 + license string).
Inside: artifacts are trusted, typed pydantic models; no re-validation.

## External deps (all permissive-license)

ebooklib, beautifulsoup4, pydantic, pydantic-settings, typer, fastapi,
uvicorn, python-multipart, kokoro-onnx, soundfile, numpy, llama-cpp-python,
httpx. Dev: pytest, ruff, mypy.
