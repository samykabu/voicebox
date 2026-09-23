"""A second engine that fails to load does not break the engine already loaded (N4).

Documents today's behaviour of ``services.generation.run_generation`` when a model
load raises (for example CUDA out of memory while VoxCPM2 loads next to a loaded
engine):

* the generation is marked ``failed`` with the load error as its message;
* the failing engine is left unloaded, and it never generates;
* the engine that was already loaded keeps its model and generates again without a
  reload; nothing unloads it automatically.

The real ``run_generation``, ``get_tts_backend_for_engine`` and ``load_engine_model``
run. Fake backends are placed in the ``_tts_backends`` cache, so no model, GPU or
download is involved. History, profiles, pronunciation, the DB session, the audio
save and the task manager are faked at the seams ``run_generation`` uses.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from backend.services import generation as generation_service

LOADED_ENGINE = "kokoro"
FAILING_ENGINE = "voxcpm"
LOAD_ERROR = "CUDA out of memory. Tried to allocate 2.00 GiB"


class FakeBackend:
    """A TTS backend that records loads, unloads and generate calls."""

    def __init__(self, load_error: BaseException | None = None) -> None:
        self.load_error = load_error
        self.model = None
        self.load_calls = 0
        self.unload_calls = 0
        self.generate_calls: list[str] = []

    def is_loaded(self) -> bool:
        return self.model is not None

    async def load_model(self, *_args, **_kwargs) -> None:
        self.load_calls += 1
        if self.is_loaded():
            return
        if self.load_error is not None:
            raise self.load_error
        self.model = object()

    def unload_model(self) -> None:
        self.unload_calls += 1
        self.model = None

    async def generate(self, text, voice_prompt, language="en", seed=None, instruct=None):
        if not self.is_loaded():
            raise AssertionError("generate called on a backend that is not loaded")
        self.generate_calls.append(text)
        return np.zeros(2400, dtype=np.float32), 24000


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch):
    """Real run_generation and load_engine_model over two fake cached backends."""
    import backend.backends as backends_pkg

    statuses: dict[str, list[tuple[str, str | None]]] = {}
    completed_tasks: list[str] = []

    class FakeSession:
        def close(self) -> None:
            pass

    def fake_get_db():
        yield FakeSession()

    async def fake_update_status(generation_id, status, db, **kwargs):
        statuses.setdefault(generation_id, []).append((status, kwargs.get("error")))

    async def fake_voice_prompt(*_a, **_k):
        return {}

    fake_task_manager = SimpleNamespace(complete_generation=completed_tasks.append)

    monkeypatch.setattr(generation_service, "get_db", fake_get_db)
    monkeypatch.setattr(generation_service, "get_task_manager", lambda: fake_task_manager)
    monkeypatch.setattr(generation_service.history, "update_generation_status", fake_update_status)
    monkeypatch.setattr(generation_service.profiles, "create_voice_prompt_for_profile", fake_voice_prompt)
    monkeypatch.setattr(generation_service.pronunciation, "apply_pronunciations", lambda text, *_a, **_k: (text, []))
    monkeypatch.setattr(generation_service, "_save_generate", lambda **_k: "generations/fake.wav")
    monkeypatch.setattr(generation_service, "_notify_speak_end", lambda *_a, **_k: None)

    loaded = FakeBackend()
    failing = FakeBackend(load_error=RuntimeError(LOAD_ERROR))
    # Registered in the real cache, so the real get_tts_backend_for_engine and
    # load_engine_model resolve them; monkeypatch restores the cache afterwards.
    monkeypatch.setitem(backends_pkg._tts_backends, LOADED_ENGINE, loaded)
    monkeypatch.setitem(backends_pkg._tts_backends, FAILING_ENGINE, failing)

    return SimpleNamespace(
        loaded=loaded,
        failing=failing,
        statuses=statuses,
        completed_tasks=completed_tasks,
        backends_pkg=backends_pkg,
    )


async def _run(generation_id: str, engine: str, text: str) -> None:
    await generation_service.run_generation(
        generation_id=generation_id,
        profile_id="profile-1",
        text=text,
        language="en",
        engine=engine,
        model_size="default",
        seed=7,
        mode="generate",
    )


def test_harness_uses_the_real_backend_seams(harness) -> None:
    """Guard: the test exercises the real registry functions, not patched stand-ins."""
    import inspect

    assert inspect.getmodule(harness.backends_pkg.load_engine_model) is harness.backends_pkg
    assert inspect.getmodule(harness.backends_pkg.get_tts_backend_for_engine) is harness.backends_pkg
    assert harness.backends_pkg.get_tts_backend_for_engine(LOADED_ENGINE) is harness.loaded
    assert harness.backends_pkg.get_tts_backend_for_engine(FAILING_ENGINE) is harness.failing


@pytest.mark.asyncio
async def test_second_engine_load_failure_marks_generation_failed_and_keeps_first_engine(harness) -> None:
    loaded, failing, statuses = harness.loaded, harness.failing, harness.statuses

    # 1. The first engine loads and generates.
    await _run("gen-a1", LOADED_ENGINE, "First line.")

    assert statuses["gen-a1"] == [("loading_model", None), ("generating", None), ("completed", None)]
    assert loaded.is_loaded()
    assert loaded.load_calls == 1
    assert loaded.generate_calls == ["First line."]

    # 2. The second engine raises while loading: the generation fails with that error.
    await _run("gen-b1", FAILING_ENGINE, "Second line.")

    assert statuses["gen-b1"][0] == ("loading_model", None)
    final_status, error = statuses["gen-b1"][-1]
    assert final_status == "failed"
    assert error is not None
    assert LOAD_ERROR in error
    assert "generating" not in [status for status, _ in statuses["gen-b1"]]
    assert "completed" not in [status for status, _ in statuses["gen-b1"]]
    # Nothing is left half-set on the failing engine.
    assert failing.load_calls == 1
    assert not failing.is_loaded()
    assert failing.model is None
    assert failing.generate_calls == []
    # The failure did not touch the engine that was already loaded.
    assert loaded.is_loaded()
    assert loaded.unload_calls == 0
    # The task manager is still released for the failed generation.
    assert harness.completed_tasks == ["gen-a1", "gen-b1"]

    # 3. The first engine generates again from its still-loaded model.
    await _run("gen-a2", LOADED_ENGINE, "Third line.")

    # Already loaded, so no "loading_model" step this time.
    assert statuses["gen-a2"] == [("generating", None), ("completed", None)]
    # load_engine_model is still called, but the backend is already loaded: no new model.
    assert loaded.load_calls == 2
    assert loaded.is_loaded()
    assert loaded.generate_calls == ["First line.", "Third line."]
    # run_generation never unloads the other engine (there is no automatic unloading today).
    assert loaded.unload_calls == 0
    assert failing.unload_calls == 0
    assert harness.completed_tasks == ["gen-a1", "gen-b1", "gen-a2"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "load_error",
    [MemoryError("not enough memory to load VoxCPM2"), RuntimeError(LOAD_ERROR)],
    ids=["MemoryError", "RuntimeError-cuda-oom"],
)
async def test_load_failure_error_text_reaches_the_generation(harness, load_error) -> None:
    harness.failing.load_error = load_error

    await _run("gen-b", FAILING_ENGINE, "Hello.")

    final_status, error = harness.statuses["gen-b"][-1]
    assert final_status == "failed"
    assert error == str(load_error)
    assert not harness.failing.is_loaded()

    # A retry of the failing engine fails the same way; it does not get stuck half-loaded.
    await _run("gen-b-retry", FAILING_ENGINE, "Hello.")

    assert harness.statuses["gen-b-retry"][0] == ("loading_model", None)
    assert harness.statuses["gen-b-retry"][-1] == ("failed", str(load_error))
    assert harness.failing.load_calls == 2
    assert harness.failing.generate_calls == []
