"""
Voice profile export/import module.

Handles exporting profiles to ZIP archives and importing them back.
Also handles exporting individual generations.
"""

import json
import logging
import zipfile
import io
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session

from ..models import VoiceProfileResponse
from ..database import VoiceProfile as DBVoiceProfile, ProfileSample as DBProfileSample, Generation as DBGeneration, GenerationVersion as DBGenerationVersion
from .profiles import create_profile, add_profile_sample
from ..models import VoiceProfileCreate
from .. import config

logger = logging.getLogger(__name__)


def _get_unique_profile_name(name: str, db: Session) -> str:
    """
    Get a unique profile name by appending a number if needed.
    
    Args:
        name: Original profile name
        db: Database session
        
    Returns:
        Unique profile name
    """
    base_name = name
    counter = 1
    
    while True:
        existing = db.query(DBVoiceProfile).filter_by(name=name).first()
        if not existing:
            return name
        
        name = f"{base_name} ({counter})"
        counter += 1


# Manifest 1.1 adds provenance (FR-027): voice_type, design_prompt,
# default_engine, and the preset engine/voice id that preset profiles need
# to be valid. Import still accepts 1.0 manifests, which lack these fields.
PROFILE_MANIFEST_VERSION = "1.1"

# Generation manifest 1.1 adds generation.voice_description (the written voice
# description retry and regenerate replay) and generation.engine / model_size (the
# engine and variant retry and regenerate run on). Import still accepts 1.0
# manifests, which lack them: voice_description restores null, and engine and
# model_size keep the column defaults.
GENERATION_MANIFEST_VERSION = "1.1"

PROVENANCE_FIELDS = (
    "voice_type",
    "preset_engine",
    "preset_voice_id",
    "design_prompt",
    "default_engine",
)


def export_profile_to_zip(profile_id: str, db: Session) -> bytes:
    """
    Export a voice profile to a ZIP archive.
    
    Args:
        profile_id: Profile ID to export
        db: Database session
        
    Returns:
        ZIP file contents as bytes
        
    Raises:
        ValueError: If profile not found, or a cloned profile has no samples
    """
    # Get profile
    profile = db.query(DBVoiceProfile).filter_by(id=profile_id).first()
    if not profile:
        raise ValueError(f"Profile {profile_id} not found")

    voice_type = profile.voice_type or "cloned"

    # Get all samples. Only cloned profiles depend on reference audio; designed
    # and preset profiles are fully described by their metadata.
    samples = db.query(DBProfileSample).filter_by(profile_id=profile_id).all()
    if not samples and voice_type == "cloned":
        raise ValueError(f"Profile {profile_id} has no samples")
    
    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Check if profile has avatar
        has_avatar = False
        if profile.avatar_path:
            avatar_path = config.resolve_storage_path(profile.avatar_path)
            if avatar_path is not None and avatar_path.exists():
                has_avatar = True
                # Add avatar to ZIP root with original extension
                avatar_ext = avatar_path.suffix
                zip_file.write(avatar_path, f"avatar{avatar_ext}")

        # Create manifest.json
        manifest = {
            "version": PROFILE_MANIFEST_VERSION,
            "profile": {
                "name": profile.name,
                "description": profile.description,
                "language": profile.language,
                "voice_type": voice_type,
                "preset_engine": profile.preset_engine,
                "preset_voice_id": profile.preset_voice_id,
                "design_prompt": profile.design_prompt,
                "default_engine": profile.default_engine,
            },
            "has_avatar": has_avatar,
        }
        zip_file.writestr("manifest.json", json.dumps(manifest, indent=2))

        # Create samples.json mapping
        samples_data = {}
        profile_dir = config.get_profiles_dir() / profile_id

        for sample in samples:
            # Get filename from audio_path (should be {sample_id}.wav)
            audio_path = config.resolve_storage_path(sample.audio_path)
            if audio_path is None:
                raise ValueError(f"Audio file not found: {sample.audio_path}")
            filename = audio_path.name

            # Read audio file
            if not audio_path.exists():
                raise ValueError(f"Audio file not found: {audio_path}")

            # Add to samples directory in ZIP
            zip_path = f"samples/{filename}"
            zip_file.write(audio_path, zip_path)

            # Map filename to reference text
            samples_data[filename] = sample.reference_text

        zip_file.writestr("samples.json", json.dumps(samples_data, indent=2))
    
    zip_buffer.seek(0)
    return zip_buffer.read()


