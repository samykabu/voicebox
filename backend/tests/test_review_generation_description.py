"""Retry and regenerate replay the voice description that applied (review finding I4, FR-015).

``POST /generate`` stores the request's ``voice_description`` on the generation row, trimmed,
but only when the resolved engine declares ``supports_voice_design``; every other engine
stores null. Retry and regenerate pass the stored value back to ``run_generation`` as
``voice_description``, so a designed voice keeps its description. A null stored value
leaves the designed profile's ``design_prompt`` fallback (FR-015a) in charge, exactly as
before, and a row migrated from an older database (null column) replays as it always did.

Every backend, model and queue call is faked; nothing loads weights.
"""

from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.services import generation as generation_service

DESCRIPTION = "A warm, low voice with a slight rasp"
DESIGN_PROMPT = "A bright, young narrator"


# --- schema and migration ------------------------------------------------------


def test_generation_model_declares_a_nullable_voice_description_column() -> None:
    from backend.database import Generation

    column = Generation.__table__.c.get("voice_description")

    assert column is not None
    assert column.nullable is True


# The generations table as it stood before this column (every column the migrations add
# before it, so only voice_description is missing).
_OLD_GENERATIONS_TABLE = """
CREATE TABLE generations (
    id VARCHAR PRIMARY KEY,
    profile_id VARCHAR NOT NULL,
    text TEXT NOT NULL,
    language VARCHAR,
    audio_path VARCHAR,
    duration FLOAT,
    seed INTEGER,
    instruct TEXT,
    engine VARCHAR DEFAULT 'qwen',
    model_size VARCHAR,
    status VARCHAR DEFAULT 'completed',
    error TEXT,
    is_favorited BOOLEAN DEFAULT 0,
    source VARCHAR NOT NULL DEFAULT 'manual',
    created_at DATETIME
)
"""


def _generation_columns(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("generations")}


def test_migration_adds_the_column_to_an_old_database_idempotently(tmp_path) -> None:
    from backend.database.migrations import run_migrations

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.connect() as conn:
        conn.execute(text(_OLD_GENERATIONS_TABLE))
        conn.execute(
            text(
                "INSERT INTO generations (id, profile_id, text, language, instruct, engine, status) "
                "VALUES ('old-1', 'p1', 'Hello.', 'en', 'calm', 'voxcpm', 'completed')"
            )
        )
        conn.commit()
    assert "voice_description" not in _generation_columns(engine)

    run_migrations(engine)
    run_migrations(engine)  # a second startup must be a no-op, not a duplicate-column error

    assert "voice_description" in _generation_columns(engine)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT instruct, voice_description FROM generations WHERE id = 'old-1'")).one()
    assert row == ("calm", None)
    engine.dispose()


@pytest.mark.asyncio
async def test_history_create_generation_persists_the_description(tmp_path) -> None:
    from backend.database import Base, Generation
    from backend.services import history

    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        await history.create_generation(
            profile_id="p1",
            text="Hello.",
            language="en",
            audio_path="",
            duration=0,
            seed=None,
            db=db,
            generation_id="g-desc",
            status="generating",
            engine="voxcpm",
            voice_description=DESCRIPTION,
        )
        await history.create_generation(
            profile_id="p1",
            text="Hello.",
            language="en",
            audio_path="",
            duration=0,
            seed=None,
            db=db,
            generation_id="g-none",
            status="generating",
            engine="kokoro",
        )

        assert db.get(Generation, "g-desc").voice_description == DESCRIPTION
        assert db.get(Generation, "g-none").voice_description is None
    finally:
        db.close()
        engine.dispose()


# --- which value is stored ----------------------------------------------------


@pytest.mark.parametrize(
    ("engine", "raw", "stored"),
    [
        ("voxcpm", DESCRIPTION, DESCRIPTION),
        ("voxcpm", f"  {DESCRIPTION}\n", DESCRIPTION),
        ("voxcpm", "   ", None),
        ("voxcpm", None, None),
        ("qwen", DESCRIPTION, None),
        ("kokoro", DESCRIPTION, None),
        ("chatterbox", DESCRIPTION, None),
        ("not_an_engine", DESCRIPTION, None),
    ],
)
def test_stored_description_only_for_voice_design_engines(engine, raw, stored) -> None:
    assert generation_service.stored_voice_description(engine, raw) == stored


