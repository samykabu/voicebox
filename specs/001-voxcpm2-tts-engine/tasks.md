# Tasks: VoxCPM2 Text-to-Speech Engine

**Input**: Design documents from `specs/001-voxcpm2-tts-engine/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)
**Source issue**: [samykabu/voicebox#13](https://github.com/samykabu/voicebox/issues/13)
**Generator**: SuperSpec Tasks, fallback mode — the Superpowers `writing-plans` skill is not installed at `.agents/skills/` or `~/.agents/skills/`, so tasks are decomposed directly from the plan.

**Tests**: Requested. The plan's Execution Strategy names three `[TDD]` areas, and backend tests follow the existing convention in `backend/tests/test_f5tts_backend.py`: no checkpoints are downloaded, the vendor package is replaced with small deterministic fakes. `just test` does not run in CI, so it is run locally and stated in the PR.

## Format: `[ID] [Markers] [Story] Headline`, detail on the indented line below

Each task line is a short headline, which becomes its GitHub sub-issue title. The full
detail, including file paths and the requirements it covers, sits on the indented line
beneath it.

| Marker | Meaning |
| --- | --- |
| `[P]` | Parallel — different files, no dependency on an unfinished task |
| `[TDD]` | Write the test first, watch it fail, then implement |
| `[REVIEW]` | Pause for human code review before dependent work proceeds |
| `[HUMAN-REVIEW]` | Decision gate — execution stops until a human decides. Not skippable under `checkpoints: required-only` |
| `[SUBAGENT]` | Self-contained enough to hand to a parallel sub-agent |
| `[US1]`…`[US4]` | The user story from spec.md the task serves |

---

## Phase 1: Setup — dependency probe (blocks everything)

**Purpose**: Answer the technical unknowns research could not settle from published metadata. Several answers can change scope, so nothing else starts until this phase closes.

- [x] T001 Run the VoxCPM2 dependency probe in a scratch venv; record findings in evidence/probe.md
  - Run the dependency probe in a scratch virtual environment outside the project env, per [quickstart.md](./quickstart.md) Step 0. Install `voxcpm` **with** its dependencies to observe the real resolution. Record every answer in `specs/001-voxcpm2-tts-engine/evidence/probe.md`: Python ceiling (expected none, research R1), CPU generation actually working and its speed, MPS where hardware allows, on-disk size (expected 4961 MB, R3), whether numpy resolves to 1.x or 2.x, whether torch satisfies `>=2.5.0`, the real `model.tts_model.sample_rate`, peak inference memory, the exact voice-design prompt form (R6), the full 30-language code list, the minimal import set that works under `--no-deps`, and whether a cached load succeeds with the network blocked without any HuggingFace or ModelScope request (Principle I). Preserve raw command output alongside the summary. **Covers**: FR-006, FR-018, FR-019, FR-023; research R1–R6.
- [x] T002 [HUMAN-REVIEW] Review probe findings: effort re-assessment, User Story 3 priority, voxcpm version pin
  - Review the probe findings and decide three things before any implementation: (a) **effort re-assessment** — research deleted work (R1, R2) and clarification added four deliverables (C1Q4, C1Q5, C1Q7, C1Q8) after the 13-point estimate was approved; re-run Scope for #13 if the estimate moves; (b) whether User Story 3 drops from P1 to P2 and FR-023's exception is withdrawn, per research's recommendations; (c) the exact `voxcpm` version to pin. Record the decisions in `specs/001-voxcpm2-tts-engine/evidence/probe.md`. **Covers**: FR-023; effort re-assessment.

**Checkpoint**: probe reviewed, effort confirmed or re-scoped, version pinned.

---

## Phase 2: Foundational — install plumbing and the capability channel

**Purpose**: Everything every user story depends on. The capability channel (FR-024) is here rather than in User Story 3 because User Story 1 already needs it — FR-007 requires the language list to come from the engine's declaration.

**⚠️ No user story work begins until this phase is complete.**

### Install and packaging

- [x] T003 [P] [SUBAGENT] Add VoxCPM2 runtime dependencies to backend/requirements.txt
  - Add the minimal required transitive dependencies from T001 to `backend/requirements.txt`: the probe found only numpy, huggingface-hub, einops, pydantic, transformers and librosa beyond torch/torchaudio (evidence/probe.md Q11); keep the existing pins. Exclude `gradio`, `datasets`, `spaces` and anything else the probe showed is unused at runtime (research R4). Must not disturb `numpy>=1.24.0,<2.0` or `transformers<=4.57.6`. **Covers**: FR-019.
- [x] T004 [P] [SUBAGENT] Install voxcpm with --no-deps on the Unix setup path in justfile
  - Add `pip install --no-deps 'voxcpm==2.0.3'` to the Unix setup path in `justfile` after the `habibi-tts` line (`justfile:67-74`), with a one-line comment on why `--no-deps`, matching the existing entries. **Covers**: FR-019.
- [x] T005 [P] [SUBAGENT] Install voxcpm with --no-deps on the Windows setup path in justfile
  - Add the same install to the Windows setup path in `justfile` (`justfile:120-123`). Do **not** change the interpreter selection at `justfile:21` — research R1 showed there is no Python ceiling. **Covers**: FR-019.

### Engine validation

- [x] T006 [TDD] Test that engine validation accepts voxcpm in backend/tests/test_engine_patterns.py
  - Write `backend/tests/test_engine_patterns.py` asserting `voxcpm` is accepted and an unknown engine is rejected by every engine-validated field in `backend/models.py` (the four patterns at lines 92, 413, 432 and 451). Watch it fail. **Covers**: FR-001.
- [x] T007 Add voxcpm to the four engine patterns in backend/models.py
  - Add `voxcpm` to all four regex alternations in `backend/models.py` (lines 92, 413, 432, 451). T006 passes. **Covers**: FR-001.

### Capability channel (FR-002, FR-004, FR-024)

- [x] T008 [TDD] Test engine availability resolution in backend/tests/test_engine_capabilities.py
  - Write `backend/tests/test_engine_capabilities.py` covering availability resolution per [data-model.md](./data-model.md) §2 and the invariants in [contracts/engine-capabilities.md](./contracts/engine-capabilities.md): empty `accelerators` → available with no reason; detected accelerator in the declared set → available; not in the set → unavailable **with** a reason; supported but marginal memory → available with a warning, never blocked (C1Q4); `available == false` always implies `reason != null`. Use injected device and memory values — no torch. Watch it fail. **Covers**: FR-002, FR-003, FR-004.
- [x] T009 Add capability fields to ModelConfig and the availability resolver in backends/base.py
  - Add `accelerators: tuple[str, ...] = ()`, `supports_voice_design: bool = False`, `requires_download_confirmation: bool = False` and `advanced_settings: tuple[AdvancedSetting, ...] = ()` to `ModelConfig` in `backend/backends/__init__.py` per [data-model.md](./data-model.md) §1, and implement the availability resolver in `backend/backends/base.py` with torch imported lazily (`# lazy: heavy import`). Every default preserves today's behaviour, so all seven existing engines are unchanged. T008 passes. **Covers**: FR-002, FR-004, FR-024.
