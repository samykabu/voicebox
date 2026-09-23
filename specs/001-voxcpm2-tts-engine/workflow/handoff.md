# Workflow handoff

- Feature: specs/001-voxcpm2-tts-engine
- Issue: samykabu/voicebox#13
- Branch: feature/001-voxcpm2-tts-engine
- Head: 4eb2a6431b416df9940831bb5f14fff34b00c059
- Reason: The revalidation driver's plan check wrongly required status Ready. plan-gate correctly returned In Progress with revalidation true and exit 0 for an in-progress feature. Recovering the plan claim so the corrected check can re-run. No artifacts changed.
- Next: {'stage': 'plan', 'command': 'speckit.plan', 'reason': 'pending'}
- Completed stages: scope, specify, clarify
- Active claim: None
- Pending task IDs: T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T046, T047, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036, T037, T038, T039, T040, T041, T042, T043, T044, T045

Read evidence paths and summaries in checkpoint.json; do not infer skipped tests passed.

Inspect git status before continuing; do not discard uncommitted files.

## Execution ownership

(Restored by the orchestrator on 2026-09-23. A runtime rewrite of this file had dropped it.)

- Execute claim: held by the dispatcher, current token c56a1c6527b242288b49f92f0ed58964 (earlier 7110c3a69ec5473c9768d3719560b8ed). Only the dispatcher completes or claims lifecycle stages.
- Orchestration agent: `a84da14fd8a1b2bec`, created by the dispatcher with the Claude Code Agent tool. It owns task assignment, integration review, the progress report (as its only writer), and phase commits and pushes.
- Progress report: `specs/001-voxcpm2-tts-engine/workflow/progress/index.html` (state is in `state.json` alongside). It is local only and excluded via `.git/info/exclude`.
- Phase 1 ran a single worker. T001 was the only ready task: T002 depended on it, and every other task depends on T002.
- T001: worker `acfb9a64552ba129d` (general-purpose, spawned by the orchestrator). The orchestrator reviewed it and marked it done. Evidence: `evidence/probe.md` and `evidence/probe/` (30 files, failed attempts kept).
- T001 scope deviation (not undone; the user decides): the worker ran `uv python install 3.12`, which linked CPython 3.12.14 under `%APPDATA%\uv\python` and added the shim `C:\Users\sabus\.local\bin\python3.12.exe`. The interpreter was probably already in uv's store. The scratch venvs `C:\Users\sabus\voxcpm-probe`, `voxcpm-nodeps` and `voxcpm-nodeps312`, the `C:\Users\sabus\voxcpm-probe-out` folder and the ~4.96 GB model in the default HF cache remain outside the repo.
- T002 ([HUMAN-REVIEW]) was decided by the user: pin voxcpm==2.0.3; effort re-scored from 13 to 8; User Story 3 moved to P2 and FR-023's exception withdrawn. Recorded in `evidence/probe.md` under "T002 decisions".
- Phase 1 commit: `08417b726c234aa342654959f097d7be0107e66d` on `feature/001-voxcpm2-tts-engine` (76 files; staged only `specs/001-voxcpm2-tts-engine/`, `.specify/scope/` and `.specify/project-sync-state.json`). Pushed with `git push -u origin feature/001-voxcpm2-tts-engine` (new remote branch, exit 0). `git ls-remote` returns the same SHA. The Sanduq upgrade changes under `.agents/`, `.claude/` and `.specify/` were left unstaged.
- Phase 2, batch 1 (2026-09-23), four workers in parallel:
  - T003 → `a4e708c2f155bbf59`, owns `backend/requirements.txt`.
  - T004 and T005 → `a8ac983afa0279999`, owns `justfile`. Both tasks go to one worker because they write the same file. The pin is `voxcpm==2.0.3 --no-deps`, and `justfile:21` is not touched.
  - T006 then T007 → `a65a7c2b10714ad2f`, owns the new `backend/tests/test_engine_patterns.py` and the four engine regexes in `backend/models.py`.
  - T008 then T009 → `a4f81f269334221b3`, owns the new `backend/tests/test_engine_capabilities.py`, the ModelConfig fields in `backend/backends/__init__.py`, and the resolver in `backend/backends/base.py`.
  - Shared resources: the scratch test env `C:\Users\sabus\voicebox-testenv` (read-only for workers) and `evidence/phase2/` (each task writes its own filenames).
  - T010 starts only after T007 and T009 are integrated, as an explicit handover of `backend/models.py` and `test_engine_capabilities.py`. T010 is a [REVIEW] gate: stop before T011.
