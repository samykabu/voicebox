# Arabic F5-TTS and Habibi-TTS implementation checklist

This checklist tracks the Docker-first integration of Arabic F5-TTS and Habibi-TTS voice cloning into Voicebox. The implementation starts from the native F5 backend proposed in upstream PR #833, hardens it for multiple checkpoints, and keeps all ML dependencies inside Docker for the initial release.

## Fixed architecture decisions

- [x] Work in `samykabu/voicebox` on `agent/arabic-f5-habibi`.
- [x] Preserve the existing standalone F5/Habibi portals; do not modify or replace them.
- [x] Reuse upstream PR #833's native `TTSBackend` implementation as the integration skeleton.
- [x] Use one Voicebox engine ID, `f5_tts`, for the Arabic F5/Habibi model family.
- [x] Use `habibi-msa` as the default. It is the same specialized checkpoint used by the standalone F5 Arabic MSA portal, so a duplicate model entry is unnecessary.
- [x] Keep Voicebox, Python, CUDA libraries, FFmpeg, F5-TTS, Habibi-TTS, and model weights inside Docker for the initial deployment.
- [x] Keep desktop/PyInstaller support best-effort and documented; Docker is the release gate.

## Model catalog

| Model ID | Display purpose | Checkpoint path | Dialect token | License/use |
|---|---|---|---|---|
| `habibi-msa` | Specialized Modern Standard Arabic; default | `Specialized/MSA/model_200000.safetensors` | None | Apache-2.0 |
| `habibi-unified` | Unified model with automatic/unknown dialect conditioning | `Unified/model_200000.safetensors` | `UNK` / `⓪` | CC-BY-NC-SA-4.0; noncommercial |
| `habibi-sau` | Specialized Saudi Arabic | `Specialized/SAU/model_200000.safetensors` | None | CC-BY-NC-SA-4.0; noncommercial |
| `habibi-uae` | Specialized UAE Arabic | `Specialized/UAE/model_100000.safetensors` | None | CC-BY-NC-SA-4.0; noncommercial |
| `habibi-alg` | Specialized Algerian Arabic | `Specialized/ALG/model_100000.safetensors` | None | Apache-2.0 |
| `habibi-irq` | Specialized Iraqi Arabic | `Specialized/IRQ/model_100000.safetensors` | None | Apache-2.0 |
| `habibi-egy` | Specialized Egyptian Arabic | `Specialized/EGY/model_100000.safetensors` | None | Apache-2.0 |
| `habibi-mar` | Specialized Moroccan Arabic | `Specialized/MAR/model_100000.safetensors` | None | Apache-2.0 |

Every model uses the matching `vocab.txt` from the same directory. The model registry must be the single source of truth for repository paths, filenames, display names, dialect conditioning, and license metadata.

## Phase 1: import and clean up the upstream F5 backend

- [x] Fetch upstream PR #833.
- [x] Cherry-pick all five PR commits onto the feature branch.
- [x] Remove Romanian-only model IDs, labels, language validation, and test text.
- [x] Remove unused imports and fragile compatibility code.
- [x] Retain the scoped SoundFile/Torchaudio compatibility wrapper rather than a process-wide monkeypatch.
- [x] Preserve incomplete Hugging Face download detection.
- [x] Keep model loading outside the async event loop.

## Phase 2: backend model lifecycle

- [x] Replace the single Romanian `MODELS` mapping with the Arabic/Habibi catalog above.
- [x] Normalize `default`, legacy aliases, and invalid IDs deterministically.
- [x] Pass the selected F5/Habibi model ID through `load_engine_model`.
- [x] Make model management load/download the selected checkpoint, vocabulary, and Vocos files.
- [x] Track the canonical loaded model ID.
- [x] Unload the previous checkpoint before switching variants.
- [x] Keep the Vocos lifecycle explicit and release GPU memory on unload.
- [x] Make `generate()` use the already selected model rather than silently resetting to a default.
- [x] Add a single inference lock around model switching and generation.
- [x] Ensure Web/API task cancellation cannot leave the backend in a partially loaded state.
- [x] Keep model-cache status accurate while Hugging Face blobs are incomplete.
- [ ] Return actionable errors for unknown models, missing references, missing transcripts, download failures, and CUDA OOM.

## Phase 3: Arabic prompt and inference behavior

