"""Contract tests for the VoxCPM2 TTS backend (T014, T016).

See specs/001-voxcpm2-tts-engine/contracts/tts-backend-protocol.md.

No checkpoint is downloaded and the real ``voxcpm`` package is never imported:
a fake ``voxcpm`` module is injected into ``sys.modules`` and the torch-touching
helpers (device detection, seeding, cache emptying, progress tracking) are
replaced on the backend module, following ``test_f5tts_backend.py``.
"""

from __future__ import annotations

import ast
import contextlib
import importlib
import subprocess
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_NAME = "backend.backends.voxcpm_backend"
MODULE_FILE = REPO_ROOT / "backend" / "backends" / "voxcpm_backend.py"

# Deliberately not 48000: a hardcoded ``return audio, 48000`` must fail.
FAKE_SAMPLE_RATE = 24_000
FAKE_DEVICE = "cuda:1"

# evidence/probe/15-language-list.txt, model card front-matter order.
EXPECTED_LANGUAGES = [
    "zh",
    "en",
    "ar",
    "my",
    "da",
    "nl",
    "fi",
    "fr",
    "de",
    "el",
    "he",
    "hi",
    "id",
    "it",
    "ja",
    "km",
    "ko",
    "lo",
    "ms",
    "no",
    "pl",
    "pt",
    "ru",
    "es",
    "sw",
    "sv",
    "tl",
    "th",
    "tr",
    "vi",
]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Recorder:
    """Ordered log of everything the fakes observe."""

    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.from_pretrained_calls: list[tuple[tuple, dict]] = []
        self.generate_calls: list[dict] = []
        self.device_calls: list[dict] = []
        self.emptied: list[str] = []
        self.cache: dict[str, dict] = {}


def _make_fake_voxcpm(recorder: _Recorder) -> types.ModuleType:
    class FakeTTSModel:
        sample_rate = FAKE_SAMPLE_RATE
        _encode_sample_rate = 16_000

    class FakeVoxCPM:
        def __init__(self) -> None:
            self.tts_model = FakeTTSModel()

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            recorder.from_pretrained_calls.append((args, kwargs))
            recorder.events.append(("from_pretrained",))
            return cls()

        def generate(self, *args, **kwargs):
            assert not args, "the backend must call generate() with keyword arguments"
            recorder.generate_calls.append(kwargs)
            recorder.events.append(("generate",))
            # Upstream returns a bare 1-D float32 ndarray, never a tuple.
            return np.linspace(-0.5, 0.5, 8, dtype=np.float32)

    module = types.ModuleType("voxcpm")
    module.VoxCPM = FakeVoxCPM  # type: ignore[attr-defined]
    return module


@pytest.fixture
def vb():
    """The backend module under test (imported lazily so each test fails on its own before T015)."""
    return importlib.import_module(MODULE_NAME)


