"""Tests for pruning clips that have aged out of the retention window."""

import os
import time
from pathlib import Path

import pytest
from src.recorder.exporter import prune_old_clips

THIRTY_DAYS = 30 * 86400.0


@pytest.fixture
def records(tmp_path: Path) -> Path:
    """A records directory holding old clips, a fresh clip, and non-clip files."""
    age = {"soonsim_old.mp4": THIRTY_DAYS * 2, "signal_old.mp4": THIRTY_DAYS * 2,
           "other.mp4": THIRTY_DAYS * 2, "detection.log": THIRTY_DAYS * 2,
           "soonsim_new.mp4": 0.0}
    for name, old_by in age.items():
        path = tmp_path / name
        path.write_bytes(b"x")
        os.utime(path, (time.time() - old_by, time.time() - old_by))
    return tmp_path


def test_only_old_clips_are_removed(records: Path) -> None:
    """Delete our aged-out clips and nothing else in the directory."""
    assert prune_old_clips(records, retention_days=30.0) == 2

    remaining = sorted(p.name for p in records.iterdir())
    assert remaining == ["detection.log", "other.mp4", "soonsim_new.mp4"]


def test_zero_days_keeps_everything(records: Path) -> None:
    """An explicit 0 is how retention gets switched off."""
    assert prune_old_clips(records, retention_days=0.0) == 0
    assert len(list(records.iterdir())) == 5


def test_a_long_window_removes_nothing(records: Path) -> None:
    assert prune_old_clips(records, retention_days=365.0) == 0
    assert len(list(records.iterdir())) == 5


def test_missing_directory_is_not_an_error(tmp_path: Path) -> None:
    """The output directory may not exist yet on a fresh deploy."""
    assert prune_old_clips(tmp_path / "nope", retention_days=30.0) == 0
