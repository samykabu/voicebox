# Phase 0 Research: VoxCPM2 TTS Engine

**Feature**: `specs/001-voxcpm2-tts-engine` | **Date**: 2026-09-22 | **Issue**: [#13](https://github.com/samykabu/voicebox/issues/13)

All findings below come from the upstream package's published metadata and its source on
`main`, retrieved 2026-09-22. Nothing here required installing the package. Two of the
source issue's five stated risks did not survive contact with that evidence; both are
recorded in full rather than quietly corrected, because the issue's own risk list is what
the effort estimate was built on.

---

## R1 — Python version ceiling

**Decision**: No Python ceiling exists. `backend/pyproject.toml` stays at `>=3.12` and
[justfile:21](../../justfile#L21) keeps its `python3.13` fallback unchanged.

**Evidence**: PyPI metadata for `voxcpm` 2.0.3 declares `requires_python: >=3.10`. There
is no upper bound.

**This contradicts the source issue.** Risk 2 states that "`voxcpm` requires Python
`<3.13`" and that the justfile's fallback to 3.13 "would break". That is not true of the
current release. Either the constraint was lifted upstream or it was read from an older
version.

**Consequence**: one planned change is deleted. Do not edit the justfile's interpreter
selection. This also removes the only part of the feature that could have pressed on the
constitution's language-floor rule, so no amendment is in play.

**Alternatives considered**: pinning an older `voxcpm` that does carry the ceiling —
rejected, as it would import the constraint the issue was worried about for no benefit.

---

## R2 — Accelerator support (the headline risk)

**Decision**: Treat VoxCPM2 as a normal multi-accelerator engine using the existing
`get_torch_device` helper. Do **not** build it as a CUDA-only engine.

**Evidence**: `src/voxcpm/core.py` documents the `device` parameter on both `__init__`
and `from_pretrained`:

> `device`: Runtime device. If set to `None` or `"auto"`, VoxCPM will choose
> automatically (preferring CUDA, then MPS, then CPU). If set explicitly, that device is
> used or a clear error is raised.
>
> Use `None`/`"auto"` for automatic fallback, or an explicit value such as `"cpu"`,
> `"mps"`, `"cuda"`, or `"cuda:0"`.

**This contradicts the source issue.** Risk 1 states the engine is "CUDA-only", that
upstream "documents no CPU or MPS path", and that this "would be our first engine with
**no macOS support at all**". Upstream documents exactly those paths, including MPS,
which is Apple Silicon. The open question the issue asked — *does `voxcpm` actually run
on CPU, just slowly?* — is answered yes by the vendor's own contract.

**Consequence, and it is large.** This is the premise of clarification question C1Q1,
which was answered A ("ship on supported hardware, with a clear unavailable state
everywhere else"). That question's own text said the decision "disappears" if a processor
path exists. It does. So:

- FR-023 remains literally true but its condition ("even if it proves to require a
  specific accelerator with no processor fallback") does not appear to trigger. The
  engine is expected to run on every accelerator the product already supports.
- The unavailable state required by FR-003 stays in scope, but as genuine defensive
  behaviour for a machine that cannot load the model, not as the normal experience for
  every Mac and AMD user.
- **User Story 3 is over-prioritised at P1** on the strength of a risk that has not
  materialised. It should be reconsidered at P2. That is a specification change, so it is
  raised here rather than made unilaterally.
- The constitution's "CPU is the guaranteed fallback" rule is satisfied normally. No
  declared exception is needed.

**Still unverified**: whether CPU inference is fast enough to be *useful* for a 2B model,
and whether MPS works in practice rather than only in the docstring. Both are performance
and correctness questions for the probe task, not blockers for planning.

**Alternatives considered**: building CUDA-only as the issue proposed — rejected, it
would gratuitously exclude Apple Silicon and AMD users the vendor already supports, and
would violate the accelerator-matrix rule for no reason.

---

## R3 — Real model footprint

**Decision**: `size_mb = 4961`. Read the output sample rate at runtime; do not hardcode.

**Evidence**: the HuggingFace API for `openbmb/VoxCPM2` reports 9 files totalling
4,960,731,866 bytes:

| File | Size |
| --- | --- |
| `model.safetensors` | 4580 MB |
| `audiovae.pth` | 377 MB |
| remaining 7 files | ~4 MB |

License confirmed `apache-2.0`, matching the issue's claim and the commercial-use premise
of the whole feature.

**Consequence**: resolves FR-018's measurement half. At 4961 MB this is comfortably the
largest model in the product — the next largest is Chatterbox at 3200 MB — which supports
the C1Q7 decision to confirm before downloading. The issue's estimate of "≈ 5000" was
accurate.

**Note**: this is download size. The issue's separate claim of ~8 GB VRAM at inference is
unverified and is a probe task; it drives the C1Q4 memory warning threshold.

---

## R4 — Transitive dependencies and conflict analysis

**Decision**: install with `--no-deps`, following the established pattern, and add only
the genuinely required transitive packages to `backend/requirements.txt`.

**Evidence**: `voxcpm` 2.0.3 declares 23 runtime dependencies: `torch>=2.5.0`,
`torchaudio>=2.5.0`, `torchcodec`, `transformers>=4.36.2`, `einops`, `gradio>=6,<7`,
`inflect`, `addict`, `wetext`, `modelscope>=1.22.0`, `datasets>=3,<4`, `huggingface-hub`,
`pydantic`, `tqdm`, `simplejson`, `sortedcontainers`, `soundfile`, `librosa`,
`matplotlib`, `funasr`, `spaces`, `argbind`, `safetensors`.

Checked against our pins in [backend/requirements.txt](../../backend/requirements.txt):

| Their requirement | Our pin | Verdict |
| --- | --- | --- |
| `transformers>=4.36.2` | `>=4.36.0,<=4.57.6` | **Compatible.** The issue expected a conflict here; there is none. |
| `torch>=2.5.0` | `torch>=2.2.0` (raised to `>=2.5.0` by user decision at T010 review, 2026-09-23) | **Needs attention.** Our floor is lower than theirs. Whether the installed torch satisfies 2.5 is environment-dependent and is a probe task. |
| `gradio>=6,<7` | not pinned; `f5-tts` already installed `--no-deps` partly over gradio bounds | **Conflict, and the main justification for `--no-deps`.** A web UI framework is not needed for library use. |
| `datasets>=3,<4` | not pinned | Exclude. Training/eval dependency. |
| `numpy` (indirect, via librosa/torch) | `>=1.24.0,<2.0` | **Unresolved.** Not declared directly by `voxcpm`, but several of its dependencies now prefer numpy 2. This is the one pin most likely to break and must be confirmed by the probe. |
| `torchcodec` | absent | **New system dependency.** Needs FFmpeg shared libraries present at runtime; matters for the frozen build. |
| `funasr`, `modelscope`, `spaces`, `argbind`, `wetext` | absent | Likely excludable. `spaces` is a HuggingFace Spaces helper with no role in a local app. |

**Consequence**: the issue's risk 3 said "the full transitive dependency set needs to be
enumerated by hand" — it is now enumerated above, which converts an unknown into a
short, concrete verification task. The genuinely open item is the numpy boundary.

**Alternatives considered**: a plain `pip install voxcpm` — rejected, `gradio>=6` and
`datasets>=3` would disturb a working environment for four other engines.

---

## R5 — Generation API

**Decision**: map our backend protocol onto `_generate` as below; read the sample rate
from the loaded model.

**Evidence**: `VoxCPM.generate(...)` delegates to `_generate`, whose real signature is:

```python
text, prompt_wav_path=None, prompt_text=None, reference_wav_path=None,
cfg_value=2.0, inference_timesteps=10, min_len=2, max_len=4096,
normalize=False, denoise=False, retry_badcase=True,
retry_badcase_max_times=3, retry_badcase_ratio_threshold=6.0,
streaming=False, seed=None
```

Findings that change the implementation:

1. **`generate()` returns a bare `np.ndarray`, not `(audio, sample_rate)`.** Our protocol
   requires the tuple, so the backend pairs the array with the rate itself. The waveform
   is float32, 1-D, already on CPU.
2. **The sample rate is not a constant.** `voxcpm2.py:249` computes
   `self.sample_rate = getattr(audio_vae, "out_sample_rate", audio_vae.sample_rate)`, and
   the encode rate differs from the output rate. Copying LuxTTS's hardcoded `return audio,
   48000` would be a latent bug. Read `model.tts_model.sample_rate` at generation time.
   The issue's 48 kHz claim is plausible but is not verifiable from source alone.
3. **`prompt_wav_path` and `prompt_text` are strictly paired** — supplying one without the
   other raises `ValueError`. Our cloning path must always provide both.
4. **`reference_wav_path` is an additional VoxCPM2-only cloning mode**, structurally
   isolated via reference-audio tokens, usable alone or combined with the prompt pair. The
   issue does not mention it. Out of scope for v1, but worth recording.
5. **`retry_badcase=True` by default** with a ratio threshold. Our `ModelConfig.retries_runaway`
   flag turns on Voicebox's own split-and-retry. The engine already retries internally, so
   VoxCPM2 sets it to `False` and we do not layer a second retry on top.
6. **`normalize=False` by default.** Our pronunciation-dictionary path (FR-008) feeds
   pre-processed text, so leaving upstream normalization off is the correct default —
   turning it on could undo our Arabic diacritics work.

**Alternatives considered**: hardcoding 48000 to match LuxTTS — rejected on the evidence
in point 2.

---

### R5 correction after the probe (T001)

The signature above was read from upstream `main`. The pinned release, **voxcpm 2.0.3**, has **no `seed`
parameter**: `inspect.signature(VoxCPM._generate)` in the installed package lists everything above except
`seed` (evidence/probe.md, question 13). Determinism (FR-009) therefore comes from the backend setting the
torch seed with `manual_seed` before generating, as LuxTTS does, never from a vendor argument.

## R6 — Voice design from a written description

**Decision**: implement behind FR-015's dedicated input, and verify the exact prompt form
during implementation.

**Evidence**: the source issue documents a `"(description)text"` prefix convention. The
files inspected for this research (`core.py`, `voxcpm2.py`) expose no dedicated parameter
for it, which is consistent with it being a text convention rather than an API argument.

**Status**: **unresolved**, and the only feature-level unknown left. It does not block
Phase 1 design, because C1Q5 already settled that the description gets its own labelled
input; what remains is how that input is encoded into `text`. Carried into tasks as a
verification step ahead of the UI work.

---

## R7 — Existing engine that most resembles this one

**Decision**: model the backend on `luxtts_backend.py`, with the three deviations below.

**Evidence**: [luxtts_backend.py](../../backend/backends/luxtts_backend.py) is the closest
match — single size, cloning, uses `model_load_progress`, `empty_device_cache`,
`manual_seed`, `get_cache_key`/`cache_voice_prompt` and the shared `combine_voice_prompts`.

Deviations required:

1. Return the model's runtime sample rate, not a literal (R5.2).
2. Use `get_torch_device(allow_mps=True)` and pass the result through explicitly rather
   than relying on the vendor's `"auto"`, so our device policy stays authoritative and
   observable (R2).
3. LuxTTS runs Whisper internally and ignores `reference_text`; VoxCPM2 requires the real
   transcript as `prompt_text`, so the cached voice prompt must carry both the audio path
   and its transcript.

---

## Open items carried into Phase 1 and tasks

| Item | Blocks | Resolved by |
| --- | --- | --- |
| numpy 1.x versus 2.x boundary under `--no-deps` | FR-019 | Probe task, first in the task list |
| Installed torch actually satisfying `>=2.5.0` | FR-019 | Probe task |
| Real inference memory, for the C1Q4 warning threshold | FR-003, edge case | Probe task |
| Actual output sample rate, and whether it is 48 kHz | FR-006 | Probe task |
| CPU and MPS being *usable*, not merely supported | Story 3 priority | Probe task |
| Exact voice-design prompt encoding | FR-015 | Probe task |
| `torchcodec`/FFmpeg presence in the frozen build | FR-020 | Packaging task |

## Specification changes this research recommends

**Update 2026-09-23:** the user decided all three at the T002 gate. Story 3 is now P2, FR-023's exception is
withdrawn, and the effort was re-scored from 13 to 8. See evidence/probe.md, "T002 decisions". Originally
raised, not applied — the spec is bound to issue #13 and changing it is a Scope and Clarify concern:

1. **User Story 3 should drop from P1 to P2.** Its P1 justification was "a user-visible
   crash on an entire class of machines, including every Mac". R2 shows that class of
   machines is not excluded.
2. **FR-023 should be revisited.** It grants a declared exception to the processor-fallback
   rule that the evidence says is not needed.
3. **The approved effort of 13 points should be re-assessed before implementation.** R1
   deletes work, R2 deletes the hardest constraint, R3 and R4 convert two unknowns into
   verification steps — all downward pressure. Against that, C1Q4, C1Q5, C1Q7 and C1Q8
   added user-facing work after the estimate was approved.
