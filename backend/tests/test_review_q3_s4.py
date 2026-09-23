"""Review follow-ups Q3 and S4.

Q3: the generation export manifest carries ``voice_description`` and import
restores it. Archives written before the field existed still import, with null.

S4: the continuation prompt's temporary file is reserved on the event-loop side
before the backend hook writes it, so cancelling ``generate_chunked`` while the
hook's write is still running in a worker thread never leaks the file.
"""

import asyncio
import contextlib
import io
import json
import os
import shutil
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import config
from backend.database import Base, Generation as DBGeneration, VoiceProfile as DBVoiceProfile
from backend.services.export_import import export_generation_to_zip, import_generation_from_zip
from backend.utils.chunked_tts import generate_chunked

DESCRIPTION = "A young woman, warm and bright voice"
SENTENCES = [
    "The lighthouse keeper climbed the spiral stairs every evening before the sun went down.",
    "He polished the great lens until it shone, then lit the lamp and watched the sea turn.",
    "Ships passed far out on the dark water, and none of them ever knew his name at all.",
]
LONG_TEXT = " ".join(SENTENCES)
MAX_CHARS = 100
SAMPLE_RATE = 24_000


# ---------------------------------------------------------------------------
# Q3: generation export / import carries voice_description
# ---------------------------------------------------------------------------


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


def _generation(db, profile, voice_description: str | None) -> DBGeneration:
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
        engine="voxcpm",
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


