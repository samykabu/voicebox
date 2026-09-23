# Verify: VoxCPM2 feature (2026-09-23)

Run by the workflow dispatcher on branch `feature/001-voxcpm2-tts-engine` after commit e1399a2, on Windows 11 with an RTX 5070 (backend/venv: Python 3.12.14, torch 2.11.0+cu128).

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `pytest backend/tests --junitxml` | 1073 tests, 1 failure, 0 errors, 9 skipped (counts from `verify-backend.xml`) |
| The one failure | `tests.test_progress::test_hf_progress_tracker` | Also fails on `main` (4eb2a64) with the same venv, see `verify-baseline-main-progress.txt`. Not caused by this feature. |
| Type check | `bun run typecheck` | exit 0 |
| Web build | `bun run build:web` | exit 0 |
| Ruff | `ruff check backend`, `ruff format --check backend` | 1060 errors and 63 unformatted files, against 1063 and 63 on `main` (T043 baseline). No increase. |
| Biome | `bun run check` | 491 errors, same as the T043 measurement. All 8 above the `main` baseline of 483 are in `.specify/` and `specs/` JSON, none in app source. |

Real-model runs (generation, cloning, Arabic, offline load, E2E) and the human listening and UI checks are recorded in the phase evidence and `evidence/human/`. They were not repeated here.

Blocking findings: 0.