- [x] Require a real reference audio path for F5/Habibi cloning.
- [x] Require non-empty reference text unless explicit ASR preprocessing has produced it.
- [x] Use deferred reference paths so Voicebox profiles remain lightweight.
- [x] Normalize audio to mono/24 kHz only through the existing audio helpers.
- [x] Enforce F5's 12-second reference limit.
- [x] If a longer reference is clipped, never retain a transcript for audio that was removed (the native backend rejects over-limit prompts instead of retaining mismatched text).
- [x] Preserve exact Arabic text and diacritics; do not silently transliterate or normalize letters.
- [x] Use Habibi's Arabic-aware inference path and Unified dialect token.
- [x] Keep specialized checkpoints unconditioned by a Unified dialect token.
- [x] Use Arabic-aware long-text chunking and cross-fading from Habibi-TTS.
- [x] Return one-dimensional `float32` audio at the actual sample rate.
- [x] Combine multiple profile samples at 24 kHz and preserve transcript ordering.

## Phase 4: backend registry and API contracts

- [x] Register all eight model configurations with `engine="f5_tts"` and `languages=["ar"]`.
- [x] Add accurate approximate download sizes.
- [x] Extend generation model validation to the eight canonical IDs only.
- [x] Keep Arabic in profile and generation language validation.
- [x] Ensure `engine_has_model_sizes("f5_tts")` returns true.
- [x] Pass the selected ID through normal generation, streaming generation, retry, history, and model-management paths.
- [x] Ensure loaded-model health/status reports the canonical ID.
- [x] Keep cloned profiles enabled for `f5_tts`.
- [x] Do not add a training workflow; this remains zero-shot cloning.

## Phase 5: frontend engine and model UX

- [x] Replace Romanian labels with Arabic F5/Habibi labels.
- [x] Add all eight canonical model IDs to TypeScript and form validation.
- [x] Force language `ar` when an Arabic F5/Habibi model is selected.
- [x] Preserve the selected model ID in `/generate` requests.
- [x] Default new selections to `habibi-msa`.
- [x] Restrict the engine to cloned/reference-audio profiles.
- [x] Add clear MSA, Unified, Saudi, UAE, Algerian, Iraqi, Egyptian, and Moroccan labels.
- [x] Explain that Unified is automatic dialect conditioning and may be less predictable than a specialized checkpoint.
- [x] Show Apache-2.0 versus CC-BY-NC-SA-4.0 in model descriptions.
- [x] Mark Unified, Saudi, and UAE as noncommercial.
- [x] Avoid duplicating the same MSA checkpoint under separate F5 and Habibi names.
- [x] Verify selector state, model management filtering, history labels, and profile compatibility.

## Phase 6: dependencies and packaging

- [x] Pin a tested F5-TTS version rather than leaving an unbounded lower constraint.
- [x] Pin a tested Habibi-TTS version.
- [x] Keep F5/Habibi package installation `--no-deps` where needed to avoid replacing Voicebox's PyTorch stack.
- [x] List only runtime subdependencies; avoid training-only packages where possible.
- [x] Pin TorchCodec to a PyTorch-compatible version in the CUDA Docker image.
- [x] Include `f5_tts`, `habibi_tts`, Vocos, tokenizer, and Hydra/OmegaConf resources in PyInstaller metadata where practical.
- [x] Do not remove existing MLX, CUDA, ROCm, MCP, or other engine packaging hooks.
- [x] Document desktop packaging as experimental until CI artifacts are exercised.

## Phase 7: Docker-only NVIDIA deployment

- [x] Preserve the existing generic CPU Compose workflow.
- [x] Add a dedicated NVIDIA/CUDA overlay or Compose file for Arabic F5/Habibi.
- [x] Use the tested PyTorch 2.8.0 / CUDA 12.8 base for RTX 50-series GPUs.
- [x] Pass all NVIDIA GPUs into the container while allowing `CUDA_VISIBLE_DEVICES` selection.
- [x] Persist Hugging Face, Torch, Voicebox database, profiles, history, and output data.
- [x] Bind the Voicebox web interface to localhost by default.
- [x] Add health checks and a sufficient first-start grace period for model downloads.
- [x] Configure shared memory and expandable CUDA allocation.
- [x] Avoid loading a second model copy in an API sidecar.
- [x] Document coexistence and VRAM contention with the standalone F5/Habibi portals.
- [x] Validate merged Compose configuration without requiring host Python or Bun.