class TestGenerationExportVoiceDescription:
    @pytest.mark.asyncio
    async def test_voice_description_survives_export_then_import(self, test_db, data_dir):
        generation = _generation(test_db, _profile(test_db), DESCRIPTION)

        zip_bytes = export_generation_to_zip(generation.id, test_db)
        manifest = _manifest(zip_bytes)
        assert manifest["generation"]["voice_description"] == DESCRIPTION
        assert manifest["version"] == "1.1"

        result = await import_generation_from_zip(zip_bytes, test_db)

        assert result["id"] != generation.id
        assert _row(test_db, result["id"]).voice_description == DESCRIPTION

    @pytest.mark.asyncio
    async def test_null_voice_description_stays_null(self, test_db, data_dir):
        generation = _generation(test_db, _profile(test_db), None)

        zip_bytes = export_generation_to_zip(generation.id, test_db)
        exported = _manifest(zip_bytes)["generation"]
        assert "voice_description" in exported
        assert exported["voice_description"] is None

        result = await import_generation_from_zip(zip_bytes, test_db)

        assert _row(test_db, result["id"]).voice_description is None

    @pytest.mark.asyncio
    async def test_legacy_manifest_without_the_key_imports_with_null(self, test_db, data_dir):
        _profile(test_db)
        manifest = {
            "version": "1.0",
            "generation": {
                "id": "old-id",
                "text": "Legacy text.",
                "language": "en",
                "duration": 2.0,
                "seed": None,
                "instruct": "speak softly",
                "created_at": "2026-01-01T00:00:00",
            },
            "profile": {"id": "p", "name": "Narrator", "description": None, "language": "en"},
            "versions": [],
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("audio/old-id.wav", b"RIFF....WAVE")

        result = await import_generation_from_zip(buf.getvalue(), test_db)

        row = _row(test_db, result["id"])
        assert row.text == "Legacy text."
        assert row.instruct == "speak softly"
        assert row.voice_description is None


# ---------------------------------------------------------------------------
# S4: the continuation temp file never leaks, even on cancellation
# ---------------------------------------------------------------------------


class _HookBackend:
    """A backend with the continuation hook; the hook write can be made to block."""

    def __init__(self, *, block: bool = False, decline: bool = False, fail: bool = False) -> None:
        self.block = block
        self.decline = decline
        self.fail = fail
        self.entered = threading.Event()
        self.proceed = threading.Event()
        self.hook_paths: list = []
        self.written_paths: list[str] = []
        self.released: list[dict] = []
        self.prompts: list = []

    async def generate(self, text, voice_prompt, language="en", seed=None, instruct=None):
        self.prompts.append(voice_prompt)
        return np.full(2_400, 0.1, dtype=np.float32), SAMPLE_RATE

    def continuation_voice_prompt(self, voice_prompt, instruct, chunk_text, chunk_audio, sample_rate, prompt_path=None):
        self.hook_paths.append(prompt_path)
        self.entered.set()
        if self.block:
            assert self.proceed.wait(10), "test never released the blocked hook"
        if self.fail:
            raise RuntimeError("hook failed")
        if self.decline:
            return None
        path = prompt_path
        if path is None:  # the pre-fix protocol: the hook makes its own temp file
            fd, path = tempfile.mkstemp(prefix="hook_test_", suffix=".wav")
            os.close(fd)
        with open(path, "wb") as handle:
            handle.write(np.asarray(chunk_audio, dtype=np.float32).tobytes())
        self.written_paths.append(path)
        return {"prompt_wav_path": path, "prompt_text": chunk_text}

    def release_continuation_voice_prompt(self, prompt: dict) -> None:
        self.released.append(prompt)
        with contextlib.suppress(FileNotFoundError):
            os.remove(prompt["prompt_wav_path"])


async def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


class TestContinuationTempFileLifecycle:
    @pytest.mark.asyncio
    async def test_cancel_while_the_hook_write_is_blocked_does_not_leak(self) -> None:
        backend = _HookBackend(block=True)
        task = asyncio.create_task(
            generate_chunked(backend, LONG_TEXT, {}, instruct=DESCRIPTION, max_chunk_chars=MAX_CHARS)
        )

        assert await _wait_until(backend.entered.is_set)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Now let the worker thread finish its write.
        backend.proceed.set()
        assert await _wait_until(lambda: len(backend.written_paths) == 1)
        written = backend.written_paths[0]

        # Once the thread is done, the file it wrote is gone and release ran.
        assert await _wait_until(lambda: len(backend.released) == 1 and not os.path.exists(written)), (
            f"leaked {written!r}; released={backend.released!r}"
        )
        assert backend.released[0]["prompt_wav_path"] == written
        # The path was reserved on the event-loop side before the hook ran.
        assert backend.hook_paths[0] == written

    @pytest.mark.asyncio
    async def test_success_path_uses_the_reserved_file_and_cleans_it_up(self) -> None:
        backend = _HookBackend()

        audio, sample_rate = await generate_chunked(
            backend, LONG_TEXT, {}, instruct=DESCRIPTION, max_chunk_chars=MAX_CHARS
        )

        assert sample_rate == SAMPLE_RATE
        assert len(audio) > 0
        reserved = backend.hook_paths[0]
        assert reserved is not None
        assert backend.written_paths == [reserved]
        assert [p["prompt_wav_path"] for p in backend.prompts[1:]] == [reserved, reserved]
        assert len(backend.released) == 1
        assert not os.path.exists(reserved)

    @pytest.mark.asyncio
    async def test_declined_hook_still_removes_the_reserved_file(self) -> None:
        backend = _HookBackend(decline=True)
        prompt: dict = {}

        await generate_chunked(backend, LONG_TEXT, prompt, instruct=DESCRIPTION, max_chunk_chars=MAX_CHARS)

        reserved = backend.hook_paths[0]
        assert reserved is not None
        assert not os.path.exists(reserved)
        assert backend.released == []
        assert all(p is prompt for p in backend.prompts)

    @pytest.mark.asyncio
    async def test_failing_hook_still_removes_the_reserved_file(self) -> None:
        backend = _HookBackend(fail=True)

        with pytest.raises(RuntimeError, match="hook failed"):
            await generate_chunked(backend, LONG_TEXT, {}, instruct=DESCRIPTION, max_chunk_chars=MAX_CHARS)

        reserved = backend.hook_paths[0]
        assert reserved is not None
        assert not os.path.exists(reserved)
        assert backend.released == []
