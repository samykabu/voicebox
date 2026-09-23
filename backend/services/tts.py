"""
TTS inference module - delegates to backend abstraction layer.
"""

from typing import Optional
import numpy as np

from ..backends import get_tts_backend, TTSBackend


def get_tts_model() -> TTSBackend:
    """
    Get TTS backend instance (MLX or PyTorch based on platform).
    
    Returns:
        TTS backend instance
    """
    return get_tts_backend()


def unload_tts_model():
    """Unload TTS model to free memory."""
    backend = get_tts_backend()
    backend.unload_model()


def audio_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """Convert generated audio to WAV bytes carrying the AI-generated disclosure (FR-026)."""
    from ..utils.audio import wav_bytes

    return wav_bytes(audio, sample_rate)