async def import_profile_from_zip(file_bytes: bytes, db: Session) -> VoiceProfileResponse:
    """
    Import a voice profile from a ZIP archive.
    
    Args:
        file_bytes: ZIP file contents
        db: Database session
        
    Returns:
        Created profile
        
    Raises:
        ValueError: If ZIP is invalid or missing required files
    """
    zip_buffer = io.BytesIO(file_bytes)
    
    try:
        with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
            # Validate ZIP structure
            namelist = zip_file.namelist()
            
            if "manifest.json" not in namelist:
                raise ValueError("ZIP archive missing manifest.json")
            
            if "samples.json" not in namelist:
                raise ValueError("ZIP archive missing samples.json")
            
            # Read manifest
            manifest_data = json.loads(zip_file.read("manifest.json"))
            
            if "version" not in manifest_data:
                raise ValueError("Invalid manifest.json: missing version")
            
            if "profile" not in manifest_data:
                raise ValueError("Invalid manifest.json: missing profile")
            
            profile_data = manifest_data["profile"]
            
            # Read samples mapping
            samples_data = json.loads(zip_file.read("samples.json"))
            
            if not isinstance(samples_data, dict):
                raise ValueError("Invalid samples.json: must be a dictionary")
            
            # Get unique profile name
            original_name = profile_data.get("name", "Imported Profile")
            unique_name = _get_unique_profile_name(original_name, db)
            
            # Restore provenance (FR-027) when the manifest carries it. Older
            # 1.0 manifests have none of these keys and import as cloned with
            # no default engine, as before. create_profile validates the
            # combination and raises ValueError on an invalid one (e.g. a
            # designed profile with a blank design_prompt) rather than
            # silently downgrading it.
            provenance = {
                field: profile_data[field]
                for field in PROVENANCE_FIELDS
                if profile_data.get(field) is not None
            }

            # Create profile
            profile_create = VoiceProfileCreate(
                name=unique_name,
                description=profile_data.get("description"),
                language=profile_data.get("language", "en"),
                **provenance,
            )

            profile = await create_profile(profile_create, db)

            # Extract and add samples
            profile_dir = config.get_profiles_dir() / profile.id
            profile_dir.mkdir(parents=True, exist_ok=True)

            # Handle avatar if present
            avatar_files = [f for f in namelist if f.startswith("avatar.")]
            if avatar_files:
                try:
                    avatar_file = avatar_files[0]
                    # Extract to temporary file
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=Path(avatar_file).suffix, delete=False) as tmp:
                        tmp.write(zip_file.read(avatar_file))
                        tmp_path = tmp.name

                    try:
                        from .profiles import upload_avatar
                        await upload_avatar(profile.id, tmp_path, db)
                    finally:
                        Path(tmp_path).unlink(missing_ok=True)
                except Exception as e:
                    # Avatar import is optional - continue even if it fails
                    pass

            for filename, reference_text in samples_data.items():
                # Validate filename
                if not filename.endswith('.wav'):
                    raise ValueError(f"Invalid sample filename: {filename} (must be .wav)")
                
                # Extract audio file to temp location
                zip_path = f"samples/{filename}"
                
                if zip_path not in namelist:
                    raise ValueError(f"Sample file not found in ZIP: {zip_path}")
                
                # Extract to temporary file
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(zip_file.read(zip_path))
                    tmp_path = tmp.name
                
                try:
                    # Add sample to profile
                    await add_profile_sample(
                        profile.id,
                        tmp_path,
                        reference_text,
                        db,
                    )
                finally:
                    # Clean up temp file
                    Path(tmp_path).unlink(missing_ok=True)
            
            return profile
            
    except zipfile.BadZipFile:
        raise ValueError("Invalid ZIP file")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in archive: {e}")
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Error importing profile: {str(e)}")


def export_generation_to_zip(generation_id: str, db: Session) -> bytes:
    """
    Export a generation to a ZIP archive.
    
    Args:
        generation_id: Generation ID to export
        db: Database session
        
    Returns:
        ZIP file contents as bytes
        
    Raises:
        ValueError: If generation not found
    """
    # Get generation
    generation = db.query(DBGeneration).filter_by(id=generation_id).first()
    if not generation:
        raise ValueError(f"Generation {generation_id} not found")
    
    # Get profile info
    profile = db.query(DBVoiceProfile).filter_by(id=generation.profile_id).first()
    if not profile:
        raise ValueError(f"Profile {generation.profile_id} not found")
    
    # Get all versions for this generation
    versions = (
        db.query(DBGenerationVersion)
        .filter_by(generation_id=generation_id)
        .order_by(DBGenerationVersion.created_at)
        .all()
    )

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Build version manifest entries
        version_entries = []
        for v in versions:
            v_path = config.resolve_storage_path(v.audio_path)
            effects_chain = None
            if v.effects_chain:
                effects_chain = json.loads(v.effects_chain)
            version_entries.append({
                "id": v.id,
                "label": v.label,
                "is_default": v.is_default,
                "effects_chain": effects_chain,
                "filename": v_path.name,
            })

        manifest = {
            "version": GENERATION_MANIFEST_VERSION,
            "generation": {
                "id": generation.id,
                "text": generation.text,
                "language": generation.language,
                "duration": generation.duration,
                "seed": generation.seed,
                "instruct": generation.instruct,
                "voice_description": generation.voice_description,
                "engine": generation.engine,
                "model_size": generation.model_size,
                "created_at": generation.created_at.isoformat(),
            },
            "profile": {
                "id": profile.id,
                "name": profile.name,
                "description": profile.description,
                "language": profile.language,
            },
            "versions": version_entries,
        }
        zip_file.writestr("manifest.json", json.dumps(manifest, indent=2))
        
        # Add all version audio files
        for v in versions:
            v_path = config.resolve_storage_path(v.audio_path)
            if v_path is not None and v_path.exists():
                zip_file.write(v_path, f"audio/{v_path.name}")

        # Fallback: if no versions exist, include the generation's main audio
        if not versions:
            audio_path = config.resolve_storage_path(generation.audio_path)
            if audio_path is not None and audio_path.exists():
                zip_file.write(audio_path, f"audio/{audio_path.name}")
    
    zip_buffer.seek(0)
    return zip_buffer.read()


