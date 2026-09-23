# Contract: VoxCPM2 against the TTSBackend protocol

**Feature**: `specs/001-voxcpm2-tts-engine` | **Date**: 2026-09-22

How `backend/backends/voxcpm_backend.py` satisfies the existing protocol in
[backend/backends/__init__.py](../../../backend/backends/__init__.py#L68). The protocol is
unchanged by this feature — this is a conformance contract for a new implementation, not a
protocol revision.

Signatures below are verified against upstream `main` (research.md R5), not assumed from
the source issue.

---

## `load_model(model_size: str = "default") -> None`

```python
VoxCPM.from_pretrained(
    "openbmb/VoxCPM2",
    load_denoiser=False,      # upstream defaults to True, which contacts ModelScope (probe Q12)
    local_files_only=<True when cached>,   # Principle I; probe Q12
    device=<our resolved device>,
)
```

- Wrapped in `model_load_progress(model_name, is_cached)` so the UI shows the download bar (FR-016).
- Runs in a worker thread via `asyncio.to_thread`; must not block the event loop.
- Idempotent — returns immediately if already loaded, as LuxTTS does.
- `from voxcpm import VoxCPM` is imported **inside** the function, marked `# lazy: heavy import` (Principle III).
- **Device is passed explicitly**, not left as `"auto"`. Upstream would pick CUDA → MPS → CPU on its own, but our `get_torch_device(allow_mps=True, allow_xpu=...)` policy must stay authoritative and observable.

## `create_voice_prompt(audio_path, reference_text, use_cache=True) -> tuple[dict, bool]`

- Cache key: `"voxcpm_" + get_cache_key(audio_path, reference_text)`. The prefix prevents cross-engine reuse producing the wrong voice.
- Returns `({"prompt_wav_path": ..., "prompt_text": ...}, was_cached)`.
- **Both keys are mandatory.** Upstream raises `ValueError` if exactly one of `prompt_wav_path`/`prompt_text` is supplied (research.md R5.3).
- Unlike LuxTTS, the real transcript matters here and must be carried, not discarded.

## `combine_voice_prompts(audio_paths, reference_texts) -> tuple[np.ndarray, str]`

- Delegates to the shared `combine_voice_prompts` in `backends/base.py` (FR-012).
- Combined audio is produced at 24000 Hz, the same rate `backend/services/profiles.py` uses when it saves a combined reference WAV, so the file the profile stores and the prompt VoxCPM2 receives agree. VoxCPM2 resamples its prompt to its own 16 kHz encode rate on load, so the combine rate does not need to match it. Amended 2026-09-23 after Phase 3 review; this replaces the earlier instruction to combine at the encode rate.

## `generate(text, voice_prompt, language="en", seed=None, instruct=None) -> tuple[np.ndarray, int]`

```python
audio = model.generate(
    text=<pronunciation-dictionary-processed text, with voice description prefix if designing>,
    prompt_wav_path=voice_prompt.get("prompt_wav_path"),
    prompt_text=voice_prompt.get("prompt_text"),
    cfg_value=<configured default, exposed as an advanced control>,
    inference_timesteps=<configured default, exposed as an advanced control>,
    normalize=False,
)
return audio, model.tts_model.sample_rate
```

Four rules this call must respect:

1. **`generate()` returns a bare `np.ndarray`, not a tuple.** The backend pairs it with the rate. The array is float32, 1-D, already on CPU.
2. **Read the sample rate from the model.** `voxcpm2.py:249` computes it as `getattr(audio_vae, "out_sample_rate", audio_vae.sample_rate)`, and the encode rate differs from the output rate. Copying LuxTTS's hardcoded `return audio, 48000` would be a latent bug even if 48000 happens to be right today.
3. **`normalize=False`.** Upstream text normalization would run after our pronunciation dictionary and could undo the Arabic diacritics handling from PR #11 (FR-008).
4. **Do not add our own runaway retry.** Upstream retries internally (`retry_badcase=True`); the engine declares `retries_runaway=True` instead.

`seed` is applied with `manual_seed(seed, device)` immediately before calling the vendor, matching the LuxTTS pattern (FR-009). It is **not** passed to the vendor: voxcpm 2.0.3, the pinned release, has no `seed` parameter (research.md R5 correction).

`instruct` carries the written voice description (FR-015). The API keeps the two apart: the request's `voice_description` field, not its `instruct` field. The generation service maps `voice_description` into this parameter only for engines declaring `supports_voice_design`, and VoxCPM2 declares `supports_instruct=False`, so delivery instructions never reach it. Existing backends see no change. The exact encoding into `text` (the documented `"(description)text"` prefix) is confirmed by the probe before this is written (research.md R6). When a voice profile with reference audio is present, the description is inactive (C1Q6).

`options: dict[str, float] | None = None` is an **additive, optional** protocol parameter carrying the request's `advanced_settings` (FR-010). The generation service passes it only to engines whose `ModelConfig.advanced_settings` is non-empty, so the eight existing backends are never called with it and need no change. VoxCPM2 maps `cfg_value` and `inference_timesteps` from it, falling back to the declared defaults.

## `unload_model() -> None`

- Drops the model reference, clears the cached device, calls `empty_device_cache(device)` (FR-017).
- After it returns, `is_loaded()` must report `False`.

## `is_loaded() -> bool` / `_get_model_path(model_size) -> str`

- `is_loaded`: `self.model is not None`.
- `_get_model_path`: returns `"openbmb/VoxCPM2"`.
- **Offline load (Principle I, non-negotiable)**: when `_is_model_cached()` is true, loading runs inside `force_offline_if_cached(True, "VoxCPM2")` from `backend/utils/hf_offline_patch.py` and the model resolves from the local HuggingFace cache only. `voxcpm` depends on `modelscope`; it must never fall back to the ModelScope hub, and a cached load must succeed with the network blocked.
- `_is_model_cached`: `is_model_cached(VOXCPM_HF_REPO, weight_extensions=(".safetensors", ".pth", ".bin"))` — note `audiovae.pth` is a `.pth`, so that extension must be included or a fully cached model will look uncached and re-trigger the progress path.

---

## Registry conformance

| Site | Change |
| --- | --- |
| `TTS_ENGINES` ([:214](../../../backend/backends/__init__.py#L214)) | add `"voxcpm": "VoxCPM2"` |
| `_get_non_qwen_tts_configs()` ([:296](../../../backend/backends/__init__.py#L296)) | add the `ModelConfig` from [data-model.md](../data-model.md) |
| `get_tts_backend_for_engine()` ([:798](../../../backend/backends/__init__.py#L798)) | add the `elif engine == "voxcpm"` dispatch branch with a lazy import |
| Unknown-engine error ([:859](../../../backend/backends/__init__.py#L859)) | no change — derives from `TTS_ENGINES` automatically |
| `backend/models.py` :92, :413, :432, :451 | add `voxcpm` to all four regex alternations |
| `CLONING_ENGINES` ([profiles.py:27](../../../backend/services/profiles.py#L27)) | add `voxcpm` |

The dispatch branch is the one place an `if engine == ...` comparison is still correct —
it is a factory, in `backends/`, not capability branching in `routes/` or `app/`.

---

## Out of scope for v1

- `generate_streaming()` — exists upstream and works, but our pipeline is chunk-based.
- `reference_wav_path` — a VoxCPM2-only structurally-isolated cloning mode upstream supports and the source issue never mentioned. Worth a follow-up issue.
- `load_denoiser=True` and the `denoise` generation flag.
- Model size variants (VoxCPM 1.5, 0.5B).
