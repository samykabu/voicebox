# T001: VoxCPM2 dependency probe findings

Issue: samykabu/voicebox#17. Feature: `specs/001-voxcpm2-tts-engine`. Procedure: quickstart.md Step 0.
Probe run: 2026-09-23, 01:42 to 02:37 (+03:00). Raw logs are in [`probe/`](probe/). Failed attempts are kept there too.

This file records findings only. The **Facts for T002** section at the end lists facts. It does not make the T002 decisions (effort, US3 priority and FR-023, the version pin). Those decisions belong to the user.

---

## Environment

| Item | Value | Log |
| --- | --- | --- |
| OS | Windows 11 Pro for Workstations 10.0.26200 | [01](probe/01-python-versions.txt) |
| CPU / RAM | Intel Core Ultra 9 285K (24 cores) / 130 GB | [01](probe/01-python-versions.txt) |
| GPUs | GPU0 **RTX 5070 12 GB**, GPU1 RTX 5060 Ti 16 GB. Both are Blackwell (compute capability 12.0). Driver 616.56, CUDA UMD 13.4 | [02](probe/02-nvidia-smi.txt) |
| System Pythons | 3.14.7 (default), 3.13, 3.10. **3.12 is not installed.** | [01](probe/01-python-versions.txt) |
| venv 1: full deps | `C:\Users\sabus\voxcpm-probe` on Python 3.13.15. 3.13 is the closest system interpreter at or above 3.12. `pip install voxcpm` was run with deps. | [03](probe/03-venv-create.txt) |
| venv 2: no-deps on 3.13 | `C:\Users\sabus\voxcpm-nodeps` on 3.13.15. This venv stalled on `numpy<2`, which has no cp313 wheel. | [20](probe/20-nodeps-step01.txt)–[23](probe/23-nodeps-numpy-lt2-on-py313.txt) |
| venv 3: no-deps on 3.12 | `C:\Users\sabus\voxcpm-nodeps312` on **CPython 3.12.14**. The interpreter came from `uv python install 3.12` into `%APPDATA%\uv\python`, which also added a `python3.12.exe` shim. This was the only way to test the project floor and the `numpy<2` pin together. | [24](probe/24-nodeps312-venv.txt) |
| Generated audio | `C:\Users\sabus\voxcpm-probe-out\` (outside the repo) | — |
| HF cache used | Default location, `C:\Users\sabus\.cache\huggingface\hub`. `HF_HOME`, `HF_HUB_CACHE` and `HUGGINGFACE_HUB_CACHE` were all unset. No HF token was set or used. | [01](probe/01-python-versions.txt), [08](probe/08-download-and-load.txt) |
| Probe harness | [`probe/probe_run.py`](probe/probe_run.py) and [`probe/design_eval.py`](probe/design_eval.py). The harness hooks `socket.getaddrinfo` and `socket.connect` for the whole process, samples RSS, times each step and writes the WAVs. | — |

### Step timings

| Step | Duration | Log |
| --- | --- | --- |
| Create venv 1 | 6 s | [03](probe/03-venv-create.txt) |
| `pip install voxcpm` with deps (py3.13) | **277 s** | [04](probe/04-pip-install-with-deps.txt) |
| First `from_pretrained`, download plus load (~4.96 GB) | **90.1 s**. The cached load alone is ~9 s, so the download itself was ~80 s. | [08](probe/08-download-and-load.txt) |
| cu128 torch wheel (2.8 GB) into venv 2 / venv 3 | 166 s / 126 s | [21](probe/21-nodeps-step02-torch-cu128.txt), [25](probe/25-nodeps312-torch-cu128.txt) |
| Load from cache, CPU / CUDA | 9.6 s / 8.6–11.6 s | [09](probe/09-cpu-generate.txt), [11b](probe/11b-cuda-generate-and-design-rerun.txt) |

---

## Summary: questions 1 to 13

| # | Question | Answer | Produced by | Raw log |
| --- | --- | --- | --- | --- |
| 1 | Python ceiling / version | **No ceiling in the metadata.** `Requires-Python: >=3.10`, voxcpm **2.0.3**. It ran on 3.13.15 (full deps, CPU) and on 3.12.14 (CUDA). The packaged README still says `Python ≥ 3.10 (<3.13)`, which is probably where the issue's "<3.13" came from. It is stale: 3.13 works. | `pip show voxcpm`, `importlib.metadata`, a real run on 3.13 | [06](probe/06-pip-show.txt), [09](probe/09-cpu-generate.txt) |
| 2 | Runs on CPU? | **Yes.** `device="cpu"`, bf16. **12.84 s wall time for 4.32 s of audio, RTF 2.97.** A repeat run gave 11.18 s / 4.32 s, RTF 2.59. | `probe_run.py --device cpu` | [09](probe/09-cpu-generate.txt), [14 O7](probe/14-offline-checks.txt) |
| 3 | Runs on MPS? | **N/A: no Apple Silicon in this environment. Not testable here.** The source has an MPS path: `resolve_runtime_device` and `pick_runtime_dtype`, which forces float32 on MPS. **CUDA: yes.** RTX 5070 (sm_120) with torch 2.11.0+cu128, RTF **0.93–1.18**. This was without torch.compile: `optimize=True` printed `torch.compile disabled - triton is not installed` and fell back. | `probe_run.py --device cuda --optimize` | [11b](probe/11b-cuda-generate-and-design-rerun.txt), [14](probe/14-offline-checks.txt) |
| 4 | Real download size | **4,960,733,321 bytes = 4961 MB (decimal), 4.7 GiB on disk.** This matches R3. `model.safetensors` is 4,580,080,592 bytes and `audiovae.pth` is 376,951,122 bytes. Cache path: `C:\Users\sabus\.cache\huggingface\hub\models--openbmb--VoxCPM2`, snapshot `32279effe8c19989596f05d353d1447f51d9e915`. | `du -sbL`, `ls -laL` | [08](probe/08-download-and-load.txt) |
| 5 | numpy 1.x or 2.x? | Unpinned, pip resolves **numpy 2.5.3**. **VoxCPM works with numpy 1.26.4.** In the 3.12 venv, import, load, generate (CPU and CUDA), cloning and normalize all passed. **Downgrading numpy is impossible on Python 3.13**, because no numpy <2 has a cp313 wheel and the 1.26.4 source build fails. That applies to the project's own pin on 3.13, not only to voxcpm. | `pip show numpy`, `pip install "numpy<2"`, `pip download --python-version` | [06](probe/06-pip-show.txt), [10](probe/10-numpy-lt2-and-pin-resolution.txt), [22](probe/22-nodeps-step03-import-loop.txt), [23](probe/23-nodeps-numpy-lt2-on-py313.txt), [26](probe/26-nodeps312-import-load-generate-loop.txt) |
| 6 | torch >=2.5 satisfied? | **Yes, in both cases.** A plain install pulled **torch 2.14.0+cpu**, torchaudio 2.11.0+cpu and torchcodec 0.16.0+cpu, with CUDA build `None`, **even though CUDA GPUs are present**. That is a finding. The project-style cu128 index gives **torch 2.11.0+cu128** and torchaudio 2.11.0+cu128 (CUDA 12.8), which works on Blackwell. | `pip show torch`, `torch.version.cuda` | [06](probe/06-pip-show.txt), [21](probe/21-nodeps-step02-torch-cu128.txt), [25](probe/25-nodeps312-torch-cu128.txt) |
| 7 | Output sample rate | **`model.tts_model.sample_rate` = 48000.** The encode rate `_encode_sample_rate` (`audio_vae.sample_rate`) is **16000**, and `audio_vae.out_sample_rate` is 48000. The written WAVs read back at 48000 Hz. This settles R5.2's 48 kHz claim. The backend should still read the rate at runtime. | `probe_run.py` prints | [08](probe/08-download-and-load.txt), [09](probe/09-cpu-generate.txt), [11b](probe/11b-cuda-generate-and-design-rerun.txt) |
| 8 | Peak inference memory | **GPU (bf16): `torch.cuda.max_memory_allocated` 5458 MB, reserved 5692 MB.** nvidia-smi sampling showed a 5885 MiB delta on GPU0 (414 to 6299 MiB), over short sentences only. That is **below the claimed ~8 GB**, but longer texts may use more. **CPU: peak RSS ~11.0 GB, Windows peak working set 11.2–11.5 GB.** Most of that comes from loading. | `torch.cuda.max_memory_*`, nvidia-smi `-lms 250/500`, psutil | [11b](probe/11b-cuda-generate-and-design-rerun.txt), [12](probe/12-cuda-nvidia-smi-sampling.txt), [08](probe/08-download-and-load.txt), [09](probe/09-cpu-generate.txt) |
| 9 | Voice-design prompt form | **`"(description)text"` with ASCII parentheses is the documented form and the working one.** Evidence: the packaged README ("put the description in parentheses at the start of `text`") and `voxcpm/cli.py:66 build_final_text()` → `f"({control}){text}"`. Test method: Whisper-base.en ASR plus pyin F0, two runs per form. With ASCII parens the description is **never spoken**, and a female description raised median F0 (304/392 Hz against 188/131 Hz with no description). **Full-width `（…）` is read aloud**, so it does not work. `[…]` is not spoken either, but its effect is unclear. The steering itself varies between runs (male design: 381/159 Hz), and the README warns about this. There is no dedicated API parameter. | `design_eval.py`, source grep | [13](probe/13-voice-design-eval.txt), [11b](probe/11b-cuda-generate-and-design-rerun.txt) |
| 10 | Language list | **30 languages, Arabic included.** Model card front-matter codes: zh, en, **ar**, my, da, nl, fi, fr, de, el, he, hi, id, it, ja, km, ko, lo, ms, no, pl, pt, ru, es, sw, sv, tl, th, tr, vi. The model card and PyPI README prose list the same 30. **The package code has no language list or language argument.** An Arabic sentence generated fine (4.80 s of audio, CUDA, offline). Intelligibility was not ASR-checked. | `sed` on the HF README front-matter, grep of the package source, a real Arabic run | [15](probe/15-language-list.txt), [17](probe/17-arabic-generate.txt) |
| 11 | Minimal `--no-deps` import set | **The following were enough for import, load and generate (CPU and CUDA) plus both cloning modes:** `torch`, `torchaudio` (a module-level import in `model/voxcpm.py`), `numpy`, `huggingface-hub`, `einops`, `pydantic`, `transformers` (which brings tokenizers and safetensors) and `librosa` (which brings soundfile, scipy and numba). The order was numpy, huggingface-hub, einops, pydantic, transformers, librosa. **`normalize=True`** adds `inflect` and `wetext`; wetext bundles its FSTs and does no download. **Not needed:** `gradio`, `datasets`, `spaces`, `funasr`, `modelscope` (needed only for the denoiser), `argbind` and `datasets` (training only), `wetext` (normalize only), plus `addict`, `simplejson`, `sortedcontainers`, `matplotlib` and **`torchcodec`**. **torchcodec needs the FFmpeg "full-shared" DLLs (FFmpeg 4–9).** Here it fails to load because the chocolatey FFmpeg is a static build, and `torchaudio.load` in 2.11 fails with it. VoxCPM2 never calls either: prompt and reference audio load through `librosa`. | the `nodeps_loop.sh` add-until-it-works loop | [26](probe/26-nodeps312-import-load-generate-loop.txt), [27](probe/27-nodeps312-optional-paths.txt), [16](probe/16-torchcodec-ffmpeg.txt), [18](probe/18-venv-sizes-and-minimal-env.txt) |
| 12 | Offline load once cached | **Yes, but only when explicitly configured. The defaults are not offline.** With `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, **or** `from_pretrained(local_files_only=True)`, and the network hard-blocked: load and generate succeeded with **0 lookups and 0 connections** (O3, O4, O4b, O7). **With defaults**, every load makes `GET huggingface.co/api/models/openbmb/VoxCPM2/revision/main`, even when fully cached (O1). If DNS or the socket is blocked, it falls back to the cache and succeeds (O2b, O6b). **Through a dead proxy, hub 0.36.2 raises `ProxyError` and the load FAILS (O2)**, while hub 1.32.0 falls back (O6). **ModelScope: `from_pretrained` defaults to `load_denoiser=True`.** That makes **modelscope.cn requests** for `iic/speech_zipenhancer_ans_multiloss_16k_base` (10 connection attempts, retried), **even with the HF offline env vars set**, and the load fails offline (O8). With `load_denoiser=False` there was no ModelScope traffic in any run. | the `probe_run.py` socket hook plus `PROBE_DENY_NET=1` hard block, `HTTP(S)_PROXY=127.0.0.1:1`, urllib3/httpx DEBUG | [14](probe/14-offline-checks.txt) (failed attempts: [14a](probe/14a-offline-attempt1-port9-HUNG.txt), [14b](probe/14b-offline-attempt2-runner-bug.txt)) |
| 13 | Other surprises | (a) A plain install gives **transformers 5.17.0**, which violates the project's `<=4.57.6`. The full resolution under project pins on 3.12 **does succeed** after backtracking (numpy 1.26.4, transformers 4.57.6, numba 0.60.0, gradio 6.17.3). **On 3.13 it is `ResolutionImpossible`** because of `numpy<2`. (b) `pip install voxcpm` with deps pulls gradio 6, datasets 3, funasr, modelscope, oss2, aliyun SDKs and others: **~145 packages (147 in `pip list`, including pip and the psutil helper), 1.8 GB venv with CPU torch.** The CUDA venvs are 4.3–4.9 GB, of which torch is 4.2 GB. (c) A plain install gets a **CPU-only torch** on a CUDA machine. (d) `optimize=True` (the default) uses torch.compile only when the device is exactly `"cuda"` and triton is importable. On Windows without triton it silently falls back, and `"cuda:0"` is never optimized. (e) The constructor runs a warm-up generation when `optimize=True`. (f) Under transformers 4.57.6, loading warns that the tokenizer class `VoxCPM2Tokenizer` ≠ `LlamaTokenizerFast`; generation is unaffected. (g) huggingface_hub 1.x called `GET /api/agent-harnesses` on the first run (unrelated to the model). (h) `generate()` has no `seed` argument in 2.0.3, which differs from R5's signature. (i) 127.0.0.1:9 is **not** a dead port on this machine: Windows Simple TCP/IP Services listens on it, and the discard service hung the first offline attempt. | multiple | [04](probe/04-pip-install-with-deps.txt), [05](probe/05-pip-list.txt), [10](probe/10-numpy-lt2-and-pin-resolution.txt), [11b](probe/11b-cuda-generate-and-design-rerun.txt), [18](probe/18-venv-sizes-and-minimal-env.txt), [08](probe/08-download-and-load.txt), [14a](probe/14a-offline-attempt1-port9-HUNG.txt) |