def _validated_engine_fields(generation_data: dict) -> dict:
    """Return the ``engine`` / ``model_size`` columns to restore from a generation manifest.

    Values are checked against the TTS registry before they reach the database:

    - no ``engine`` (a 1.0 manifest), or one that is not a string in
      ``backends.TTS_ENGINES``: return nothing, so the column defaults apply
      (engine ``"qwen"``, model_size null), exactly as import did before 1.1;
    - a known engine with several sizes: keep ``model_size`` when it is one of that
      engine's configured sizes, otherwise store the engine's registry default;
    - a known engine without sizes: store null, as ``POST /generate`` does.

    Every rejected manifest value is logged as a warning.
    """
    from ..backends import TTS_ENGINES, engine_has_model_sizes, get_default_model_size, get_tts_model_configs

    if "engine" not in generation_data or generation_data["engine"] is None:
        return {}
    engine = generation_data["engine"]
    if not isinstance(engine, str) or engine not in TTS_ENGINES:
        logger.warning("Generation import: unknown engine %r in manifest; using the default engine", engine)
        return {}

    model_size = generation_data.get("model_size")
    valid = isinstance(model_size, str) and model_size in {
        c.model_size for c in get_tts_model_configs() if c.engine == engine
    }
    if not engine_has_model_sizes(engine):
        if model_size is not None and not valid:
            logger.warning(
                "Generation import: model_size %r is not valid for engine %r; storing null",
                model_size,
                engine,
            )
        return {"engine": engine, "model_size": None}

    if not valid:
        fallback = get_default_model_size(engine)
        if model_size is not None:
            logger.warning(
                "Generation import: model_size %r is not valid for engine %r; using %r",
                model_size,
                engine,
                fallback,
            )
        return {"engine": engine, "model_size": fallback}
    return {"engine": engine, "model_size": model_size}


def _validated_voice_description(generation_data: dict, engine: str) -> str | None:
    """Return the ``voice_description`` to restore from a generation manifest, or None.

    The manifest value gets the same checks as ``POST /generate``: it must be a string of
    at most ``MAX_VOICE_DESCRIPTION_CHARS`` characters once stripped (the API rejects a
    longer one rather than truncating it, so import stores null), and it is then kept only
    when *engine*, the engine the row is restored with, supports voice design
    (``stored_voice_description``). A blank value stores null. Every rejected non-blank
    value is logged as a warning.
    """
    from ..models import MAX_VOICE_DESCRIPTION_CHARS
    from .generation import stored_voice_description

    value = generation_data.get("voice_description")
    if value is None:
        return None
    if not isinstance(value, str):
        logger.warning(
            "Generation import: voice_description is a %s, not a string; storing null",
            type(value).__name__,
        )
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > MAX_VOICE_DESCRIPTION_CHARS:
        logger.warning(
            "Generation import: voice_description has %d characters, over the %d limit; storing null",
            len(value),
            MAX_VOICE_DESCRIPTION_CHARS,
        )
        return None
    stored = stored_voice_description(engine, value)
    if stored is None:
        logger.warning(
            "Generation import: engine %r does not support voice design; storing voice_description as null",
            engine,
        )
    return stored


def _manifest_value(generation_data: dict, field: str, types: tuple[type, ...], fallback):
    """Return ``generation_data[field]`` when it is one of *types*, else *fallback*.

    ``bool`` is never accepted (it is an ``int`` subclass). A missing or null value
    returns *fallback* silently; any other rejected value is logged as a warning, so a
    crafted manifest cannot fail the database commit.
    """
    value = generation_data.get(field)
    if value is None:
        return fallback
    if isinstance(value, bool) or not isinstance(value, types):
        logger.warning(
            "Generation import: %s is a %s, not the expected type; using %r",
            field,
            type(value).__name__,
            fallback,
        )
        return fallback
    return value


