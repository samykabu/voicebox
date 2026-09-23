"""Review follow-up S6: an imported ``voice_description`` is validated like the API's.

``POST /generate`` accepts ``voice_description`` only as a string of at most
``MAX_VOICE_DESCRIPTION_CHARS`` (500) characters (a longer one is a 422, never
truncated) and stores it, stripped, only for an engine with voice design
(``stored_voice_description``). Generation import applies the same rule to the
manifest value:

- a value that is not a string (a dict or a list), a blank one, or one longer than
  500 characters after stripping is stored as null, with a logged warning, and the
  import still succeeds with its audio file copied and referenced;
- the description is then kept only when the restored engine (or the column default
  ``"qwen"`` when none is restored) supports voice design.

The other manifest fields (``text``, ``language``, ``duration``, ``seed``,
``instruct``) are type-checked too, so a crafted value cannot fail the commit
and leave the copied audio file orphaned.
"""

import io
import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import config
from backend.database import Base, Generation as DBGeneration, VoiceProfile as DBVoiceProfile
from backend.models import MAX_VOICE_DESCRIPTION_CHARS, GenerationRequest
from backend.services.export_import import import_generation_from_zip

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


@pytest.fixture
def profile(test_db) -> DBVoiceProfile:
    profile = DBVoiceProfile(name="Narrator", language="en")
    test_db.add(profile)
    test_db.commit()
    test_db.refresh(profile)
    return profile


def _archive(version: str = "1.1", **generation_extra) -> bytes:
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


def _row(db, generation_id: str) -> DBGeneration:
    return db.query(DBGeneration).filter_by(id=generation_id).first()


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def _assert_audio_referenced(db, generation_id: str) -> None:
    """The copied audio file exists, the row points at it, and nothing else is in the folder."""
    row = _row(db, generation_id)
    assert row is not None
    audio = config.resolve_storage_path(row.audio_path)
    assert audio is not None
    assert audio.exists()
    assert sorted(p.name for p in config.get_generations_dir().iterdir()) == [audio.name]


def test_the_api_and_import_share_one_limit():
    field = GenerationRequest.model_fields["voice_description"]
    assert MAX_VOICE_DESCRIPTION_CHARS == 500
    assert any(getattr(m, "max_length", None) == MAX_VOICE_DESCRIPTION_CHARS for m in field.metadata)


