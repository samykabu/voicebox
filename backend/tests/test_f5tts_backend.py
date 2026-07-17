"""Focused tests for the native F5/Habibi model family.

No checkpoints are downloaded.  Model loading and inference are replaced with
small deterministic fakes so the tests exercise selection and synchronization.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import types
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from backend.backends import (
    check_model_cached,
    check_model_loaded,
    get_default_model_size,
    get_model_load_func,
    get_tts_model_configs,
    unload_model_by_config,
)
from backend.backends.f5tts_backend import MODELS, F5TTSBackend
from backend.models import GenerationRequest


@pytest.fixture
def reference_file(tmp_path: Path) -> Path:
    path = tmp_path / "reference.wav"
    path.write_bytes(b"unit-test-audio")
    return path


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> F5TTSBackend:
    instance = F5TTSBackend()
    monkeypatch.setattr("backend.backends.f5tts_backend._audio_duration_seconds", lambda _: 3.0)
    monkeypatch.setattr("backend.backends.f5tts_backend.empty_device_cache", lambda _: None)
    return instance


def _install_fake_loader(backend: F5TTSBackend, loaded: list[str]) -> None:
    def fake_load(model_size: str) -> None:
        loaded.append(model_size)
        backend.model = object()
        backend.vocoder = object()
        backend._device = "cpu"
        backend._current_model_size = model_size

    backend._load_model_sync = fake_load  # type: ignore[method-assign]


def test_arabic_model_registry_has_canonical_ids_and_checkpoint_paths() -> None:
    expected = {
        "habibi-unified": "Unified/model_200000.safetensors",
        "habibi-msa": "Specialized/MSA/model_200000.safetensors",
        "habibi-sau": "Specialized/SAU/model_200000.safetensors",
        "habibi-uae": "Specialized/UAE/model_100000.safetensors",
        "habibi-alg": "Specialized/ALG/model_100000.safetensors",
        "habibi-irq": "Specialized/IRQ/model_100000.safetensors",
        "habibi-egy": "Specialized/EGY/model_100000.safetensors",
        "habibi-mar": "Specialized/MAR/model_100000.safetensors",
    }
    assert {model_id: MODELS[model_id]["ckpt_file"] for model_id in expected} == expected
    assert MODELS["habibi-unified"]["dialect_id"] == "⓪"
    assert all(MODELS[model_id]["language"] == "ar" for model_id in expected)


def test_model_configs_expose_language_and_license_policy() -> None:
    configs = {c.model_name: c for c in get_tts_model_configs() if c.engine == "f5_tts"}
    assert configs["habibi-msa"].model_size == "habibi-msa"
    assert configs["habibi-msa"].languages == ["ar"]
    assert configs["habibi-msa"].license_id == "Apache-2.0"
    assert configs["habibi-msa"].commercial_use is True
    assert configs["habibi-unified"].license_id == "CC-BY-NC-SA-4.0"
    assert configs["habibi-unified"].commercial_use is False
    assert configs["habibi-sau"].commercial_use is False
    assert configs["habibi-uae"].commercial_use is False


def test_shared_repository_cache_status_checks_the_selected_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configs = {c.model_name: c for c in get_tts_model_configs() if c.engine == "f5_tts"}
    checked: list[str] = []

    def fake_is_cached(model_size: str) -> bool:
        checked.append(model_size)
        return model_size == "habibi-msa"

    monkeypatch.setattr(
        "backend.backends.get_tts_backend_for_engine",
        lambda _: type("Backend", (), {"_is_model_cached": staticmethod(fake_is_cached)})(),
    )

    assert check_model_cached(configs["habibi-msa"]) is True
    assert check_model_cached(configs["habibi-egy"]) is False
    assert checked == ["habibi-msa", "habibi-egy"]


@pytest.mark.asyncio
async def test_model_management_load_status_and_unload_are_variant_specific(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configs = {c.model_name: c for c in get_tts_model_configs() if c.engine == "f5_tts"}

    class FakeBackend:
        _current_model_size: str | None = None

        async def load_model(self, model_size: str) -> None:
            self._current_model_size = model_size

        def is_loaded(self) -> bool:
            return self._current_model_size is not None

        def unload_model(self) -> None:
            self._current_model_size = None

    fake_backend = FakeBackend()
    monkeypatch.setattr("backend.backends.get_tts_backend_for_engine", lambda _: fake_backend)

    result = get_model_load_func(configs["habibi-egy"])()
    await result
    assert fake_backend._current_model_size == "habibi-egy"
    assert check_model_loaded(configs["habibi-egy"]) is True
    assert check_model_loaded(configs["habibi-msa"]) is False
    assert unload_model_by_config(configs["habibi-msa"]) is False
    assert unload_model_by_config(configs["habibi-egy"]) is True


def test_generation_request_accepts_only_canonical_habibi_model_ids() -> None:
    for model_id in MODELS:
        request = GenerationRequest(
            profile_id="profile", text="اختبار", language="ar", engine="f5_tts", model_size=model_id
        )
        assert request.model_size == model_id

    with pytest.raises(ValidationError):
        GenerationRequest(
            profile_id="profile",
            text="اختبار",
            language="ar",
            engine="f5_tts",
            model_size="habibi-lev",
        )


def test_omitted_f5_model_resolves_to_specialized_msa() -> None:
    request = GenerationRequest(profile_id="profile", text="اختبار", language="ar", engine="f5_tts")
    assert request.model_size is None
    assert get_default_model_size(request.engine or "qwen") == "habibi-msa"


@pytest.mark.asyncio
async def test_model_selection_alias_and_switching(
    backend: F5TTSBackend,
) -> None:
    loaded: list[str] = []
    _install_fake_loader(backend, loaded)

    await backend.load_model("default")
    assert backend.model_size == "habibi-msa"
    await backend.load_model("habibi-msa")
    assert loaded == ["habibi-msa"]  # same model is not loaded twice

    await backend.load_model("habibi-egy")
    assert backend.model_size == "habibi-egy"
    assert loaded == ["habibi-msa", "habibi-egy"]

    with pytest.raises(ValueError, match="Unknown F5/Habibi model"):
        await backend.load_model("not-a-model")


@pytest.mark.asyncio
async def test_voice_prompt_requires_file_exact_text_and_max_twelve_seconds(
    backend: F5TTSBackend,
    reference_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_loader(backend, [])
    with pytest.raises(ValueError, match="exact transcript"):
        await backend.create_voice_prompt(str(reference_file), "   ")

    with pytest.raises(ValueError, match="Reference audio not found"):
        await backend.create_voice_prompt(str(reference_file.with_name("missing.wav")), "نص")

    monkeypatch.setattr("backend.backends.f5tts_backend._audio_duration_seconds", lambda _: 12.01)
    with pytest.raises(ValueError, match=r"at most 12s.*exactly aligned"):
        await backend.create_voice_prompt(str(reference_file), "النص المرجعي الدقيق")

    monkeypatch.setattr("backend.backends.f5tts_backend._audio_duration_seconds", lambda _: 12.0)
    await backend.load_model("habibi-msa")
    prompt, was_cached = await backend.create_voice_prompt(str(reference_file), " النص المرجعي الدقيق ")
    assert prompt == {
        "ref_audio": str(reference_file),
        "ref_text": "النص المرجعي الدقيق",
        "model_size": "habibi-msa",
    }
    assert was_cached is False


@pytest.mark.asyncio
async def test_concurrent_requests_keep_model_selection_atomic_and_serialize_inference(
    backend: F5TTSBackend,
    reference_file: Path,
) -> None:
    loaded: list[str] = []
    _install_fake_loader(backend, loaded)
    active = 0
    max_active = 0
    observations: list[str] = []
    counter_lock = threading.Lock()

    def fake_generate(
        requested: str,
        ref_audio: str,
        ref_text: str,
        text: str,
        seed: int | None,
    ) -> tuple[np.ndarray, int]:
        nonlocal active, max_active
        del ref_audio, ref_text, text, seed
        with backend._sync_state_lock:
            backend._ensure_model_loaded_sync(requested)
            with counter_lock:
                active += 1
                max_active = max(max_active, active)
            observations.append(backend.model_size or "")
            time.sleep(0.04)
            with counter_lock:
                active -= 1
            marker = 1.0 if requested == "habibi-msa" else 2.0
            return np.array([marker], dtype=np.float32), 24_000

    backend._generate_sync = fake_generate  # type: ignore[method-assign]
    first_loaded = asyncio.Event()
    second_loaded = asyncio.Event()

    async def first_request() -> np.ndarray:
        await backend.load_model("habibi-msa")
        prompt, _ = await backend.create_voice_prompt(str(reference_file), "مرحباً")
        first_loaded.set()
        await second_loaded.wait()  # ensure EGY replaced MSA before this generates
        audio, _ = await backend.generate("النص الأول", prompt, language="ar")
        return audio

    async def second_request() -> np.ndarray:
        await first_loaded.wait()
        await backend.load_model("habibi-egy")
        prompt, _ = await backend.create_voice_prompt(str(reference_file), "أهلاً")
        second_loaded.set()
        audio, _ = await backend.generate("النص الثاني", prompt, language="ar")
        return audio

    msa_audio, egy_audio = await asyncio.gather(first_request(), second_request())

    assert msa_audio.tolist() == [1.0]
    assert egy_audio.tolist() == [2.0]
    assert sorted(observations) == ["habibi-egy", "habibi-msa"]
    assert max_active == 1
    assert loaded[:2] == ["habibi-msa", "habibi-egy"]
    # Whichever request wins the inference lock reloads only when its desired
    # checkpoint differs from the competing request's last loaded checkpoint.
    assert loaded[-1] == observations[-1]


@pytest.mark.asyncio
async def test_generate_rejects_wrong_language_and_empty_text(
    backend: F5TTSBackend,
    reference_file: Path,
) -> None:
    _install_fake_loader(backend, [])
    await backend.load_model("habibi-msa")
    prompt, _ = await backend.create_voice_prompt(str(reference_file), "مرحباً")

    with pytest.raises(ValueError, match="cannot be empty"):
        await backend.generate("  ", prompt, language="ar")
    with pytest.raises(ValueError, match="supports language 'ar'"):
        await backend.generate("اختبار", prompt, language="en")


def test_inference_passes_only_unified_dialect_token_and_normalizes_audio(
    backend: F5TTSBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_infer_process(**kwargs):
        calls.append(kwargs)
        return np.array([[0.25, -0.25]], dtype=np.float64), 24_000, None

    infer_module = types.ModuleType("habibi_tts.infer.utils_infer")
    infer_module.infer_process = fake_infer_process  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "habibi_tts", types.ModuleType("habibi_tts"))
    monkeypatch.setitem(sys.modules, "habibi_tts.infer", types.ModuleType("habibi_tts.infer"))
    monkeypatch.setitem(sys.modules, "habibi_tts.infer.utils_infer", infer_module)

    torchaudio_module = types.ModuleType("torchaudio")
    torchaudio_module.load = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)

    def select(model_size: str) -> None:
        backend.model = object()
        backend.vocoder = object()
        backend._device = "cpu"
        backend._current_model_size = model_size

    for model_size, expected_token in (("habibi-unified", "⓪"), ("habibi-msa", None)):
        select(model_size)
        audio, sample_rate = backend._generate_sync(
            model_size, "reference.wav", "النص المرجعي", "النص الجديد", None
        )
        assert calls[-1]["dialect_id"] == expected_token
        assert audio.dtype == np.float32
        assert audio.shape == (2,)
        assert sample_rate == 24_000


@pytest.mark.asyncio
async def test_generation_error_releases_inference_lock(
    backend: F5TTSBackend,
    reference_file: Path,
) -> None:
    _install_fake_loader(backend, [])
    await backend.load_model("habibi-msa")
    prompt, _ = await backend.create_voice_prompt(str(reference_file), "النص المرجعي")
    attempts = 0

    def flaky_generate(*_args) -> tuple[np.ndarray, int]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("synthetic inference failure")
        return np.array([0.0], dtype=np.float32), 24_000

    backend._generate_sync = flaky_generate  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="synthetic inference failure"):
        await backend.generate("المحاولة الأولى", prompt, language="ar")

    audio, sample_rate = await backend.generate("المحاولة الثانية", prompt, language="ar")
    assert audio.tolist() == [0.0]
    assert sample_rate == 24_000
