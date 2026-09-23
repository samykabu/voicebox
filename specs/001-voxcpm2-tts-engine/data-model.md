# Phase 1 Data Model: VoxCPM2 TTS Engine

**Feature**: `specs/001-voxcpm2-tts-engine` | **Date**: 2026-09-22

This feature stores no new persistent data. It extends one existing in-memory descriptor,
adds two transient runtime shapes, and reuses the existing Voice Profile and cache entities
unchanged. There is no database migration.

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
| `retries_runaway` | `True` | `retry_badcase=True` upstream, research.md R5.5 |
| `supports_instruct` | `False` | VoxCPM2 takes no delivery instructions; keeps the existing instruction box off for it (C1Q5) |
| `supports_voice_design` | `True` | FR-015 |
| `requires_download_confirmation` | `True` | FR-018, C1Q7 |
| `advanced_settings` | `cfg_value` (default 2.0), `inference_timesteps` (default 10) | FR-010, C1Q8; defaults from upstream, bounds confirmed by the probe (T001) |
| `languages` | 30 codes including `ar` | FR-007; exact list confirmed by the probe |
| `license_id` | `Apache-2.0` | confirmed via the HuggingFace API |
| `commercial_use` | `True` | the premise of the whole feature |
| `dialect` | `None` | multi-dialect, not a single-dialect checkpoint |
| `accelerators` | `("cuda", "mps", "cpu")` | research.md R2 — vendor documents all three |
| `min_memory_mb` | set in T016 from the probe (peak about 5.9 GB of GPU memory on short text) | C1Q4; evidence/probe.md Q8 |

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
detected accelerator not in set        -> unavailable, reason          (FR-003)
```

Memory is deliberately **not** a hard gate (C1Q4 answered B): free memory changes with
whatever else is running, so a threshold would wrongly exclude machines that would have
worked. The warning is surfaced before the 4961 MB download, which is the last moment it
is cheap to act on.

---

## 3. `VoiceDescription` — new, transient

The written description of a voice, used when no reference audio is supplied (FR-015).

| Field | Type | Rules |
| --- | --- | --- |
| `text` | `str` | Free text. Any language is accepted (C1Q9); no language match with the spoken text is required. |
| `active` | `bool` | False when a Voice Profile with reference audio is also selected — the recording wins (C1Q6) and the interface must say the description is unused. |

Not persisted as its own record in v1. It travels in a new optional `voice_description`
field on the generation request, never in `instruct`, which stays the delivery-instruction
channel (C1Q5). The service passes it to the backend only for engines whose
`supports_voice_design` is true, and the backend encodes it into the prompt text; the exact
encoding is confirmed by the probe (research.md R6).

**Precedence**, resolving the C1Q6 edge case:

```text
profile with reference audio + description  -> clone from audio; description inactive, stated in the UI
profile with reference audio, no description -> clone from audio
description only, no profile                 -> design the voice from the description
neither                                      -> default voice for the engine
```

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

## 5. Reused unchanged

- **Voice Profile** and its reference clips — no schema change. Multi-clip profiles go
  through the shared `combine_voice_prompts` helper (FR-012).
- **Pronunciation dictionary** — applied to input text before generation (FR-008). Upstream
  normalization stays off (`normalize=False`) so it cannot undo the Arabic diacritics
  handling from PR #11.
- **Model download progress** and the HuggingFace cache — reused via `model_load_progress`
  (FR-016).
- **Generation queue, history and effects** — untouched.

---

## Entity relationships

```text
ModelConfig(engine="voxcpm", accelerators=("cuda","mps","cpu"))
      │
      ├── declares ──> EngineAvailability   (computed per machine, never stored)
      │
      └── selected by ──> GenerationRequest
                               │
                               ├── VoiceProfile ──> VoxCPM2VoicePrompt  (cached)
                               │                        └── prompt_wav_path + prompt_text
                               │
                               └── VoiceDescription  (inactive when a profile is present)
```
