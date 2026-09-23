"""Advanced generation settings reach only the engines that declare them (T023, FR-010).

``GenerationRequest.advanced_settings`` is validated in ``backend/models.py``. These
tests cover what happens after validation:

* the ``/generate`` and ``/generate/stream`` routes thread the settings through;
* ``services/generation.py`` passes them to the backend as the additive ``options``
  argument, but only for engines whose ``ModelConfig.advanced_settings`` is non-empty;
* the eight pre-existing backends never receive an ``options`` keyword at all.

Every backend, database and model call is faked; nothing loads weights.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from backend import models
from backend.services import generation as generation_service

PRE_VOXCPM_ENGINES = [
    "qwen",
    "qwen_custom_voice",
    "luxtts",
    "chatterbox",
    "chatterbox_turbo",
    "tada",
    "kokoro",
    "f5_tts",
]
SETTINGS = {"cfg_value": 2.5, "inference_timesteps": 16.0}


class StrictBackend:
    """A backend with today's protocol signature: an ``options`` keyword raises TypeError."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def is_loaded(self) -> bool:
        return True

    async def generate(self, text, voice_prompt, language="en", seed=None, instruct=None):
        self.calls.append({"text": text, "language": language, "seed": seed, "instruct": instruct})
        return np.zeros(2400, dtype=np.float32), 24000


class OptionsBackend(StrictBackend):
    """A backend that accepts the additive ``options`` argument, as VoxCPM2 does."""

    async def generate(self, text, voice_prompt, language="en", seed=None, instruct=None, options=None):
        self.calls.append({"text": text, "language": language, "seed": seed, "instruct": instruct, "options": options})
        return np.zeros(2400, dtype=np.float32), 24000


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch):
    """run_generation with every collaborator faked; returns the recorded statuses."""
    import backend.backends as backends_pkg

    statuses: list[tuple] = []
    state = SimpleNamespace(backend=None, statuses=statuses)

    class FakeSession:
        def close(self) -> None:
            pass

    def fake_get_db():
        yield FakeSession()

    async def fake_update_status(generation_id, status, db, **kwargs):
        statuses.append((status, kwargs.get("error")))

    async def fake_voice_prompt(*_a, **_k):
        return {}

    async def fake_load(*_a, **_k):
        return None

    monkeypatch.setattr(generation_service, "get_db", fake_get_db)
    monkeypatch.setattr(generation_service.history, "update_generation_status", fake_update_status)
    monkeypatch.setattr(generation_service.profiles, "create_voice_prompt_for_profile", fake_voice_prompt)
    monkeypatch.setattr(generation_service.pronunciation, "apply_pronunciations", lambda text, *_a, **_k: (text, []))
    monkeypatch.setattr(generation_service, "_save_generate", lambda **_k: "generations/fake.wav")
    monkeypatch.setattr(backends_pkg, "get_tts_backend_for_engine", lambda _engine: state.backend)
    monkeypatch.setattr(backends_pkg, "load_engine_model", fake_load)
    return state


async def _run(engine: str, advanced_settings):
    await generation_service.run_generation(
        generation_id="gen-1",
        profile_id="profile-1",
        text="Hello there.",
        language="en",
        engine=engine,
        model_size="default",
        seed=7,
        mode="generate",
        advanced_settings=advanced_settings,
    )


# --- services/generation.py -------------------------------------------------


@pytest.mark.asyncio
async def test_declaring_engine_receives_the_settings_as_options(service) -> None:
    service.backend = OptionsBackend()

    await _run("voxcpm", SETTINGS)

    assert service.statuses[-1] == ("completed", None)
    (call,) = service.backend.calls
    assert call["options"] == SETTINGS
    assert call["seed"] == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("advanced_settings", [None, {}])