class TestImportedVoiceDescription:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("bogus", [{"prompt": DESCRIPTION}, [DESCRIPTION], 42, True])
    async def test_non_string_description_is_stored_as_null_and_the_audio_is_kept(
        self, test_db, data_dir, profile, caplog, bogus
    ):
        with caplog.at_level(logging.WARNING):
            result = await import_generation_from_zip(_archive(engine="voxcpm", voice_description=bogus), test_db)

        row = _row(test_db, result["id"])
        assert row.voice_description is None
        assert row.engine == "voxcpm"
        _assert_audio_referenced(test_db, result["id"])
        assert any("voice_description" in m for m in _warnings(caplog))

    @pytest.mark.asyncio
    async def test_over_limit_description_is_stored_as_null_with_a_warning(self, test_db, data_dir, profile, caplog):
        with caplog.at_level(logging.WARNING):
            result = await import_generation_from_zip(
                _archive(engine="voxcpm", voice_description="x" * (MAX_VOICE_DESCRIPTION_CHARS + 1)), test_db
            )

        assert _row(test_db, result["id"]).voice_description is None
        _assert_audio_referenced(test_db, result["id"])
        assert any("voice_description" in m and "501" in m for m in _warnings(caplog))

    @pytest.mark.asyncio
    async def test_description_at_the_limit_is_kept(self, test_db, data_dir, profile, caplog):
        at_limit = "y" * MAX_VOICE_DESCRIPTION_CHARS

        with caplog.at_level(logging.WARNING):
            result = await import_generation_from_zip(_archive(engine="voxcpm", voice_description=at_limit), test_db)

        assert _row(test_db, result["id"]).voice_description == at_limit
        assert not _warnings(caplog)

    @pytest.mark.asyncio
    async def test_limit_applies_after_stripping(self, test_db, data_dir, profile):
        padded = "  " + "z" * MAX_VOICE_DESCRIPTION_CHARS + "  "

        result = await import_generation_from_zip(_archive(engine="voxcpm", voice_description=padded), test_db)

        assert _row(test_db, result["id"]).voice_description == "z" * MAX_VOICE_DESCRIPTION_CHARS

    @pytest.mark.asyncio
    @pytest.mark.parametrize("engine", ["qwen", "kokoro"])
    async def test_description_on_an_engine_without_voice_design_is_stored_as_null(
        self, test_db, data_dir, profile, caplog, engine
    ):
        with caplog.at_level(logging.WARNING):
            result = await import_generation_from_zip(_archive(engine=engine, voice_description=DESCRIPTION), test_db)

        row = _row(test_db, result["id"])
        assert row.engine == engine
        assert row.voice_description is None
        assert any("voice_description" in m for m in _warnings(caplog))

    @pytest.mark.asyncio
    async def test_description_with_no_restored_engine_uses_the_default_engine(self, test_db, data_dir, profile):
        result = await import_generation_from_zip(_archive(voice_description=DESCRIPTION), test_db)

        row = _row(test_db, result["id"])
        assert row.engine == "qwen"
        assert row.voice_description is None

    @pytest.mark.asyncio
    async def test_valid_voxcpm_description_round_trips_stripped(self, test_db, data_dir, profile, caplog):
        with caplog.at_level(logging.WARNING):
            result = await import_generation_from_zip(
                _archive(engine="voxcpm", voice_description=f"  {DESCRIPTION}\n"), test_db
            )

        row = _row(test_db, result["id"])
        assert row.engine == "voxcpm"
        assert row.voice_description == DESCRIPTION
        assert not _warnings(caplog)

    @pytest.mark.asyncio
    async def test_legacy_archive_imports_as_before(self, test_db, data_dir, profile, caplog):
        with caplog.at_level(logging.WARNING):
            result = await import_generation_from_zip(_archive("1.0", instruct="speak softly", seed=3), test_db)

        row = _row(test_db, result["id"])
        assert row.engine == "qwen"
        assert row.model_size is None
        assert row.voice_description is None
        assert row.instruct == "speak softly"
        assert row.seed == 3
        assert row.text == "Archived text."
        assert row.language == "en"
        assert row.duration == 2.0
        _assert_audio_referenced(test_db, result["id"])
        assert not _warnings(caplog)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
    async def test_whitespace_only_description_is_stored_as_null(self, test_db, data_dir, profile, blank):
        result = await import_generation_from_zip(_archive(engine="voxcpm", voice_description=blank), test_db)

        assert _row(test_db, result["id"]).voice_description is None


class TestImportedOtherFields:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("field", "bogus", "expected"),
        [
            ("instruct", {"a": 1}, None),
            ("instruct", ["slowly"], None),
            ("seed", {"a": 1}, None),
            ("seed", "7", None),
            ("seed", True, None),
            ("seed", 1.5, None),
            ("duration", {"a": 1}, None),
            ("duration", "2.0", None),
            ("duration", True, None),
            ("language", {"a": 1}, "en"),
            ("language", ["en"], "en"),
        ],
    )
    async def test_non_matching_type_gets_a_safe_fallback_and_the_audio_is_kept(
        self, test_db, data_dir, profile, caplog, field, bogus, expected
    ):
        with caplog.at_level(logging.WARNING):
            result = await import_generation_from_zip(_archive(**{field: bogus}), test_db)

        assert getattr(_row(test_db, result["id"]), field) == expected
        _assert_audio_referenced(test_db, result["id"])
        assert any(field in m for m in _warnings(caplog))

    @pytest.mark.asyncio
    async def test_integer_duration_is_kept(self, test_db, data_dir, profile):
        result = await import_generation_from_zip(_archive(duration=3), test_db)

        assert _row(test_db, result["id"]).duration == 3.0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bogus", [{"a": 1}, ["Archived text."], 42, None, "   "])
    async def test_non_string_or_blank_text_rejects_the_import_without_leaving_audio(
        self, test_db, data_dir, profile, bogus
    ):
        with pytest.raises(ValueError, match=r"generation\.text"):
            await import_generation_from_zip(_archive(text=bogus), test_db)

        assert test_db.query(DBGeneration).count() == 0
        generations_dir = config.get_generations_dir()
        assert not generations_dir.exists() or not any(generations_dir.iterdir())

    @pytest.mark.asyncio
    async def test_a_failed_commit_removes_the_copied_audio(self, test_db, data_dir, profile, monkeypatch):
        def failing_commit():
            raise RuntimeError("database is locked")

        monkeypatch.setattr(test_db, "commit", failing_commit)

        with pytest.raises(ValueError, match="database is locked"):
            await import_generation_from_zip(_archive(), test_db)

        generations_dir = config.get_generations_dir()
        assert not generations_dir.exists() or not any(generations_dir.iterdir())
