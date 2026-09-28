"""Tests for configuration parsing."""

from pathlib import Path
from src.config import load_config


def test_load_config_default_fallback():
    """Verify loading config from existing example or defaults."""
    config = load_config("config/config.example.toml")
    assert config.camera.fps == 15
    assert len(config.zone.polygon) >= 3
    assert config.detector.animal_class_ids == [15, 16, 77]
    assert config.recorder.pre_buffer_sec == 5
    assert config.telegram.instant_alert_enabled is False
    assert config.telegram.instant_alert_stay_sec == 1.0


def test_load_config_nonexistent(tmp_path: Path):
    """Verify fallback when non-existent config path provided."""
    config = load_config(tmp_path / "nonexistent.toml")
    assert config.camera.fps == 15
