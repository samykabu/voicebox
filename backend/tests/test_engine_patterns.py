"""
Engine-name validation on every engine-validated request/response field (FR-001).

The TTS engine name is validated by a regex on four Pydantic fields in
``backend/models.py``. Adding an engine means adding it to all four; missing
one silently rejects the engine on that surface. These tests pin that:

* ``voxcpm`` is accepted by every field.
* Every pre-existing engine is still accepted (the change cannot narrow).
* An unknown engine is rejected.
* The four patterns are the identical string, so they cannot drift.

Usage:
    python -m pytest backend/tests/test_engine_patterns.py -v
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.models import (
    GenerationRequest,
    MCPClientBindingResponse,
    MCPClientBindingUpsert,
    SpeakRequest,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

# (model, engine field, minimum valid required fields)
ENGINE_FIELDS = [
    (GenerationRequest, "engine", {"profile_id": "p1", "text": "hello"}),
    (
        MCPClientBindingResponse,
        "default_engine",
        {"client_id": "c1", "created_at": _NOW, "updated_at": _NOW},
    ),
    (MCPClientBindingUpsert, "default_engine", {"client_id": "c1"}),
    (SpeakRequest, "engine", {"text": "hello"}),
]
ENGINE_FIELD_IDS = [f"{model.__name__}.{field}" for model, field, _ in ENGINE_FIELDS]

EXISTING_ENGINES = [
    "qwen",
    "qwen_custom_voice",
    "luxtts",
    "chatterbox",
    "chatterbox_turbo",
    "tada",
    "kokoro",
    "f5_tts",
]


@pytest.mark.parametrize(("model", "field", "required"), ENGINE_FIELDS, ids=ENGINE_FIELD_IDS)
def test_voxcpm_is_accepted(model, field, required):
    instance = model(**required, **{field: "voxcpm"})
    assert getattr(instance, field) == "voxcpm"


@pytest.mark.parametrize("engine", EXISTING_ENGINES)
@pytest.mark.parametrize(("model", "field", "required"), ENGINE_FIELDS, ids=ENGINE_FIELD_IDS)
def test_existing_engines_still_accepted(model, field, required, engine):
    instance = model(**required, **{field: engine})
    assert getattr(instance, field) == engine


@pytest.mark.parametrize("engine", ["not_an_engine", "voxcpm2", "VOXCPM", " voxcpm", ""])
@pytest.mark.parametrize(("model", "field", "required"), ENGINE_FIELDS, ids=ENGINE_FIELD_IDS)
def test_unknown_engine_is_rejected(model, field, required, engine):
    with pytest.raises(ValidationError):
        model(**required, **{field: engine})


def _engine_pattern(model, field):
    """Return the regex pattern from the field's JSON schema (Optional[str] -> anyOf)."""
    prop = model.model_json_schema()["properties"][field]
    candidates = [prop, *prop.get("anyOf", [])]
    patterns = [c["pattern"] for c in candidates if "pattern" in c]
    assert len(patterns) == 1, f"{model.__name__}.{field}: expected one pattern, got {patterns}"
    return patterns[0]


def test_engine_patterns_are_identical():
    patterns = {f"{model.__name__}.{field}": _engine_pattern(model, field) for model, field, _ in ENGINE_FIELDS}
    assert len(set(patterns.values())) == 1, f"engine patterns drifted: {patterns}"
