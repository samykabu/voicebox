"""The HF cache symlink probe must switch huggingface_hub to copy mode when links cannot be read."""

from pathlib import Path

import pytest
from huggingface_hub import file_download

from backend.app import disable_hf_symlinks_if_unreadable


@pytest.fixture
def restore_hf(monkeypatch):
    monkeypatch.setattr(file_download, "are_symlinks_supported", file_download.are_symlinks_supported)
    yield


def test_readable_symlinks_leave_hf_alone(tmp_path, restore_hf):
    original = file_download.are_symlinks_supported
    assert disable_hf_symlinks_if_unreadable(tmp_path) is False
    assert file_download.are_symlinks_supported is original


def test_unreadable_symlinks_make_hf_copy_files(tmp_path, restore_hf, monkeypatch):
    real_read_text = Path.read_text

    def failing_read_text(self, *args, **kwargs):
        if self.name == "dst":
            raise OSError(22, "Invalid argument", str(self))
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", failing_read_text)
    assert disable_hf_symlinks_if_unreadable(tmp_path) is True
    # huggingface_hub consults this per model directory; it must say no everywhere now.
    assert file_download.are_symlinks_supported(tmp_path / "models--x--y") is False

    # And _create_symlink must then produce a real file, not a link.
    blob = tmp_path / "blobs" / "abc"
    blob.parent.mkdir()
    blob.write_text("payload")
    pointer = tmp_path / "snapshots" / "sha" / "config.yaml"
    pointer.parent.mkdir(parents=True)
    file_download._create_symlink(str(blob), str(pointer), new_blob=False)
    assert pointer.is_file() and not pointer.is_symlink()
    assert pointer.read_text() == "payload"
