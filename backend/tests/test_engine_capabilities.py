"""Tests for the engine capability channel (FR-002, FR-003, FR-004, FR-024).

Covers availability resolution per specs/001-voxcpm2-tts-engine/data-model.md §2 and the
invariants in contracts/engine-capabilities.md. Device and memory values are injected, so
nothing here needs torch.

Sections:
  1. ModelConfig capability fields
  2. Existing registered engines are unchanged
  3. Pure availability resolution
  4. Device-detecting wrapper (fake torch only)
  (T010 adds the GET /models/engines route tests below these.)
"""

import ast
import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.backends import AdvancedSetting, ModelConfig, get_tts_model_configs
from backend.backends.base import (
    EngineAvailability,
    detect_engine_availability,
    resolve_engine_availability,
)


def _config(**overrides) -> ModelConfig:
    values = {
        "model_name": "test-model",
        "display_name": "Test Engine",
        "engine": "testengine",
        "hf_repo_id": "example/test-model",
    }
    values.update(overrides)
    return ModelConfig(**values)


CONSTRAINED = ("cuda", "mps", "cpu")


# ---------------------------------------------------------------------------
# 1. ModelConfig capability fields
# ---------------------------------------------------------------------------


def test_model_config_capability_fields_default_to_todays_behaviour():
    config = _config()

    assert config.accelerators == ()
    assert config.supports_voice_design is False
    assert config.requires_download_confirmation is False
    assert config.advanced_settings == ()


def test_model_config_declares_the_new_fields():
    names = {f.name for f in fields(ModelConfig)}

    assert {"accelerators", "supports_voice_design", "requires_download_confirmation", "advanced_settings"} <= names


def test_advanced_setting_carries_contract_shape_and_is_frozen():
    setting = AdvancedSetting(name="cfg_value", label="Guidance", default=2.0, min=1.0, max=5.0)

    assert (setting.name, setting.label, setting.default, setting.min, setting.max) == (
        "cfg_value",
        "Guidance",
        2.0,
        1.0,
        5.0,
    )
    with pytest.raises(FrozenInstanceError):
        setting.default = 3.0  # type: ignore[misc]

    config = _config(advanced_settings=(setting,))
    assert config.advanced_settings == (setting,)


# ---------------------------------------------------------------------------
# 2. Existing registered engines are unchanged
# ---------------------------------------------------------------------------


# The eight engines registered before VoxCPM2. Their "unchanged" assertions are pinned to
# this explicit set; engines that declare capabilities (VoxCPM2) get their own tests below.
PRE_VOXCPM_ENGINES = frozenset(
    {"qwen", "qwen_custom_voice", "luxtts", "chatterbox", "chatterbox_turbo", "tada", "kokoro", "f5_tts"}
)

EXISTING_TTS_CONFIGS = [c for c in get_tts_model_configs() if c.engine in PRE_VOXCPM_ENGINES]


def test_there_are_existing_tts_configs_to_check():
    assert EXISTING_TTS_CONFIGS
    assert {c.engine for c in EXISTING_TTS_CONFIGS} == PRE_VOXCPM_ENGINES


@pytest.mark.parametrize("config", EXISTING_TTS_CONFIGS, ids=lambda c: c.model_name)
def test_existing_tts_config_keeps_default_capabilities(config):
    assert config.accelerators == ()
    assert config.supports_voice_design is False
    assert config.requires_download_confirmation is False
    assert config.advanced_settings == ()


@pytest.mark.parametrize("config", EXISTING_TTS_CONFIGS, ids=lambda c: c.model_name)
@pytest.mark.parametrize("detected", ["cuda", "mps", "cpu", "xpu", "directml"])
def test_existing_tts_config_is_always_available(config, detected):
    result = resolve_engine_availability(config, detected, memory_mb=1024, min_memory_mb=8192)

    assert result.available is True
    assert result.reason is None
    assert result.warning is None
    assert result.supported_accelerators == []


