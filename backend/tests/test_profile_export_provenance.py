"""
T052 / FR-027: profile export and import preserve provenance.

The export manifest carries the profile's voice type, its written design
prompt and its default engine (plus the preset engine and voice id for
built-in voices), and import restores them instead of rebuilding every
profile as a cloned one. A designed or preset profile needs no audio
samples to be exported; a cloned profile without samples still cannot be.
"""

import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import config
from backend.database import Base, ProfileSample as DBProfileSample, VoiceProfile as DBVoiceProfile
from backend.models import VoiceProfileCreate
from backend.services.export_import import export_profile_to_zip, import_profile_from_zip
from backend.services.profiles import add_profile_sample, create_profile


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
    """Point the storage root (profiles dir, storage paths) at a temp dir."""
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setattr(config, "_data_dir", root.resolve())
    return root


@pytest.fixture
def reference_wav(tmp_path):
    """A 3-second tone that passes reference-audio validation."""
    sr = 24000
    t = np.linspace(0, 3.0, int(sr * 3.0), endpoint=False)
    audio = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    path = tmp_path / "ref.wav"
    sf.write(str(path), audio, sr)
    return path


def _manifest(zip_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return json.loads(zf.read("manifest.json"))


def _db_profile(db, profile_id):
    return db.query(DBVoiceProfile).filter_by(id=profile_id).first()


def _sample_count(db, profile_id):
    return db.query(DBProfileSample).filter_by(profile_id=profile_id).count()


async def _cloned_with_sample(db, reference_wav, name="Cloned Voice"):
    profile = await create_profile(
        VoiceProfileCreate(name=name, language="en", voice_type="cloned", default_engine="voxcpm"),
        db,
    )
    await add_profile_sample(profile.id, str(reference_wav), "Hello there.", db)
    return profile


async def _designed(db, name="Designed Voice"):
    return await create_profile(
        VoiceProfileCreate(
            name=name,
            language="en",
            voice_type="designed",
            design_prompt="A calm, low-pitched narrator with a slight rasp.",
            default_engine="voxcpm",
        ),
        db,
    )


def _zip(manifest: dict, samples: dict, sample_files: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("samples.json", json.dumps(samples))
        for name, path in (sample_files or {}).items():
            zf.write(path, f"samples/{name}")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_export_manifest_contains_provenance_keys(test_db, data_dir, reference_wav):
    profile = await _cloned_with_sample(test_db, reference_wav)

    manifest = _manifest(export_profile_to_zip(profile.id, test_db))

    exported = manifest["profile"]
    assert exported["voice_type"] == "cloned"
    assert exported["default_engine"] == "voxcpm"
    assert "design_prompt" in exported
    assert exported["design_prompt"] is None


@pytest.mark.asyncio
async def test_cloned_round_trip_preserves_voice_type_and_default_engine(test_db, data_dir, reference_wav):
    profile = await _cloned_with_sample(test_db, reference_wav)
    zip_bytes = export_profile_to_zip(profile.id, test_db)

    imported = await import_profile_from_zip(zip_bytes, test_db)

    assert imported.id != profile.id
    row = _db_profile(test_db, imported.id)
    assert row.voice_type == "cloned"
    assert row.default_engine == "voxcpm"
    assert row.design_prompt is None
    assert _sample_count(test_db, row.id) == 1


@pytest.mark.asyncio
async def test_designed_profile_without_samples_is_exportable(test_db, data_dir):
    profile = await _designed(test_db)

    manifest = _manifest(export_profile_to_zip(profile.id, test_db))

    exported = manifest["profile"]
    assert exported["voice_type"] == "designed"
    assert exported["design_prompt"] == "A calm, low-pitched narrator with a slight rasp."
    assert exported["default_engine"] == "voxcpm"


@pytest.mark.asyncio
async def test_designed_round_trip_restores_design_prompt_and_default_engine(test_db, data_dir):
    profile = await _designed(test_db)
    zip_bytes = export_profile_to_zip(profile.id, test_db)

    imported = await import_profile_from_zip(zip_bytes, test_db)

    row = _db_profile(test_db, imported.id)
    assert row.voice_type == "designed"
    assert row.design_prompt == "A calm, low-pitched narrator with a slight rasp."
    assert row.default_engine == "voxcpm"
    assert _sample_count(test_db, row.id) == 0
    assert imported.voice_type == "designed"


@pytest.mark.asyncio
async def test_preset_round_trip_restores_preset_fields(test_db, data_dir):
    profile = await create_profile(
        VoiceProfileCreate(
            name="Preset Voice",
            language="en",
            voice_type="preset",
            preset_engine="kokoro",
            preset_voice_id="af_alloy",
        ),
        test_db,
    )
    zip_bytes = export_profile_to_zip(profile.id, test_db)
    exported = _manifest(zip_bytes)["profile"]
    assert exported["voice_type"] == "preset"
    assert exported["preset_engine"] == "kokoro"
    assert exported["preset_voice_id"] == "af_alloy"
    assert exported["default_engine"] == "kokoro"

    imported = await import_profile_from_zip(zip_bytes, test_db)

    row = _db_profile(test_db, imported.id)
    assert row.voice_type == "preset"
    assert row.preset_engine == "kokoro"
    assert row.preset_voice_id == "af_alloy"
    assert row.default_engine == "kokoro"


@pytest.mark.asyncio
async def test_cloned_profile_without_samples_still_refuses_export(test_db, data_dir):
    profile = await create_profile(VoiceProfileCreate(name="Empty Clone", language="en"), test_db)

    with pytest.raises(ValueError, match="has no samples"):
        export_profile_to_zip(profile.id, test_db)


@pytest.mark.asyncio
async def test_legacy_1_0_manifest_imports_as_cloned(test_db, data_dir, reference_wav):
    manifest = {
        "version": "1.0",
        "profile": {"name": "Legacy Voice", "description": "old export", "language": "en"},
        "has_avatar": False,
    }
    zip_bytes = _zip(manifest, {"legacy.wav": "Hello there."}, {"legacy.wav": reference_wav})

    imported = await import_profile_from_zip(zip_bytes, test_db)

    row = _db_profile(test_db, imported.id)
    assert row.name == "Legacy Voice"
    assert row.voice_type == "cloned"
    assert row.default_engine is None
    assert row.design_prompt is None
    assert _sample_count(test_db, row.id) == 1


@pytest.mark.asyncio
async def test_import_rejects_designed_manifest_with_blank_prompt(test_db, data_dir):
    manifest = {
        "version": "1.1",
        "profile": {
            "name": "Broken Design",
            "description": None,
            "language": "en",
            "voice_type": "designed",
            "design_prompt": "   ",
            "default_engine": "voxcpm",
        },
        "has_avatar": False,
    }

    with pytest.raises(ValueError, match="Designed profiles require a design_prompt"):
        await import_profile_from_zip(_zip(manifest, {}), test_db)

    assert test_db.query(DBVoiceProfile).filter_by(name="Broken Design").first() is None
