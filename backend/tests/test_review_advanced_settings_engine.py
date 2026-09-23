"""Advanced settings are checked against the engine the route resolves (review finding S1, FR-010).

With ``"engine": null`` the request does not name an engine, so ``GenerationRequest`` cannot
know which settings apply: it used to assume qwen, which rejected valid VoxCPM2 settings sent
for a profile whose default engine is voxcpm. The validator now skips the name and bounds
check when ``engine`` is None, and ``/generate`` and ``/generate/stream`` run the same check,
with the same messages, after resolving the engine (request, then the profile's default).
An explicit engine is validated by the model exactly as before.

Every profile, backend, history and queue call is faked; nothing loads weights.
"""

from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import models

BASE = {"profile_id": "p1", "text": "Hello."}


class _OptionsBackend:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def is_loaded(self) -> bool:
        return True

    async def generate(self, text, voice_prompt, language="en", seed=None, instruct=None, options=None):
        self.calls.append({"options": options})
        return np.zeros(2400, dtype=np.float32), 24000


@pytest.fixture
def app_state(monkeypatch: pytest.MonkeyPatch):
    """The generations router over a fake profile whose ``default_engine`` is settable."""
    import backend.backends as backends_pkg
    import backend.routes.generations as routes_mod
    from backend.database import get_db

    state = SimpleNamespace(
        profile=SimpleNamespace(
            id="p1",
            default_engine="voxcpm",
            preset_engine=None,
            personality=None,
            effects_chain=None,
        ),
        created={},
        run={},
        backend=_OptionsBackend(),
    )

    async def fake_get_profile(*_a, **_k):
        return state.profile

    async def fake_create_generation(**kwargs):
        state.created.update(kwargs)
        return models.GenerationResponse(
            id=kwargs["generation_id"],
            profile_id=kwargs["profile_id"],
            text=kwargs["text"],
            language=kwargs["language"],
            engine=kwargs["engine"],
            status="generating",
            created_at=datetime(2026, 9, 23),
        )

    def fake_run_generation(**kwargs):
        state.run.update(kwargs)
        return "job"

    async def noop(*_a, **_k):
        return None

    async def fake_voice_prompt(*_a, **_k):
        return {}

    monkeypatch.setattr(routes_mod.profiles, "get_profile", fake_get_profile)
    monkeypatch.setattr(routes_mod.profiles, "validate_profile_engine", lambda *_a, **_k: None)
    monkeypatch.setattr(routes_mod.profiles, "create_voice_prompt_for_profile", fake_voice_prompt)
    monkeypatch.setattr(routes_mod.pronunciation, "apply_pronunciations", lambda t, *_a, **_k: (t, []))
    monkeypatch.setattr(routes_mod, "_require_available_engine", lambda _engine: None)
    monkeypatch.setattr(routes_mod.history, "create_generation", fake_create_generation)
    monkeypatch.setattr(routes_mod, "run_generation", fake_run_generation)
    monkeypatch.setattr(routes_mod, "enqueue_generation", lambda *_a, **_k: None)
    monkeypatch.setattr(routes_mod, "get_task_manager", lambda: SimpleNamespace(start_generation=lambda **_k: None))
    monkeypatch.setattr(backends_pkg, "get_tts_backend_for_engine", lambda _engine: state.backend)
    monkeypatch.setattr(backends_pkg, "ensure_model_cached_or_raise", noop)
    monkeypatch.setattr(backends_pkg, "load_engine_model", noop)

    class FakeQuery:
        def filter_by(self, **_k):
            return self

        def first(self):
            return None

    fake_db = SimpleNamespace(query=lambda *_a: FakeQuery())
    app = FastAPI()
    app.include_router(routes_mod.router)
    app.dependency_overrides[get_db] = lambda: fake_db
    state.client = TestClient(app, raise_server_exceptions=False)
    return state


def _detail(response) -> str:
    return str(response.json().get("detail"))


# --- the model no longer guesses qwen for a null engine ---------------------------


def test_null_engine_defers_the_check_to_the_route() -> None:
    request = models.GenerationRequest(**BASE, engine=None, advanced_settings={"cfg_value": 9.0, "bogus": 1.0})

    assert request.advanced_settings == {"cfg_value": 9.0, "bogus": 1.0}


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"cfg_value": 9.0}, "Advanced setting 'cfg_value' must be between"),
        ({"bogus": 1.0}, "Engine 'voxcpm' does not declare an advanced setting named 'bogus'"),
    ],
)
def test_the_shared_check_returns_the_validator_messages(settings, message) -> None:
    assert message in models.advanced_settings_error("voxcpm", settings)
    assert models.advanced_settings_error("voxcpm", {"cfg_value": 2.0}) is None
    assert models.advanced_settings_error("voxcpm", None) is None