- [x] T010 [REVIEW] Add GET /models/engines and the optional GenerationRequest fields
  - Add the Pydantic response models to `backend/models.py` and `GET /models/engines` to `backend/routes/models.py`, per [contracts/engine-capabilities.md](./contracts/engine-capabilities.md). Add the two optional `GenerationRequest` fields from the contract, `voice_description` and `advanced_settings`, both defaulting to `None`, with 422 validation against the engine's declared bounds. Extend `test_engine_capabilities.py` with a route test and a validation test. The endpoint must never load a model or trigger a download. **Review the contract shape before T011** — it is a public surface under Principle V and plan.md Human Checkpoint 2. **Covers**: FR-004, FR-024.
- [x] T011 Regenerate the TypeScript client with bun run generate:api
  - Regenerate the TypeScript client with `bun run generate:api`. Never hand-edit the generated directories `app/src/lib/api/models/`, `app/src/lib/api/services/` or `app/src/lib/api/core/`. (Note: `app/src/lib/api/types.ts` is hand-written — see Notes.) **Covers**: FR-024.
- [x] T012 [P] Document GET /models/engines in backend/README.md
  - Document `GET /models/engines` in `backend/README.md` (Principle V). **Covers**: FR-024.
- [x] T013 [P] Add the useEngineCapabilities hook in app/src/lib/hooks/useEngineCapabilities.ts
  - Create `app/src/lib/hooks/useEngineCapabilities.ts`, a query hook over the regenerated client, following the `cuda-status` query pattern in `app/src/components/ServerSettings/GpuAcceleration.tsx`. **Covers**: FR-004, FR-024.

