"""Regression tests for generation-history bulk deletion."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import config
from backend.database import Base, Generation, VoiceProfile
from backend.services.history import delete_generations


@pytest.mark.asyncio
async def test_bulk_delete_removes_selected_files_and_preserves_active_jobs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(
        config,
        "resolve_storage_path",
        lambda value: Path(value) if value else None,
    )

    profile = VoiceProfile(id="profile", name="Test voice", language="ar")
    selected_audio = tmp_path / "selected.wav"
    all_audio = tmp_path / "all.wav"
    selected_audio.write_bytes(b"selected")
    all_audio.write_bytes(b"all")
    session.add_all(
        [
            profile,
            Generation(
                id="selected",
                profile_id=profile.id,
                text="selected",
                status="completed",
                audio_path=str(selected_audio),
            ),
            Generation(
                id="active",
                profile_id=profile.id,
                text="active",
                status="generating",
            ),
            Generation(
                id="excluded",
                profile_id=profile.id,
                text="excluded",
                status="failed",
            ),
            Generation(
                id="all",
                profile_id=profile.id,
                text="all",
                status="completed",
                audio_path=str(all_audio),
            ),
        ]
    )
    session.commit()

    deleted = await delete_generations(
        session,
        generation_ids=["selected", "active"],
    )

    assert deleted == 1
    assert session.get(Generation, "selected") is None
    assert session.get(Generation, "active") is not None
    assert not selected_audio.exists()

    deleted = await delete_generations(
        session,
        delete_all=True,
        excluded_ids=["excluded"],
    )

    assert deleted == 1
    assert session.get(Generation, "all") is None
    assert session.get(Generation, "active") is not None
    assert session.get(Generation, "excluded") is not None
    assert not all_audio.exists()

    session.close()
    engine.dispose()