@pytest.fixture
def generate_route(monkeypatch: pytest.MonkeyPatch):
    """generate_speech with the profile, history, queue and availability faked."""
    from backend.routes import generations as routes_mod

    state = SimpleNamespace(
        created={},
        run={},
        profile=SimpleNamespace(default_engine=None, preset_engine=None, personality=None, effects_chain=None),
    )

    async def fake_get_profile(*_a, **_k):
        return state.profile

    async def fake_create_generation(**kwargs):
        state.created.update(kwargs)
        return SimpleNamespace(id=kwargs["generation_id"])

    def fake_run_generation(**kwargs):
        state.run.update(kwargs)
        return "job"

    class FakeQuery:
        def filter_by(self, **_k):
            return self

        def first(self):
            return None

    state.db = SimpleNamespace(query=lambda *_a: FakeQuery())
    monkeypatch.setattr(routes_mod.profiles, "get_profile", fake_get_profile)
    monkeypatch.setattr(routes_mod.profiles, "validate_profile_engine", lambda *_a, **_k: None)
    monkeypatch.setattr(routes_mod, "_require_available_engine", lambda _engine: None)
    monkeypatch.setattr(routes_mod.history, "create_generation", fake_create_generation)
    monkeypatch.setattr(routes_mod, "run_generation", fake_run_generation)
    monkeypatch.setattr(routes_mod, "enqueue_generation", lambda *_a, **_k: None)
    state.routes = routes_mod
    return state


@pytest.mark.asyncio
async def test_generate_with_voxcpm_stores_the_trimmed_description(generate_route) -> None:
    data = models.GenerationRequest(
        profile_id="p1", text="Hello.", engine="voxcpm", instruct="slowly", voice_description=f"  {DESCRIPTION} "
    )

    await generate_route.routes.generate_speech(data, db=generate_route.db)

    assert generate_route.created["voice_description"] == DESCRIPTION
    assert generate_route.created["instruct"] == "slowly"  # instruct is not overloaded
    assert generate_route.run["voice_description"] == f"  {DESCRIPTION} "  # the live run is unchanged


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["qwen", "kokoro", "luxtts"])
async def test_generate_with_a_non_voice_design_engine_stores_null(generate_route, engine) -> None:
    data = models.GenerationRequest(profile_id="p1", text="Hello.", engine=engine, voice_description=DESCRIPTION)

    await generate_route.routes.generate_speech(data, db=generate_route.db)

    assert "voice_description" in generate_route.created
    assert generate_route.created["voice_description"] is None


@pytest.mark.asyncio
async def test_generate_resolving_voxcpm_from_the_profile_stores_the_description(generate_route) -> None:
    generate_route.profile.default_engine = "voxcpm"
    data = models.GenerationRequest(profile_id="p1", text="Hello.", engine=None, voice_description=DESCRIPTION)

    await generate_route.routes.generate_speech(data, db=generate_route.db)

    assert generate_route.created["engine"] == "voxcpm"
    assert generate_route.created["voice_description"] == DESCRIPTION


# --- retry and regenerate replay it ---------------------------------------------


def _row(status: str, *, engine: str = "voxcpm", **extra):
    values = dict(
        id="gen-1",
        profile_id="p1",
        text="Hello there.",
        language="en",
        audio_path="generations/gen-1.wav",
        duration=1.5,
        seed=7,
        instruct="slowly",
        engine=engine,
        model_size=None,
        status=status,
        error=None,
        is_favorited=False,
        source="manual",
        created_at=datetime(2026, 9, 23),
    )
    values.update(extra)
    return SimpleNamespace(**values)


@pytest.fixture
def replay_route(monkeypatch: pytest.MonkeyPatch):
    """retry_generation / regenerate_generation over one stored row; captures run_generation kwargs."""
    from backend.routes import generations as routes_mod

    state = SimpleNamespace(row=None, run={})

    def fake_run_generation(**kwargs):
        state.run.update(kwargs)
        return "job"

    class FakeQuery:
        def filter_by(self, **_k):
            return self

        def first(self):
            return state.row

    state.db = SimpleNamespace(query=lambda *_a: FakeQuery(), commit=lambda: None, refresh=lambda _o: None)
    monkeypatch.setattr(routes_mod, "_require_available_engine", lambda _engine: None)
    monkeypatch.setattr(routes_mod, "run_generation", fake_run_generation)
    monkeypatch.setattr(routes_mod, "enqueue_generation", lambda *_a, **_k: None)
    monkeypatch.setattr(routes_mod, "get_task_manager", lambda: SimpleNamespace(start_generation=lambda **_k: None))

    async def call(mode: str):
        handler = routes_mod.retry_generation if mode == "retry" else routes_mod.regenerate_generation
        return await handler("gen-1", db=state.db)

    state.call = call
    return state