- Test environment: `backend/venv` does not exist and `just` is not installed. Phase 2 tests run in a scratch venv outside the repo (py3.12.14 via uv, with fastapi, pydantic, numpy<2, librosa, pytest and ruff, but no torch). The baseline is in `evidence/phase2/00-baseline-pytest.txt`. `just test` has NOT been run.
- Phase 2, batch 1 accepted by the orchestrator after its own re-runs:
  - T003, T004 and T005 accepted on diff review.
  - T006 and T007: TDD red (4 failed), then green (57 passed).
  - T008 and T009: TDD red (ImportError), then green (198 passed).
  - ruff: no new findings.
- Open items for the user from T003:
  - `torch>=2.2.0` in requirements.txt is below voxcpm's declared `>=2.5.0`. It was left unchanged per the no-pin-change rule.
  - research.md R4 says the pin is `torch>=2.1`, but the actual pin is `>=2.2.0`.
- Phase 2, batch 2: T010 → `a65a7c2b10714ad2f`. This is the same owner as `backend/models.py`, and `test_engine_capabilities.py` was handed over from `a4f81f269334221b3` as append-only section 5. T010 is a [REVIEW] gate: stop before T011, T012 and T013.
- T010 implemented by `a65a7c2b10714ad2f` and verified by the orchestrator:
  - Red run: 41 failed.
  - Green run: 239 passed.
  - Whole suite in the scratch env: 15 failed, 415 passed, 5 skipped, 10 errors. The failure set is the same as the baseline.
  - ruff: no new findings.
- T010 is marked `blocked` in the report while it awaits the human contract review. Phase 2 is paused at this gate: T011, T012 and T013 have not started, and nothing is committed.
- Contract diff: `evidence/phase2/T010-contract-diff.txt`.
- Open review questions:
  - Should each engine be reported from its default-size config? That picks tada-1b (en only) and habibi-msa (Apache-2.0).
  - `display_name` is the variant name, not the engine name.
  - An engine with no config is skipped silently.
  - No memory-threshold field exists yet, so no warning is ever produced.
  - The route test stubs out `backend.services.profiles`, because it imports torch in this env.

## Dispatcher notes

- 2026-09-23 T010 code review (user): the contract was approved with two fixes. First, engine-level
  aggregation across variants: languages are combined, licence and commercial use are null when the
  variants disagree, and the display name comes from TTS_ENGINES. Second, `min_memory_mb` on
  ModelConfig so the C1Q4 warning can fire. The user also raised the torch floor to `>=2.5.0`.
- Upstream artifacts amended during Execute to match: contracts/engine-capabilities.md
  (invariants 6 and 7, plus field rules), data-model.md (`min_memory_mb`), and research.md (R4 torch
  pin). **Before completing the Execute claim, recover it and revalidate Plan → Tasks-to-Issues**,
  because the runtime rejects upstream drift at completion. The change is batched, so run the
  revalidation once at the end of Execute rather than per edit.
- T010 fix round (T010b), done by `a65a7c2b10714ad2f`. That worker took over the single `ModelConfig.min_memory_mb` field from `a4f81f269334221b3` by explicit handover.
  - `/models/engines` now aggregates every variant of an engine:
    - `display_name` comes from `TTS_ENGINES`.
    - `languages` is the union of all variants.
    - `license_id` and `commercial_use` are the value all variants share, or null if they differ.
    - Size, capability flags and `min_memory_mb` come from the default-size variant.
  - The route passes `min_memory_mb` through.
  - Results, verified by the orchestrator:
    - JUnit red run: tests=250, failures=12.
    - Green run: tests=307, failures=0.
    - Whole suite: tests=456, failures=15, errors=10, skipped=5. These are the same IDs that fail in the baseline.
