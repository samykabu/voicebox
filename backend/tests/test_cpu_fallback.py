"""FR-023: an engine that declares the processor runs there when no supported accelerator is found.

On an Intel XPU or DirectML machine the detector reports that accelerator, but an engine that
declares ("cuda", "mps", "cpu") (VoxCPM2) resolves its own device without XPU or DirectML and so
genuinely runs on the processor. It must be offered and allowed, with an advisory warning, not
refused. An engine that does not declare the processor is still refused, and its reason never
claims the machine lacks something it has. Hardware is injected; nothing here needs torch.
"""

import pytest

from backend.backends import ModelConfig, get_tts_model_configs
from backend.backends.base import resolve_engine_availability
from backend.tests import test_engine_capabilities as capabilities
from backend.tests.test_engine_capabilities import (
    PRE_VOXCPM_ENGINES,
    _call_entry_point,
    _constrained_default_qwen,
    _engines,
)

# Reuse the route-test fixtures (fixed hardware, guarded load and download paths).
engines_client = capabilities.engines_client
generation_app = capabilities.generation_app

FALLBACK_HARDWARE = ["xpu", "directml"]
LABELS = {"xpu": "Intel XPU", "directml": "DirectML"}


def _config(**overrides) -> ModelConfig:
    values = {
        "model_name": "test-model",
        "display_name": "Test Engine",
        "engine": "testengine",
        "hf_repo_id": "example/test-model",
    }
    values.update(overrides)
    return ModelConfig(**values)


def _voxcpm_config():
    (config,) = [c for c in get_tts_model_configs() if c.engine == "voxcpm"]
    return config


def _fallback_warning(name, detected):
    return f"{name} doesn't support {LABELS[detected]} here, so it will run on the processor, which is slower."


# --- Pure resolution ---------------------------------------------------------------------


@pytest.mark.parametrize("detected", FALLBACK_HARDWARE)
@pytest.mark.parametrize("memory_mb", [None, 1024, 16384])
def test_voxcpm_falls_back_to_the_processor_on_xpu_and_directml(detected, memory_mb):
    config = _voxcpm_config()

    result = resolve_engine_availability(config, detected, memory_mb=memory_mb, min_memory_mb=config.min_memory_mb)

    assert result.available is True
    assert result.reason is None
    # The CUDA memory warning never applies to a processor fallback; only the fallback warning.
    assert result.warning == _fallback_warning(config.display_name, detected)
    # Truthful: the machine's accelerator is still reported as detected.
    assert result.detected_accelerator == detected
    assert result.supported_accelerators == ["cuda", "mps", "cpu"]


def test_fallback_applies_to_any_engine_that_declares_the_processor():
    result = resolve_engine_availability(_config(accelerators=("cuda", "cpu")), "mps")

    assert result.available is True
    assert result.reason is None
    assert result.warning == (
        "Test Engine doesn't support Apple Silicon (MPS) here, so it will run on the processor, which is slower."
    )
    assert result.detected_accelerator == "mps"


@pytest.mark.parametrize("detected", FALLBACK_HARDWARE)
def test_engine_without_the_processor_is_still_unavailable_on_xpu_and_directml(detected):
    result = resolve_engine_availability(_config(accelerators=("cuda",)), detected, memory_mb=1024, min_memory_mb=8192)

    assert result.available is False
    assert result.warning is None
    assert result.reason
    assert "Test Engine" in result.reason
    assert "CUDA" in result.reason
    assert LABELS[detected] in result.reason
    # Never names the processor as something the machine lacks.
    assert "CPU" not in result.reason
    assert "processor" not in result.reason
    assert result.detected_accelerator == detected


@pytest.mark.parametrize("accelerators", [("cuda",), ("cuda", "mps"), ("mps",), ("cuda", "mps", "cpu"), ("cpu",)])
@pytest.mark.parametrize("detected", ["cuda", "mps", "cpu", "xpu", "directml"])
def test_an_unavailable_reason_never_lists_what_the_machine_has(accelerators, detected):
    result = resolve_engine_availability(_config(accelerators=accelerators), detected)

    if "cpu" in accelerators or detected in accelerators:
        assert result.available is True
        return
    assert result.available is False
    # Every machine has a processor, so a reason may name CPU only as what was detected.
    if detected != "cpu":
        assert "CPU" not in result.reason