---

## Detail notes

### Q2 / Q3: speed

| Run | Device | Audio s | Wall s | RTF |
| --- | --- | --- | --- | --- |
| 09 cpu_plain (venv1, torch 2.14 cpu) | CPU bf16 | 4.32 | 12.84 | 2.97 |
| 14 O7 (venv1, offline) | CPU bf16 | 4.32 | 11.18 | 2.59 |
| 11b cuda_plain (venv3, torch 2.11+cu128) | RTX 5070 bf16 | 5.60 | 5.41 | 0.97 |
| 11b design female / male / full-width | RTX 5070 | 2.72 / 4.00 / 6.72 | 2.55 / 3.82 / 6.22 | 0.94 / 0.95 / 0.93 |
| 17 Arabic | RTX 5070 | 4.80 | 5.45 | 1.14 |

All CUDA figures are without torch.compile, because triton is not installed. Upstream reports RTF ~0.3 on an RTX 4090 with the standard PyTorch implementation.

### Q9: voice-design evaluation ([13](probe/13-voice-design-eval.txt))

| Form | Spoken as text? | Median F0 run 1 / 2 (Hz) | Duration run 1 / 2 (s) |
| --- | --- | --- | --- |
| no description | — | 188 / 131 | 3.20 / 3.04 |
| `(A young woman, gentle and sweet voice)…` | no | 304 / 392 | 3.20 / 3.20 |
| `(An old man, deep, slow and raspy voice)…` | no | 381 / 159 | 3.20 / 3.20 |
| `（…）` full-width | **yes**: "a young woman, gentle and sweet voice. Hello, …" | 164 / 113 | 6.56 / 8.32 |
| `[…]` square | no | 229 / 235 | 3.20 / 3.20 |
| `(…) ` with a trailing space | no | 376 / 274 | 2.24 / 2.72 |

