"""
TTS-language validation on every TTS-language request field (FR-007).

VoxCPM2 declares 30 languages. Seven of them (``my``, ``id``, ``km``, ``lo``,
``tl``, ``th``, ``vi``) were outside the 22-code ``language`` pattern shared by
the TTS request models in ``backend/models.py``, so a VoxCPM2 request in those
languages was rejected with 422. These tests pin that:

* The seven new codes are accepted by every TTS-language field.
* Every pre-existing code is still accepted (the change cannot narrow).
* Unknown or malformed codes are rejected.
* All TTS-language patterns are the identical string, and no TTS-language
  field is missed (discovered by scanning ``backend.models``).
* The Whisper/STT ``language`` fields keep their own 10-code list.
* Every language VoxCPM2 declares is accepted by ``GenerationRequest.language``.

Usage:
    python -m pytest backend/tests/test_language_patterns.py -v
"""

import inspect
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend import models as models_module
from backend.backends import get_tts_model_configs
from backend.models import (
    CaptureRetranscribeRequest,
    GenerationRequest,
    PronunciationEntryCreate,
    PronunciationEntryUpdate,
    SpeakRequest,
    TranscriptionRequest,
    VoiceProfileCreate,
)

# (model, language field, minimum valid required fields)
TTS_LANGUAGE_FIELDS = [
    (VoiceProfileCreate, "language", {"name": "Voice"}),
    (GenerationRequest, "language", {"profile_id": "p1", "text": "hello"}),
    (PronunciationEntryCreate, "language", {"term": "foo", "replacement": "bar"}),
    (PronunciationEntryUpdate, "language", {}),
    (SpeakRequest, "language", {"text": "hello"}),
]
TTS_FIELD_IDS = [f"{model.__name__}.{field}" for model, field, _ in TTS_LANGUAGE_FIELDS]

STT_LANGUAGE_FIELDS = [
    (TranscriptionRequest, "language", {}),
    (CaptureRetranscribeRequest, "language", {}),
]
STT_FIELD_IDS = [f"{model.__name__}.{field}" for model, field, _ in STT_LANGUAGE_FIELDS]
STT_PATTERN = "^(en|zh|ja|ko|de|fr|ru|pt|es|it)$"

NEW_CODES = ["my", "id", "km", "lo", "tl", "th", "vi"]
EXISTING_CODES = [
    "zh", "en", "ja", "ko", "de", "fr", "ru", "pt", "es", "it", "he",
    "ar", "da", "el", "fi", "hi", "ms", "nl", "no", "pl", "sv", "sw", "tr",
]  # fmt: skip
INVALID_CODES = ["xx", "EN", "en-US", ""]


def _field_pattern(model: type[BaseModel], field: str) -> str | None:
    for meta in model.model_fields[field].metadata:
        pattern = getattr(meta, "pattern", None)
        if pattern is not None:
            return pattern
    return None


def _all_language_fields() -> dict[str, str]:
    """Every ``language`` field with a pattern in backend.models, keyed Model.field."""
    found = {}
    for name, obj in inspect.getmembers(models_module, inspect.isclass):
        if not issubclass(obj, BaseModel) or obj.__module__ != models_module.__name__:
            continue
        if "language" in obj.model_fields:
            pattern = _field_pattern(obj, "language")
            if pattern is not None:
                found[f"{name}.language"] = pattern
    return found


@pytest.mark.parametrize(("model", "field", "required"), TTS_LANGUAGE_FIELDS, ids=TTS_FIELD_IDS)
@pytest.mark.parametrize("code", NEW_CODES)
def test_new_codes_accepted(model, field, required, code):
    instance = model(**required, **{field: code})
    assert getattr(instance, field) == code


@pytest.mark.parametrize(("model", "field", "required"), TTS_LANGUAGE_FIELDS, ids=TTS_FIELD_IDS)
@pytest.mark.parametrize("code", EXISTING_CODES)
def test_existing_codes_still_accepted(model, field, required, code):
    instance = model(**required, **{field: code})
    assert getattr(instance, field) == code


@pytest.mark.parametrize(("model", "field", "required"), TTS_LANGUAGE_FIELDS, ids=TTS_FIELD_IDS)
@pytest.mark.parametrize("code", INVALID_CODES, ids=repr)
def test_invalid_codes_rejected(model, field, required, code):
    with pytest.raises(ValidationError):
        model(**required, **{field: code})


def test_tts_language_patterns_are_identical_and_complete():
    """Every non-STT language pattern is one string, on exactly the listed fields."""
    found = _all_language_fields()
    tts = {key: pattern for key, pattern in found.items() if pattern != STT_PATTERN}
    assert set(tts) == set(TTS_FIELD_IDS)
    assert len(set(tts.values())) == 1, tts


@pytest.mark.parametrize(("model", "field", "required"), STT_LANGUAGE_FIELDS, ids=STT_FIELD_IDS)
def test_stt_language_fields_unchanged(model, field, required):
    assert _field_pattern(model, field) == STT_PATTERN
    with pytest.raises(ValidationError):
        model(**required, **{field: "th"})


def test_every_voxcpm_declared_language_accepted_by_generation_request():
    voxcpm = [c for c in get_tts_model_configs() if c.engine == "voxcpm"]
    assert voxcpm, "no voxcpm model config"
    languages = voxcpm[0].languages
    assert len(languages) == 30
    for code in languages:
        request = GenerationRequest(profile_id="p1", text="hello", language=code, engine="voxcpm")
        assert request.language == code
