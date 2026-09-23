"""Review follow-ups for the VoxCPM2 backend: runaway retry, locking and design-mode chunking.

No checkpoint is downloaded and the real ``voxcpm`` package is never imported: a fake
``voxcpm`` module is injected into ``sys.modules`` and the torch-touching helpers are
replaced on the backend module, as in ``test_voxcpm_backend.py``.
"""

import asyncio
import importlib
import os
import sys
import threading
import time
import types
from contextlib import contextmanager
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from backend.backends import engine_retries_runaway
from backend.utils.audio import has_tts_runaway
from backend.utils.chunked_tts import generate_chunked, split_text_into_chunks

MODULE_NAME = "backend.backends.voxcpm_backend"
FAKE_SAMPLE_RATE = 24_000
FAKE_DEVICE = "cuda:0"
DESCRIPTION = "A young woman, warm and bright voice"

# Three sentences of about 90 characters: three chunks at max_chunk_chars=100.
SENTENCES = [
    "The lighthouse keeper climbed the spiral stairs every evening before the sun went down.",
    "He polished the great lens until it shone, then lit the lamp and watched the sea turn.",
    "Ships passed far out on the dark water, and none of them ever knew his name at all.",
]
LONG_TEXT = " ".join(SENTENCES)
MAX_CHARS = 100


def _runaway_audio(sample_rate: int) -> np.ndarray:
    """Speech, a 2.5 s silence, then more output: the shape has_tts_runaway flags."""
    speech = np.full(sample_rate, 0.2, dtype=np.float32)
    silence = np.zeros(int(sample_rate * 2.5), dtype=np.float32)
    noise = np.full(sample_rate, 0.8, dtype=np.float32)
    return np.concatenate([speech, silence, noise])


class _Vendor:
    """Configurable fake of voxcpm.VoxCPM; records every call and any overlap."""

    def __init__(self) -> None:
        self.from_pretrained_calls = 0
        self.load_delay = 0.0
        self.generate_calls: list[dict] = []
        self.generate_delay = 0.0
        self.active = 0
        self.max_active = 0
        self.intervals: list[tuple[float, float]] = []
        self.audio_for = lambda index, kwargs: np.full(4_800, 0.1 * (index + 1), dtype=np.float32)
        self.fail_on_call: int | None = None
        self._guard = threading.Lock()

    def module(self) -> types.ModuleType:
        vendor = self

        class FakeTTSModel:
            sample_rate = FAKE_SAMPLE_RATE

        class FakeVoxCPM:
            def __init__(self) -> None:
                self.tts_model = FakeTTSModel()

            @classmethod
            def from_pretrained(cls, *args, **kwargs):
                with vendor._guard:
                    vendor.from_pretrained_calls += 1
                time.sleep(vendor.load_delay)
                return cls()

            def generate(self, **kwargs):
                with vendor._guard:
                    index = len(vendor.generate_calls)
                    wav = kwargs.get("prompt_wav_path")
                    record = dict(kwargs)
                    record["prompt_wav_exists"] = bool(wav) and os.path.exists(wav)
                    record["prompt_wav_audio"] = sf.read(wav, dtype="float32") if record["prompt_wav_exists"] else None
                    vendor.generate_calls.append(record)
                    vendor.active += 1
                    vendor.max_active = max(vendor.max_active, vendor.active)
                start = time.perf_counter()
                try:
                    time.sleep(vendor.generate_delay)
                    if vendor.fail_on_call == index:
                        raise RuntimeError("vendor failed")
                    return vendor.audio_for(index, kwargs)
                finally:
                    with vendor._guard:
                        vendor.active -= 1
                        vendor.intervals.append((start, time.perf_counter()))

        module = types.ModuleType("voxcpm")
        module.VoxCPM = FakeVoxCPM  # type: ignore[attr-defined]
        return module


@pytest.fixture
def vb():
    return importlib.import_module(MODULE_NAME)


@pytest.fixture
def vendor(vb, monkeypatch: pytest.MonkeyPatch) -> _Vendor:
    fake = _Vendor()
    monkeypatch.setitem(sys.modules, "voxcpm", fake.module())

    @contextmanager
    def fake_progress(*_args, **_kwargs):
        yield None

    monkeypatch.setattr(vb, "get_torch_device", lambda **_kwargs: FAKE_DEVICE)
    monkeypatch.setattr(vb, "manual_seed", lambda *_args: None)
    monkeypatch.setattr(vb, "empty_device_cache", lambda *_args: None)
    monkeypatch.setattr(vb, "model_load_progress", fake_progress)
    return fake