@pytest.fixture
def recorder(vb, monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setitem(sys.modules, "voxcpm", _make_fake_voxcpm(rec))

    def fake_get_torch_device(**kwargs) -> str:
        rec.device_calls.append(kwargs)
        return FAKE_DEVICE

    def fake_manual_seed(seed: int, device: str) -> None:
        rec.events.append(("manual_seed", seed, device))

    def fake_empty_device_cache(device: str) -> None:
        rec.emptied.append(device)

    @contextmanager
    def fake_model_load_progress(model_name: str, is_cached: bool, *args, **kwargs):
        rec.events.append(("progress_enter", model_name, is_cached))
        try:
            yield None
        finally:
            rec.events.append(("progress_exit", model_name))

    def fake_get_cached(key: str):
        return rec.cache.get(key)

    def fake_cache(key: str, value) -> None:
        rec.cache[key] = value

    monkeypatch.setattr(vb, "get_torch_device", fake_get_torch_device)
    monkeypatch.setattr(vb, "manual_seed", fake_manual_seed)
    monkeypatch.setattr(vb, "empty_device_cache", fake_empty_device_cache)
    monkeypatch.setattr(vb, "model_load_progress", fake_model_load_progress)
    monkeypatch.setattr(vb, "get_cached_voice_prompt", fake_get_cached)
    monkeypatch.setattr(vb, "cache_voice_prompt", fake_cache)
    return rec


@pytest.fixture
def backend(vb, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch):
    instance = vb.VoxCPMBackend()
    monkeypatch.setattr(instance, "_is_model_cached", lambda *_a, **_k: True)
    return instance


@pytest.fixture
def reference_file(tmp_path: Path) -> Path:
    path = tmp_path / "reference.wav"
    path.write_bytes(b"unit-test-audio")
    return path


def _clone_prompt(reference_file: Path) -> dict:
    return {"prompt_wav_path": str(reference_file), "prompt_text": "The reference transcript."}


# ---------------------------------------------------------------------------
# load_model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_model_is_idempotent(backend, recorder: _Recorder) -> None:
    await backend.load_model()
    await backend.load_model()
    await backend.load_model("default")

    assert len(recorder.from_pretrained_calls) == 1
    assert backend.is_loaded() is True


@pytest.mark.asyncio
async def test_load_model_disables_the_modelscope_denoiser(backend, recorder: _Recorder) -> None:
    await backend.load_model()

    args, kwargs = recorder.from_pretrained_calls[0]
    assert kwargs.get("load_denoiser") is False
    repo = kwargs.get("hf_model_id", args[0] if args else None)
    assert repo == "openbmb/VoxCPM2"


@pytest.mark.asyncio
async def test_load_model_passes_an_explicit_device_from_our_policy(backend, recorder: _Recorder) -> None:
    await backend.load_model()

    _args, kwargs = recorder.from_pretrained_calls[0]
    assert kwargs.get("device") == FAKE_DEVICE
    assert kwargs.get("device") not in (None, "auto")
    assert recorder.device_calls, "the device must come from get_torch_device"
    assert recorder.device_calls[0].get("allow_mps") is True


@pytest.mark.asyncio
async def test_cached_model_loads_with_local_files_only(backend, recorder: _Recorder) -> None:
    await backend.load_model()

    _args, kwargs = recorder.from_pretrained_calls[0]
    assert kwargs.get("local_files_only") is True


@pytest.mark.asyncio
async def test_uncached_model_may_download(backend, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backend, "_is_model_cached", lambda *_a, **_k: False)

    await backend.load_model()

    _args, kwargs = recorder.from_pretrained_calls[0]
    assert kwargs.get("local_files_only", False) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("is_cached", [True, False])
async def test_load_runs_inside_model_load_progress(
    backend, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch, is_cached: bool
) -> None:
    monkeypatch.setattr(backend, "_is_model_cached", lambda *_a, **_k: is_cached)

    await backend.load_model()

    names = [event[0] for event in recorder.events]
    assert names == ["progress_enter", "from_pretrained", "progress_exit"]
    assert recorder.events[0] == ("progress_enter", "voxcpm2", is_cached)


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_the_array_and_the_model_runtime_sample_rate(
    backend, recorder: _Recorder, reference_file: Path
) -> None:
    audio, sample_rate = await backend.generate("Hello there.", _clone_prompt(reference_file))

    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert sample_rate == FAKE_SAMPLE_RATE


@pytest.mark.asyncio
async def test_generate_keeps_upstream_normalization_off(backend, recorder: _Recorder, reference_file: Path) -> None:
    await backend.generate("Hello there.", _clone_prompt(reference_file))

    assert recorder.generate_calls[0].get("normalize") is False


@pytest.mark.asyncio
async def test_seed_is_applied_before_the_vendor_call_and_never_forwarded(
    backend, recorder: _Recorder, reference_file: Path
) -> None:
    await backend.generate("Hello there.", _clone_prompt(reference_file), seed=1234)

    names = [event[0] for event in recorder.events]
    assert "manual_seed" in names
    assert names.index("manual_seed") < names.index("generate")
    assert ("manual_seed", 1234, FAKE_DEVICE) in recorder.events
    assert "seed" not in recorder.generate_calls[0]


@pytest.mark.asyncio
async def test_no_seed_means_no_manual_seed(backend, recorder: _Recorder, reference_file: Path) -> None:
    await backend.generate("Hello there.", _clone_prompt(reference_file))

    assert not [event for event in recorder.events if event[0] == "manual_seed"]
    assert "seed" not in recorder.generate_calls[0]


@pytest.mark.asyncio
async def test_generate_passes_the_prompt_pair_together(backend, recorder: _Recorder, reference_file: Path) -> None:
    await backend.generate("Hello there.", _clone_prompt(reference_file), language="ar")

    kwargs = recorder.generate_calls[0]
    assert kwargs["text"] == "Hello there."
    assert kwargs["prompt_wav_path"] == str(reference_file)
    assert kwargs["prompt_text"] == "The reference transcript."
    assert "language" not in kwargs  # voxcpm 2.0.3 takes no language argument


@pytest.mark.asyncio
@pytest.mark.parametrize("voice_prompt", [None, {}])
async def test_generate_without_reference_passes_neither_prompt_key(backend, recorder: _Recorder, voice_prompt) -> None:
    await backend.generate("Hello there.", voice_prompt)

    kwargs = recorder.generate_calls[0]
    assert kwargs.get("prompt_wav_path") is None
    assert kwargs.get("prompt_text") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "voice_prompt",
    [{"prompt_wav_path": "ref.wav"}, {"prompt_text": "only text"}, {"prompt_wav_path": "ref.wav", "prompt_text": "  "}],
)
async def test_generate_rejects_half_a_prompt_pair(backend, recorder: _Recorder, voice_prompt) -> None:
    with pytest.raises(ValueError, match="prompt_wav_path"):
        await backend.generate("Hello there.", voice_prompt)

    assert recorder.generate_calls == []


@pytest.mark.asyncio
async def test_generate_uses_declared_defaults_without_options(
    backend, recorder: _Recorder, reference_file: Path
) -> None:
    await backend.generate("Hello there.", _clone_prompt(reference_file))

    kwargs = recorder.generate_calls[0]
    assert kwargs["cfg_value"] == 2.0
    assert kwargs["inference_timesteps"] == 10