Judged by ASR transcript (whisper-base.en) and pitch (librosa.pyin). The F0 figures are noisy: pyin can make octave errors, and the design is stochastic. The robust signal is that the ASCII parenthesised description is consumed as a control prefix and not read aloud.

### Q12: offline scenario matrix ([14](probe/14-offline-checks.txt))

| ID | venv / hub | Block | Offline setting | Result | Lookups / connects |
| --- | --- | --- | --- | --- | --- |
| O1 | 3.12 / 0.36.2 | none | none | load and generate OK | `huggingface.co:443` / 1 (`GET …/revision/main`) |
| O2 | 3.12 / 0.36.2 | proxy 127.0.0.1:1 + deny | none | **load FAILED**: `requests.exceptions.ProxyError` from `model_info` | proxy / 1 |
| O2b | 3.12 / 0.36.2 | deny only | none | load OK after a cache fallback | `huggingface.co` attempted and blocked / 0 |
| O3 | 3.12 / 0.36.2 | proxy + deny | `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` | load and generate OK | **0 / 0** |
| O4 | 3.12 / 0.36.2 | proxy + deny | `local_files_only=True` | load and generate OK | **0 / 0** |
| O4b | 3.12 / 0.36.2 | proxy only | `local_files_only=True` | load and generate OK | **0 / 0** |
| O5 | 3.12 / 0.36.2 | proxy + deny | env vars + `load_denoiser=True` | FAIL: `No module named 'modelscope'` | 0 / 0 |
| O6 | 3.13 / 1.32.0 | proxy + deny | none | load OK after a cache fallback | proxy / 1 attempted |
| O6b | 3.13 / 1.32.0 | deny only | none | load OK after a cache fallback | `huggingface.co` attempted and blocked / 0 |
| O7 | 3.13 / 1.32.0 | proxy + deny | env vars | load and generate OK (CPU) | **0 / 0** |
| O8 | 3.13 / 1.32.0 | proxy + deny | env vars + `load_denoiser=True` | **FAIL**: `modelscope_hub.errors.NetworkError … host='modelscope.cn' …/iic/speech_zipenhancer_ans_multiloss_16k_base` | 10 `modelscope.cn` connection attempts via the proxy |