**Checkpoint**: `just test` green for the new tests; `/models/engines` returns all engines, with every existing engine reporting `supported_accelerators: []` and `available: true`.

---

## Phase 3: User Story 1 — Generate speech, including Arabic, under a permissive licence (P1) 🎯 MVP

**Goal**: VoxCPM2 is selectable, downloads with confirmation and progress, and generates speech — Arabic included — respecting the pronunciation dictionary.

**Independent Test**: [quickstart.md](./quickstart.md) Steps 2 and 3.

### Tests for User Story 1

- [ ] T014 [TDD] [US1] Test the VoxCPM2 backend contract in backend/tests/test_voxcpm_backend.py
  - Write `backend/tests/test_voxcpm_backend.py` with a fake `voxcpm` module injected into `sys.modules`, following `test_f5tts_backend.py`. Assert, per [contracts/tts-backend-protocol.md](./contracts/tts-backend-protocol.md): `load_model` is idempotent, passes `load_denoiser=False`, passes an explicit device (never `"auto"`), and runs inside `model_load_progress`; `generate` returns `(ndarray, model.tts_model.sample_rate)` — the fake uses a non-48000 rate so a hardcoded literal fails; `normalize=False` is passed; `manual_seed` is applied before the vendor call and no `seed` argument reaches the vendor (voxcpm 2.0.3 has none; research R5 correction); no heavy import happens at module import time; `unload_model` calls `empty_device_cache` and leaves `is_loaded()` false; `_is_model_cached` recognises `.pth` as well as `.safetensors`. Watch it fail. **Covers**: FR-006, FR-009, FR-016, FR-017.

### Implementation for User Story 1

- [ ] T015 [US1] Create backend/backends/voxcpm_backend.py (load, generate, unload)
  - Create `backend/backends/voxcpm_backend.py` modelled on `luxtts_backend.py` with the three deviations in research R7: runtime sample rate, explicit device from `get_torch_device(allow_mps=True, ...)`, and a transcript-carrying voice prompt. Implement `load_model`, `generate`, `unload_model`, `is_loaded`, `_get_model_path`, `_is_model_cached`. T014 passes. **Covers**: FR-006, FR-016, FR-017.
- [ ] T016 [US1] Register VoxCPM2 in TTS_ENGINES, the model configs and the backend dispatcher
  - Register the engine in `backend/backends/__init__.py`: `"voxcpm": "VoxCPM2"` in `TTS_ENGINES` (line 214); the `ModelConfig` from [data-model.md](./data-model.md) §1 in `_get_non_qwen_tts_configs()` (line 296), using the probe's size, language list and accelerators, with `supports_instruct=False`, `supports_voice_design=True`, `requires_download_confirmation=True` and the two declared `advanced_settings`; the lazy-import dispatch branch in `get_tts_backend_for_engine()` (line 798). **Covers**: FR-001, FR-005, FR-007.
- [ ] T017 [P] [US1] [SUBAGENT] Add VoxCPM2 hidden imports and data files to backend/build_binary.py
  - Add `voxcpm` hidden imports and data collection to `backend/build_binary.py`, mirroring the `kokoro` (line 276) and `f5_tts` (line 310) entries. Account for `torchcodec` and its FFmpeg shared libraries (research R4). **Covers**: FR-020.