@pytest.fixture
def backend(vb, vendor: _Vendor, monkeypatch: pytest.MonkeyPatch):
    instance = vb.VoxCPMBackend()
    monkeypatch.setattr(instance, "_is_model_cached", lambda *_a, **_k: True)
    return instance


@pytest.fixture
def reference_file(tmp_path: Path) -> Path:
    path = tmp_path / "reference.wav"
    sf.write(str(path), np.zeros(2_400, dtype=np.float32), FAKE_SAMPLE_RATE)
    return path


def _clone_prompt(reference_file: Path) -> dict:
    return {"prompt_wav_path": str(reference_file), "prompt_text": "The reference transcript."}


class TestNoVoiceboxRunawayRetry:
    """I1: the vendor retries runaway output itself, so Voicebox must not add its own retry."""

    def test_voxcpm_does_not_declare_voicebox_runaway_retry(self) -> None:
        assert engine_retries_runaway("voxcpm") is False

    @pytest.mark.asyncio
    async def test_chunked_path_never_calls_the_detector_or_resplits(self, backend, vendor: _Vendor) -> None:
        vendor.audio_for = lambda _index, _kwargs: _runaway_audio(FAKE_SAMPLE_RATE)
        assert has_tts_runaway(_runaway_audio(FAKE_SAMPLE_RATE), FAKE_SAMPLE_RATE) is True

        detector_calls: list[int] = []

        def spy_detector(audio, sample_rate):
            detector_calls.append(len(audio))
            return has_tts_runaway(audio, sample_rate)

        # Built exactly as services/generation.py and routes/generations.py build it.
        runaway_detector = spy_detector if engine_retries_runaway("voxcpm") else None

        await generate_chunked(
            backend,
            LONG_TEXT,
            {},
            max_chunk_chars=MAX_CHARS,
            runaway_detector=runaway_detector,
        )

        assert detector_calls == []
        assert len(vendor.generate_calls) == len(split_text_into_chunks(LONG_TEXT, MAX_CHARS)) == 3

    @pytest.mark.asyncio
    async def test_service_path_never_calls_the_detector_for_voxcpm(
        self, backend, vendor: _Vendor, reference_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import backend.backends as backends_pkg
        import backend.utils.audio as audio_utils
        from backend.services import generation as generation_service

        vendor.audio_for = lambda _index, _kwargs: _runaway_audio(FAKE_SAMPLE_RATE)
        detector_calls: list[int] = []

        def spy_detector(audio, sample_rate=24000, **kwargs):
            detector_calls.append(len(audio))
            return True

        class FakeSession:
            def close(self) -> None:
                pass

        def fake_get_db():
            yield FakeSession()

        async def fake_voice_prompt(*_a, **_k):
            return _clone_prompt(reference_file)

        async def fake_load(*_a, **_k):
            return None

        monkeypatch.setattr(audio_utils, "has_tts_runaway", spy_detector)
        monkeypatch.setattr(generation_service, "get_db", fake_get_db)
        monkeypatch.setattr(generation_service.profiles, "create_voice_prompt_for_profile", fake_voice_prompt)
        monkeypatch.setattr(generation_service, "ensure_engine_available", lambda _engine: None)
        monkeypatch.setattr(backends_pkg, "get_tts_backend_for_engine", lambda _engine: backend)
        monkeypatch.setattr(backends_pkg, "load_engine_model", fake_load)

        await generation_service.generate_audio_sync(
            profile_id="p1",
            text=LONG_TEXT,
            language="en",
            engine="voxcpm",
            model_size="default",
            max_chunk_chars=MAX_CHARS,
            normalize=False,
        )

        assert detector_calls == []
        assert [c["text"] for c in vendor.generate_calls] == SENTENCES


class TestLoadAndInferenceLocks:
    """I2: concurrent callers outside the serial queue must not double-load or overlap."""

    @pytest.mark.asyncio
    async def test_concurrent_async_loads_call_from_pretrained_once(self, backend, vendor: _Vendor) -> None:
        vendor.load_delay = 0.2

        await asyncio.gather(*(backend.load_model() for _ in range(5)))

        assert vendor.from_pretrained_calls == 1
        assert backend.is_loaded()

    def test_concurrent_thread_loads_call_from_pretrained_once(self, backend, vendor: _Vendor) -> None:
        vendor.load_delay = 0.2
        barrier = threading.Barrier(5)
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                barrier.wait()
                backend._load_model_sync()
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert vendor.from_pretrained_calls == 1

    @pytest.mark.asyncio
    async def test_concurrent_generates_never_overlap_in_the_vendor(
        self, backend, vendor: _Vendor, reference_file: Path
    ) -> None:
        vendor.generate_delay = 0.05
        prompt = _clone_prompt(reference_file)

        results = await asyncio.gather(*(backend.generate(f"Line {i}.", prompt, seed=i) for i in range(4)))

        assert len(results) == 4
        assert len(vendor.generate_calls) == 4
        assert vendor.max_active == 1
        ordered = sorted(vendor.intervals)
        assert all(prev_end <= next_start for (_, prev_end), (next_start, _) in pairwise(ordered))

    @pytest.mark.asyncio
    async def test_generate_during_a_load_waits_and_loads_once(
        self, backend, vendor: _Vendor, reference_file: Path
    ) -> None:
        vendor.load_delay = 0.2
        prompt = _clone_prompt(reference_file)

        await asyncio.gather(backend.load_model(), backend.generate("One.", prompt), backend.generate("Two.", prompt))

        assert vendor.from_pretrained_calls == 1
        assert len(vendor.generate_calls) == 2


class TestDesignModeChunkContinuity:
    """I3: long voice-design text keeps chunk 0's speaker for every later chunk."""

    @pytest.mark.asyncio
    async def test_later_chunks_continue_from_chunk_zero(self, backend, vendor: _Vendor) -> None:
        audio, sample_rate = await generate_chunked(
            backend,
            LONG_TEXT,
            {"voice_type": "designed", "design_prompt": DESCRIPTION},
            seed=42,
            instruct=DESCRIPTION,
            max_chunk_chars=MAX_CHARS,
        )

        calls = vendor.generate_calls
        assert [c["text"] for c in calls] == [f"({DESCRIPTION}){SENTENCES[0]}", SENTENCES[1], SENTENCES[2]]
        assert calls[0]["prompt_wav_path"] is None
        assert calls[0]["prompt_text"] is None

        continuation_wav = calls[1]["prompt_wav_path"]
        assert continuation_wav
        for call in calls[1:]:
            assert call["prompt_wav_path"] == continuation_wav
            assert call["prompt_text"] == SENTENCES[0]
            assert call["prompt_wav_exists"] is True
            assert not call["text"].startswith("(")

        written, written_rate = calls[1]["prompt_wav_audio"]
        assert written_rate == FAKE_SAMPLE_RATE
        np.testing.assert_allclose(written, np.full(4_800, 0.1, dtype=np.float32), atol=1e-4)
        assert sample_rate == FAKE_SAMPLE_RATE
        assert len(audio) > 0

    @pytest.mark.asyncio
    async def test_continuation_temp_file_is_removed(self, backend, vendor: _Vendor) -> None:
        await generate_chunked(backend, LONG_TEXT, {}, instruct=DESCRIPTION, max_chunk_chars=MAX_CHARS)

        continuation_wav = vendor.generate_calls[1]["prompt_wav_path"]
        assert not os.path.exists(continuation_wav)

    @pytest.mark.asyncio
    async def test_continuation_temp_file_is_removed_when_a_later_chunk_fails(self, backend, vendor: _Vendor) -> None:
        vendor.fail_on_call = 2

        with pytest.raises(RuntimeError, match="vendor failed"):
            await generate_chunked(backend, LONG_TEXT, {}, instruct=DESCRIPTION, max_chunk_chars=MAX_CHARS)

        continuation_wav = vendor.generate_calls[1]["prompt_wav_path"]
        assert continuation_wav
        assert not os.path.exists(continuation_wav)

    @pytest.mark.asyncio
    async def test_seeds_still_vary_per_chunk(self, backend, vendor: _Vendor, vb, monkeypatch) -> None:
        seeds: list[int] = []
        monkeypatch.setattr(vb, "manual_seed", lambda seed, _device: seeds.append(seed))

        await generate_chunked(backend, LONG_TEXT, {}, seed=42, instruct=DESCRIPTION, max_chunk_chars=MAX_CHARS)

        assert seeds == [42, 43, 44]

    @pytest.mark.asyncio
    async def test_short_design_text_is_a_single_unchanged_call(self, backend, vendor: _Vendor) -> None:
        await generate_chunked(backend, SENTENCES[0], {}, instruct=DESCRIPTION, max_chunk_chars=MAX_CHARS)

        assert len(vendor.generate_calls) == 1
        call = vendor.generate_calls[0]
        assert call["text"] == f"({DESCRIPTION}){SENTENCES[0]}"
        assert call["prompt_wav_path"] is None
        assert call["prompt_text"] is None

    @pytest.mark.asyncio
    async def test_long_text_without_a_description_is_unchanged(self, backend, vendor: _Vendor) -> None:
        await generate_chunked(backend, LONG_TEXT, {}, max_chunk_chars=MAX_CHARS)

        assert [c["text"] for c in vendor.generate_calls] == SENTENCES
        assert all(c["prompt_wav_path"] is None and c["prompt_text"] is None for c in vendor.generate_calls)

    @pytest.mark.asyncio
    async def test_cloned_profile_keeps_its_reference_for_every_chunk(
        self, backend, vendor: _Vendor, reference_file: Path
    ) -> None:
        await generate_chunked(
            backend, LONG_TEXT, _clone_prompt(reference_file), instruct=DESCRIPTION, max_chunk_chars=MAX_CHARS
        )

        assert [c["text"] for c in vendor.generate_calls] == SENTENCES
        for call in vendor.generate_calls:
            assert call["prompt_wav_path"] == str(reference_file)
            assert call["prompt_text"] == "The reference transcript."

    @pytest.mark.asyncio
    async def test_hook_is_reached_through_the_advanced_settings_wrapper(self, backend, vendor: _Vendor) -> None:
        from backend.services.generation import backend_with_generation_options

        wrapped = backend_with_generation_options(backend, "voxcpm", {"cfg_value": 2.5})
        assert wrapped is not backend

        await generate_chunked(wrapped, LONG_TEXT, {}, instruct=DESCRIPTION, max_chunk_chars=MAX_CHARS)

        calls = vendor.generate_calls
        assert calls[0]["prompt_wav_path"] is None
        assert all(c["prompt_text"] == SENTENCES[0] for c in calls[1:])
        assert all(c["cfg_value"] == 2.5 for c in calls)

    def test_hook_returns_nothing_outside_design_mode(self, backend, reference_file: Path) -> None:
        audio = np.zeros(10, dtype=np.float32)

        assert backend.continuation_voice_prompt({}, None, "Hi.", audio, FAKE_SAMPLE_RATE) is None
        assert backend.continuation_voice_prompt({}, "   ", "Hi.", audio, FAKE_SAMPLE_RATE) is None
        assert (
            backend.continuation_voice_prompt(
                _clone_prompt(reference_file), DESCRIPTION, "Hi.", audio, FAKE_SAMPLE_RATE
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_engines_without_the_hook_are_unaffected(self) -> None:
        class PlainBackend:
            def __init__(self) -> None:
                self.calls: list[tuple] = []

            async def generate(self, text, voice_prompt, language="en", seed=None, instruct=None):
                self.calls.append((text, voice_prompt, seed, instruct))
                return np.zeros(2_400, dtype=np.float32), 24_000

        plain = PlainBackend()
        prompt = {"voice_type": "designed", "design_prompt": DESCRIPTION}

        await generate_chunked(plain, LONG_TEXT, prompt, seed=7, instruct=DESCRIPTION, max_chunk_chars=MAX_CHARS)

        assert plain.calls == [
            (SENTENCES[0], prompt, 7, DESCRIPTION),
            (SENTENCES[1], prompt, 8, DESCRIPTION),
            (SENTENCES[2], prompt, 9, DESCRIPTION),
        ]
        assert all(call[1] is prompt for call in plain.calls)

    @pytest.mark.asyncio
    async def test_a_hook_that_declines_leaves_the_prompt_unchanged(self) -> None:
        class DecliningBackend:
            def __init__(self) -> None:
                self.prompts: list = []
                self.hook_calls = 0

            async def generate(self, text, voice_prompt, language="en", seed=None, instruct=None):
                self.prompts.append(voice_prompt)
                return np.zeros(2_400, dtype=np.float32), 24_000

            def continuation_voice_prompt(self, *_args):
                self.hook_calls += 1

        declining = DecliningBackend()
        prompt: dict = {}

        await generate_chunked(declining, LONG_TEXT, prompt, instruct=DESCRIPTION, max_chunk_chars=MAX_CHARS)

        assert declining.hook_calls == 1
        assert all(p is prompt for p in declining.prompts)
