# Voicebox Backend

FastAPI server powering voice cloning, speech generation, and audio processing. Runs locally as a Tauri sidecar or standalone via `python -m backend.main`.

## Running

```bash
# Via justfile (recommended)
just dev:server

# Standalone
python -m backend.main --host 127.0.0.1 --port 17493

# With custom data directory
python -m backend.main --data-dir /path/to/data
```

The server auto-initializes the SQLite database on first startup. Models are downloaded from HuggingFace on first use.

## Architecture

```
backend/
  app.py                  # FastAPI app factory, CORS, lifecycle events
  main.py                 # Entry point (imports app, runs uvicorn)
  config.py               # Data directory paths and configuration
  models.py               # Pydantic request/response schemas
  server.py               # Tauri sidecar launcher, parent-pid watchdog

  routes/                 # Thin HTTP handlers — validation, delegation, response formatting
  services/               # Business logic, CRUD, orchestration
  backends/               # TTS/STT engine implementations (MLX, PyTorch, etc.)
  database/               # ORM models, session management, migrations, seed data
  utils/                  # Shared utilities (audio, effects, caching, progress tracking)
```

### Request flow

```
HTTP request
  -> routes/        (validate input, parse params)
  -> services/      (business logic, database queries, orchestration)
  -> backends/      (TTS/STT inference)
  -> utils/         (audio processing, effects, caching)
```

Route handlers are intentionally thin. They validate input, delegate to a service function, and format the response. All business logic lives in `services/`.

### Key modules

**services/generation.py** -- Single `run_generation()` function that handles all three generation modes (generate, retry, regenerate). Manages model loading, voice prompt creation, chunked inference, normalization, effects, and version persistence.

**services/task_queue.py** -- Serial generation queue. Ensures only one GPU inference runs at a time. Background tasks are tracked to prevent garbage collection.

**backends/__init__.py** -- Protocol definitions (`TTSBackend`, `STTBackend`), model config registry, and factory functions. Adding a new engine means implementing the protocol and registering a config entry.

**backends/base.py** -- Shared utilities used across all engine implementations: HuggingFace cache checks, device detection, voice prompt combination, progress tracking.