- [ ] T018 [P] [US1] Add 'voxcpm' to the engine union in app/src/lib/api/types.ts
  - Add `'voxcpm'` to the engine union in `app/src/lib/api/types.ts` (hand-written). **Covers**: FR-001.
- [ ] T019 [US1] Add VoxCPM2 to the engine picker in EngineModelSelector.tsx
  - Add the VoxCPM2 option to `ENGINE_OPTIONS` in `app/src/components/Generation/EngineModelSelector.tsx`. Registration is the only per-engine line allowed; any availability or capability decision reads `useEngineCapabilities`, never the engine name (FR-004). **Covers**: FR-001, FR-004.
- [ ] T020 [US1] Read VoxCPM2 languages from its capability declaration in languages.ts
  - Make `getLanguageOptionsForEngine` in `app/src/lib/constants/languages.ts` prefer the engine's declared `languages` from `useEngineCapabilities` when present, falling back to the existing hardcoded map for the seven unmigrated engines (FR-007, FR-024). **Covers**: FR-007, FR-024.
- [ ] T021 [P] [US1] Wire VoxCPM2 through useGenerationForm, FloatingGenerateBox and format.ts
  - Wire the engine through `app/src/lib/hooks/useGenerationForm.ts`, `app/src/components/Generation/FloatingGenerateBox.tsx` and `app/src/lib/utils/format.ts` (display name, engine label). **Covers**: FR-001.
- [ ] T022 [US1] Show VoxCPM2 licence, size and a download confirmation in ModelManagement.tsx
  - Add a VoxCPM2 entry to the model description map in `app/src/components/ServerSettings/ModelManagement.tsx` (around line 76) stating Apache-2.0 and commercial use (FR-005). Show the download size and require confirmation before starting the VoxCPM2 download in `app/src/components/ServerSettings/ModelManagement.tsx` (FR-018, C1Q7). Driven by the capability's `requires_download_confirmation`, never the engine name. **Covers**: FR-005, FR-016, FR-018.
- [ ] T023 [US1] Expose VoxCPM2 advanced generation settings from its declaration
  - Render advanced controls from the capability's `advanced_settings` with each default preselected (FR-010, C1Q8), send them as the request's `advanced_settings`, pass them as the optional `options` argument only to engines that declare settings (in `backend/services/generation.py`), and apply them in `voxcpm_backend.generate` with declared defaults as fallback. Bounds come from T001. **Covers**: FR-010.
- [ ] T024 [US1] Verify Arabic generation respects the pronunciation dictionary
  - Verify Arabic end to end: add a case to `backend/tests/test_voxcpm_backend.py` proving pronunciation-dictionary-processed text reaches the vendor unchanged with `normalize=False`, then generate Arabic manually per quickstart Step 3 and record the result in `specs/001-voxcpm2-tts-engine/evidence/`. Confirms FR-008 does not regress the PR #11 diacritics work. **Covers**: FR-007, FR-008.

- [ ] T046 [TDD] [US1] Test that a cached VoxCPM2 model loads with the network blocked
  - Add an offline-load test to `backend/tests/test_voxcpm_backend.py`: with `_is_model_cached()` true and every socket connection patched to fail, `load_model` succeeds, runs inside `force_offline_if_cached`, and the fake vendor records no HuggingFace or ModelScope resolution. Watch it fail. **Covers**: constitution Principle I.
- [ ] T047 [US1] Load VoxCPM2 offline from the local HuggingFace cache only
  - Wrap the cached load in `force_offline_if_cached(True, "VoxCPM2")` from `backend/utils/hf_offline_patch.py` and resolve the model from the local HuggingFace cache only, never the ModelScope hub, in `backend/backends/voxcpm_backend.py`. T046 passes; confirm manually with [quickstart.md](./quickstart.md) Step 2b. **Covers**: constitution Principle I.

**Checkpoint**: VoxCPM2 selectable, downloads with confirmation and progress, generates in English and Arabic. MVP.