@pytest.mark.parametrize("detected", ["cuda", "mps", "cpu"])
def test_voxcpm_on_its_declared_accelerators_is_unchanged(detected):
    config = _voxcpm_config()

    result = resolve_engine_availability(config, detected, memory_mb=16384, min_memory_mb=config.min_memory_mb)

    assert (result.available, result.reason, result.warning, result.detected_accelerator) == (
        True,
        None,
        None,
        detected,
    )


def test_voxcpm_cuda_memory_warning_is_unchanged():
    config = _voxcpm_config()

    result = resolve_engine_availability(config, "cuda", memory_mb=4096, min_memory_mb=config.min_memory_mb)

    assert result.available is True
    assert result.reason is None
    assert result.warning == (
        f"This machine has about 4 GB of graphics memory. {config.display_name} usually needs about 6 GB, "
        "so generation may fail."
    )


@pytest.mark.parametrize("detected", ["cuda", "mps", "cpu", "xpu", "directml"])
def test_undeclared_engines_are_unchanged(detected):
    result = resolve_engine_availability(_config(), detected, memory_mb=1024, min_memory_mb=8192)

    assert (result.available, result.reason, result.warning, result.supported_accelerators) == (True, None, None, [])


# --- The refusal path --------------------------------------------------------------------


@pytest.mark.parametrize("detected", FALLBACK_HARDWARE)
def test_ensure_engine_available_allows_voxcpm_on_xpu_and_directml(monkeypatch, detected):
    import backend.backends.base as base_mod
    from backend.services import generation as generation_service

    monkeypatch.setattr(base_mod, "detect_accelerator_and_memory", lambda: (detected, None))

    generation_service.ensure_engine_available("voxcpm")  # must not raise


@pytest.mark.parametrize("detected", FALLBACK_HARDWARE)
def test_ensure_engine_available_still_refuses_an_engine_without_the_processor(monkeypatch, detected):
    import backend.backends as backends_pkg
    import backend.backends.base as base_mod
    from backend.services import generation as generation_service

    monkeypatch.setattr(backends_pkg, "get_tts_model_configs", _constrained_default_qwen(accelerators=("cuda",)))
    monkeypatch.setattr(base_mod, "detect_accelerator_and_memory", lambda: (detected, None))

    with pytest.raises(generation_service.EngineUnavailableError) as excinfo:
        generation_service.ensure_engine_available("qwen")

    assert "Qwen Test" in excinfo.value.reason
    assert "CPU" not in excinfo.value.reason


# --- Route level ------------------------------------------------------------------------


def test_engines_route_offers_voxcpm_on_directml_with_the_fallback_warning(engines_client, monkeypatch):
    import backend.backends.base as base_mod

    monkeypatch.setattr(base_mod, "detect_accelerator_and_memory", lambda: ("directml", None))

    engines = {e["engine"]: e for e in _engines(engines_client)}

    voxcpm = engines["voxcpm"]
    assert voxcpm["available"] is True
    assert voxcpm["reason"] is None
    assert voxcpm["warning"] == _fallback_warning(_voxcpm_config().display_name, "directml")
    assert voxcpm["detected_accelerator"] == "directml"
    for engine in PRE_VOXCPM_ENGINES:
        assert engines[engine]["available"] is True
        assert engines[engine]["warning"] is None


@pytest.mark.parametrize("detected", FALLBACK_HARDWARE)
@pytest.mark.parametrize("entry_point", ["generate", "stream", "retry", "regenerate", "speak", "mcp_speak"])
async def test_generation_proceeds_for_voxcpm_on_xpu_and_directml(generation_app, entry_point, detected):
    generation_app.forbid = False
    generation_app.hardware = (detected, None)

    status_code, detail = await _call_entry_point(generation_app, entry_point, "voxcpm")

    assert status_code == 200, (status_code, detail)
    assert generation_app.calls, "a processor-fallback engine must reach the generation pipeline"