@pytest.mark.asyncio
async def test_generate_maps_advanced_options(backend, recorder: _Recorder, reference_file: Path) -> None:
    await backend.generate(
        "Hello there.",
        _clone_prompt(reference_file),
        options={"cfg_value": 2.5, "inference_timesteps": 16.0},
    )

    kwargs = recorder.generate_calls[0]
    assert kwargs["cfg_value"] == 2.5
    assert kwargs["inference_timesteps"] == 16
    assert isinstance(kwargs["inference_timesteps"], int)


@pytest.mark.asyncio
async def test_generate_partial_options_fall_back_per_setting(
    backend, recorder: _Recorder, reference_file: Path
) -> None:
    await backend.generate("Hello there.", _clone_prompt(reference_file), options={"cfg_value": 1.5})

    kwargs = recorder.generate_calls[0]
    assert kwargs["cfg_value"] == 1.5
    assert kwargs["inference_timesteps"] == 10


@pytest.mark.asyncio
async def test_voice_description_becomes_the_ascii_paren_prefix_without_reference(backend, recorder: _Recorder) -> None:
    await backend.generate("Hello there.", {}, instruct="  A young woman, gentle and sweet voice  ")

    assert recorder.generate_calls[0]["text"] == "(A young woman, gentle and sweet voice)Hello there."


@pytest.mark.asyncio
async def test_voice_description_is_inactive_when_reference_audio_is_present(
    backend, recorder: _Recorder, reference_file: Path
) -> None:
    await backend.generate("Hello there.", _clone_prompt(reference_file), instruct="An old man, deep voice")

    assert recorder.generate_calls[0]["text"] == "Hello there."


@pytest.mark.asyncio
@pytest.mark.parametrize("instruct", [None, "", "   "])
async def test_blank_voice_description_adds_no_prefix(backend, recorder: _Recorder, instruct) -> None:
    await backend.generate("Hello there.", None, instruct=instruct)

    assert recorder.generate_calls[0]["text"] == "Hello there."


# ---------------------------------------------------------------------------
# unload_model / is_loaded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unload_empties_the_device_cache_and_reports_unloaded(backend, recorder: _Recorder) -> None:
    await backend.load_model()
    assert backend.is_loaded() is True

    backend.unload_model()

    assert backend.is_loaded() is False
    assert backend.model is None
    assert recorder.emptied == [FAKE_DEVICE]


def test_unload_when_not_loaded_is_a_no_op(backend, recorder: _Recorder) -> None:
    backend.unload_model()

    assert backend.is_loaded() is False
    assert recorder.emptied == []


@pytest.mark.asyncio
async def test_reload_after_unload_loads_again(backend, recorder: _Recorder) -> None:
    await backend.load_model()
    backend.unload_model()
    await backend.load_model()

    assert len(recorder.from_pretrained_calls) == 2


# ---------------------------------------------------------------------------
# _get_model_path / _is_model_cached
# ---------------------------------------------------------------------------


def test_model_path_is_the_hf_repo(vb) -> None:
    assert vb.VoxCPMBackend()._get_model_path("default") == "openbmb/VoxCPM2"


def _fake_hf_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from huggingface_hub import constants as hf_constants

    monkeypatch.setattr(hf_constants, "HF_HUB_CACHE", str(tmp_path))
    snapshot = tmp_path / "models--openbmb--VoxCPM2" / "snapshots" / "32279effe8c19989596f05d353d1447f51d9e915"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    return snapshot