# ---------------------------------------------------------------------------
# 3. Pure availability resolution
# ---------------------------------------------------------------------------


def test_empty_accelerators_is_available_with_no_reason():
    result = resolve_engine_availability(_config(), "cpu")

    assert isinstance(result, EngineAvailability)
    assert result.engine == "testengine"
    assert result.available is True
    assert result.reason is None
    assert result.warning is None
    assert result.supported_accelerators == []
    assert result.detected_accelerator == "cpu"


@pytest.mark.parametrize("detected", CONSTRAINED)
def test_detected_accelerator_in_declared_set_is_available(detected):
    result = resolve_engine_availability(_config(accelerators=CONSTRAINED), detected)

    assert result.available is True
    assert result.reason is None
    assert result.warning is None
    assert result.supported_accelerators == list(CONSTRAINED)


def test_indexed_cuda_device_counts_as_cuda():
    result = resolve_engine_availability(_config(accelerators=("cuda",)), "cuda:1")

    assert result.available is True
    assert result.detected_accelerator == "cuda"


def test_detected_accelerator_not_in_set_is_unavailable_with_specific_reason():
    result = resolve_engine_availability(_config(accelerators=("cuda", "mps")), "cpu")

    assert result.available is False
    assert result.reason
    # FR-003: a specific sentence naming the engine, what was found and what is needed.
    assert "Test Engine" in result.reason
    assert "CPU" in result.reason
    assert "CUDA" in result.reason
    assert "MPS" in result.reason
    assert result.warning is None


def test_supported_but_marginal_memory_warns_and_never_blocks():
    result = resolve_engine_availability(
        _config(accelerators=CONSTRAINED),
        "cuda",
        memory_mb=6 * 1024,
        min_memory_mb=8 * 1024,
    )

    assert result.available is True
    assert result.reason is None
    assert result.warning
    assert "6 GB" in result.warning
    assert "Test Engine" in result.warning


def test_sufficient_memory_has_no_warning():
    result = resolve_engine_availability(
        _config(accelerators=CONSTRAINED),
        "cuda",
        memory_mb=24 * 1024,
        min_memory_mb=8 * 1024,
    )

    assert result.available is True
    assert result.warning is None


@pytest.mark.parametrize(("memory_mb", "min_memory_mb"), [(None, 8192), (4096, None), (None, None)])
def test_unknown_memory_or_threshold_has_no_warning(memory_mb, min_memory_mb):
    result = resolve_engine_availability(
        _config(accelerators=CONSTRAINED), "cuda", memory_mb=memory_mb, min_memory_mb=min_memory_mb
    )

    assert result.available is True
    assert result.warning is None


def test_unavailable_engine_carries_reason_not_warning_even_with_marginal_memory():
    result = resolve_engine_availability(
        _config(accelerators=("cuda",)),
        "mps",
        memory_mb=1024,
        min_memory_mb=8192,
    )

    assert result.available is False
    assert result.reason is not None
    assert result.warning is None


@pytest.mark.parametrize("accelerators", [(), ("cuda",), ("cuda", "mps", "cpu"), ("mps",)])
@pytest.mark.parametrize("detected", ["cuda", "cuda:0", "mps", "cpu", "xpu", "directml"])
@pytest.mark.parametrize(("memory_mb", "min_memory_mb"), [(None, None), (2048, 8192), (16384, 8192)])
def test_contract_invariants_hold_everywhere(accelerators, detected, memory_mb, min_memory_mb):
    result = resolve_engine_availability(
        _config(accelerators=accelerators), detected, memory_mb=memory_mb, min_memory_mb=min_memory_mb
    )

    # Invariant 1: unavailable implies a reason; reason only when unavailable.
    assert (result.reason is not None) == (not result.available)
    # Invariant 2: unconstrained engines are always offered.
    if not accelerators:
        assert result.available is True
    # Invariant 3: an unavailable engine carries a reason, not a warning.
    if not result.available:
        assert result.warning is None
    # Memory is never a hard gate (C1Q4): availability depends only on the accelerator.
    baseline = resolve_engine_availability(_config(accelerators=accelerators), detected)
    assert result.available == baseline.available