How this was confirmed:
- A process-wide hook on `socket.getaddrinfo` and `socket.socket.connect` logs every Python-level lookup and connect, and refuses non-loopback ones when `PROBE_DENY_NET=1`.
- The proxy variables point at a verified-closed port.
- urllib3, httpx and huggingface_hub debug logging shows the target URLs.
- Limitation: the native Rust hf-xet client bypasses a Python hook. It is used only for real file transfers, which cannot occur for a complete cached snapshot. The first attempt ([14a](probe/14a-offline-attempt1-port9-HUNG.txt)) hung on port 9 and was discarded. The second ([14b](probe/14b-offline-attempt2-runner-bug.txt)) had a runner bug, and only its O1 is valid.

### Failed attempts kept in the raw logs

- [22](probe/22-nodeps-step03-import-loop.txt): `numpy<2` on py3.13 was retried 25 times by my loop, each time a failed source build. The loop was then fixed to stop on a repeated failure. Root cause in [23](probe/23-nodeps-numpy-lt2-on-py313.txt).
- [10](probe/10-numpy-lt2-and-pin-resolution.txt) A/B: the numpy downgrade in venv1 and the full resolution under project pins on 3.13 both fail.
- [11](probe/11-cuda-generate-and-design.txt): the harness crashed printing full-width parentheses to cp1252 stdout. It was rerun with `PYTHONIOENCODING=utf-8` as [11b](probe/11b-cuda-generate-and-design-rerun.txt).
- [14a](probe/14a-offline-attempt1-port9-HUNG.txt) and [14b](probe/14b-offline-attempt2-runner-bug.txt): the offline attempts described above.
- [16](probe/16-torchcodec-ffmpeg.txt): torchcodec fails to load because there are no FFmpeg shared DLLs.
- [14](probe/14-offline-checks.txt) O2, O5 and O8: offline failures. These are findings, not harness errors.