- Torch floor raised to `torch>=2.5.0` in `backend/requirements.txt` (user decision; T003 follow-up by `a4e708c2f155bbf59`).
- T012 (README) done by `acdf87d17c5c83c4d`.
- T011 is blocked. `bun run generate:api` fails with `/usr/bin/bash: line 1: bun: command not found`, exit 127. The backend is not running (curl returns 000), and `backend/venv` does not exist. The generated client was not hand-edited. Evidence: `evidence/phase2/T011-generate-api-blocked.txt`.
- T013 is blocked on T011, because there is no regenerated client to build the hook on.
- Nothing is committed yet. The dispatcher confirms the Phase 2 commit.
- The user approved a partial Phase 2 commit. T011 and T013 stay blocked. Setting up the environment for T011 (bun, backend venv, running backend) is assigned to the dispatcher.
- Phase 2 partial commit: `cd42d4cdb319f2b2b084ec72458e284071fe3d61` on `feature/001-voxcpm2-tts-engine`.
  - 37 files. Staged were only the nine allowed backend/`justfile` paths plus `specs/001-voxcpm2-tts-engine/`.
  - The secret scan was clean. No hooks are installed (only `.sample` files, and no `core.hooksPath`), so no hook output was produced.
  - Pushed `08417b7..cd42d4c`, exit 0. `git ls-remote` returns the same SHA.
  - Phase 2 is recorded as `in-progress` because T011 and T013 are blocked.
  - Git for Windows was removed partway through the first commit attempt by external installers. It was reinstalled (2.55.0) via winget, and the staged set was checked and found intact before the commit.
- Phase 2 completion round. The dispatcher built the real environment: `backend/venv` with torch 2.11+cu128, bun 1.4.2, just 1.58.0, and the backend running on :17493, which the dispatcher owns. Assignments:
  - T011 then T013 → `a8f07092c2e5968c1`. It owns `app/src/lib/api/` (generator output), `app/openapi.json` and `app/src/lib/hooks/useEngineCapabilities.ts`, and backs up the hand-written `client.ts` and `types.ts` before regenerating.
  - The first full test run in the real env → `ab7e9bbf07701e289`. It writes evidence files only.
  - The `justfile:69` comment fix ("our torch>=2.1" becomes "our torch>=2.5.0") → `a8ac983afa0279999`.
- T011 done by `a8f07092c2e5968c1`.
  - `bun run generate:api` does not work on Windows: it prints "bun: unknown error" and exits 1. The same script run through Git Bash, `bash scripts/generate-api.sh`, against the running backend exits 0.
  - The client now has the `/models/engines` service method, the three Engine* models, and the two new GenerationRequest fields.
  - Also regenerated: 40 modified and 142 new files, all churn from the stale generated client.
  - The hand-written `client.ts` and `types.ts` are unchanged.
- T013 done by `a8f07092c2e5968c1`.
  - `app/src/lib/hooks/useEngineCapabilities.ts` uses the generated `request()` and types, with a per-call BASE set to `serverUrl`.
  - `bun run typecheck` exits 0, and Biome reports the hook clean.
  - `bun run check` fails, with pre-existing errors plus about 143 new format/import errors inside the generated directory. The user should decide whether to exclude that directory in `biome.json` or format it after generation.
- `justfile:69` comment updated to "our torch>=2.5.0" by `a8ac983afa0279999`.
- Real-env tests by `ab7e9bbf07701e289`:
  - Phase 2 files: tests=307, failures=0.
  - `just test` stops at collection on the error in `test_profile_duplicate_names`, which is not a Phase 2 file.
  - A run with `--continue-on-collection-errors` gave 516 passed, 1 failed (`test_progress::test_hf_progress_tracker`) and 6 skipped before it was stopped.