# --- /generate --------------------------------------------------------------------


def test_null_engine_on_a_voxcpm_profile_accepts_voxcpm_settings(app_state) -> None:
    response = app_state.client.post(
        "/generate", json={**BASE, "engine": None, "advanced_settings": {"cfg_value": 2.0}}
    )

    assert response.status_code == 200, response.text
    assert app_state.run["engine"] == "voxcpm"
    assert app_state.run["advanced_settings"] == {"cfg_value": 2.0}


def test_null_engine_on_a_voxcpm_profile_rejects_out_of_bounds_values(app_state) -> None:
    response = app_state.client.post(
        "/generate", json={**BASE, "engine": None, "advanced_settings": {"cfg_value": 9.0}}
    )

    assert response.status_code == 422, response.text
    assert "Advanced setting 'cfg_value' must be between" in _detail(response)
    assert "for engine 'voxcpm'" in _detail(response)
    assert app_state.created == {}
    assert app_state.run == {}


def test_null_engine_on_a_voxcpm_profile_rejects_an_unknown_setting(app_state) -> None:
    response = app_state.client.post("/generate", json={**BASE, "engine": None, "advanced_settings": {"bogus": 1.0}})

    assert response.status_code == 422, response.text
    assert "Engine 'voxcpm' does not declare an advanced setting named 'bogus'" in _detail(response)
    assert app_state.created == {}
    assert app_state.run == {}


@pytest.mark.parametrize("default_engine", ["qwen", None])
def test_null_engine_on_a_qwen_profile_still_rejects_any_setting(app_state, default_engine) -> None:
    app_state.profile.default_engine = default_engine

    response = app_state.client.post(
        "/generate", json={**BASE, "engine": None, "advanced_settings": {"cfg_value": 2.0}}
    )

    assert response.status_code == 422, response.text
    assert "Engine 'qwen' does not declare an advanced setting named 'cfg_value'" in _detail(response)
    assert app_state.created == {}
    assert app_state.run == {}


def test_null_engine_without_settings_is_unaffected(app_state) -> None:
    app_state.profile.default_engine = "qwen"

    response = app_state.client.post("/generate", json={**BASE, "engine": None})

    assert response.status_code == 200, response.text
    assert app_state.run["engine"] == "qwen"


# --- explicit engines: unchanged ---------------------------------------------------


def test_explicit_voxcpm_is_accepted_whatever_the_profile_default(app_state) -> None:
    app_state.profile.default_engine = "qwen"

    response = app_state.client.post(
        "/generate", json={**BASE, "engine": "voxcpm", "advanced_settings": {"cfg_value": 2.0}}
    )

    assert response.status_code == 200, response.text
    assert app_state.run["advanced_settings"] == {"cfg_value": 2.0}


@pytest.mark.parametrize(
    "body",
    [
        {"engine": "voxcpm", "advanced_settings": {"cfg_value": 9.0}},
        {"engine": "voxcpm", "advanced_settings": {"bogus": 1.0}},
        {"engine": "kokoro", "advanced_settings": {"cfg_value": 2.0}},
        {"advanced_settings": {"cfg_value": 2.0}},  # omitted engine defaults to qwen in the schema
    ],
)
def test_explicit_engine_is_still_rejected_by_the_schema(app_state, body) -> None:
    response = app_state.client.post("/generate", json={**BASE, **body})

    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], list)  # the pydantic validation shape, as before
    assert app_state.created == {}
    assert app_state.run == {}


# --- /generate/stream --------------------------------------------------------------


def test_stream_null_engine_on_a_voxcpm_profile_passes_the_settings(app_state) -> None:
    response = app_state.client.post(
        "/generate/stream", json={**BASE, "engine": None, "advanced_settings": {"cfg_value": 2.0}}
    )

    assert response.status_code == 200, response.text
    assert app_state.backend.calls[0]["options"] == {"cfg_value": 2.0}


@pytest.mark.parametrize(
    ("default_engine", "settings", "message"),
    [
        ("voxcpm", {"cfg_value": 9.0}, "Advanced setting 'cfg_value' must be between"),
        ("voxcpm", {"bogus": 1.0}, "Engine 'voxcpm' does not declare an advanced setting named 'bogus'"),
        ("qwen", {"cfg_value": 2.0}, "Engine 'qwen' does not declare an advanced setting named 'cfg_value'"),
    ],
)
def test_stream_null_engine_rejects_invalid_settings_before_any_load(
    app_state, default_engine, settings, message
) -> None:
    app_state.profile.default_engine = default_engine

    response = app_state.client.post("/generate/stream", json={**BASE, "engine": None, "advanced_settings": settings})

    assert response.status_code == 422, response.text
    assert message in _detail(response)
    assert app_state.backend.calls == []
