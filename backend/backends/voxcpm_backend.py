"""
VoxCPM2 backend implementation.

Wraps openbmb's VoxCPM2 (voxcpm 2.0.3) for multilingual voice cloning and
voice design from a written description. About 5.9 GB of GPU memory on short
text, 48 kHz output, runs on CUDA, MPS and CPU.

Modelled on the LuxTTS backend with three deviations (research.md R7): the
sample rate is read from the loaded model, the device is resolved by our own
policy and passed explicitly, and the voice prompt carries the reference
transcript because the vendor needs it.

Contract: specs/001-voxcpm2-tts-engine/contracts/tts-backend-protocol.md.
"""

import asyncio
import logging

import numpy as np

from ..utils.cache import cache_voice_prompt, get_cache_key, get_cached_voice_prompt
from ..utils.hf_offline_patch import force_offline_if_cached
from .base import (
    combine_voice_prompts as _combine_voice_prompts,
    empty_device_cache,
    get_torch_device,
    is_model_cached,
    manual_seed,
    model_load_progress,
)

logger = logging.getLogger(__name__)

# HuggingFace repo for the model weights.
VOXCPM_HF_REPO = "openbmb/VoxCPM2"

# Progress-tracking key; matches ModelConfig.model_name.
VOXCPM_MODEL_NAME = "voxcpm2"

# The snapshot holds model.safetensors plus audiovae.pth; both count as weights.
VOXCPM_WEIGHT_EXTENSIONS = (".safetensors", ".pth", ".bin")

# Defaults of voxcpm 2.0.3 VoxCPM._generate(); also the declared advanced-setting defaults.
DEFAULT_CFG_VALUE = 2.0
DEFAULT_INFERENCE_TIMESTEPS = 10

# services/profiles.py saves the combined reference with save_audio(..., 24000),
# so the samples must be combined at that rate or the WAV would be mislabelled.
# The vendor resamples prompt audio to its own encode rate when it loads it.
COMBINE_SAMPLE_RATE = 24000


