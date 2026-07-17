"""Tests for multi-GPU device selection shared by model backends."""

import sys
from types import SimpleNamespace

from backend.backends.base import get_torch_device


class _FakeCuda:
    def is_available(self):
        return True

    def device_count(self):
        return 2

    def mem_get_info(self, index):
        return ((2, 16)[index] * 1024**3, 24 * 1024**3)

    def get_device_name(self, index):
        return f"GPU {index}"


def _install_fake_torch(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=_FakeCuda()))


def test_selects_cuda_device_with_most_free_memory(monkeypatch):
    _install_fake_torch(monkeypatch)

    assert get_torch_device(prefer_cuda_with_most_free_memory=True) == "cuda:1"


def test_cuda_device_environment_override_wins(monkeypatch):
    _install_fake_torch(monkeypatch)
    monkeypatch.setenv("VOICEBOX_TADA_CUDA_DEVICE", "cuda:0")

    assert (
        get_torch_device(
            cuda_device_env="VOICEBOX_TADA_CUDA_DEVICE",
            prefer_cuda_with_most_free_memory=True,
        )
        == "cuda:0"
    )


def test_auto_override_uses_free_memory_selection(monkeypatch):
    _install_fake_torch(monkeypatch)
    monkeypatch.setenv("VOICEBOX_TADA_CUDA_DEVICE", "auto")

    assert (
        get_torch_device(
            cuda_device_env="VOICEBOX_TADA_CUDA_DEVICE",
            prefer_cuda_with_most_free_memory=True,
        )
        == "cuda:1"
    )
