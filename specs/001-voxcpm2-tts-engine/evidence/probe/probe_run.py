"""VoxCPM2 probe harness (T001). Runs in a scratch venv OUTSIDE the repo.

Records: every outbound DNS lookup / socket connect (host, port) made by the
process, wall-clock timings, peak RSS, CUDA peak memory, sample rates, and
writes generated WAVs to --out (a scratch dir outside the repo).

Usage: python probe_run.py --device cpu --out <dir> [--denoiser] [--optimize]
       [--local-files-only] [--design] [--skip-generate]
"""
import argparse
import os
import socket
import sys
import threading
import time

# ---- network hook: installed before any third-party import ---------------
NET_EVENTS = []
_orig_getaddrinfo = socket.getaddrinfo
_orig_connect = socket.socket.connect


def _log_net(kind, detail):
    NET_EVENTS.append((time.time(), kind, detail))
    print(f"[NET] {kind}: {detail}", file=sys.stderr, flush=True)


DENY = os.environ.get("PROBE_DENY_NET") == "1"  # hard block: refuse any non-loopback lookup/connect
_LOCAL = ("127.0.0.1", "localhost", "::1")


def _hook_getaddrinfo(host, port, *a, **k):
    _log_net("getaddrinfo", f"{host}:{port}")
    if DENY and str(host) not in _LOCAL:
        _log_net("BLOCKED", f"getaddrinfo {host}:{port}")
        raise socket.gaierror(11001, f"PROBE_DENY_NET blocked lookup of {host}")
    return _orig_getaddrinfo(host, port, *a, **k)


def _hook_connect(self, address):
    _log_net("connect", repr(address))
    if DENY and isinstance(address, tuple) and str(address[0]) not in _LOCAL:
        _log_net("BLOCKED", f"connect {address!r}")
        raise ConnectionRefusedError(f"PROBE_DENY_NET blocked connect to {address!r}")
    return _orig_connect(self, address)


socket.getaddrinfo = _hook_getaddrinfo
socket.socket.connect = _hook_connect

import logging  # noqa: E402

logging.basicConfig(level=logging.WARNING, stream=sys.stderr,
                    format="[LOG] %(name)s %(levelname)s %(message)s")
for name in ("urllib3", "huggingface_hub", "httpx", "httpcore", "modelscope"):
    logging.getLogger(name).setLevel(logging.DEBUG)

ap = argparse.ArgumentParser()
ap.add_argument("--device", default="cpu")
ap.add_argument("--out", required=True)
ap.add_argument("--denoiser", action="store_true")
ap.add_argument("--optimize", action="store_true")
ap.add_argument("--local-files-only", action="store_true")
ap.add_argument("--design", action="store_true")
ap.add_argument("--skip-generate", action="store_true")
ap.add_argument("--text", default="Hello, this is a short test of the VoxCPM two speech engine, running locally.")
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)

print("=== ENV ===")
print("python", sys.version)
print("executable", sys.executable)
for k in ("HF_HOME", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HF_HUB_OFFLINE",
          "TRANSFORMERS_OFFLINE", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
          "MODELSCOPE_CACHE", "HF_TOKEN", "PROBE_DENY_NET"):
    v = os.environ.get(k)
    if k == "HF_TOKEN" and v:
        v = "<redacted>"
    print(f"{k}={v}")
print("args", vars(args))

# ---- memory sampler ------------------------------------------------------
import psutil  # noqa: E402

proc = psutil.Process()
PEAK = {"rss": 0}
_stop = threading.Event()


def _sampler():
    while not _stop.is_set():
        try:
            PEAK["rss"] = max(PEAK["rss"], proc.memory_info().rss)
        except Exception:
            pass
        time.sleep(0.2)


threading.Thread(target=_sampler, daemon=True).start()

T = {}
t0 = time.time()
import numpy as np  # noqa: E402
import torch  # noqa: E402
import soundfile as sf  # noqa: E402
from voxcpm import VoxCPM  # noqa: E402
import huggingface_hub  # noqa: E402
from huggingface_hub import constants as hfc  # noqa: E402