---

## Phase 4: User Story 2 — Clone a voice with the new engine (P1)

**Goal**: Existing Voice Profiles, single- or multi-clip, clone with VoxCPM2; same seed gives identical audio.

**Independent Test**: [quickstart.md](./quickstart.md) Step 4.

- [ ] T025 [TDD] [US2] Test VoxCPM2 voice prompt caching, pairing and seeding
  - Extend `backend/tests/test_voxcpm_backend.py`: `create_voice_prompt` uses the `"voxcpm_"` cache-key prefix, returns both `prompt_wav_path` and `prompt_text`, and reports `was_cached=True` on the second call; `generate` never passes exactly one of the pair (the vendor raises); `combine_voice_prompts` uses the model's encode rate, not a literal; the same seed produces identical fake output. Watch it fail. **Covers**: FR-009, FR-011, FR-012, FR-013.
- [ ] T026 [US2] Implement VoxCPM2 voice prompts, multi-clip combining and seeding
  - Implement `create_voice_prompt`, `combine_voice_prompts` (delegating to the shared helper in `backends/base.py`) and seeding with `manual_seed` in `backend/backends/voxcpm_backend.py`. T025 passes. **Covers**: FR-009, FR-011, FR-012, FR-013.
- [ ] T027 [P] [US2] Add voxcpm to CLONING_ENGINES in backend/services/profiles.py
  - Add `voxcpm` to `CLONING_ENGINES` in `backend/services/profiles.py` (line 27) (FR-014). **Covers**: FR-014.
- [ ] T028 [US2] Offer cloning profiles for VoxCPM2 from its capability declaration
  - Make profile/engine compatibility in `EngineModelSelector.tsx` and `app/src/components/VoiceProfiles/ProfileForm.tsx` offer cloning profiles for VoxCPM2 via the capability's `supports_cloning`, not the engine name. **Covers**: FR-011, FR-014.

**Checkpoint**: cloning works for single- and multi-clip profiles; seeded runs are reproducible.

---

## Phase 5: User Story 3 — Know up front whether this engine can run here (P2)

**Goal**: An unusable engine is visibly greyed out with a reason; a marginal machine is warned before the download; nothing reaches a crash.

**Independent Test**: [quickstart.md](./quickstart.md) Step 5.

- [ ] T029 [TDD] [US3] Test that generation refuses an unavailable engine with its reason
  - Test that a generation request for an engine the resolver marks unavailable is refused with its stated reason before any model load, in `backend/tests/test_engine_capabilities.py`. The refusal must be generic — driven by the resolver, not an engine-name check in `backend/routes/`. Watch it fail. **Covers**: FR-003.
- [ ] T030 [US3] Refuse generation for unavailable engines in the generation service
  - Implement the generic refusal where generation requests are accepted (`backend/routes/generations.py` / `backend/services/generation.py`). T029 passes. **Covers**: FR-003.
- [ ] T031 [US3] Show an unavailable engine greyed out with its reason in the picker
  - Render an unavailable engine greyed out with its `reason`, never hidden, and show `warning` when present, in `EngineModelSelector.tsx` (FR-003, C1Q3). **Covers**: FR-003.
- [ ] T032 [US3] Warn about insufficient memory before the VoxCPM2 download
  - Surface the insufficient-memory `warning` before the download starts in `ModelManagement.tsx` — advisory only, never blocking (C1Q4). **Covers**: FR-003.
- [ ] T033 [US3] Verify no engine-name capability branching for voxcpm in app and routes
  - Verify no hardware or capability branching on the engine name: `grep -rn "voxcpm" app/src backend/routes` must show only registration lines. Record the output in `specs/001-voxcpm2-tts-engine/evidence/` (FR-004, SC-009). **Covers**: FR-004.

**Checkpoint**: forcing an unsupported device shows a greyed-out engine with a reason and no path to a crash.

---

## Phase 6: User Story 4 — Create a voice without a recording (P3)

**Goal**: A written description produces a voice; it has its own labelled input; a profile's recording wins over it.

