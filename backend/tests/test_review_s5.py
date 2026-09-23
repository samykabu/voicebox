"""Review follow-up S5: a generation archive carries its ``engine`` and ``model_size``.

The 1.1 generation manifest exports ``engine`` and ``model_size`` next to
``voice_description``. Import restores them only after checking them against the
TTS registry (``backend.backends.TTS_ENGINES`` and ``get_tts_model_configs``):

- a 1.0 manifest, a missing engine or an unknown engine leaves ``engine`` unset, so the
  column default (``"qwen"``) applies, exactly as import behaved before, and leaves
  ``model_size`` null;
- a known engine is kept; for an engine with several sizes the ``model_size`` must be one
  of that engine's sizes, otherwise the engine's registry default is stored; an engine
  without sizes stores null, as ``POST /generate`` does;
- every rejected manifest value is logged as a warning.

So an imported VoxCPM2 voice-design generation regenerates on VoxCPM2 with its
restored voice description, not on Qwen.
"""

import io
import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import config
from backend.backends import get_default_model_size
from backend.database import Base, Generation as DBGeneration, VoiceProfile as DBVoiceProfile
from backend.services.export_import import export_generation_to_zip, import_generation_from_zip

DESCRIPTION = "A young woman, warm and bright voice"


@pytest.fixture
def test_db():
    temp_dir = tempfile.mkdtemp()
    engine = create_engine(f"sqlite:///{Path(temp_dir) / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    engine.dispose()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def data_dir(monkeypatch, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setattr(config, "_data_dir", root.resolve())
    return root


def _profile(db) -> DBVoiceProfile:
    profile = DBVoiceProfile(name="Narrator", language="en")
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _generation(db, profile, *, engine: str, model_size: str | None, voice_description: str | None = None):
    generations_dir = config.get_generations_dir()
    generations_dir.mkdir(parents=True, exist_ok=True)
    audio_path = generations_dir / "source.wav"
    audio_path.write_bytes(b"RIFF....WAVE")
    generation = DBGeneration(
        profile_id=profile.id,
        text="Hello there.",
        language="en",
        audio_path=config.to_storage_path(audio_path),
        duration=1.5,
        seed=7,
        instruct=None,
        voice_description=voice_description,
        engine=engine,
        model_size=model_size,
    )
    db.add(generation)
    db.commit()
    db.refresh(generation)
    return generation


def _manifest(zip_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return json.loads(zf.read("manifest.json"))


def _row(db, generation_id: str) -> DBGeneration:
    return db.query(DBGeneration).filter_by(id=generation_id).first()


def _archive(version: str, **generation_extra) -> bytes:
    manifest = {
        "version": version,
        "generation": {
            "id": "old-id",
            "text": "Archived text.",
            "language": "en",
            "duration": 2.0,
            "seed": None,
            "instruct": None,
            "created_at": "2026-01-01T00:00:00",
            **generation_extra,
        },
        "profile": {"id": "p", "name": "Narrator", "description": None, "language": "en"},
        "versions": [],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("audio/old-id.wav", b"RIFF....WAVE")
    return buf.getvalue()


def _column_default_engine() -> str:
    return DBGeneration.__table__.c.engine.default.arg


class TestGenerationExportEngine:
    @pytest.mark.asyncio
    async def test_voxcpm_designed_generation_round_trips(self, test_db, data_dir):
        generation = _generation(
            test_db, _profile(test_db), engine="voxcpm", model_size=None, voice_description=DESCRIPTION
        )

        zip_bytes = export_generation_to_zip(generation.id, test_db)
        exported = _manifest(zip_bytes)
        assert exported["version"] == "1.1"
        assert exported["generation"]["engine"] == "voxcpm"
        assert "model_size" in exported["generation"]
        assert exported["generation"]["model_size"] is None

        result = await import_generation_from_zip(zip_bytes, test_db)

        row = _row(test_db, result["id"])
        assert row.engine == "voxcpm"
        assert row.model_size is None
        assert row.voice_description == DESCRIPTION

    @pytest.mark.asyncio
    async def test_qwen_small_model_round_trips_with_its_size(self, test_db, data_dir):
        generation = _generation(test_db, _profile(test_db), engine="qwen", model_size="0.6B")

        zip_bytes = export_generation_to_zip(generation.id, test_db)
        assert _manifest(zip_bytes)["generation"]["model_size"] == "0.6B"

        result = await import_generation_from_zip(zip_bytes, test_db)

        row = _row(test_db, result["id"])
        assert row.engine == "qwen"
        assert row.model_size == "0.6B"

    @pytest.mark.asyncio
    async def test_legacy_manifest_without_the_keys_gets_the_column_defaults(self, test_db, data_dir, caplog):
        _profile(test_db)

        with caplog.at_level(logging.WARNING):
            result = await import_generation_from_zip(_archive("1.0"), test_db)

        row = _row(test_db, result["id"])
        assert _column_default_engine() == "qwen"
        assert row.engine == "qwen"
        assert row.model_size is None
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    @pytest.mark.asyncio
    async def test_unknown_engine_falls_back_to_the_default_with_a_warning(self, test_db, data_dir, caplog):
        _profile(test_db)

        with caplog.at_level(logging.WARNING):
            result = await import_generation_from_zip(_archive("1.1", engine="evil_engine", model_size="0.6B"), test_db)

        row = _row(test_db, result["id"])
        assert row.engine == "qwen"
        assert row.model_size is None
        assert any("evil_engine" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)

    @pytest.mark.asyncio
    async def test_non_string_engine_falls_back_to_the_default(self, test_db, data_dir):
        _profile(test_db)

        result = await import_generation_from_zip(_archive("1.1", engine=["voxcpm"], model_size=None), test_db)

        row = _row(test_db, result["id"])
        assert row.engine == "qwen"
        assert row.model_size is None

    @pytest.mark.asyncio
    async def test_known_engine_with_bogus_size_keeps_engine_and_uses_its_default_size(self, test_db, data_dir, caplog):
        _profile(test_db)

        with caplog.at_level(logging.WARNING):
            result = await import_generation_from_zip(_archive("1.1", engine="qwen", model_size="999B"), test_db)

        row = _row(test_db, result["id"])
        assert row.engine == "qwen"
        assert row.model_size == get_default_model_size("qwen")
        assert any("999B" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)

    @pytest.mark.asyncio
    async def test_known_engine_with_non_string_size_uses_its_default_size(self, test_db, data_dir):
        _profile(test_db)

        result = await import_generation_from_zip(_archive("1.1", engine="qwen", model_size=["0.6B"]), test_db)

        row = _row(test_db, result["id"])
        assert row.engine == "qwen"
        assert row.model_size == get_default_model_size("qwen")

    @pytest.mark.asyncio
    async def test_engine_without_sizes_stores_null_size(self, test_db, data_dir, caplog):
        _profile(test_db)

        with caplog.at_level(logging.WARNING):
            result = await import_generation_from_zip(
                _archive("1.1", engine="voxcpm", model_size="bogus", voice_description=DESCRIPTION), test_db
            )

        row = _row(test_db, result["id"])
        assert row.engine == "voxcpm"
        assert row.model_size is None
        assert row.voice_description == DESCRIPTION
        assert any("bogus" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)

    @pytest.mark.asyncio
    async def test_regenerate_after_import_runs_voxcpm_with_the_description(self, test_db, data_dir, monkeypatch):
        from backend.routes import generations as routes_mod

        generation = _generation(
            test_db, _profile(test_db), engine="voxcpm", model_size=None, voice_description=DESCRIPTION
        )
        result = await import_generation_from_zip(export_generation_to_zip(generation.id, test_db), test_db)

        run = {}

        def fake_run_generation(**kwargs):
            run.update(kwargs)
            return "job"

        required = []
        monkeypatch.setattr(routes_mod, "_require_available_engine", required.append)
        monkeypatch.setattr(routes_mod, "run_generation", fake_run_generation)
        monkeypatch.setattr(routes_mod, "enqueue_generation", lambda *_a, **_k: None)
        monkeypatch.setattr(routes_mod, "get_task_manager", lambda: SimpleNamespace(start_generation=lambda **_k: None))

        await routes_mod.regenerate_generation(result["id"], db=test_db)

        assert required == ["voxcpm"]
        assert run["engine"] == "voxcpm"
        assert run["model_size"] == get_default_model_size("voxcpm")
        assert run["voice_description"] == DESCRIPTION
        assert run["mode"] == "regenerate"