_MODES = [("retry", "failed"), ("regenerate", "completed")]


@pytest.mark.asyncio
@pytest.mark.parametrize(("mode", "status"), _MODES)
async def test_replay_passes_the_stored_description(replay_route, mode, status) -> None:
    replay_route.row = _row(status, voice_description=DESCRIPTION)

    await replay_route.call(mode)

    assert replay_route.run["mode"] == mode
    assert replay_route.run["voice_description"] == DESCRIPTION
    assert replay_route.run["instruct"] == "slowly"


@pytest.mark.asyncio
@pytest.mark.parametrize(("mode", "status"), _MODES)
@pytest.mark.parametrize("old_row", [True, False], ids=["attribute-missing", "column-null"])
async def test_replay_of_an_old_row_passes_no_description(replay_route, mode, status, old_row) -> None:
    replay_route.row = _row(status, engine="qwen") if old_row else _row(status, engine="qwen", voice_description=None)

    await replay_route.call(mode)

    assert replay_route.run.get("voice_description") is None
    assert replay_route.run["instruct"] == "slowly"
    assert replay_route.run["engine"] == "qwen"


# --- end to end through run_generation: what the backend receives ----------------


class _RecordingBackend:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def is_loaded(self) -> bool:
        return True

    async def generate(self, text, voice_prompt, language="en", seed=None, instruct=None, options=None):
        self.calls.append({"instruct": instruct, "voice_prompt": voice_prompt})
        return np.zeros(2400, dtype=np.float32), 24000


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch):
    """run_generation with every collaborator faked; ``voice_prompt`` is settable."""
    import backend.backends as backends_pkg

    state = SimpleNamespace(backend=_RecordingBackend(), voice_prompt={}, statuses=[])

    class FakeSession:
        def close(self) -> None:
            pass

    def fake_get_db():
        yield FakeSession()

    async def fake_update_status(generation_id, status, db, **kwargs):
        state.statuses.append((status, kwargs.get("error")))

    async def fake_voice_prompt(*_a, **_k):
        return state.voice_prompt

    async def fake_load(*_a, **_k):
        return None

    monkeypatch.setattr(generation_service, "get_db", fake_get_db)
    monkeypatch.setattr(generation_service.history, "update_generation_status", fake_update_status)
    monkeypatch.setattr(generation_service.profiles, "create_voice_prompt_for_profile", fake_voice_prompt)
    monkeypatch.setattr(generation_service.pronunciation, "apply_pronunciations", lambda t, *_a, **_k: (t, []))
    monkeypatch.setattr(generation_service, "_save_retry", lambda **_k: "generations/fake.wav")
    monkeypatch.setattr(generation_service, "_save_regenerate", lambda **_k: "generations/fake.wav")
    monkeypatch.setattr(backends_pkg, "get_tts_backend_for_engine", lambda _engine: state.backend)
    monkeypatch.setattr(backends_pkg, "load_engine_model", fake_load)
    return state


_DESIGNED_PROMPT = {"voice_type": "designed", "design_prompt": DESIGN_PROMPT}


@pytest.mark.asyncio
@pytest.mark.parametrize(("mode", "status"), _MODES)
async def test_replayed_description_reaches_the_backend_over_the_design_prompt(
    replay_route, service, mode, status
) -> None:
    replay_route.row = _row(status, voice_description=DESCRIPTION)
    service.voice_prompt = _DESIGNED_PROMPT
    await replay_route.call(mode)

    await generation_service.run_generation(**replay_route.run)

    assert service.statuses[-1] == ("completed", None), service.statuses
    assert service.backend.calls[0]["instruct"] == DESCRIPTION


@pytest.mark.asyncio
@pytest.mark.parametrize(("mode", "status"), _MODES)
async def test_designed_profile_without_a_stored_description_falls_back_to_its_design_prompt(
    replay_route, service, mode, status
) -> None:
    replay_route.row = _row(status, voice_description=None)
    service.voice_prompt = _DESIGNED_PROMPT
    await replay_route.call(mode)

    await generation_service.run_generation(**replay_route.run)

    assert service.statuses[-1] == ("completed", None), service.statuses
    assert service.backend.calls[0]["instruct"] == DESIGN_PROMPT