**Independent Test**: [quickstart.md](./quickstart.md) Step 6.

- [ ] T034 [TDD] [US4] Test VoxCPM2 voice design precedence and encoding
  - Extend `backend/tests/test_voxcpm_backend.py` with the precedence table from [data-model.md](./data-model.md) §3: description only → the service passes `voice_description` into the backend's `instruct` parameter, which is encoded into `text` in the form confirmed by T001, and delivery-instruction text in `instruct` never reaches VoxCPM2; profile audio plus description → clone from audio and the description is **not** applied (C1Q6); description in a different language from the text → accepted (C1Q9). Watch it fail. **Covers**: FR-015.
- [ ] T035 [US4] Implement voice_description mapping and voice design in the backend
  - Map `voice_description` into the backend `instruct` parameter only for engines declaring `supports_voice_design` in `backend/services/generation.py`, and implement the encoding and precedence in `voxcpm_backend.generate`. T034 passes. **Covers**: FR-015.
- [ ] T036 [US4] Add a labelled voice-description input to FloatingGenerateBox.tsx
  - Add a distinct, clearly labelled voice-description input to `app/src/components/Generation/FloatingGenerateBox.tsx`, separate from the delivery-instruction field and shown only when the engine's `supports_voice_design` is true and sent as `voice_description`, never as `instruct` (FR-015, C1Q5). When a profile with reference audio is selected, state plainly that the description is not being used (C1Q6). **Covers**: FR-015.
- [ ] T037 [REVIEW] [HUMAN-REVIEW] [US4] Consent and disclosure review of the voice design path (Principle II)
  - Principle II consent review: confirm the voice-design path carries the same responsible-use acknowledgement and AI-generated disclosure affordances as the cloning path, since it creates a voice without the reference-audio step (plan.md Human Checkpoint 3). **Covers**: FR-015; constitution Principle II.

**Checkpoint**: voice design works and has passed the consent review.

---

## Phase 7: Polish & Cross-Cutting

- [ ] T038 [P] [SUBAGENT] Document VoxCPM2 in tts-engines.mdx
  - Add VoxCPM2 to `docs/content/docs/developer/tts-engines.mdx`, following its own new-engine guidance (FR-021). **Covers**: FR-021.
- [ ] T039 [P] [SUBAGENT] Document VoxCPM2 in model-management.mdx
  - Add VoxCPM2 to `docs/content/docs/developer/model-management.mdx`, including the ~4961 MB size and the confirmation step (FR-021). **Covers**: FR-021.
- [ ] T040 [P] [SUBAGENT] Record VoxCPM2 in CHANGELOG.md
  - Record the user-visible addition in `CHANGELOG.md` (FR-022). **Covers**: FR-022.
- [ ] T041 Add a VoxCPM2 case to backend/tests/test_all_models_e2e.py
  - Add a VoxCPM2 case to `backend/tests/test_all_models_e2e.py`, respecting its existing opt-in/skip behaviour for models that download. **Covers**: FR-006, FR-011.
- [ ] T042 Build the frozen desktop backend and confirm VoxCPM2 is registered
  - Build the frozen desktop backend with `python backend/build_binary.py` and confirm it starts with VoxCPM2 registered (FR-020, SC-008). Record output in `specs/001-voxcpm2-tts-engine/evidence/`. **Covers**: FR-020.
- [ ] T043 Run all constitution quality gates and keep the output as evidence
  - Run every constitution quality gate and keep the output as evidence: `just check-js`, `bun run typecheck`, `just check-python`, `just test`, `bun run build:web`. **Covers**: constitution quality gates.
- [ ] T044 Run quickstart Steps 1-8 on Windows and Linux
  - Run [quickstart.md](./quickstart.md) Steps 1–8, including `just setup` from a clean checkout on Windows **and** Linux, and confirm every pre-existing engine still generates (SC-007). Record results in `specs/001-voxcpm2-tts-engine/evidence/`. **Covers**: FR-019, SC-001–SC-009.