# ---------------------------------------------------------------------------
# 4. Device-detecting wrapper (fake torch only; never loads or downloads a model)
# ---------------------------------------------------------------------------


def _fake_torch(*, cuda: bool = False, mps: bool = False, total_memory_bytes: int = 0):
    cuda_ns = SimpleNamespace(
        is_available=lambda: cuda,
        device_count=lambda: 1 if cuda else 0,
        current_device=lambda: 0,
        get_device_properties=lambda index: SimpleNamespace(total_memory=total_memory_bytes),
    )
    mps_ns = SimpleNamespace(is_available=lambda: mps)
    return SimpleNamespace(cuda=cuda_ns, backends=SimpleNamespace(mps=mps_ns))


def test_wrapper_detects_mps_and_resolves(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(mps=True))

    result = detect_engine_availability(_config(accelerators=("cuda",)))

    assert result.detected_accelerator == "mps"
    assert result.available is False
    assert result.reason


def test_wrapper_reads_cuda_memory_for_the_warning(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(cuda=True, total_memory_bytes=6 * 1024**3))

    result = detect_engine_availability(_config(accelerators=CONSTRAINED), min_memory_mb=8 * 1024)

    assert result.detected_accelerator == "cuda"
    assert result.available is True
    assert result.warning
    assert "6 GB" in result.warning


# ---------------------------------------------------------------------------
# 5. GET /models/engines and the GenerationRequest capability fields (T010)
# ---------------------------------------------------------------------------

_PROFILES_SOURCE = Path(__file__).resolve().parent.parent / "services" / "profiles.py"
_DETECTED = ("cuda", 6 * 1024)

CONTRACT_FIELDS = {
    "engine",
    "display_name",
    "available",
    "reason",
    "warning",
    "supported_accelerators",
    "detected_accelerator",
    "languages",
    "supports_cloning",
    "supports_voice_design",
    "requires_download_confirmation",
    "advanced_settings",
    "size_mb",
    "license_id",
    "commercial_use",
}
SETTING_FIELDS = {"name", "label", "default", "min", "max"}