async def test_declaring_engine_without_settings_gets_no_options(service, advanced_settings) -> None:
    service.backend = OptionsBackend()

    await _run("voxcpm", advanced_settings)

    assert service.statuses[-1] == ("completed", None)
    assert service.backend.calls[0]["options"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", PRE_VOXCPM_ENGINES)
async def test_existing_engines_never_receive_an_options_keyword(service, engine) -> None:
    # Validation would already reject these settings; the service must not forward them regardless.
    service.backend = StrictBackend()

    await _run(engine, SETTINGS)

    assert service.statuses[-1] == ("completed", None), service.statuses
    assert len(service.backend.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", PRE_VOXCPM_ENGINES)
async def test_existing_engines_are_called_exactly_as_before_without_settings(service, engine) -> None:
    service.backend = StrictBackend()

    await _run(engine, None)

    assert service.statuses[-1] == ("completed", None), service.statuses


def test_backend_is_returned_unwrapped_when_nothing_applies() -> None:
    backend = StrictBackend()

    assert generation_service.backend_with_generation_options(backend, "kokoro", SETTINGS) is backend
    assert generation_service.backend_with_generation_options(backend, "voxcpm", None) is backend
    assert generation_service.backend_with_generation_options(backend, "voxcpm", {}) is backend


@pytest.mark.asyncio
async def test_wrapped_backend_delegates_everything_else() -> None:
    backend = OptionsBackend()
    wrapped = generation_service.backend_with_generation_options(backend, "voxcpm", SETTINGS)

    assert wrapped is not backend
    assert wrapped.is_loaded() is True
    audio, sample_rate = await wrapped.generate("Hi.", {}, "en", None, None)
    assert sample_rate == 24000
    assert audio.shape == (2400,)
    assert backend.calls[0]["options"] == SETTINGS


def test_declaration_lookup_reads_the_model_configs() -> None:
    assert generation_service.engine_declares_advanced_settings("voxcpm") is True
    for engine in PRE_VOXCPM_ENGINES:
        assert generation_service.engine_declares_advanced_settings(engine) is False


@pytest.mark.asyncio
async def test_voxcpm_backend_applies_options_with_declared_defaults_as_fallback(monkeypatch) -> None:
    """Confirms the receiving side: voxcpm_backend.generate maps options, falling back per setting."""
    import sys
    import types

    from backend.backends import voxcpm_backend

    seen: list[dict] = []

    class FakeVoxCPM:
        tts_model = SimpleNamespace(sample_rate=48000)

        @classmethod
        def from_pretrained(cls, *_a, **_k):
            return cls()

        def generate(self, **kwargs):
            seen.append(kwargs)
            return np.zeros(4, dtype=np.float32)

    fake = types.ModuleType("voxcpm")
    fake.VoxCPM = FakeVoxCPM  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "voxcpm", fake)
    monkeypatch.setattr(voxcpm_backend, "get_torch_device", lambda **_k: "cpu")
    backend = voxcpm_backend.VoxCPMBackend()
    monkeypatch.setattr(backend, "_is_model_cached", lambda *_a, **_k: True)

    await backend.generate("Hi.", {}, options={"inference_timesteps": 20.0})
    await backend.generate("Hi.", {}, options=None)

    assert (seen[0]["cfg_value"], seen[0]["inference_timesteps"]) == (2.0, 20)
    assert (seen[1]["cfg_value"], seen[1]["inference_timesteps"]) == (2.0, 10)


# --- routes/generations.py --------------------------------------------------


@pytest.mark.asyncio
async def test_generate_route_threads_advanced_settings_to_the_service(monkeypatch) -> None:
    from backend.routes import generations as routes_mod

    captured: dict = {}

    async def fake_get_profile(*_a, **_k):
        return SimpleNamespace(default_engine=None, preset_engine=None, personality=None, effects_chain=None)

    async def fake_create_generation(**kwargs):
        return SimpleNamespace(id=kwargs["generation_id"])

    def fake_run_generation(**kwargs):
        captured.update(kwargs)
        return "job"

    class FakeQuery:
        def filter_by(self, **_k):
            return self

        def first(self):
            return None

    fake_db = SimpleNamespace(query=lambda *_a: FakeQuery())

    monkeypatch.setattr(routes_mod.profiles, "get_profile", fake_get_profile)
    monkeypatch.setattr(routes_mod.profiles, "validate_profile_engine", lambda *_a, **_k: None)
    monkeypatch.setattr(routes_mod.history, "create_generation", fake_create_generation)
    monkeypatch.setattr(routes_mod, "run_generation", fake_run_generation)
    monkeypatch.setattr(routes_mod, "enqueue_generation", lambda *_a, **_k: None)

    data = models.GenerationRequest(profile_id="p1", text="Hello.", engine="voxcpm", advanced_settings=SETTINGS)
    await routes_mod.generate_speech(data, db=fake_db)

    assert captured["engine"] == "voxcpm"
    assert captured["advanced_settings"] == SETTINGS


@pytest.mark.asyncio
async def test_stream_route_passes_options_to_a_declaring_engine(monkeypatch) -> None:
    import backend.backends as backends_pkg
    from backend.routes import generations as routes_mod

    backend = OptionsBackend()

    async def fake_get_profile(*_a, **_k):
        return SimpleNamespace(default_engine=None, preset_engine=None, personality=None, effects_chain=None)

    async def noop(*_a, **_k):
        return None

    async def fake_voice_prompt(*_a, **_k):
        return {}

    monkeypatch.setattr(routes_mod.profiles, "get_profile", fake_get_profile)
    monkeypatch.setattr(routes_mod.profiles, "validate_profile_engine", lambda *_a, **_k: None)
    monkeypatch.setattr(routes_mod.profiles, "create_voice_prompt_for_profile", fake_voice_prompt)
    monkeypatch.setattr(routes_mod.pronunciation, "apply_pronunciations", lambda text, *_a, **_k: (text, []))
    monkeypatch.setattr(backends_pkg, "get_tts_backend_for_engine", lambda _engine: backend)
    monkeypatch.setattr(backends_pkg, "ensure_model_cached_or_raise", noop)
    monkeypatch.setattr(backends_pkg, "load_engine_model", noop)

    data = models.GenerationRequest(profile_id="p1", text="Hello.", engine="voxcpm", advanced_settings=SETTINGS)
    await routes_mod.stream_speech(data, db=None)

    assert backend.calls[0]["options"] == SETTINGS