- [ ] T045 [HUMAN-REVIEW] Final review against the spec before merge
  - Final review against the spec before merge (plan.md Human Checkpoint 4). The PR must state that `just test` was run locally. **Covers**: all.

---

## Dependencies & Execution Order

### Phase dependencies

```text
Phase 1 (T001 → T002)            blocks everything; T002 is a human gate
      ↓
Phase 2 install   (T003, T004, T005)          parallel with ↓
Phase 2 patterns  (T006 → T007)
Phase 2 capability(T008 → T009 → T010 → T011 → T013)   T010 is a review gate; T012 parallel after T010
      ↓
Phase 3 US1 (T014 → T015 → T016; T017, T018 parallel; T019–T023 after T013 + T016; T024 and T046 → T047 after T015)
      ↓
Phase 4 US2 (T025 → T026; T027 parallel; T028 after T013)      needs T015
Phase 5 US3 (T029 → T030; T031, T032 after T013; T033 last)    needs T009, T016
Phase 6 US4 (T034 → T035 → T036 → T037)                         needs T015 and T001's prompt form
      ↓
Phase 7 (T038–T040 parallel any time after T016; T041–T045 after all stories)
```

### Within each story

`[TDD]` tests are written and seen failing before their implementation task. Backend before frontend. The frontend never reads a capability before T011 regenerates the client.

### Parallel opportunities

| Stream | Tasks | Why independent |
| --- | --- | --- |
| Install plumbing | T003, T004, T005 | Disjoint files; only need T002's pinned version |
| Frozen build | T017 | Only `build_binary.py` |
| Docs | T038, T039, T040 | No code files |
| Cloning backend vs. availability refusal | T025–T027 vs. T029–T030 | Different files, both only need Phase 2 and T015 |

Backend engine work (T014–T016) and install plumbing (T003–T005) are the plan's named parallel pair after the probe.

---

## Implementation Strategy

1. **Probe first, alone** (T001), then stop at the human gate (T002). Do not start Phase 2 on assumptions the probe could overturn.
2. **Foundational** — install plumbing in parallel with the capability channel; pause at T010 for contract review.
3. **MVP = User Story 1** — selectable, downloads with confirmation, generates English and Arabic. Validate independently.
4. **User Stories 2 and 3** can proceed in parallel after US1's backend exists.
5. **User Story 4** last; it waits on the probe's prompt-form answer and ends at a consent review.
6. **Polish** — docs, E2E case, frozen build, every gate, quickstart on both platforms, final review.

Per the project's standing preference, execution commits and pushes at each phase's completion.

---

## Notes

**`app/src/lib/api/types.ts` is hand-written, not generated.** Its header reads "API Types matching backend Pydantic models", and the generated client lives in `app/src/lib/api/models/`, `services/` and `core/`. Corrected in the contract and plan during Analyze (finding M1). T018 edits it deliberately.

**Contract gaps resolved during Analyze (findings H3–H5).** The capability contract now declares `supports_voice_design`, `requires_download_confirmation` and `advanced_settings`, and `GenerationRequest` gains two optional fields, `voice_description` and `advanced_settings`. Voice descriptions never travel in `instruct`, and VoxCPM2 declares `supports_instruct=False`, so the delivery-instruction box stays off for it (C1Q5). The backend protocol is unchanged for the eight existing engines: `voice_description` reaches the existing `instruct` parameter only for engines declaring voice design, and the optional `options` argument is passed only to engines declaring advanced settings.

**Offline load added during Analyze (finding C1).** Principle I requires a cached model to load with no network. `voxcpm` depends on `modelscope`, which the existing HuggingFace offline switch does not cover, and `force_offline_if_cached` had no backend caller. T046 and T047 close that gap. Their IDs follow T045 to keep existing IDs stable, and they sit in Phase 3 where they belong.

**Research recommendations still pending a human decision (T002).** User Story 3's P1 rating and FR-023's exception both rest on a CUDA-only risk that research R2 showed is not real. They are left as written here — changing them is a spec decision, not a task-generation one.