- **The backend venv is damaged.** `test_rocm_build.py::TestRocmBuildE2E::test_rocm_binary_compiles_and_runs` has no gate. It runs `build_binary.py --rocm`, which force-reinstalled ROCm torch into `backend/venv`. Stopping the run skipped its restore step.
  - The venv now has torch 2.9.1+rocm7.2.1 and CUDA is unavailable.
  - It needs a reinstall of cu128 torch, torchaudio and torchvision and removal of the rocm packages. The commands are in `evidence/phase2/realenv-suite.txt`.
  - This is assigned to the dispatcher; the orchestrator has not repaired it.
- Phase 2 completion commit `0c35cabce63ac9bb93537343bb77ca7cf4f9f4b7`: 193 files, pushed as `cd42d4c..0c35cab`. `git ls-remote` returns the same SHA. No hooks are installed. Phase 2 is marked complete in the report.
- Chores committed and pushed:
  - A1 `e94d457`: gates the ROCm E2E test behind `VOICEBOX_TEST_ROCM_INSTALL`.
  - A2 `ef5fe32`: switches the duplicate-names test to `backend.` imports and adds `engine.dispose()`.
  - A3 `d6a3a11`: Biome now excludes the generated client (core, models, schemas, services, index.ts).
  - The remote matches `d6a3a11`.
- New real-env suite baseline (JUnit): tests=544, failures=1, errors=0, skipped=8. The failure is `tests.test_progress::test_hf_progress_tracker` ("Should have captured progress updates"). Evidence: `evidence/chores/suite-baseline.*`.
- Phase 3, batch 1:
  - `a9197df34d3ed7487` (backend) owns T014, T015 and T016: `test_voxcpm_backend.py`, `voxcpm_backend.py` and the registry sites in `__init__.py`. It stays the single writer of `voxcpm_backend.py` for T046, T047, T024 and the T023 backend part.
  - `a97468ba17891381a` owns T017 (`build_binary.py`) and T018 (`types.ts`, which is handed to the frontend worker afterwards).
- Phase 3, batch 1 reviewed:
  - T014 and T015 are done. T017 and T018 are done.
  - T017 incident: the worker's evidence script called `build_server()`, which ran `pip --force-reinstall` for CPU torch and then cu128 torch in `backend/venv` (16:16–16:17 +03:00). The orchestrator verified torch is back at 2.11.0+cu128 with CUDA available.
  - T016's registry is accepted. The capability tests are handed over to the backend worker.
- Phase 3, batch 2:
  - `a9197df34d3ed7487` owns the caps-test fix, T046, T047, the T024 test and the T023 backend part. That covers `test_engine_capabilities.py` (handover), `generation.py` and `routes/generations.py`. It also does the real-model Arabic and offline runs.
  - `a9505a747d4388a3b` owns T019–T022 and the T023 frontend part, with `types.ts` handed over from `a97468ba17891381a`.
  - Open for the dispatcher: `COMBINE_SAMPLE_RATE` is 24000, matching the `profiles.py` save, but the contract says to use the encode rate (16 kHz).
- Phase 3 reviewed:
  - T014–T024, T046 and T047 are done.
  - Full suite (JUnit): tests=637, failures=1, errors=0, skipped=8. The one failure is the baseline `test_hf_progress_tracker`.
  - Real Arabic run on CUDA: 6.40 s of audio at 48 kHz, peak 5464 MiB. The WAV is outside the repo and still needs a human listen to judge intelligibility.
  - Real offline run: 0 HuggingFace and 0 ModelScope requests, both with and without the env vars.
- Open items for the dispatcher and user:
  1. `COMBINE_SAMPLE_RATE` is 24000, but the contract specifies the 16 kHz encode rate.
  2. Seven VoxCPM2 languages (my, id, km, lo, tl, th, vi) are rejected by the backend language regexes. The app filters them out.
  3. VoxCPM2 is not offered for cloned profiles until Phase 4 adds cloning (`supports_cloning` is false).
  4. Retry, regenerate and `/speak` do not carry `advanced_settings`.
  5. `run_generation` still sends `instruct` to every engine. The mapping from `voice_description` belongs to US4.
  6. There is no frontend test runner. The capability-logic tests were run from the scratchpad (16 tests, 0 failures) and are not committed.
  7. Suggest adding `step` to the `advanced_settings` contract.
  8. During T017 the worker accidentally swapped torch in the venv; it was restored.
