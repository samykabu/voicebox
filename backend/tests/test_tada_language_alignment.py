"""Regression tests for TADA multilingual prompt alignment."""

import pytest

from backend.backends import hume_backend
from backend.backends.hume_backend import HumeTadaBackend


async def _skip_model_load(_model_size):
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "cache_prefix"),
    [("ar", "tada_ar_"), ("zh", "tada_ch_"), ("en", "tada_en_")],
)
async def test_voice_prompt_cache_is_scoped_to_aligner_language(
    monkeypatch, tmp_path, language, cache_prefix
):
    backend = HumeTadaBackend()
    backend.model_size = "3B"
    monkeypatch.setattr(backend, "load_model", _skip_model_load)

    captured = {}

    def _cached(key):
        captured["key"] = key
        return {"cached": True}

    monkeypatch.setattr(hume_backend, "get_cached_voice_prompt", _cached)
    audio = tmp_path / "reference.wav"
    audio.write_bytes(b"audio")

    prompt, was_cached = await backend.create_voice_prompt(
        str(audio), "النص المرجعي", language=language
    )

    assert was_cached is True
    assert prompt == {"cached": True}
    assert captured["key"].startswith(cache_prefix)


@pytest.mark.asyncio
async def test_arabic_prompt_requires_reference_transcript(monkeypatch, tmp_path):
    backend = HumeTadaBackend()
    backend.model_size = "3B"
    monkeypatch.setattr(backend, "load_model", _skip_model_load)

    with pytest.raises(ValueError, match="exact reference transcript"):
        await backend.create_voice_prompt(
            str(tmp_path / "reference.wav"), "   ", language="ar"
        )


@pytest.mark.asyncio
async def test_non_english_prompt_rejects_english_only_model(monkeypatch, tmp_path):
    backend = HumeTadaBackend()
    backend.model_size = "1B"
    monkeypatch.setattr(backend, "load_model", _skip_model_load)

    with pytest.raises(ValueError, match="requires the 3B model"):
        await backend.create_voice_prompt(
            str(tmp_path / "reference.wav"), "النص المرجعي", language="ar"
        )