async def import_generation_from_zip(file_bytes: bytes, db: Session) -> dict:
    """
    Import a generation from a ZIP archive.
    
    Args:
        file_bytes: ZIP file contents
        db: Database session
        
    Returns:
        Dictionary with generation ID and profile info
        
    Raises:
        ValueError: If ZIP is invalid or missing required files
    """
    from pathlib import Path
    import tempfile
    import shutil
    from datetime import datetime
    from .. import config
    
    zip_buffer = io.BytesIO(file_bytes)
    
    try:
        with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
            # Validate ZIP structure
            namelist = zip_file.namelist()
            
            if "manifest.json" not in namelist:
                raise ValueError("ZIP archive missing manifest.json")
            
            # Read manifest
            manifest_data = json.loads(zip_file.read("manifest.json"))
            
            if "version" not in manifest_data:
                raise ValueError("Invalid manifest.json: missing version")
            
            if "generation" not in manifest_data:
                raise ValueError("Invalid manifest.json: missing generation data")
            
            generation_data = manifest_data["generation"]
            profile_data = manifest_data.get("profile", {})
            
            # Validate required fields
            required_fields = ["text", "language", "duration"]
            for field in required_fields:
                if field not in generation_data:
                    raise ValueError(f"Invalid manifest.json: missing generation.{field}")

            # Type-check every restored field before any file is copied, so a crafted
            # value cannot fail the commit and orphan the audio (review S6).
            text = generation_data["text"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Invalid manifest.json: generation.text must be a non-empty string")
            engine_fields = _validated_engine_fields(generation_data)
            restored_engine = engine_fields.get("engine") or DBGeneration.__table__.c.engine.default.arg
            restored_fields = {
                "text": text,
                "language": _manifest_value(generation_data, "language", (str,), "en"),
                "duration": _manifest_value(generation_data, "duration", (int, float), None),
                "seed": _manifest_value(generation_data, "seed", (int,), None),
                "instruct": _manifest_value(generation_data, "instruct", (str,), None),
                "voice_description": _validated_voice_description(generation_data, restored_engine),
                **engine_fields,
            }

            # Find audio file in archive
            audio_files = [f for f in namelist if f.startswith("audio/") and f.endswith(".wav")]
            if not audio_files:
                raise ValueError("No audio file found in ZIP archive")
            
            audio_file_path = audio_files[0]
            
            # Check if we should match an existing profile or create metadata
            profile_id = None
            profile_name = profile_data.get("name", "Unknown Profile")
            
            # Try to find matching profile by name
            if profile_name and profile_name != "Unknown Profile":
                existing_profile = db.query(DBVoiceProfile).filter_by(name=profile_name).first()
                if existing_profile:
                    profile_id = existing_profile.id
            
            # If no matching profile, use a placeholder or the first available profile
            if not profile_id:
                # Get any profile, or None if no profiles exist
                any_profile = db.query(DBVoiceProfile).first()
                if any_profile:
                    profile_id = any_profile.id
                    profile_name = any_profile.name
                else:
                    raise ValueError("No voice profiles found. Please create a profile before importing generations.")
            
            # Extract audio file to temporary location
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(zip_file.read(audio_file_path))
                tmp_path = tmp.name
            
            try:
                # Create generations directory
                generations_dir = config.get_generations_dir()
                generations_dir.mkdir(parents=True, exist_ok=True)
                
                # Generate new ID for this generation
                new_generation_id = str(__import__('uuid').uuid4())
                
                # Copy audio to generations directory
                audio_dest = generations_dir / f"{new_generation_id}.wav"
                shutil.copy(tmp_path, audio_dest)
                
                # Create generation record
                db_generation = DBGeneration(
                    id=new_generation_id,
                    profile_id=profile_id,
                    audio_path=config.to_storage_path(audio_dest),
                    created_at=datetime.utcnow(),
                    **restored_fields,
                )

                try:
                    db.add(db_generation)
                    db.commit()
                except Exception:
                    # Never leave the copied audio behind without a row that references it.
                    db.rollback()
                    audio_dest.unlink(missing_ok=True)
                    raise
                db.refresh(db_generation)
                
                return {
                    "id": db_generation.id,
                    "profile_id": profile_id,
                    "profile_name": profile_name,
                    "text": db_generation.text,
                    "message": f"Generation imported successfully (assigned to profile: {profile_name})"
                }
                
            finally:
                # Clean up temp file
                Path(tmp_path).unlink(missing_ok=True)
            
    except zipfile.BadZipFile:
        raise ValueError("Invalid ZIP file")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in archive: {e}")
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Error importing generation: {str(e)}")
