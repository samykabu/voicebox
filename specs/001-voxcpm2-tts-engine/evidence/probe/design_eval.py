"""Voice-design prompt-form check (T001 Q9). Scratch venv only.

For each prompt form, generate twice on CUDA, then measure duration, median F0
(librosa.pyin) and an ASR transcript (openai/whisper-base.en via transformers).
If the description were read aloud, the transcript and duration would show it.
"""
import os
import sys

import librosa
import numpy as np
import soundfile as sf
import torch
from transformers import pipeline
from voxcpm import VoxCPM

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
BODY = "Hello, welcome to the voice design test."
FORMS = {
    "none": BODY,
    "ascii_female": "(A young woman, gentle and sweet voice)" + BODY,
    "ascii_male": "(An old man, deep, slow and raspy voice)" + BODY,
    "fullwidth_female": "（A young woman, gentle and sweet voice）" + BODY,
    "square_female": "[A young woman, gentle and sweet voice]" + BODY,
    "ascii_space_female": "(A young woman, gentle and sweet voice) " + BODY,
}
m = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False, optimize=False, device="cuda",
                           local_files_only=True)
sr = m.tts_model.sample_rate
asr = pipeline("automatic-speech-recognition", model="openai/whisper-base.en", device=0)
print("form | run | audio_s | median_F0_Hz | transcript")
for name, text in FORMS.items():
    for run in (1, 2):
        wav = m.generate(text=text)
        path = os.path.join(OUT, f"design_{name}_{run}.wav")
        sf.write(path, wav, sr)
        y16 = librosa.resample(wav.astype(np.float32), orig_sr=sr, target_sr=16000)
        f0, voiced, _ = librosa.pyin(y16, fmin=60, fmax=500, sr=16000)
        f0med = float(np.nanmedian(f0[voiced])) if np.any(voiced) else float("nan")
        tr = asr({"raw": y16, "sampling_rate": 16000})["text"].strip()
        print(f"{name} | {run} | {len(wav)/sr:.2f} | {f0med:.0f} | {tr}", flush=True)