T["import_s"] = time.time() - t0
print("=== VERSIONS ===")
print("numpy", np.__version__, "| torch", torch.__version__, "cuda build", torch.version.cuda,
      "| cuda available", torch.cuda.is_available(), "| huggingface_hub", huggingface_hub.__version__)
try:
    import transformers
    print("transformers", transformers.__version__)
except Exception as e:  # pragma: no cover
    print("transformers import failed", e)
print("HF_HUB_CACHE resolved:", hfc.HF_HUB_CACHE, "| HF_HUB_OFFLINE const:", hfc.HF_HUB_OFFLINE)

if args.device.startswith("cuda") and torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        print("cuda device", i, torch.cuda.get_device_name(i), torch.cuda.get_device_capability(i))
    torch.cuda.reset_peak_memory_stats()

print("=== LOAD ===", flush=True)
t0 = time.time()
model = VoxCPM.from_pretrained(
    "openbmb/VoxCPM2",
    load_denoiser=args.denoiser,
    optimize=args.optimize,
    device=args.device,
    local_files_only=args.local_files_only,
)
T["load_s"] = time.time() - t0
tm = model.tts_model
print("model device:", tm.device, "| dtype:", tm.config.dtype)
print("tts_model.sample_rate (output):", tm.sample_rate)
print("tts_model._encode_sample_rate:", getattr(tm, "_encode_sample_rate", None))
print("audio_vae.sample_rate:", getattr(tm.audio_vae, "sample_rate", None),
      "| audio_vae.out_sample_rate:", getattr(tm.audio_vae, "out_sample_rate", None))
print("denoiser:", model.denoiser)
print("peak RSS after load (MB):", round(PEAK["rss"] / 2**20))

results = []


def run(label, text, **kw):
    if args.device.startswith("cuda"):
        torch.cuda.synchronize()
    t = time.time()
    wav = model.generate(text=text, **kw)
    if args.device.startswith("cuda"):
        torch.cuda.synchronize()
    dt = time.time() - t
    secs = len(wav) / tm.sample_rate
    path = os.path.join(args.out, f"{label}.wav")
    sf.write(path, wav, tm.sample_rate)
    info = sf.info(path)
    rms = float(np.sqrt(np.mean(np.square(wav)))) if len(wav) else 0.0
    r = dict(label=label, text=text, wall_s=round(dt, 2), audio_s=round(secs, 2),
             rtf=round(dt / secs, 3) if secs else None, dtype=str(wav.dtype), shape=wav.shape,
             rms=round(rms, 4), file=path, file_sr=info.samplerate)
    results.append(r)
    print("GEN", r, flush=True)


if not args.skip_generate:
    print("=== GENERATE ===", flush=True)
    run(f"{args.device.replace(':', '')}_plain", args.text)
    if args.design:
        run(f"{args.device.replace(':', '')}_design_female",
            "(A young woman, gentle and sweet voice)Hello, welcome to the voice design test.")
        run(f"{args.device.replace(':', '')}_design_male",
            "(An old man, deep, slow and raspy voice)Hello, welcome to the voice design test.")
        # full-width parentheses variant, to see whether it is treated as a control prefix or read aloud
        run(f"{args.device.replace(':', '')}_design_fullwidth",
            "（A young woman, gentle and sweet voice）Hello, welcome to the voice design test.")

_stop.set()
print("=== SUMMARY ===")
print("timings", {k: round(v, 2) for k, v in T.items()})
print("peak RSS sampled (MB):", round(PEAK["rss"] / 2**20))
try:
    print("peak working set (MB, Windows peak_wset):", round(proc.memory_info().peak_wset / 2**20))
except Exception:
    pass
if args.device.startswith("cuda") and torch.cuda.is_available():
    print("torch.cuda.max_memory_allocated (MB):", round(torch.cuda.max_memory_allocated() / 2**20))
    print("torch.cuda.max_memory_reserved (MB):", round(torch.cuda.max_memory_reserved() / 2**20))
for r in results:
    print("RESULT", r)
hosts = sorted({d for _, k, d in NET_EVENTS if k == "getaddrinfo"})
print("NETWORK getaddrinfo hosts:", hosts)
print("NETWORK connect count:", sum(1 for _, k, _d in NET_EVENTS if k == "connect"))