---

## Facts for T002 (not decisions)

These are observations only. The effort re-assessment, US3 priority / FR-023 and the voxcpm pin remain the user's decisions.

- voxcpm 2.0.3 is the current PyPI release: `Requires-Python >=3.10`, 23 runtime deps plus dev extras.
- A CPU path exists and works (RTF ~2.6–3.0 on a 24-core Core Ultra 9). The CUDA path works on Blackwell with cu128 torch. MPS is untested here.
- A plain install on this machine selected CPU-only torch, transformers 5.x and numpy 2.x. All three differ from the project environment.
- VoxCPM2 works with numpy 1.26.4, transformers 4.57.6 and torch 2.11.0+cu128, all installed with `--no-deps`.
- The runtime needs only 8 packages beyond voxcpm (listed in Q11). It needs 10 with `normalize=True`.
- The ModelScope denoiser is on by default in `from_pretrained`. The HF snapshot check is also on by default. Both must be switched off explicitly for local-first behaviour: pass `load_denoiser=False`, plus `local_files_only=True` or the HF offline env vars.
- Download: 4961 MB. Peak VRAM on short texts ≈ 5.5–5.9 GB. CPU RSS ≈ 11 GB.
- Output is 48 kHz and reference input is 16 kHz, both read at runtime.
- Voice design is the ASCII `(description)` text prefix. Arabic is in the 30-language list.