**database/** -- SQLAlchemy ORM models with a re-exporting `__init__.py` for backward compatibility. Migrations run automatically on startup.

### Backend selection

The server detects the best inference backend at startup:

| Platform | Backend | Acceleration |
|----------|---------|-------------|
| macOS (Apple Silicon) | MLX | Metal / Neural Engine |
| Windows / Linux (NVIDIA) | PyTorch | CUDA |
| Linux (AMD) | PyTorch | ROCm |
| Intel Arc | PyTorch | IPEX / XPU |
| Windows (any GPU) | PyTorch | DirectML |
| Any | PyTorch | CPU fallback |

Detection is handled by `utils/platform_detect.py`. Both backends implement the same `TTSBackend` protocol, so the API layer is engine-agnostic.

## API

90 endpoints organized by domain. Full interactive documentation available at `http://localhost:17493/docs` when the server is running.

| Domain | Prefix | Description |
|--------|--------|-------------|
| Health | `/`, `/health` | Server status, GPU info, filesystem checks |
| Profiles | `/profiles` | Voice profile CRUD, samples, avatars, import/export |
| Channels | `/channels` | Audio channel management and voice assignment |
| Generation | `/generate` | TTS generation, retry, regenerate, status SSE |
| History | `/history` | Generation history, search, favorites, export |
| Transcription | `/transcribe` | Whisper-based audio-to-text |
| Stories | `/stories` | Multi-track timeline editor, audio export |
| Effects | `/effects` | Effect presets, preview, version management |
| Audio | `/audio`, `/samples` | Audio file serving |
| Models | `/models` | Load, unload, download, migrate, status, engine capabilities |
| Tasks | `/tasks`, `/cache` | Active task tracking, cache management |
| CUDA | `/backend/cuda-*` | CUDA binary download and management |

### Quick examples

```bash
# Generate speech
curl -X POST http://localhost:17493/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "profile_id": "...", "language": "en"}'

# List profiles
curl http://localhost:17493/profiles

# Stream generation status (SSE)
curl http://localhost:17493/generate/{id}/status
```

### Engine capabilities

`GET /models/engines` is read-only and takes no parameters. It returns one entry per TTS engine in `TTS_ENGINES`, so the app can learn what an engine supports and whether it can run on this machine. It never loads a model, never starts a download and never imports torch at module scope.

```bash
curl http://localhost:17493/models/engines
```

```json
{
  "engines": [
    {
      "engine": "kokoro",
      "display_name": "Kokoro",
      "available": true,
      "reason": null,
      "warning": null,
      "supported_accelerators": [],
      "detected_accelerator": "cuda",
      "languages": ["en", "es", "fr", "hi", "it", "pt", "ja", "zh"],
      "supports_cloning": false,
      "supports_voice_design": false,
      "requires_download_confirmation": false,
      "advanced_settings": [],
      "size_mb": 350,
      "license_id": null,
      "commercial_use": null
    }
  ]
}
```

Each entry describes the engine across all of its model variants:

- `display_name` is the engine name from `TTS_ENGINES` (for example "TADA" or "F5-TTS"), not a variant name.
- `languages` is the union of every variant's languages.
- `license_id` and `commercial_use` hold the shared value when every variant agrees, and `null` when they differ.
- `size_mb`, `supports_voice_design`, `requires_download_confirmation`, `advanced_settings` and `supported_accelerators` come from the default-size variant, the one downloaded by default.
- `supports_cloning` comes from `CLONING_ENGINES`.
- `detected_accelerator` is the accelerator detected on this machine.
- `reason` is non-null if and only if `available` is false. An empty `supported_accelerators` list means unconstrained, and such an engine is always available.
- `warning` is advisory. It appears when detected memory is below the engine's usual need (`min_memory_mb`) and never blocks generation.

`POST /generate` accepts two optional fields, both defaulting to `null`, so existing callers are unaffected:

- `voice_description`: up to 500 characters, for engines with `supports_voice_design`. It is never sent as `instruct`.
- `advanced_settings`: an object mapping a setting name to a number. Only names the engine declares in `advanced_settings` are allowed, within their `min`/`max`. Anything else returns 422.

See [contracts/engine-capabilities.md](../specs/001-voxcpm2-tts-engine/contracts/engine-capabilities.md) for the full field contract.

A generation route asked to use an engine this machine can't run returns 400. The detail is the same `reason` that `/models/engines` reports. `/generate`, `/generate/stream`, retry and regenerate all check. Only engines that declare accelerators can be refused, which today means only VoxCPM2.

### Profile export manifest

`GET /profiles/{id}/export` returns a ZIP with `manifest.json`, `samples.json`, a `samples/` folder and, when set, the avatar. The manifest is version `1.1`:

```json
{
  "version": "1.1",
  "profile": {
    "name": "Narrator",
    "description": null,
    "language": "en",
    "voice_type": "designed",
    "preset_engine": null,
    "preset_voice_id": null,
    "design_prompt": "A calm older woman with a low, warm voice",
    "default_engine": "voxcpm"
  },
  "has_avatar": false
}
```

- Version 1.1 adds `voice_type`, `design_prompt`, `default_engine`, `preset_engine` and `preset_voice_id`. `POST /profiles/import` restores them instead of rebuilding the profile as cloned. An invalid combination is refused, not downgraded.
- A cloned profile needs at least one sample to export. Designed and preset profiles export without samples.
- Version 1.0 manifests still import, as cloned profiles with no default engine.
- The personality prompt is not exported.

The change is additive: 1.1 keeps every 1.0 key and adds the new ones beside them.

### AI-generated label in WAV files

Every WAV the backend generates carries a RIFF `LIST/INFO` chunk with `ICMT` = "AI-generated by Voicebox" and `ISFT` = "Voicebox". The audio samples are unchanged. Two helpers in `utils/audio.py` write it, and both default to `AI_GENERATED_DISCLOSURE`:

- `save_audio(audio, path, sample_rate, *, disclosure=...)` writes files: generations (including those started by `POST /speak` and the MCP `voicebox.speak` tool), effects versions and story exports.
- `wav_bytes(audio, sample_rate, *, disclosure=...)` returns bytes without saving. It is used by `/generate/stream` (through `services/tts.audio_to_wav_bytes()`) and the effects preview.

The user's own audio is saved with `disclosure=None` and has no label: profile reference samples, the combined reference, and the temp WAV re-encoded for transcription.

Code that parses WAV headers by hand should skip unknown chunks, as the RIFF format expects. soundfile reads the files and the tag back (see `tests/test_audio_disclosure.py`).

## Data directory

```
{data_dir}/
  voicebox.db             # SQLite database
  profiles/{id}/          # Voice samples per profile
  generations/            # Generated audio files
  cache/                  # Voice prompt cache (memory + disk)
  backends/               # Downloaded CUDA binary (if applicable)
```

Default location is the OS-specific app data directory. Override with `--data-dir` or the `VOICEBOX_DATA_DIR` environment variable.

## Code quality

Linting and formatting are enforced by [ruff](https://docs.astral.sh/ruff/), configured in `pyproject.toml`. See `STYLE_GUIDE.md` for conventions.

```bash
just check-python       # lint + format check
just fix-python         # auto-fix lint issues + reformat
just test               # run pytest
```

## Dependencies

Runtime dependencies are in `requirements.txt`. macOS-only MLX dependencies are in `requirements-mlx.txt`. Dev tools (ruff, pytest) are installed automatically by `just setup-python`.
