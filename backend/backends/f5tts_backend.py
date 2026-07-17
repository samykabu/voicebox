"""Native F5-TTS/Habibi backend for zero-shot voice cloning.

The Arabic models are all hosted in ``SWivid/Habibi-TTS``.  Habibi uses the
F5 DiT architecture and inference utilities, adding dialect tokens for the
Unified checkpoint.  Model state is deliberately protected by one async lock:
the streaming and non-persistent generation routes can run concurrently and a
model switch must never happen while another request is synthesizing.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import threading
from pathlib import Path
from typing import Any, Final
from unittest.mock import patch

import numpy as np

from .base import (
    combine_voice_prompts as _combine_voice_prompts,
    empty_device_cache,
    get_torch_device,
    is_model_cached,
    manual_seed,
    model_load_progress,
)

logger = logging.getLogger(__name__)

VOCOS_REPO: Final = "charactr/vocos-mel-24khz"
HABIBI_REPO: Final = "SWivid/Habibi-TTS"
TARGET_SAMPLE_RATE: Final = 24_000
MAX_REFERENCE_SECONDS: Final = 12.0
MIN_REFERENCE_SECONDS: Final = 0.25

_F5_MODEL_CFG: Final = {
    "dim": 1024,
    "depth": 22,
    "heads": 16,
    "ff_mult": 2,
    "text_dim": 512,
    "conv_layers": 4,
}

# ``dialect_id`` is used only by Habibi's Unified checkpoint.  Specialized
# checkpoints are already dialect-specific and therefore use no control token.
MODELS: Final[dict[str, dict[str, Any]]] = {
    "habibi-unified": {
        "repo": HABIBI_REPO,
        "ckpt_file": "Unified/model_200000.safetensors",
        "vocab_file": "Unified/vocab.txt",
        "dialect_id": "⓪",  # UNK: automatic/unknown Arabic dialect
        "language": "ar",
    },
    "habibi-msa": {
        "repo": HABIBI_REPO,
        "ckpt_file": "Specialized/MSA/model_200000.safetensors",
        "vocab_file": "Specialized/MSA/vocab.txt",
        "dialect_id": None,
        "language": "ar",
    },
    "habibi-sau": {
        "repo": HABIBI_REPO,
        "ckpt_file": "Specialized/SAU/model_200000.safetensors",
        "vocab_file": "Specialized/SAU/vocab.txt",
        "dialect_id": None,
        "language": "ar",
    },
    "habibi-uae": {
        "repo": HABIBI_REPO,
        "ckpt_file": "Specialized/UAE/model_100000.safetensors",
        "vocab_file": "Specialized/UAE/vocab.txt",
        "dialect_id": None,
        "language": "ar",
    },
    "habibi-alg": {
        "repo": HABIBI_REPO,
        "ckpt_file": "Specialized/ALG/model_100000.safetensors",
        "vocab_file": "Specialized/ALG/vocab.txt",
        "dialect_id": None,
        "language": "ar",
    },
    "habibi-irq": {
        "repo": HABIBI_REPO,
        "ckpt_file": "Specialized/IRQ/model_100000.safetensors",
        "vocab_file": "Specialized/IRQ/vocab.txt",
        "dialect_id": None,
        "language": "ar",
    },
    "habibi-egy": {
        "repo": HABIBI_REPO,
        "ckpt_file": "Specialized/EGY/model_100000.safetensors",
        "vocab_file": "Specialized/EGY/vocab.txt",
        "dialect_id": None,
        "language": "ar",
    },
    "habibi-mar": {
        "repo": HABIBI_REPO,
        "ckpt_file": "Specialized/MAR/model_100000.safetensors",
        "vocab_file": "Specialized/MAR/vocab.txt",
        "dialect_id": None,
        "language": "ar",
    },
}

_MODEL_ALIASES: Final = {
    "default": "habibi-msa",
    "f5-tts": "habibi-msa",
    "f5-tts-ar": "habibi-msa",
}


def _audio_duration_seconds(path: str) -> float:
    """Read reference duration without decoding the full recording."""
    try:
        import soundfile as sf

        info = sf.info(path)
        if not info.samplerate:
            raise ValueError("audio has no sample rate")
        return float(info.frames) / float(info.samplerate)
    except Exception as soundfile_error:
        # pydub covers formats such as M4A when FFmpeg is available.
        try:
            from pydub import AudioSegment

            return len(AudioSegment.from_file(path)) / 1000.0
        except Exception as pydub_error:
            raise ValueError(f"Unable to read reference audio '{path}': {pydub_error}") from soundfile_error


def _safe_torchaudio_load(uri: str, **_: Any):
    """TorchAudio loader replacement that avoids TorchCodec on Windows."""
    import soundfile as sf
    import torch

    try:
        audio, sample_rate = sf.read(uri, dtype="float32", always_2d=True)
        return torch.from_numpy(audio.T), sample_rate
    except Exception as soundfile_error:
        # libsndfile support varies by platform. FFmpeg via pydub covers
        # common compressed references such as MP3, AAC, and M4A.
        try:
            from pydub import AudioSegment

            segment = AudioSegment.from_file(uri)
            samples = np.asarray(segment.get_array_of_samples(), dtype=np.float32)
            samples = samples.reshape((-1, segment.channels))
            scale = float(1 << (8 * segment.sample_width - 1))
            return torch.from_numpy((samples / scale).T.copy()), segment.frame_rate
        except Exception as pydub_error:
            raise ValueError(
                f"Unable to decode reference audio '{uri}' with soundfile or FFmpeg: {pydub_error}"
            ) from soundfile_error


class F5TTSBackend:
    """F5/Habibi model family with atomic model selection and inference."""

    def __init__(self):
        self.model = None
        self.vocoder = None
        self._device: str | None = None
        self._current_model_size: str | None = None
        # ContextVars make the model selected by load_model request-scoped.
        # This matters because multiple async request handlers share this object.
        self._requested_model: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            f"f5_requested_model_{id(self)}", default=None
        )
        self._inference_lock = asyncio.Lock()
        self._sync_state_lock = threading.RLock()

    @property
    def model_size(self) -> str | None:
        return self._current_model_size

    def _get_device(self) -> str:
        return get_torch_device(allow_mps=True, allow_xpu=True)

    def is_loaded(self) -> bool:
        return self.model is not None and self.vocoder is not None

    def _normalize_model_size(self, model_size: str | None) -> str:
        normalized = _MODEL_ALIASES.get(model_size or "default", model_size or "default")
        if normalized not in MODELS:
            raise ValueError(f"Unknown F5/Habibi model '{model_size}'. Available models: {', '.join(MODELS)}")
        return normalized

    def _get_model_path(self, model_size: str = "default") -> str:
        return MODELS[self._normalize_model_size(model_size)]["repo"]

    def _is_model_cached(self, model_size: str = "default") -> bool:
        model_info = MODELS[self._normalize_model_size(model_size)]
        model_cached = is_model_cached(
            model_info["repo"],
            required_files=[model_info["ckpt_file"], model_info["vocab_file"]],
        )
        vocoder_cached = is_model_cached(VOCOS_REPO, required_files=["pytorch_model.bin", "config.yaml"])
        return model_cached and vocoder_cached

    async def load_model(self, model_size: str = "default") -> None:
        """Select and load a model atomically for the current async request."""
        normalized = self._normalize_model_size(model_size)
        self._requested_model.set(normalized)
        async with self._inference_lock:
            await asyncio.to_thread(self._ensure_model_loaded_sync, normalized)

    def _ensure_model_loaded_sync(self, model_size: str) -> None:
        with self._sync_state_lock:
            if self.is_loaded() and self._current_model_size == model_size:
                return
            if self.is_loaded():
                self._unload_model_sync()
            self._load_model_sync(model_size)

    def _load_model_sync(self, model_size: str) -> None:
        model_info = MODELS[model_size]
        with model_load_progress(model_size, self._is_model_cached(model_size)):
            from f5_tts.infer.utils_infer import load_model, load_vocoder
            from f5_tts.model import DiT
            from huggingface_hub import hf_hub_download

            device = self._get_device()
            logger.info("Loading %s on %s", model_size, device)
            ckpt_path = hf_hub_download(repo_id=model_info["repo"], filename=model_info["ckpt_file"])
            vocab_path = hf_hub_download(repo_id=model_info["repo"], filename=model_info["vocab_file"])
            vocoder = load_vocoder(vocoder_name="vocos", is_local=False, device=device)
            model = load_model(
                model_cls=DiT,
                model_cfg=dict(_F5_MODEL_CFG),
                ckpt_path=ckpt_path,
                mel_spec_type="vocos",
                vocab_file=vocab_path,
                ode_method="euler",
                use_ema=True,
                device=device,
            )

            # Publish state only after every load step succeeds.
            self._device = device
            self.vocoder = vocoder
            self.model = model
            self._current_model_size = model_size
            logger.info("%s loaded successfully", model_size)

    def _unload_model_sync(self) -> None:
        if not self.is_loaded():
            self._current_model_size = None
            return
        device = self._device
        self.model = None
        self.vocoder = None
        self._device = None
        self._current_model_size = None
        empty_device_cache(device)
        logger.info("F5/Habibi model unloaded")

    def unload_model(self) -> None:
        """Unload safely even if called while an inference thread is active."""
        with self._sync_state_lock:
            self._unload_model_sync()

    def _validate_reference(self, audio_path: str, reference_text: str) -> tuple[str, str, float]:
        path = Path(audio_path)
        if not path.is_file():
            raise ValueError(f"Reference audio not found: {audio_path}")
        text = (reference_text or "").strip()
        if not text:
            raise ValueError("F5/Habibi voice cloning requires an exact transcript of the reference audio")
        duration = _audio_duration_seconds(str(path))
        if duration < MIN_REFERENCE_SECONDS:
            raise ValueError(
                f"Reference audio is too short ({duration:.2f}s); use at least {MIN_REFERENCE_SECONDS:.2f}s"
            )
        if duration > MAX_REFERENCE_SECONDS:
            raise ValueError(
                f"Reference audio is {duration:.2f}s; F5/Habibi supports at most "
                f"{MAX_REFERENCE_SECONDS:.0f}s. Trim the audio and update its transcript "
                "so the prompt remains exactly aligned."
            )
        return str(path), text, duration

    async def create_voice_prompt(
        self,
        audio_path: str,
        reference_text: str,
        use_cache: bool = True,
    ) -> tuple[dict, bool]:
        """Validate and defer reference processing until inference."""
        del use_cache  # A file path is intentionally cheap and deterministic.
        audio_path, reference_text, _ = await asyncio.to_thread(self._validate_reference, audio_path, reference_text)
        requested = self._requested_model.get() or self._current_model_size or "habibi-msa"
        return {
            "ref_audio": audio_path,
            "ref_text": reference_text,
            "model_size": requested,
        }, False

    async def combine_voice_prompts(
        self,
        audio_paths: list[str],
        reference_texts: list[str],
    ) -> tuple[np.ndarray, str]:
        """Combine only complete samples that fit F5's 12-second prompt limit."""
        if len(audio_paths) != len(reference_texts):
            raise ValueError("Each reference recording must have a matching transcript")
        selected_paths: list[str] = []
        selected_texts: list[str] = []
        total_duration = 0.0
        for audio_path, reference_text in zip(audio_paths, reference_texts, strict=True):
            validated_path, validated_text, duration = await asyncio.to_thread(
                self._validate_reference, audio_path, reference_text
            )
            if total_duration + duration > MAX_REFERENCE_SECONDS:
                logger.warning(
                    "Skipping reference sample %s because the combined F5 prompt would exceed 12s",
                    audio_path,
                )
                continue
            selected_paths.append(validated_path)
            selected_texts.append(validated_text)
            total_duration += duration
        if not selected_paths:
            raise ValueError("No complete reference samples fit within the 12-second F5 prompt limit")
        return await _combine_voice_prompts(selected_paths, selected_texts, sample_rate=TARGET_SAMPLE_RATE)

    async def generate(
        self,
        text: str,
        voice_prompt: dict,
        language: str = "ar",
        seed: int | None = None,
        instruct: str | None = None,
    ) -> tuple[np.ndarray, int]:
        """Synthesize while holding the model state lock for the full request."""
        del instruct  # F5/Habibi has no instruction channel.
        generation_text = (text or "").strip()
        if not generation_text:
            raise ValueError("Text to generate cannot be empty")
        ref_audio, ref_text, _ = await asyncio.to_thread(
            self._validate_reference,
            voice_prompt.get("ref_audio", ""),
            voice_prompt.get("ref_text", ""),
        )
        requested = self._normalize_model_size(
            voice_prompt.get("model_size") or self._requested_model.get() or self._current_model_size or "default"
        )
        expected_language = MODELS[requested]["language"]
        if language not in (expected_language, "auto", ""):
            raise ValueError(f"Model '{requested}' supports language '{expected_language}', not '{language}'")

        async with self._inference_lock:
            return await asyncio.to_thread(
                self._generate_sync,
                requested,
                ref_audio,
                ref_text,
                generation_text,
                seed,
            )

    def _generate_sync(
        self,
        model_size: str,
        ref_audio: str,
        ref_text: str,
        text: str,
        seed: int | None,
    ) -> tuple[np.ndarray, int]:
        with self._sync_state_lock:
            self._ensure_model_loaded_sync(model_size)
            if seed is not None:
                manual_seed(seed, self._device)

            model_info = MODELS[model_size]
            try:
                from habibi_tts.infer.utils_infer import infer_process
            except ImportError as exc:
                raise RuntimeError(
                    "Arabic F5 models require habibi-tts. Install habibi-tts==0.1.1 alongside f5-tts."
                ) from exc
            infer_kwargs = {"dialect_id": model_info["dialect_id"]}

            logger.info("[%s] Generating", model_size)
            with patch("torchaudio.load", _safe_torchaudio_load):
                audio_array, sample_rate, _ = infer_process(
                    ref_audio=ref_audio,
                    ref_text=ref_text,
                    gen_text=text,
                    model_obj=self.model,
                    vocoder=self.vocoder,
                    mel_spec_type="vocos",
                    show_info=logger.info,
                    progress=None,
                    device=self._device,
                    **infer_kwargs,
                )

            if audio_array is None:
                raise RuntimeError(f"{model_size} returned no audio")
            try:
                import torch

                if isinstance(audio_array, torch.Tensor):
                    audio_array = audio_array.squeeze().detach().cpu().numpy()
            except ImportError:
                pass
            audio = np.asarray(audio_array, dtype=np.float32).squeeze()
            if audio.ndim != 1 or audio.size == 0:
                raise RuntimeError(f"{model_size} returned an invalid audio array")
            return audio, int(sample_rate)
