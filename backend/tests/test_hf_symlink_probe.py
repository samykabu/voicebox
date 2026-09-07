"""The HF cache symlink probe must disable symlinks when links cannot be read."""

from pathlib import Path

import pytest
from huggingface_hub import file_download

from backend.app import disable_hf_symlinks_if_unreadable


def _key(path: Path) -> str:
    return str(path.expanduser().resolve())


def test_readable_symlinks_leave_hf_alone(tmp_path):
    before = dict(file_download._are_symlinks_supported_in_dir)
    try:
        assert disable_hf_symlinks_if_unreadable(tmp_path) is False
        assert _key(tmp_path) not in file_download._are_symlinks_supported_in_dir
    finally:
        file_download._are_symlinks_supported_in_dir.clear()
        file_download._are_symlinks_supported_in_dir.update(before)


def test_unreadable_symlinks_disable_hf_symlinks(tmp_path, monkeypatch):
    real_read_text = Path.read_text

    def failing_read_text(self, *args, **kwargs):
        if self.name == "dst":
            raise OSError(22, "Invalid argument", str(self))
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", failing_read_text)
    before = dict(file_download._are_symlinks_supported_in_dir)
    try:
        assert disable_hf_symlinks_if_unreadable(tmp_path) is True
        assert file_download._are_symlinks_supported_in_dir[_key(tmp_path)] is False
        assert file_download.are_symlinks_supported(tmp_path) is False
    finally:
        file_download._are_symlinks_supported_in_dir.clear()
        file_download._are_symlinks_supported_in_dir.update(before)