def test_is_model_cached_recognises_pth_weights(vb, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _fake_hf_snapshot(tmp_path, monkeypatch)
    backend = vb.VoxCPMBackend()
    assert backend._is_model_cached() is False  # config only, no weights

    (snapshot / "audiovae.pth").write_bytes(b"weights")

    assert backend._is_model_cached() is True


def test_is_model_cached_recognises_safetensors_weights(vb, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _fake_hf_snapshot(tmp_path, monkeypatch)
    (snapshot / "model.safetensors").write_bytes(b"weights")

    assert vb.VoxCPMBackend()._is_model_cached() is True


def test_is_model_cached_rejects_incomplete_downloads(vb, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _fake_hf_snapshot(tmp_path, monkeypatch)
    (snapshot / "audiovae.pth").write_bytes(b"weights")
    blobs = snapshot.parents[1] / "blobs"
    blobs.mkdir()
    (blobs / "abc.incomplete").write_bytes(b"partial")

    assert vb.VoxCPMBackend()._is_model_cached() is False


# ---------------------------------------------------------------------------
# create_voice_prompt / combine_voice_prompts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_prompt_carries_the_audio_path_and_transcript(
    backend, recorder: _Recorder, reference_file: Path
) -> None:
    prompt, was_cached = await backend.create_voice_prompt(str(reference_file), " The reference transcript. ")

    assert prompt == {"prompt_wav_path": str(reference_file), "prompt_text": "The reference transcript."}
    assert was_cached is False
    assert list(recorder.cache)
    assert all(key.startswith("voxcpm_") for key in recorder.cache)


@pytest.mark.asyncio
async def test_voice_prompt_is_served_from_the_engine_scoped_cache(
    backend, recorder: _Recorder, reference_file: Path
) -> None:
    first, first_cached = await backend.create_voice_prompt(str(reference_file), "The reference transcript.")
    second, second_cached = await backend.create_voice_prompt(str(reference_file), "The reference transcript.")

    assert first_cached is False
    assert second_cached is True
    assert second == first


@pytest.mark.asyncio
async def test_voice_prompt_without_cache_writes_nothing(backend, recorder: _Recorder, reference_file: Path) -> None:
    prompt, was_cached = await backend.create_voice_prompt(str(reference_file), "Text.", use_cache=False)

    assert prompt["prompt_wav_path"] == str(reference_file)
    assert was_cached is False
    assert recorder.cache == {}


@pytest.mark.asyncio
async def test_voice_prompt_requires_a_transcript(backend, recorder: _Recorder, reference_file: Path) -> None:
    with pytest.raises(ValueError, match="transcript"):
        await backend.create_voice_prompt(str(reference_file), "   ")


@pytest.mark.asyncio
async def test_combine_voice_prompts_delegates_to_the_shared_helper(
    vb, backend, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict = {}

    async def fake_combine(audio_paths, reference_texts, *, sample_rate=None):
        seen.update(paths=audio_paths, texts=reference_texts, sample_rate=sample_rate)
        return np.zeros(4, dtype=np.float32), " ".join(reference_texts)

    monkeypatch.setattr(vb, "_combine_voice_prompts", fake_combine)

    audio, text = await backend.combine_voice_prompts(["a.wav", "b.wav"], ["one", "two"])

    assert audio.shape == (4,)
    assert text == "one two"
    assert seen["paths"] == ["a.wav", "b.wav"]
    # services/profiles.py writes the combined reference with save_audio(..., 24000);
    # combining at any other rate would mislabel the WAV and change its speed and pitch.
    assert seen["sample_rate"] == 24_000


# ---------------------------------------------------------------------------
# T025: voice prompt caching, pairing, multi-clip combining and seeding (US2)
# ---------------------------------------------------------------------------


@pytest.fixture
def real_prompt_cache(vb, recorder: _Recorder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put the real utils.cache helpers back, pointed at an empty tmp cache dir.

    The recorder fixture swaps them for a dict; these tests want the real
    memory + disk (torch.save / torch.load) round trip instead.
    """
    from backend import config
    from backend.utils import cache as cache_mod

    cache_dir = tmp_path / "prompt-cache"
    cache_dir.mkdir()
    monkeypatch.setattr(config, "get_cache_dir", lambda: cache_dir)
    monkeypatch.setattr(cache_mod, "_memory_cache", {})
    monkeypatch.setattr(vb, "get_cached_voice_prompt", cache_mod.get_cached_voice_prompt)
    monkeypatch.setattr(vb, "cache_voice_prompt", cache_mod.cache_voice_prompt)
    return cache_dir


def _speech_like_wav(path: Path, *, seconds: float, freq: float, sample_rate: int) -> Path:
    import soundfile as sf

    t = np.arange(int(seconds * sample_rate), dtype=np.float32) / sample_rate
    sf.write(str(path), (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32), sample_rate)
    return path


@pytest.mark.asyncio
async def test_voice_prompt_key_is_the_prefixed_shared_cache_key(
    vb, backend, recorder: _Recorder, reference_file: Path
) -> None:
    from backend.utils.cache import get_cache_key

    await backend.create_voice_prompt(str(reference_file), "The reference transcript.")

    assert list(recorder.cache) == ["voxcpm_" + get_cache_key(str(reference_file), "The reference transcript.")]


@pytest.mark.asyncio
async def test_real_cache_returns_the_pair_and_reports_cached_on_the_second_call(
    backend, real_prompt_cache: Path, reference_file: Path
) -> None:
    from backend.utils import cache as cache_mod

    first, first_cached = await backend.create_voice_prompt(str(reference_file), "The reference transcript.")
    second, second_cached = await backend.create_voice_prompt(str(reference_file), "The reference transcript.")

    assert set(first) == {"prompt_wav_path", "prompt_text"}
    assert first == {"prompt_wav_path": str(reference_file), "prompt_text": "The reference transcript."}
    assert (first_cached, second_cached) == (False, True)
    assert second == first

    files = sorted(p.name for p in real_prompt_cache.glob("*.prompt"))
    assert len(files) == 1
    assert files[0].startswith("voxcpm_")

    # A fresh process (empty memory cache) still gets the prompt from disk, as cached.
    cache_mod._memory_cache.clear()
    third, third_cached = await backend.create_voice_prompt(str(reference_file), "The reference transcript.")
    assert third_cached is True
    assert third == first


@pytest.mark.asyncio
async def test_real_cache_does_not_serve_another_engines_entry(
    backend, real_prompt_cache: Path, reference_file: Path
) -> None:
    """An unprefixed entry for the same audio and text (another engine's) must never be reused."""
    from backend.utils.cache import cache_voice_prompt, get_cache_key

    cache_voice_prompt(get_cache_key(str(reference_file), "The reference transcript."), {"other": "engine"})

    prompt, was_cached = await backend.create_voice_prompt(str(reference_file), "The reference transcript.")

    assert was_cached is False
    assert prompt == {"prompt_wav_path": str(reference_file), "prompt_text": "The reference transcript."}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "voice_prompt",
    [
        None,
        {},
        {"prompt_wav_path": "ref.wav", "prompt_text": "Text."},
        {"prompt_wav_path": "ref.wav"},
        {"prompt_text": "Text."},
        {"prompt_wav_path": "", "prompt_text": "Text."},
        {"prompt_wav_path": "ref.wav", "prompt_text": ""},
        {"prompt_wav_path": None, "prompt_text": "Text."},
    ],
)
async def test_vendor_never_receives_exactly_one_of_the_pair(backend, recorder: _Recorder, voice_prompt) -> None:
    with contextlib.suppress(ValueError):  # a half pair is refused before the vendor call
        await backend.generate("Hello there.", voice_prompt)

    for kwargs in recorder.generate_calls:
        has_wav = kwargs.get("prompt_wav_path") is not None
        has_text = kwargs.get("prompt_text") is not None
        assert has_wav == has_text, kwargs


@pytest.mark.asyncio
async def test_a_created_prompt_reaches_the_vendor_as_a_complete_pair(
    backend, recorder: _Recorder, reference_file: Path
) -> None:
    prompt, _ = await backend.create_voice_prompt(str(reference_file), "The reference transcript.")

    await backend.generate("Something else entirely.", prompt)

    kwargs = recorder.generate_calls[0]
    assert kwargs["prompt_wav_path"] == str(reference_file)
    assert kwargs["prompt_text"] == "The reference transcript."


def test_combine_rate_is_the_profiles_save_rate(vb) -> None:
    # services/profiles.py saves the combined reference with save_audio(..., 24000).
    assert vb.COMBINE_SAMPLE_RATE == 24_000


def test_combine_passes_the_named_constant_not_a_literal() -> None:
    tree = ast.parse(MODULE_FILE.read_text(encoding="utf-8"))
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "combine_voice_prompts"
    )
    calls = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_combine_voice_prompts"
    ]
    assert len(calls) == 1, "combine_voice_prompts must delegate to base.combine_voice_prompts exactly once"
    rate = {kw.arg: kw.value for kw in calls[0].keywords}.get("sample_rate")
    assert isinstance(rate, ast.Name), "the rate must be passed by name, not as a literal"
    assert rate.id == "COMBINE_SAMPLE_RATE"


def test_combine_delegate_is_the_shared_base_helper(vb) -> None:
    from backend.backends import base

    assert vb._combine_voice_prompts is base.combine_voice_prompts


@pytest.mark.asyncio
async def test_multi_clip_prompt_is_combined_and_then_used_by_generate(
    vb, backend, recorder: _Recorder, real_prompt_cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The services/profiles.py multi-clip flow, with the real shared combine helper.

    combine -> save_audio(..., 24000) -> create_voice_prompt(combined) -> generate.
    """
    from backend.backends import base
    from backend.utils.audio import save_audio

    rates_seen: list = []
    real_combine = base.combine_voice_prompts

    async def spy_combine(audio_paths, reference_texts, *, sample_rate=None):
        rates_seen.append(sample_rate)
        return await real_combine(audio_paths, reference_texts, sample_rate=sample_rate)

    monkeypatch.setattr(vb, "_combine_voice_prompts", spy_combine)

    clip_a = _speech_like_wav(tmp_path / "a.wav", seconds=1.0, freq=220.0, sample_rate=48_000)
    clip_b = _speech_like_wav(tmp_path / "b.wav", seconds=0.5, freq=330.0, sample_rate=16_000)

    combined_audio, combined_text = await backend.combine_voice_prompts(
        [str(clip_a), str(clip_b)], ["First clip.", "Second clip."]
    )

    assert rates_seen == [vb.COMBINE_SAMPLE_RATE]
    assert combined_text == "First clip. Second clip."
    # Both clips, each resampled to the combine rate: 1.0 s + 0.5 s at 24 kHz.
    assert combined_audio.ndim == 1
    assert abs(len(combined_audio) - int(1.5 * vb.COMBINE_SAMPLE_RATE)) <= 2

    combined_path = real_prompt_cache / "combined_profile_abc.wav"
    save_audio(combined_audio, str(combined_path), 24000)

    prompt, was_cached = await backend.create_voice_prompt(str(combined_path), combined_text)
    assert was_cached is False

    await backend.generate("A new sentence in the combined voice.", prompt, seed=7)

    kwargs = recorder.generate_calls[0]
    assert kwargs["prompt_wav_path"] == str(combined_path)
    assert kwargs["prompt_text"] == "First clip. Second clip."


@pytest.fixture
def rng_vendor(vb, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch):
    """Fake vendor whose output is drawn from torch's global RNG, with the real manual_seed."""
    import torch

    from backend.backends import base

    fake_module = sys.modules["voxcpm"]

    def generate(self, *args, **kwargs):
        recorder.generate_calls.append(kwargs)
        return torch.randn(16).numpy().astype(np.float32)

    monkeypatch.setattr(fake_module.VoxCPM, "generate", generate)
    # Real seeding; the CPU generator is what torch.randn above draws from.
    monkeypatch.setattr(vb, "manual_seed", base.manual_seed)
    monkeypatch.setattr(vb.VoxCPMBackend, "_get_device", lambda self: "cpu")
    return torch


@pytest.mark.asyncio
async def test_same_seed_gives_identical_output(backend, rng_vendor, reference_file: Path) -> None:
    prompt = _clone_prompt(reference_file)

    first, _ = await backend.generate("Same text.", prompt, seed=1234)
    rng_vendor.randn(100)  # disturb the global RNG between the two runs
    second, _ = await backend.generate("Same text.", prompt, seed=1234)

    assert first.tobytes() == second.tobytes()


@pytest.mark.asyncio
async def test_different_seed_gives_different_output(backend, rng_vendor, reference_file: Path) -> None:
    prompt = _clone_prompt(reference_file)

    first, _ = await backend.generate("Same text.", prompt, seed=1234)
    second, _ = await backend.generate("Same text.", prompt, seed=4321)

    assert first.tobytes() != second.tobytes()


# ---------------------------------------------------------------------------
# T027: voxcpm clones existing voice profiles (FR-014)
# ---------------------------------------------------------------------------


def test_voxcpm_is_a_cloning_engine() -> None:
    from backend.services.profiles import CLONING_ENGINES

    assert "voxcpm" in CLONING_ENGINES


def test_cloned_profile_with_voxcpm_passes_profile_validation() -> None:
    from types import SimpleNamespace

    from backend.services.profiles import _validate_profile_fields, validate_profile_engine

    assert (
        _validate_profile_fields(
            voice_type="cloned",
            preset_engine=None,
            preset_voice_id=None,
            design_prompt=None,
            default_engine="voxcpm",
        )
        is None
    )
    validate_profile_engine(SimpleNamespace(id="p1", voice_type="cloned"), "voxcpm")


# ---------------------------------------------------------------------------
# No heavy import at module import time (Principle III)
# ---------------------------------------------------------------------------

_HEAVY_ROOTS = {"torch", "torchaudio", "voxcpm", "transformers", "librosa"}


def test_module_has_no_top_level_heavy_import() -> None:
    tree = ast.parse(MODULE_FILE.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in tree.body:
        for sub in ast.walk(node):
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                break
            if isinstance(sub, ast.Import):
                offenders += [a.name for a in sub.names if a.name.split(".")[0] in _HEAVY_ROOTS]
            elif (
                isinstance(sub, ast.ImportFrom)
                and sub.module
                and sub.level == 0
                and sub.module.split(".")[0] in _HEAVY_ROOTS
            ):
                offenders.append(sub.module)
    assert offenders == []


def test_vendor_import_is_marked_lazy() -> None:
    source = MODULE_FILE.read_text(encoding="utf-8")
    lines = [line for line in source.splitlines() if "from voxcpm import" in line or "import voxcpm" in line]
    assert lines, "the vendor must be imported somewhere (inside the load function)"
    assert all("# lazy: heavy import" in line for line in lines)


def _run_isolated(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


def test_importing_and_constructing_the_backend_does_not_import_the_vendor() -> None:
    out = _run_isolated(
        "import sys\n"
        "import backend.backends\n"
        "import backend.backends.voxcpm_backend as m\n"
        "m.VoxCPMBackend()\n"
        "print(sorted(n for n in sys.modules if n == 'voxcpm' or n.startswith('voxcpm.')))\n"
    )
    assert out == "[]"


# ---------------------------------------------------------------------------
# T016: registry
# ---------------------------------------------------------------------------


def _voxcpm_configs():
    from backend.backends import get_tts_model_configs

    return [c for c in get_tts_model_configs() if c.engine == "voxcpm"]


def test_engine_is_registered_by_name() -> None:
    from backend.backends import TTS_ENGINES

    assert TTS_ENGINES["voxcpm"] == "VoxCPM2"


def test_model_config_declares_the_data_model_values() -> None:
    configs = _voxcpm_configs()
    assert len(configs) == 1
    config = configs[0]

    assert config.model_name == "voxcpm2"
    assert config.display_name == "VoxCPM2 (Multilingual, Voice Design)"
    assert config.hf_repo_id == "openbmb/VoxCPM2"
    assert config.model_size == "default"
    assert config.size_mb == 4961
    assert config.needs_trim is False
    assert config.retries_runaway is True
    assert config.supports_instruct is False
    assert config.supports_voice_design is True
    assert config.requires_download_confirmation is True
    assert config.accelerators == ("cuda", "mps", "cpu")
    assert config.license_id == "Apache-2.0"
    assert config.commercial_use is True
    assert config.dialect is None
    assert config.min_memory_mb == 6144
    assert config.languages == EXPECTED_LANGUAGES
    assert len(config.languages) == 30


def test_model_config_declares_the_two_advanced_settings() -> None:
    (config,) = _voxcpm_configs()
    settings = {s.name: s for s in config.advanced_settings}

    assert [s.name for s in config.advanced_settings] == ["cfg_value", "inference_timesteps"]
    assert settings["cfg_value"].label == "Guidance"
    assert settings["cfg_value"].default == 2.0
    assert settings["inference_timesteps"].label == "Quality steps"
    assert settings["inference_timesteps"].default == 10
    for setting in settings.values():
        assert setting.min <= setting.default <= setting.max
        assert setting.min < setting.max
    # Within the hard ranges voxcpm 2.0.3's CLI enforces (cli.py validate_ranges).
    assert settings["cfg_value"].min >= 0.1
    assert settings["cfg_value"].max <= 10.0
    assert settings["inference_timesteps"].min >= 1
    assert settings["inference_timesteps"].max <= 100


def test_backend_defaults_match_the_declared_settings(vb) -> None:
    (config,) = _voxcpm_configs()
    settings = {s.name: s.default for s in config.advanced_settings}

    assert settings["cfg_value"] == vb.DEFAULT_CFG_VALUE
    assert settings["inference_timesteps"] == vb.DEFAULT_INFERENCE_TIMESTEPS


def test_default_model_size_is_default() -> None:
    from backend.backends import get_default_model_size

    assert get_default_model_size("voxcpm") == "default"


def test_dispatch_returns_the_voxcpm_backend(vb) -> None:
    from backend.backends import get_tts_backend_for_engine

    assert isinstance(get_tts_backend_for_engine("voxcpm"), vb.VoxCPMBackend)


def test_dispatch_does_not_import_the_vendor() -> None:
    out = _run_isolated(
        "import sys\n"
        "from backend.backends import get_tts_backend_for_engine\n"
        "b = get_tts_backend_for_engine('voxcpm')\n"
        "print(type(b).__name__, sorted(n for n in sys.modules if n == 'voxcpm' or n.startswith('voxcpm.')))\n"
    )
    assert out == "VoxCPMBackend []"


def test_all_four_engine_patterns_accept_voxcpm() -> None:
    from datetime import UTC, datetime

    from backend.models import GenerationRequest, MCPClientBindingResponse, MCPClientBindingUpsert, SpeakRequest

    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert GenerationRequest(profile_id="p1", text="hi", engine="voxcpm").engine == "voxcpm"
    assert SpeakRequest(text="hi", engine="voxcpm").engine == "voxcpm"
    assert MCPClientBindingUpsert(client_id="c1", default_engine="voxcpm").default_engine == "voxcpm"
    assert (
        MCPClientBindingResponse(client_id="c1", created_at=now, updated_at=now, default_engine="voxcpm").default_engine
        == "voxcpm"
    )


def test_generation_request_accepts_the_declared_advanced_settings() -> None:
    from backend.models import GenerationRequest

    request = GenerationRequest(
        profile_id="p1",
        text="hi",
        engine="voxcpm",
        advanced_settings={"cfg_value": 2.0, "inference_timesteps": 10},
    )
    assert request.advanced_settings == {"cfg_value": 2.0, "inference_timesteps": 10}


# ---------------------------------------------------------------------------
# T046: a cached model loads with the network blocked (Principle I)
# ---------------------------------------------------------------------------


@pytest.fixture
def blocked_network(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Every non-loopback socket lookup and connect raises, and is recorded.

    Loopback stays open, as in the probe's hook (evidence/probe/probe_run.py): the
    Windows asyncio event loop builds its self-pipe from a loopback socketpair.
    """
    import socket

    attempts: list[tuple] = []
    real_getaddrinfo = socket.getaddrinfo
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    loopback = {"localhost", "127.0.0.1", "::1"}

    def _host(address) -> str:
        return str(address[0]) if isinstance(address, tuple) else str(address)

    def refuse_getaddrinfo(host, *args, **kwargs):
        if str(host) in loopback:
            return real_getaddrinfo(host, *args, **kwargs)
        attempts.append(("getaddrinfo", host))
        raise OSError(f"network blocked by test: getaddrinfo({host!r})")

    def refuse_connect(self, address):
        if _host(address) in loopback:
            return real_connect(self, address)
        attempts.append(("connect", address))
        raise OSError(f"network blocked by test: connect({address!r})")

    def refuse_connect_ex(self, address):
        if _host(address) in loopback:
            return real_connect_ex(self, address)
        attempts.append(("connect_ex", address))
        raise OSError(f"network blocked by test: connect_ex({address!r})")

    monkeypatch.setattr(socket, "getaddrinfo", refuse_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", refuse_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse_connect_ex)
    return attempts


@pytest.fixture
def offline_vendor(recorder: _Recorder, monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Make the fake vendor behave like voxcpm 2.0.3 about the network.

    from_pretrained() resolves the snapshot through the HuggingFace hub unless it
    is told local_files_only=True or HF offline mode is on, and loads the
    ModelScope denoiser when load_denoiser is left True. Each would-be
    resolution is recorded and then attempted over the (blocked) network.
    """
    import os
    import socket

    import huggingface_hub.constants as hf_constants

    resolutions: list[tuple] = []
    fake_module = sys.modules["voxcpm"]
    plain_from_pretrained = fake_module.VoxCPM.from_pretrained

    def from_pretrained(*args, **kwargs):
        hf_offline = bool(hf_constants.HF_HUB_OFFLINE) and os.environ.get("HF_HUB_OFFLINE") == "1"
        recorder.events.append(("offline_state", hf_offline))
        if not kwargs.get("local_files_only") and not hf_offline:
            resolutions.append(("huggingface", kwargs.get("hf_model_id", args[0] if args else None)))
            socket.getaddrinfo("huggingface.co", 443)
        if kwargs.get("load_denoiser", True):
            resolutions.append(("modelscope", "iic/speech_zipenhancer_ans_multiloss_16k_base"))
            socket.getaddrinfo("modelscope.cn", 443)
        return plain_from_pretrained(*args, **kwargs)

    monkeypatch.setattr(fake_module.VoxCPM, "from_pretrained", staticmethod(from_pretrained))
    monkeypatch.delitem(sys.modules, "modelscope", raising=False)
    return resolutions


@pytest.fixture
def offline_spy(vb, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Wrap the real force_offline_if_cached so its entry and arguments are recorded."""
    from backend.utils.hf_offline_patch import force_offline_if_cached as real_force_offline

    calls: list[tuple] = []

    @contextmanager
    def spy(is_cached: bool, model_label: str = ""):
        calls.append((is_cached, model_label))
        recorder.events.append(("offline_enter", is_cached, model_label))
        with real_force_offline(is_cached, model_label):
            yield
        recorder.events.append(("offline_exit",))

    # raising=False so the red run (no wrapper yet) fails on the assertions, not here.
    monkeypatch.setattr(vb, "force_offline_if_cached", spy, raising=False)
    return calls


@pytest.mark.asyncio
async def test_cached_load_succeeds_with_the_network_blocked(
    backend, recorder: _Recorder, blocked_network, offline_vendor, offline_spy
) -> None:
    await backend.load_model()

    assert backend.is_loaded() is True
    assert blocked_network == []
    assert offline_vendor == []
    assert "modelscope" not in sys.modules


@pytest.mark.asyncio
async def test_cached_load_runs_inside_force_offline_if_cached(
    backend, recorder: _Recorder, blocked_network, offline_vendor, offline_spy
) -> None:
    await backend.load_model()

    assert offline_spy == [(True, "VoxCPM2")]
    names = [event[0] for event in recorder.events]
    assert names.index("offline_enter") < names.index("from_pretrained") < names.index("offline_exit")
    # HF offline mode is really on (env and huggingface_hub constant) while the vendor resolves.
    assert ("offline_state", True) in recorder.events


@pytest.mark.asyncio
async def test_cached_load_passes_local_files_only_and_no_denoiser(
    backend, recorder: _Recorder, blocked_network, offline_vendor, offline_spy
) -> None:
    await backend.load_model()

    _args, kwargs = recorder.from_pretrained_calls[0]
    assert kwargs.get("local_files_only") is True
    assert kwargs.get("load_denoiser") is False


@pytest.mark.asyncio
async def test_offline_mode_is_restored_after_the_cached_load(
    backend, recorder: _Recorder, blocked_network, offline_vendor, offline_spy
) -> None:
    import os

    import huggingface_hub.constants as hf_constants

    before = (hf_constants.HF_HUB_OFFLINE, os.environ.get("HF_HUB_OFFLINE"))

    await backend.load_model()

    assert (hf_constants.HF_HUB_OFFLINE, os.environ.get("HF_HUB_OFFLINE")) == before


@pytest.mark.asyncio
async def test_uncached_load_is_not_forced_offline(
    backend, recorder: _Recorder, offline_spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backend, "_is_model_cached", lambda *_a, **_k: False)

    await backend.load_model()

    assert offline_spy == [(False, "VoxCPM2")]
    _args, kwargs = recorder.from_pretrained_calls[0]
    assert kwargs.get("local_files_only", False) is False


# ---------------------------------------------------------------------------
# T024: dictionary-processed Arabic reaches the vendor unchanged (FR-008)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pronunciation_processed_arabic_reaches_the_vendor_byte_for_byte(
    backend, recorder: _Recorder, reference_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real dictionary rewrite and the real chunker the generation service uses,
    with the real VoxCPM2 backend in front of the fake vendor.

    services/generation.py runs pronunciation.apply_pronunciations() and then
    utils.chunked_tts.generate_chunked(); the same two calls are made here. Only
    the dictionary's database read (get_entries) is replaced, so no app DB is needed.
    """
    from types import SimpleNamespace

    from backend.services import pronunciation
    from backend.utils.chunked_tts import generate_chunked

    entry = SimpleNamespace(id="entry-1", term="محمد", replacement="مُحَمَّد", language="ar", profile_id=None, enabled=True)
    monkeypatch.setattr(pronunciation, "get_entries", lambda *_a, **_k: [entry])

    authored = "قالَ محمد: السَّلامُ عَلَيْكُم."
    processed, applied = pronunciation.apply_pronunciations(authored, "ar", db=None)
    assert processed == "قالَ مُحَمَّد: السَّلامُ عَلَيْكُم."
    assert applied
    assert applied[0]["replacement"] == "مُحَمَّد"
    # The diacritics are combining marks (shadda U+0651, fatha U+064E); they must survive untouched.
    assert "\u0651" in processed
    assert "\u064e" in processed

    audio, sample_rate = await generate_chunked(backend, processed, _clone_prompt(reference_file), language="ar")

    (kwargs,) = recorder.generate_calls
    assert kwargs["text"] == processed
    assert kwargs["text"].encode("utf-8") == processed.encode("utf-8")
    assert kwargs["normalize"] is False
    assert sample_rate == FAKE_SAMPLE_RATE
    assert audio.dtype == np.float32