## T002 decisions (made by the user, 2026-09-23)

Recorded by the dispatcher from the user's own answers in the session, after the facts
above were presented. These are decisions, not probe findings.

| Decision | Choice | Consequence |
| --- | --- | --- |
| Version pin | `voxcpm==2.0.3`, the current PyPI release | 2.0.3 has no `seed` argument, so the backend sets the torch seed itself before generating (the LuxTTS pattern) for FR-009. T014 and T026 assert that `manual_seed` is applied rather than that `seed` is forwarded. |
| Effort | Re-score from 13 to **8** | The rubric's uncertainty dimension falls from 3 to 1 now that the probe has answered the open questions; breadth 3, integration 3, data_security 0 and verification 3 are unchanged. Sum 10 maps to 8 points, still `scope:large`. Scope is republished; the prior keep-together approval carries forward. |
| User Story 3 / FR-023 | Story 3 moves from P1 to **P2**; FR-023's exception is **withdrawn** | The engine runs on CPU and has an MPS path, so it honours the processor-fallback rule like every other engine. The greyed-out-with-reason behaviour (FR-003) stays as defensive behaviour for machines that cannot load the model. |

Also carried into implementation from the facts above: install with `--no-deps` using the
8-package minimal set, pass `load_denoiser=False`, and load with `local_files_only=True`
once cached (T046, T047).