def _real_cloning_engines() -> set[str]:
    """Read CLONING_ENGINES from services/profiles.py without importing it (it pulls in torch)."""
    tree = ast.parse(_PROFILES_SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "CLONING_ENGINES" for t in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError("CLONING_ENGINES not found in services/profiles.py")


REAL_CLONING_ENGINES = _real_cloning_engines()


def _forbid(name):
    def _raise(*args, **kwargs):
        raise AssertionError(f"GET /models/engines must not call {name}")

    return _raise


@pytest.fixture
def engines_client(monkeypatch):
    """A fresh app with only the models router, fixed hardware and no load/download paths."""
    import backend.backends as backends_pkg
    import backend.backends.base as base_mod
    import backend.routes.models as routes_mod

    calls = []

    def _fake_detect():
        calls.append("detect")
        return _DETECTED

    monkeypatch.setattr(base_mod, "detect_accelerator_and_memory", _fake_detect)
    # services.profiles imports torch through utils.cache; serve the real set without it.
    monkeypatch.setitem(sys.modules, "backend.services.profiles", SimpleNamespace(CLONING_ENGINES=REAL_CLONING_ENGINES))
    for name in (
        "get_model_load_func",
        "load_engine_model",
        "get_tts_backend_for_engine",
        "get_tts_backend",
        "unload_model_by_config",
        "check_model_loaded",
        "check_model_cached",
    ):
        monkeypatch.setattr(backends_pkg, name, _forbid(name))
    monkeypatch.setattr(routes_mod, "create_background_task", _forbid("create_background_task"))

    app = FastAPI()
    app.include_router(routes_mod.router)
    client = TestClient(app)
    client.detect_calls = calls
    return client


def _engines(client):
    response = client.get("/models/engines")
    assert response.status_code == 200, response.text
    return response.json()["engines"]


def test_engines_route_returns_every_tts_engine_with_every_contract_field(engines_client):
    from backend.backends import TTS_ENGINES

    engines = _engines(engines_client)

    assert [e["engine"] for e in engines] == list(TTS_ENGINES)
    for entry in engines:
        assert set(entry) == CONTRACT_FIELDS, entry["engine"]
        for setting in entry["advanced_settings"]:
            assert set(setting) == SETTING_FIELDS


def test_engines_route_detects_hardware_once_per_request(engines_client):
    _engines(engines_client)

    assert engines_client.detect_calls == ["detect"]


def test_engines_route_existing_engines_keep_todays_behaviour(engines_client):
    entries = [e for e in _engines(engines_client) if e["engine"] in PRE_VOXCPM_ENGINES]
    assert {e["engine"] for e in entries} == PRE_VOXCPM_ENGINES
    for entry in entries:
        assert entry["supported_accelerators"] == []
        assert entry["available"] is True
        assert entry["reason"] is None
        assert entry["warning"] is None
        assert entry["requires_download_confirmation"] is False
        assert entry["supports_voice_design"] is False
        assert entry["advanced_settings"] == []
        assert entry["detected_accelerator"] == "cuda"


def _variants_by_engine():
    from backend.backends import get_tts_model_configs

    grouped = {}
    for config in get_tts_model_configs():
        grouped.setdefault(config.engine, []).append(config)
    return grouped


def _default_variant(engine):
    from backend.backends import get_default_model_size

    default_size = get_default_model_size(engine)
    return next(c for c in _variants_by_engine()[engine] if c.model_size == default_size)


def test_engines_route_describes_each_engine_from_all_of_its_variants(engines_client):
    from backend.backends import TTS_ENGINES

    grouped = _variants_by_engine()
    for entry in _engines(engines_client):
        engine = entry["engine"]
        variants = grouped[engine]
        expected_languages = list(dict.fromkeys(lang for c in variants for lang in c.languages))
        licenses = {c.license_id for c in variants}
        commercial = {c.commercial_use for c in variants}

        assert entry["display_name"] == TTS_ENGINES[engine]
        assert entry["languages"] == expected_languages
        assert entry["size_mb"] == _default_variant(engine).size_mb
        assert entry["license_id"] == (licenses.pop() if len(licenses) == 1 else None)
        assert entry["commercial_use"] == (commercial.pop() if len(commercial) == 1 else None)
        assert entry["supports_cloning"] is (engine in REAL_CLONING_ENGINES)


def test_engines_route_display_name_is_the_engine_name(engines_client):
    from backend.backends import TTS_ENGINES

    names = {e["engine"]: e["display_name"] for e in _engines(engines_client)}

    assert names == TTS_ENGINES
    assert names["tada"] == "TADA"
    assert names["f5_tts"] == "F5-TTS"


def test_engines_route_tada_languages_include_the_multilingual_variant(engines_client):
    tada = next(e for e in _engines(engines_client) if e["engine"] == "tada")

    assert "ar" in tada["languages"]
    assert tada["languages"][0] == "en"  # first-seen order: tada-1b (en) comes first in the registry
    assert len(tada["languages"]) == len(set(tada["languages"]))


def test_engines_route_f5_license_is_null_when_variants_disagree(engines_client):
    f5 = next(e for e in _engines(engines_client) if e["engine"] == "f5_tts")

    assert f5["license_id"] is None
    assert f5["commercial_use"] is None
    assert f5["size_mb"] == _default_variant("f5_tts").size_mb


def _qwen_variants(*variants):
    """Real TTS configs, with every qwen config replaced by the given test variants."""
    from backend.backends import get_tts_model_configs as real_configs

    configs = list(variants) + [c for c in real_configs() if c.engine != "qwen"]
    return lambda: configs


def _qwen_variant(model_size, **overrides):
    values = {
        "model_name": f"qwen-test-{model_size}",
        "display_name": f"Qwen Test {model_size}",
        "engine": "qwen",
        "hf_repo_id": f"example/qwen-test-{model_size}",
        "model_size": model_size,
    }
    values.update(overrides)
    return ModelConfig(**values)


def test_engines_route_returns_the_shared_license_when_variants_agree(engines_client, monkeypatch):
    import backend.backends as backends_pkg

    monkeypatch.setattr(
        backends_pkg,
        "get_tts_model_configs",
        _qwen_variants(
            _qwen_variant("1.7B", license_id="MIT", commercial_use=True, languages=["en", "zh"], size_mb=3000),
            _qwen_variant("0.6B", license_id="MIT", commercial_use=True, languages=["zh", "ar"], size_mb=1000),
        ),
    )

    qwen = next(e for e in _engines(engines_client) if e["engine"] == "qwen")

    assert qwen["license_id"] == "MIT"
    assert qwen["commercial_use"] is True
    assert qwen["languages"] == ["en", "zh", "ar"]
    assert qwen["size_mb"] == 3000  # the default-size (first) variant
    assert qwen["display_name"] == "Qwen TTS"


def test_engines_route_returns_null_license_when_synthetic_variants_disagree(engines_client, monkeypatch):
    import backend.backends as backends_pkg

    monkeypatch.setattr(
        backends_pkg,
        "get_tts_model_configs",
        _qwen_variants(
            _qwen_variant("1.7B", license_id="MIT", commercial_use=True),
            _qwen_variant("0.6B", license_id="CC-BY-NC-4.0", commercial_use=False),
        ),
    )

    qwen = next(e for e in _engines(engines_client) if e["engine"] == "qwen")

    assert qwen["license_id"] is None
    assert qwen["commercial_use"] is None


def test_current_engine_variants_agree_on_default_variant_fields():
    """The route reads these from the default-size variant; today no variant differs, so nothing is hidden."""
    for engine, variants in _variants_by_engine().items():
        for field_name in (
            "supports_voice_design",
            "requires_download_confirmation",
            "advanced_settings",
            "accelerators",
            "min_memory_mb",
        ):
            values = {getattr(c, field_name) for c in variants}
            assert len(values) == 1, f"{engine}.{field_name} differs across variants: {values}"


def test_engine_configs_declare_the_expected_memory_threshold():
    """Pre-VoxCPM2 engines declare none; VoxCPM2 declares 6144 MB (probe Q8, about 5.9 GB)."""
    from backend.backends import get_tts_model_configs

    for config in get_tts_model_configs():
        if config.engine in PRE_VOXCPM_ENGINES:
            assert config.min_memory_mb is None, config.model_name
        elif config.engine == "voxcpm":
            assert config.min_memory_mb == 6144, config.model_name
        else:
            raise AssertionError(f"unexpected engine {config.engine!r}: add an explicit expectation")


def test_model_config_min_memory_mb_defaults_to_none():
    assert _config().min_memory_mb is None


def test_engines_route_warns_when_memory_is_below_the_declared_threshold(engines_client, monkeypatch):
    import backend.backends as backends_pkg
    import backend.backends.base as base_mod

    monkeypatch.setattr(base_mod, "detect_accelerator_and_memory", lambda: ("cuda", 4096))
    monkeypatch.setattr(
        backends_pkg,
        "get_tts_model_configs",
        _qwen_variants(_qwen_variant("1.7B", accelerators=("cuda", "cpu"), min_memory_mb=8192)),
    )

    qwen = next(e for e in _engines(engines_client) if e["engine"] == "qwen")

    assert qwen["available"] is True
    assert qwen["reason"] is None
    assert qwen["warning"]
    assert "4 GB" in qwen["warning"]


def test_engines_route_has_no_warning_without_a_declared_threshold(engines_client, monkeypatch):
    import backend.backends as backends_pkg
    import backend.backends.base as base_mod

    monkeypatch.setattr(base_mod, "detect_accelerator_and_memory", lambda: ("cuda", 4096))
    monkeypatch.setattr(
        backends_pkg,
        "get_tts_model_configs",
        _qwen_variants(_qwen_variant("1.7B", accelerators=("cuda", "cpu"), min_memory_mb=None)),
    )

    qwen = next(e for e in _engines(engines_client) if e["engine"] == "qwen")

    assert qwen["available"] is True
    assert qwen["reason"] is None
    assert qwen["warning"] is None


def test_engines_route_uses_the_default_variant_memory_threshold(engines_client, monkeypatch):
    import backend.backends as backends_pkg
    import backend.backends.base as base_mod

    monkeypatch.setattr(base_mod, "detect_accelerator_and_memory", lambda: ("cuda", 4096))
    monkeypatch.setattr(
        backends_pkg,
        "get_tts_model_configs",
        _qwen_variants(
            _qwen_variant("1.7B", accelerators=("cuda",), min_memory_mb=None),
            _qwen_variant("0.6B", accelerators=("cuda",), min_memory_mb=8192),
        ),
    )

    qwen = next(e for e in _engines(engines_client) if e["engine"] == "qwen")

    assert qwen["warning"] is None


def test_engines_route_engine_ids_match_the_request_engine_pattern(engines_client):
    from backend.models import GenerationRequest

    for entry in _engines(engines_client):
        GenerationRequest(profile_id="p1", text="hello", engine=entry["engine"])


def _constrained_default_qwen(**overrides):
    """Real TTS configs, with the default qwen config replaced by a declared test config."""
    from backend.backends import get_tts_model_configs as real_configs

    values = {
        "model_name": "qwen-test",
        "display_name": "Qwen Test",
        "engine": "qwen",
        "hf_repo_id": "example/qwen-test",
        "model_size": "1.7B",
    }
    values.update(overrides)
    fake = ModelConfig(**values)
    configs = [fake] + [c for c in real_configs() if c.engine != "qwen"]
    return lambda: configs


def test_engines_route_invariants_hold_for_a_constrained_engine(engines_client, monkeypatch):
    import backend.backends as backends_pkg

    monkeypatch.setattr(backends_pkg, "get_tts_model_configs", _constrained_default_qwen(accelerators=("mps",)))

    engines = {e["engine"]: e for e in _engines(engines_client)}

    qwen = engines["qwen"]
    assert qwen["available"] is False
    assert qwen["reason"]
    assert qwen["warning"] is None
    assert qwen["supported_accelerators"] == ["mps"]
    for entry in engines.values():
        # Invariant 1 (and its converse): a reason exactly when unavailable.
        assert (entry["reason"] is not None) == (not entry["available"])
        # Invariant 2: unconstrained engines are always offered.
        if not entry["supported_accelerators"]:
            assert entry["available"] is True
        # Invariant 3: an unavailable engine carries a reason, not a warning.
        if not entry["available"]:
            assert entry["warning"] is None


def test_engines_route_passes_declared_capabilities_through(engines_client, monkeypatch):
    import backend.backends as backends_pkg

    setting = AdvancedSetting(name="cfg_value", label="Guidance", default=2.0, min=1.0, max=5.0)
    monkeypatch.setattr(
        backends_pkg,
        "get_tts_model_configs",
        _constrained_default_qwen(
            accelerators=("cuda", "cpu"),
            supports_voice_design=True,
            requires_download_confirmation=True,
            advanced_settings=(setting,),
        ),
    )

    qwen = next(e for e in _engines(engines_client) if e["engine"] == "qwen")

    assert qwen["available"] is True
    assert qwen["supported_accelerators"] == ["cuda", "cpu"]
    assert qwen["supports_voice_design"] is True
    assert qwen["requires_download_confirmation"] is True
    assert qwen["advanced_settings"] == [
        {"name": "cfg_value", "label": "Guidance", "default": 2.0, "min": 1.0, "max": 5.0}
    ]
    # The test config declares no memory threshold, so the marginal 6 GB machine gets no warning.
    assert qwen["warning"] is None


def test_engines_route_never_imports_torch(engines_client):
    had_torch = "torch" in sys.modules

    _engines(engines_client)

    assert ("torch" in sys.modules) == had_torch


# --- GenerationRequest: voice_description and advanced_settings -----------


_BASE_REQUEST = {"profile_id": "p1", "text": "hello"}


def test_existing_generation_payloads_still_validate():
    from backend.models import GenerationRequest

    request = GenerationRequest(**_BASE_REQUEST, engine="kokoro", language="en", instruct="calm")

    assert request.voice_description is None
    assert request.advanced_settings is None


@pytest.mark.parametrize("engine", [None, "qwen", "kokoro", "f5_tts"])
@pytest.mark.parametrize("value", [None, {}])
def test_empty_advanced_settings_pass_for_every_engine(engine, value):
    from backend.models import GenerationRequest

    request = GenerationRequest(**_BASE_REQUEST, engine=engine, advanced_settings=value)

    assert request.advanced_settings == value


@pytest.mark.parametrize("engine", [None, "qwen", "luxtts", "chatterbox", "tada", "kokoro", "f5_tts"])
def test_existing_engines_reject_any_advanced_setting(engine):
    from backend.models import GenerationRequest

    with pytest.raises(ValidationError, match="cfg_value"):
        GenerationRequest(**_BASE_REQUEST, engine=engine, advanced_settings={"cfg_value": 2.0})


def test_voice_description_accepts_500_characters_and_rejects_501():
    from backend.models import GenerationRequest

    assert GenerationRequest(**_BASE_REQUEST, voice_description="a" * 500).voice_description == "a" * 500
    with pytest.raises(ValidationError):
        GenerationRequest(**_BASE_REQUEST, voice_description="a" * 501)


@pytest.fixture
def declared_qwen(monkeypatch):
    """Make the default qwen config declare one bounded setting, without adding a real engine."""
    import backend.backends as backends_pkg

    setting = AdvancedSetting(name="cfg_value", label="Guidance", default=2.0, min=1.0, max=5.0)
    monkeypatch.setattr(backends_pkg, "get_tts_model_configs", _constrained_default_qwen(advanced_settings=(setting,)))


@pytest.mark.parametrize("engine", ["qwen", None])
@pytest.mark.parametrize("value", [1.0, 2.5, 5.0, 3])
def test_declared_setting_within_bounds_passes(declared_qwen, engine, value):
    from backend.models import GenerationRequest

    request = GenerationRequest(**_BASE_REQUEST, engine=engine, advanced_settings={"cfg_value": value})

    assert request.advanced_settings == {"cfg_value": float(value)}


@pytest.mark.parametrize("value", [0.99, 5.01, -1.0, float("inf"), float("nan")])
def test_declared_setting_out_of_bounds_is_rejected(declared_qwen, value):
    from backend.models import GenerationRequest

    with pytest.raises(ValidationError, match="cfg_value"):
        GenerationRequest(**_BASE_REQUEST, engine="qwen", advanced_settings={"cfg_value": value})


def test_undeclared_setting_is_rejected_even_when_the_engine_declares_others(declared_qwen):
    from backend.models import GenerationRequest

    with pytest.raises(ValidationError, match="not_a_setting"):
        GenerationRequest(**_BASE_REQUEST, engine="qwen", advanced_settings={"cfg_value": 2.0, "not_a_setting": 1.0})


def test_declared_setting_is_scoped_to_its_engine(declared_qwen):
    from backend.models import GenerationRequest

    with pytest.raises(ValidationError, match="cfg_value"):
        GenerationRequest(**_BASE_REQUEST, engine="kokoro", advanced_settings={"cfg_value": 2.0})


def test_invalid_generation_body_is_a_422_through_fastapi(declared_qwen):
    from backend.models import GenerationRequest

    app = FastAPI()

    @app.post("/probe")
    def probe(request: GenerationRequest):
        return {"ok": True}

    client = TestClient(app)

    assert client.post("/probe", json=_BASE_REQUEST).status_code == 200
    assert client.post("/probe", json={**_BASE_REQUEST, "advanced_settings": {"cfg_value": 2.0}}).status_code == 200
    for body in (
        {**_BASE_REQUEST, "advanced_settings": {"cfg_value": 9.0}},
        {**_BASE_REQUEST, "advanced_settings": {"unknown": 1.0}},
        {**_BASE_REQUEST, "engine": "kokoro", "advanced_settings": {"cfg_value": 2.0}},
        {**_BASE_REQUEST, "voice_description": "a" * 501},
    ):
        assert client.post("/probe", json=body).status_code == 422, body


# --- VoxCPM2: the first engine that declares capabilities (T016) ----------------------------


VOXCPM_ACCELERATORS = ["cuda", "mps", "cpu"]


def _voxcpm_config():
    (config,) = [c for c in get_tts_model_configs() if c.engine == "voxcpm"]
    return config


@pytest.mark.parametrize("detected", VOXCPM_ACCELERATORS)
@pytest.mark.parametrize("memory_mb", [6144, 16384, None])
def test_voxcpm_is_available_without_warning_on_its_accelerators(detected, memory_mb):
    config = _voxcpm_config()

    result = resolve_engine_availability(config, detected, memory_mb=memory_mb, min_memory_mb=config.min_memory_mb)

    assert result.available is True
    assert result.reason is None
    assert result.warning is None
    assert result.supported_accelerators == VOXCPM_ACCELERATORS


def test_voxcpm_warns_but_stays_available_on_a_4gb_gpu():
    config = _voxcpm_config()

    result = resolve_engine_availability(config, "cuda", memory_mb=4096, min_memory_mb=config.min_memory_mb)

    assert result.available is True
    assert result.reason is None
    assert result.warning
    assert "VoxCPM2" in result.warning


@pytest.mark.parametrize("detected", ["xpu", "directml"])
def test_voxcpm_is_unavailable_with_a_reason_on_other_accelerators(detected):
    config = _voxcpm_config()

    result = resolve_engine_availability(config, detected, memory_mb=16384, min_memory_mb=config.min_memory_mb)

    assert result.available is False
    assert result.reason is not None
    assert result.warning is None


def test_engines_route_describes_voxcpm_from_its_declaration(engines_client):
    voxcpm = next(e for e in _engines(engines_client) if e["engine"] == "voxcpm")

    assert voxcpm["display_name"] == "VoxCPM2"
    assert voxcpm["supported_accelerators"] == VOXCPM_ACCELERATORS
    assert voxcpm["detected_accelerator"] == "cuda"
    # The fixture's machine has exactly 6144 MB, which meets the declared threshold.
    assert voxcpm["available"] is True
    assert voxcpm["reason"] is None
    assert voxcpm["warning"] is None
    assert voxcpm["requires_download_confirmation"] is True
    assert voxcpm["supports_voice_design"] is True
    assert voxcpm["advanced_settings"] == [
        {"name": "cfg_value", "label": "Guidance", "default": 2.0, "min": 1.0, "max": 3.0},
        {"name": "inference_timesteps", "label": "Quality steps", "default": 10, "min": 4, "max": 30},
    ]
    assert voxcpm["size_mb"] == 4961
    assert voxcpm["license_id"] == "Apache-2.0"
    assert voxcpm["commercial_use"] is True
    assert len(voxcpm["languages"]) == 30
    assert "ar" in voxcpm["languages"]
