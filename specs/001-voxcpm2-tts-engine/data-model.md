# Phase 1 Data Model: VoxCPM2 TTS Engine

**Feature**: `specs/001-voxcpm2-tts-engine` | **Date**: 2026-09-22

This feature adds one nullable column, `generations.voice_description` (TEXT), through the existing additive `_add_column` migration in `backend/database/migrations.py`; no table is added. It extends
one existing in-memory descriptor and adds two transient runtime shapes. It puts existing
Voice Profile columns to new use (the designed source, §3), writes a disclosure tag into
generated WAV files (§6), and moves the profile export manifest to version 1.1 (§7). The generation export manifest
also moves to 1.1, adding `voice_description`, `engine` and `model_size` (§5).

---

## 1. `ModelConfig` — extended (existing entity)

Defined in [backend/backends/__init__.py](../../backend/backends/__init__.py#L45). Today it
carries `model_name`, `display_name`, `engine`, `hf_repo_id`, `model_size`, `size_mb`,
`needs_trim`, `retries_runaway`, `supports_instruct`, `languages`, `license_id`,
`commercial_use` and `dialect`.

### New field

| Field | Type | Default | Why |
| --- | --- | --- | --- |
| `accelerators` | `tuple[str, ...]` | `()` | The accelerators this model can run on, e.g. `("cuda", "mps", "cpu")`. Empty means "unconstrained", preserving today's behaviour for the seven existing engines so none of them change. Required by FR-002 and FR-004: capability is declared once here and queried, never branched on by engine name. |
| `supports_voice_design` | `bool` | `False` | Accepts a written description of a voice in place of reference audio (FR-015). Deliberately separate from `supports_instruct`, which means delivery instructions (C1Q5). |
| `requires_download_confirmation` | `bool` | `False` | The app asks the user to confirm before downloading this model (FR-018; C1Q7 chose this engine only, not a size threshold). |
| `min_memory_mb` | `int \| None` | `None` | Memory below which the app warns before download (C1Q4). Advisory only, never a gate. `None` means no warning. Added after the T010 code review on 2026-09-23. |
| `advanced_settings` | `tuple[AdvancedSetting, ...]` | `()` | Generation settings the app may expose as advanced controls, each with a name, label, default, minimum and maximum (FR-010, C1Q8). Empty for every existing engine. |

### The VoxCPM2 instance

| Field | Value | Source |
| --- | --- | --- |
| `model_name` | `voxcpm2` | — |
| `display_name` | `VoxCPM2 (Multilingual, Voice Design)` | — |
| `engine` | `voxcpm` | FR-001 |
| `hf_repo_id` | `openbmb/VoxCPM2` | issue #13 |
| `model_size` | `default` | single size only; out of scope to add variants |
| `size_mb` | `4961` | research.md R3, measured |
| `needs_trim` | `False` | vendor trims internally via VAD (`voxcpm2.py:420`) |
| `retries_runaway` | `False` | Voicebox's own split-and-retry stays off; upstream already retries (`retry_badcase=True`), research.md R5.5 |
| `supports_instruct` | `False` | VoxCPM2 takes no delivery instructions; keeps the existing instruction box off for it (C1Q5) |
| `supports_voice_design` | `True` | FR-015 |
| `requires_download_confirmation` | `True` | FR-018, C1Q7 |
| `advanced_settings` | `cfg_value` (default 2.0, range 1.0–3.0), `inference_timesteps` (default 10, range 4–30) | FR-010, C1Q8; the "recommended" ranges in voxcpm 2.0.3 `cli.py` |
| `languages` | 30 codes including `ar`, in model-card order | FR-007; evidence/probe/15-language-list.txt |
| `license_id` | `Apache-2.0` | confirmed via the HuggingFace API |
| `commercial_use` | `True` | the premise of the whole feature |
| `dialect` | `None` | multi-dialect, not a single-dialect checkpoint |
| `accelerators` | `("cuda", "mps", "cpu")` | research.md R2 — vendor documents all three |
| `min_memory_mb` | `6144` (the probe's peak of about 5.9 GB of GPU memory on short text, rounded up) | C1Q4; evidence/probe.md Q8 |

**Validation**: `engine` must match the four regex patterns in
[backend/models.py](../../backend/models.py) at lines 92, 413, 432 and 451. All four take
the same alternation and all four must be updated together.

---

## 2. `EngineAvailability` — new, transient

Computed per request from the declared `accelerators` and the machine's detected hardware.
Never persisted; there is no stored notion of "this machine cannot run this engine".

| Field | Type | Meaning |
| --- | --- | --- |
| `engine` | `str` | Engine identifier, e.g. `voxcpm`. |
| `available` | `bool` | Whether the engine can be selected here. |
| `reason` | `str \| None` | Present only when `available` is false. A short, specific, user-facing sentence — FR-003 requires a stated reason, not a bare disabled control. |
| `warning` | `str \| None` | Present when the engine is available but the machine looks marginal. Carries the C1Q4 insufficient-memory warning. |
| `supported_accelerators` | `list[str]` | Echo of the declaration, so the UI can explain what would be needed. |

### State rules

```text
declared accelerators empty            -> available, no warning        (all existing engines)
detected accelerator in declared set
    and memory looks sufficient        -> available, no warning
    and memory looks marginal          -> available, warning           (C1Q4)
detected accelerator not in set,
    but "cpu" is declared              -> available, warning that it   (FR-023)
                                          runs on the processor
detected accelerator not in set,
    and "cpu" is not declared          -> unavailable, reason          (FR-003)
```

The processor-fallback row is what happens to VoxCPM2 on an Intel XPU or DirectML machine.
The detector reports that accelerator, but VoxCPM2 picks its own device without XPU or
DirectML, so it really does run on the processor. It is offered, with a warning that it will
be slower; the graphics-memory warning does not apply there. No registered engine currently
reaches the unavailable row; it stays as a guard for an engine that declares no processor path.

Memory is deliberately **not** a hard gate (C1Q4 answered B): free memory changes with
whatever else is running, so a threshold would wrongly exclude machines that would have
worked. The warning is surfaced before the 4961 MB download, which is the last moment it
is cheap to act on.

---

## 3. Voice description and the designed profile

Every generation needs a Voice Profile, so voice design (FR-015) is reached through a
**designed profile** (FR-015a). A written description can come from two places:

| Source | Where it lives | Stored? |
| --- | --- | --- |
| Designed profile | Voice Profile with `voice_type = "designed"` and a required `design_prompt` (up to 2000 characters). Created with the "Describe a voice" source in the profile dialog. | Yes, in the existing `design_prompt` column. No new column, no migration. |
| One-off request description | The optional `voice_description` field on the generation request (up to 500 characters). | Yes, in the new nullable `generations.voice_description` column, stripped, and only when the resolved engine declares voice design (otherwise null). Retry and regenerate replay it. When it is null, a designed profile's `design_prompt` applies as before. Reference audio still wins over both. |

Rules for both:

- Any language is accepted (C1Q9); it does not have to match the spoken text.
- The description never travels in `instruct`, which stays the delivery-instruction channel
  (C1Q5). `resolve_backend_instruct` in `backend/services/generation.py` puts it into the
  backend's `instruct` parameter only for engines whose `supports_voice_design` is true.
  Other engines get `instruct` unchanged, exactly as before.
- VoxCPM2 encodes it as the `"(description)text"` prefix (probe Q9).

**Precedence** (T048, resolving the C1Q6 edge case):

```text
profile with reference audio (cloned)       -> clone from the audio; any description is unused,
                                               and the generate box says so
request voice_description, not blank        -> design the voice from the request description
designed profile, blank request description -> design the voice from the profile's design_prompt
```

The first row is enforced in the backend: VoxCPM2 ignores the description whenever the voice
prompt carries a recording. The other two are decided in `resolve_backend_instruct`, which
falls back to `profile_design_prompt(voice_prompt)` when the request description is blank.

---

## 4. `VoxCPM2VoicePrompt` — new, transient and cached

The prepared reference for one profile, reused across generations (FR-013).

| Field | Type | Notes |
| --- | --- | --- |
| `prompt_wav_path` | `str` | Path to the reference audio. |
| `prompt_text` | `str` | Its transcript. **Both fields are mandatory together** — the vendor raises `ValueError` if exactly one is supplied (research.md R5.3). |

**Cache key**: `"voxcpm_" + get_cache_key(audio_path, reference_text)`, following the
`"luxtts_"` prefix convention. The prefix is what keeps one profile's prepared reference
from being served to a different engine, which would silently produce the wrong voice.

**Difference from LuxTTS**: LuxTTS runs Whisper internally and ignores the supplied
transcript, so it caches only an encoded blob. VoxCPM2 needs the real transcript at
generation time, so the cached value must carry it.

---

## 5. Reused, with the changes this feature made

- **Voice Profile** and its reference clips — no schema change. Multi-clip profiles go
  through the shared `combine_voice_prompts` helper (FR-012), combined at 24000 Hz to match
  the combined reference `backend/services/profiles.py` saves. The designed source (§3) uses
  existing columns. The profile service now saves reference samples and the combined
  reference with `disclosure=None` (§6).
- **Pronunciation dictionary** — applied to input text before generation (FR-008). Upstream
  normalization stays off (`normalize=False`) so it cannot undo the Arabic diacritics
  handling from PR #11.
- **Model download progress** and the HuggingFace cache — reused via `model_load_progress`
  (FR-016).
- **Generation queue and history** — the queue is unchanged. Generations are stored as
  before, plus the one-off `voice_description` (voice-design engines only) so retry and regenerate can replay it. Advanced settings are not stored. The generation export manifest moves to 1.1 and carries `voice_description` (null when empty); a 1.0 archive imports with none.
- **Audio writing** — changed. `save_audio` in `backend/utils/audio.py` now writes the
  AI-generated disclosure by default, and a new `wav_bytes()` helper does the same for audio
  that is never saved to disk (§6).
- **Effects** — the effect chain itself is unchanged, but the effects preview route
  (`backend/routes/effects.py`) now encodes its WAV with `wav_bytes()`, so a preview carries
  the disclosure. Processed versions are saved through `save_audio` and are tagged too.

---

## 6. AI-generated disclosure metadata (FR-026)

Generated audio carries a disclosure in the WAV's RIFF `LIST`/`INFO` chunk:

| INFO tag | Value written | Value read back |
| --- | --- | --- |
| `ICMT` (comment) | `AI-generated by Voicebox` (`AI_GENERATED_DISCLOSURE`) | the same |
| `ISFT` (software) | `Voicebox` | libsndfile appends its version, e.g. `Voicebox (libsndfile-1.2.2)` |

Source: `_write_wav` in `backend/utils/audio.py`. The read-back values are from a real run,
evidence/phase6/realrun-t051-tag.txt. The audio samples are unchanged; only the metadata is
added.

Where it is written:

| Surface | Writer | Tagged? |
| --- | --- | --- |
| Saved generations and processed versions, including `/speak` and MCP speak (both go through `generate_speech`) | `save_audio(...)`, disclosure on by default | Yes |
| `/generate/stream` | `tts.audio_to_wav_bytes` → `wav_bytes()` | Yes |
| Effects preview | `wav_bytes()` in `routes/effects.py` | Yes |
| Profile reference samples | `save_audio(..., disclosure=None)` in `services/profiles.py` | No |
| Combined multi-clip reference | `save_audio(..., 24000, disclosure=None)` in `services/profiles.py` | No |
| Transcription re-encode of the user's upload | `save_audio(..., disclosure=None)` in `routes/transcription.py` | No |
| Temporary chunk-0 prompt for designed long text (internal, deleted when the generation ends) | `save_audio(..., disclosure=None)` in `voxcpm_backend.continuation_voice_prompt` | No, never shown or saved for the user |

With `disclosure=None` no comment and no software tag are set, so libsndfile writes no INFO
chunk at all. The user's own recordings are never labelled AI-generated.

---

## 7. Profile export manifest 1.1 (FR-027)

`backend/services/export_import.py` writes `manifest.json` with `"version": "1.1"`. The
`profile` object gains five fields next to `name`, `description` and `language`:

| Field | Meaning |
| --- | --- |
| `voice_type` | `cloned`, `preset` or `designed` |
| `preset_engine` | The engine of a preset voice; null otherwise |
| `preset_voice_id` | The preset voice's id; null otherwise |
| `design_prompt` | A designed profile's written description; null otherwise |
| `default_engine` | The profile's default engine, or null |

- All five are existing profile columns, so there is no migration.
- On import, each field present and not null is restored, and `create_profile` validates the
  combination. An invalid one (for example a designed profile with a blank description) is
  refused, not silently turned into a cloned profile.
- A 1.0 manifest has none of these fields and imports as a cloned profile with no default
  engine, as before.
- A cloned profile still needs at least one sample to export. Designed and preset profiles
  can be exported with no samples, since their metadata fully describes them.
- The profile's personality text is not carried by the export.

---

## Entity relationships

```text
ModelConfig(engine="voxcpm", accelerators=("cuda","mps","cpu"))
      │
      ├── declares ──> EngineAvailability   (computed per machine, never stored)
      │
      └── selected by ──> GenerationRequest
                               │
                               ├── VoiceProfile (cloned) ──> VoxCPM2VoicePrompt  (cached)
                               │                                └── prompt_wav_path + prompt_text
                               ├── VoiceProfile (designed) ──> design_prompt  (stored)
                               │
                               └── voice_description  (one-off; stored on the generation for voice-design engines; unused with a cloned profile)
```