## Phase 8: automated tests

- [x] Replace the root-level manual Romanian script with tests under `backend/tests/`.
- [x] Test model alias normalization and unknown-ID rejection.
- [x] Test every model's repository, checkpoint, vocabulary, dialect token, language, and license metadata.
- [x] Test cache checks for checkpoint, vocabulary, Vocos, and shared-repository variants.
- [x] Test loading the same model is idempotent.
- [x] Test switching models unloads the previous checkpoint.
- [x] Test generation does not reset the selected model.
- [x] Test reference path/text validation.
- [x] Test Unified passes the `UNK` dialect token.
- [x] Test specialized models pass no dialect token.
- [x] Test audio output conversion and sample rate through a real MSA generation.
- [x] Test two concurrent generations are serialized.
- [x] Test cancellation/error paths release locks.
- [ ] Run existing backend tests to catch regressions in other engines. Current Docker run: 126 passed, 1 skipped, and the unrelated `test_hf_progress_tracker` failed; two legacy collection-only files also require their native packaging/import harness.
- [x] Run TypeScript type checking, Biome checks, and web build.

## Phase 9: container and UI validation

- [x] Build the CUDA image and validate every image stage.
- [x] Start Voicebox without installing host ML dependencies.
- [x] Confirm CUDA availability and both intended GPUs inside the container.
- [x] Confirm the web app loads without framework overlays or relevant console errors.
- [x] Create or import a cloned Arabic profile with an exact transcript.
- [x] Verify the Arabic F5/Habibi selector shows the expected models and license warnings.
- [x] Generate MSA audio and verify WAV serving/history metadata.
- [ ] Generate at least two dialect variants.
- [ ] Switch checkpoints and confirm VRAM/model status changes.
- [ ] Run ten consecutive generations without a restart or growing GPU allocation.
- [ ] Submit simultaneous requests and confirm serialization rather than OOM.
- [x] Restart containers and verify profile/model/history persistence.

## Phase 10: documentation and publishing

- [x] Add Docker prerequisites, setup, start, stop, update, logs, GPU, persistence, and security instructions.
- [x] Add reference-audio quality and speaker-consent guidance.
- [x] Document every model's license and commercial-use restriction.
- [x] Add a troubleshooting section for model downloads, ports, CUDA, VRAM, TorchCodec, and playback.
- [x] Leave the generated changelog untouched and add the implementation/operator documentation instead.
- [ ] Review the complete diff and exclude generated caches, model weights, audio, databases, and secrets.
- [ ] Commit with an implementation-focused message.
- [ ] Push `agent/arabic-f5-habibi` to `samykabu/voicebox`.
- [ ] Open a draft PR against `samykabu/voicebox:main` with validation evidence and known limitations.

## Release acceptance criteria

- [x] Voicebox can create and use a cloned Arabic profile with reference audio and an exact transcript.
- [x] `habibi-msa` is the default and produces Arabic audio.
- [ ] Unified and all seven specialized model selections load the intended checkpoint.
- [x] Model switching never reuses the wrong checkpoint (covered by competing-model regression tests).
- [x] Unified generation applies automatic/unknown dialect conditioning; specialized models do not.
- [x] Generated WAV files are served as audio and appear in Voicebox history.
- [x] Concurrent inference is serialized without GPU OOM.
- [x] Model/profile/history data survives container recreation.
- [x] Both configured NVIDIA GPUs are visible to Docker; the selected device is used by Voicebox.
- [x] No Python, Bun, FFmpeg, CUDA Toolkit, F5-TTS, Habibi-TTS, or model package is installed on Windows for normal operation.
- [x] Noncommercial model restrictions are visible before selection/download.
- [x] Existing Voicebox engines and CPU/ROCm Compose paths remain intact.

## Deferred follow-up

- [ ] Evaluate a stable external `/v1/tts` provider after the native Docker integration is measured in production.
- [ ] Add explicit dialect selection independent of checkpoint selection if Voicebox adopts provider capabilities.
- [ ] Contribute the hardened generic F5 backend upstream after PR #833 is merged or superseded.
- [ ] Revisit cross-platform desktop bundling only after Windows CUDA, Linux CUDA, CPU, and Apple Silicon CI coverage exists.