class VoxCPMBackend:
    """VoxCPM2 backend for voice cloning and voice design."""

    def __init__(self):
        self.model = None
        self.model_size = "default"  # VoxCPM2 has only one model size
        self._device = None

    def _get_device(self) -> str:
        # No allow_xpu / allow_directml: voxcpm's resolve_runtime_device() accepts only
        # cpu, mps and cuda[:N] and raises on anything else. Matches the declared
        # accelerators ("cuda", "mps", "cpu").
        return get_torch_device(allow_mps=True)

    def is_loaded(self) -> bool:
        return self.model is not None

    @property
    def device(self) -> str:
        if self._device is None:
            self._device = self._get_device()
        return self._device

    def _get_model_path(self, model_size: str = "default") -> str:
        return VOXCPM_HF_REPO

    def _is_model_cached(self, model_size: str = "default") -> bool:
        return is_model_cached(VOXCPM_HF_REPO, weight_extensions=VOXCPM_WEIGHT_EXTENSIONS)

    async def load_model(self, model_size: str = "default") -> None:
        """Load the VoxCPM2 model. Idempotent."""
        if self.model is not None:
            return

        await asyncio.to_thread(self._load_model_sync)

    def _load_model_sync(self) -> None:
        if self.model is not None:
            return

        is_cached = self._is_model_cached()

        with model_load_progress(VOXCPM_MODEL_NAME, is_cached):
            from voxcpm import VoxCPM  # lazy: heavy import

            device = self.device
            logger.info(f"Loading VoxCPM2 on {device}...")

            # Principle I (T047): once cached, load with HF offline mode forced on and
            # local_files_only, so the model resolves from the local HuggingFace cache only.
            # load_denoiser=False keeps the ModelScope hub out entirely.
            with force_offline_if_cached(is_cached, "VoxCPM2"):
                self.model = VoxCPM.from_pretrained(
                    VOXCPM_HF_REPO,
                    # Upstream defaults to True, which loads a ModelScope denoiser over the network.
                    load_denoiser=False,
                    # Resolve from the local HuggingFace cache only once downloaded.
                    local_files_only=is_cached,
                    # Explicit, never None/"auto": our device policy stays authoritative.
                    device=device,
                )

        logger.info("VoxCPM2 loaded successfully")

    def unload_model(self) -> None:
        """Unload the model to free memory."""
        if self.model is not None:
            device = self.device
            del self.model
            self.model = None
            self._device = None

            empty_device_cache(device)

            logger.info("VoxCPM2 unloaded")

    async def create_voice_prompt(
        self,
        audio_path: str,
        reference_text: str,
        use_cache: bool = True,
    ) -> tuple[dict, bool]:
        """
        Create a voice prompt from reference audio.

        VoxCPM2 encodes the reference itself at generation time, so the prompt is
        the audio path plus its real transcript. Both are required: upstream
        raises if only one of prompt_wav_path / prompt_text is given. The model
        is not loaded here because nothing needs encoding yet.
        """
        prompt_text = (reference_text or "").strip()
        if not prompt_text:
            raise ValueError("VoxCPM2 voice cloning needs the reference audio's transcript")

        cache_key = ("voxcpm_" + get_cache_key(audio_path, prompt_text)) if use_cache else None

        if cache_key:
            cached = get_cached_voice_prompt(cache_key)
            if cached is not None and isinstance(cached, dict):
                return cached, True

        voice_prompt = {"prompt_wav_path": str(audio_path), "prompt_text": prompt_text}

        if cache_key:
            cache_voice_prompt(cache_key, voice_prompt)

        return voice_prompt, False

    async def combine_voice_prompts(self, audio_paths, reference_texts):
        return await _combine_voice_prompts(audio_paths, reference_texts, sample_rate=COMBINE_SAMPLE_RATE)

    async def generate(
        self,
        text: str,
        voice_prompt: dict,
        language: str = "en",
        seed: int | None = None,
        instruct: str | None = None,
        options: dict[str, float] | None = None,
    ) -> tuple[np.ndarray, int]:
        """
        Generate audio from text using VoxCPM2.

        Args:
            text: Text to synthesize (already processed by the pronunciation dictionary).
            voice_prompt: {"prompt_wav_path", "prompt_text"} from create_voice_prompt(),
                or empty/None for voice design without reference audio.
            language: Unused; VoxCPM2 detects the language from the text.
            seed: Random seed, applied with manual_seed() before the vendor call.
                voxcpm 2.0.3 has no seed argument, so it is never forwarded.
            instruct: Written voice description. Encoded as the "(description)text"
                prefix, and only when there is no reference audio (C1Q6).
            options: Advanced settings (cfg_value, inference_timesteps); missing
                keys fall back to the declared defaults.

        Returns:
            Tuple of (audio_array, sample_rate), the rate read from the loaded model.
        """
        prompt_wav_path, prompt_text = _prompt_pair(voice_prompt)
        final_text = _apply_voice_description(text, instruct, has_reference=prompt_wav_path is not None)

        settings = options or {}
        cfg_value = float(settings.get("cfg_value", DEFAULT_CFG_VALUE))
        # The vendor takes an int step count; the request carries floats.
        inference_timesteps = round(float(settings.get("inference_timesteps", DEFAULT_INFERENCE_TIMESTEPS)))

        await self.load_model()

        def _generate_sync():
            if seed is not None:
                manual_seed(seed, self.device)

            audio = self.model.generate(
                text=final_text,
                prompt_wav_path=prompt_wav_path,
                prompt_text=prompt_text,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
                # Upstream normalization would undo our pronunciation-dictionary output (FR-008).
                normalize=False,
            )

            # generate() returns a bare float32 1-D CPU ndarray; pair it with the model's
            # own output rate rather than a literal (research.md R5.2).
            return np.asarray(audio, dtype=np.float32), int(self.model.tts_model.sample_rate)

        return await asyncio.to_thread(_generate_sync)


def _prompt_pair(voice_prompt: dict | None) -> tuple[str | None, str | None]:
    """Return (prompt_wav_path, prompt_text): both set, or both None."""
    if not voice_prompt:
        return None, None

    prompt_wav_path = voice_prompt.get("prompt_wav_path") or None
    prompt_text = (voice_prompt.get("prompt_text") or "").strip() or None

    if (prompt_wav_path is None) != (prompt_text is None):
        raise ValueError(
            "VoxCPM2 needs prompt_wav_path and prompt_text together; "
            f"got a voice prompt with only {'prompt_wav_path' if prompt_wav_path else 'prompt_text'}"
        )

    return prompt_wav_path, prompt_text


def _apply_voice_description(text: str, instruct: str | None, *, has_reference: bool) -> str:
    """Prefix the voice description as "(description)text" (probe Q9), unless cloning."""
    description = (instruct or "").strip()
    if not description or has_reference:
        return text
    return f"({description}){text}"
