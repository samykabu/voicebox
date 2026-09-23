# Verify: VoxCPM2 feature (2026-09-23, re-run after the code-review fixes)

Run by the workflow dispatcher on branch `feature/001-voxcpm2-tts-engine` at HEAD 68e9cc0 (includes review fixes 20c4224 through 68e9cc0), on Windows 11 with an RTX 5070 (backend/venv: Python 3.12.14, torch 2.11.0+cu128).

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `pytest backend/tests --junitxml` | 1187 tests, 1 failure, 0 errors, 9 skipped (counts from `verify-backend.xml`) |
| The one failure | `tests.test_progress::test_hf_progress_tracker` | Also fails on `main` (4eb2a64) with the same venv, see `verify-baseline-main-progress.txt`. Not caused by this feature. |
| Type check | `bun run typecheck` | exit 0 |
| Web build | `bun run build:web` | exit 0 |
| Ruff | `ruff check backend`, `ruff format --check backend` | 1058 errors and 63 unformatted files, against 1063 and 63 on `main` (T043 baseline). No increase. |
| Biome | `bun run check` | 492 errors against 483 on `main`. The added findings are in `.specify/` and `specs/` JSON and one evidence copy of a test file, none in shipped app code. See the CRLF note in `verify-biome.txt`. |

Real-model runs (generation, cloning, Arabic, offline load, E2E, and the designed long-text run in evidence/review/I3-realrun.txt) and the human listening and UI checks are recorded in the phase evidence and `evidence/human/`. They were not repeated here.

Blocking findings: 0.
