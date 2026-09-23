# Quickstart Validation: VoxCPM2 TTS Engine

**Feature**: `specs/001-voxcpm2-tts-engine` | **Date**: 2026-09-22

How to verify this feature actually works. Every check maps to a requirement or a success
criterion, so a reviewer can confirm coverage rather than take it on trust.

**Before anything else**: `just test` does not run in CI (constitution, Quality Gates). The
author runs it locally and says so in the PR. That is a standing obligation, not a
formality.

---

## Step 0 — The dependency probe (do this first, alone)

The source issue requires this before backend code is written. Phase 0 research already
answered several of its questions from published metadata; this step confirms them against
a real environment and answers the rest.

```bash
python -m venv /tmp/voxcpm-probe          # a scratch venv, never the project env
/tmp/voxcpm-probe/bin/pip install voxcpm  # WITH deps, to observe the real resolution
/tmp/voxcpm-probe/bin/pip list
```

Record answers to all of these:

| Question | Expected from research | Confirm |
| --- | --- | --- |
| Python ceiling? | None. `requires-python >=3.10` (R1) | `pip show voxcpm` |
| Runs on CPU? | Yes. CUDA → MPS → CPU (R2) | `VoxCPM.from_pretrained(..., device="cpu")` and generate |
| Runs on MPS? | Documented (R2) | On Apple Silicon only |
| Real download size? | 4961 MB (R3) | `du -sh` the HF cache dir |
| numpy 1.x or 2.x? | **Unknown — the likely breakage** | `pip show numpy` |
| torch >= 2.5 satisfied? | **Unknown** | `pip show torch` |
| Output sample rate? | Claimed 48 kHz, not verifiable from source (R5.2) | `model.tts_model.sample_rate` |
| Inference memory? | Claimed ~8 GB, unverified | Watch during generation |
| Voice-design prompt form? | `"(description)text"`, unconfirmed (R6) | Generate with a description |
| Minimal import set? | 23 declared; several look excludable (R4) | Import in a `--no-deps` env, add until it works |
| Loads offline once cached? | **Unknown, Principle I gate** | With the model cached, block the network and load; confirm no HuggingFace or ModelScope request is attempted |

**Stop here and review the findings with a human** before writing backend code
(plan.md, Human Checkpoint 1). Several answers can change scope.

---

## Step 1 — Setup still works (FR-019, SC-007)

```bash
just setup          # on Windows AND on Linux, from a clean checkout
just check-python   # ruff
just test           # pytest — must pass locally
```

The thing that matters: **every engine that worked before still works after.** A `--no-deps`
mistake breaks Chatterbox, TADA, F5-TTS and Habibi silently. Generate once with an existing
engine before declaring this step done.

---

## Step 2 — Engine appears and generates (FR-001, FR-006, US1)

1. Start the backend and app.
2. Open the engine picker → **VoxCPM2 is listed** (SC-001 path).
3. Select it. A confirmation appears stating the download is ~4961 MB (FR-018, C1Q7).
4. Confirm → progress bar advances and completes (FR-016, SC-006).
5. Generate English text → audio plays.
6. Check the returned sample rate is the model's own, not a hardcoded literal.

## Step 2b — Offline load (Principle I, non-negotiable)

1. With VoxCPM2 fully downloaded, disconnect the network or block it at the firewall.
2. Restart the backend, select VoxCPM2 and generate.
3. It must load and generate with **no** request to HuggingFace or ModelScope. Any network attempt is a release-blocking failure, not a warning.

## Step 3 — Arabic under a permissive licence (FR-007, FR-008, SC-001)

1. Language selector with VoxCPM2 selected → the list comes from the engine's declaration and **includes Arabic** (FR-007).
2. Generate Arabic text → intelligible speech.
3. Generate Arabic text containing pronunciation-dictionary entries → pronounced as the dictionary specifies (FR-008). This is the PR #11 interaction; confirm upstream normalization did not undo it.
4. Inspect the engine's licence display → Apache-2.0, commercial use allowed.

## Step 4 — Cloning (FR-011 to FR-014, US2, SC-002)

1. Single-clip profile → generate → **recognisably the same speaker** (SC-002: 4 of 5 blind attempts).
2. Multi-clip profile → generate → succeeds and uses all clips (FR-012).
3. Generate twice with the same profile → the second run reuses the prepared reference (FR-013). Check the log or timing.
4. Same text, voice and seed twice → **byte-identical audio** (FR-009, SC-003).
5. Confirm the profile is offered for VoxCPM2 at all — it must be in `CLONING_ENGINES` (FR-014).

## Step 5 — Availability and memory (FR-002 to FR-004, US3, SC-004)

1. `GET /models/engines` → VoxCPM2 reports `supported_accelerators: ["cuda","mps","cpu"]`.
2. On a supported machine → `available: true`, no reason.
3. On a machine with a supported accelerator but little memory → `available: true` with a **warning before the download** (C1Q4). Not blocked.
4. To exercise the unavailable path, force an unsupported device. The engine must appear **greyed out with a specific reason** (C1Q3, FR-003), never hidden, and no route to it may reach a crash (SC-004).
5. `grep -rn "voxcpm" app/src` → **no hardware or capability branching on the engine name** (FR-004, SC-009). Data-driven conditionals are fine.

## Step 6 — Voice design (FR-015, US4, SC-005)

1. With no profile selected, a **distinct labelled voice-description input** is visible (C1Q5), not the delivery-instruction box, which stays hidden for VoxCPM2. Its text is sent as `voice_description`, never as `instruct`.
2. Enter a description, generate → the voice matches it.
3. Enter a description in English and generate Arabic speech → accepted (C1Q9). Record the real behaviour; document it if poor.
4. Select a profile *and* enter a description → **the recording wins and the UI says the description is unused** (C1Q6).
5. **Consent check (Principle II)**: the voice-design path carries the same disclosure affordances as cloning. This is a review gate, not a checkbox.

## Step 7 — Settings and lifecycle (FR-010, FR-017)

1. The generation-quality settings are exposed as **advanced controls with the chosen defaults preselected** (C1Q8, FR-010), rendered from the engine's declared `advanced_settings`. A value outside its declared bounds is rejected.
2. Unload the model → memory returns to the OS and the engine reports not loaded (FR-017).

## Step 8 — Packaging and docs (FR-020 to FR-022, SC-008)

1. `python backend/build_binary.py` → the frozen bundle builds and starts with VoxCPM2 registered (FR-020, SC-008). Watch for `torchcodec`/FFmpeg, a new system dependency (R4).
2. `bun run build:web`, `just check-js`, `bun run typecheck` all pass.
3. `tts-engines.mdx` and the model-management page cover VoxCPM2 (FR-021).
4. `CHANGELOG.md` records the addition (FR-022).
5. `backend/README.md` documents the new endpoint and the TS client was regenerated with `bun run generate:api`, not hand-edited (Principle V).

---

## Done when

- [ ] Probe findings recorded and reviewed
- [ ] `just setup` clean on Windows and Linux; all pre-existing engines still work
- [ ] Steps 2–7 pass
- [ ] Frozen build produces and starts
- [ ] Docs, changelog and API docs updated
- [ ] `just test` run locally and stated in the PR
