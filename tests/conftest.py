"""Pytest fixtures and test doubles."""

from pathlib import Path
import numpy as np
import pytest
from src.capture.stream import FramePacket
from src.config import AppConfig, CameraConfig, DetectorConfig, RecorderConfig, TelegramConfig, ZoneConfig


@pytest.fixture
def mock_config(tmp_path: Path) -> AppConfig:
    """Return test AppConfig."""
    return AppConfig(
        camera=CameraConfig(source="dummy.mp4", fps=10, reconnect_interval_sec=1.0),
        zone=ZoneConfig(polygon=[[100, 100], [300, 100], [300, 300], [100, 300]]),
        detector=DetectorConfig(model_name="yolov8n.pt", confidence_threshold=0.3),
        recorder=RecorderConfig(
            pre_buffer_sec=2,
            post_buffer_sec=2,
            output_dir=tmp_path / "records",
            min_stay_duration_sec=0.5,
        ),
        telegram=TelegramConfig(enabled=False),
    )


@pytest.fixture
def sample_frame() -> np.ndarray:
    """Return 640x360 blank image."""
    return np.zeros((360, 640, 3), dtype=np.uint8)


@pytest.fixture
def sample_frame_packet(sample_frame: np.ndarray) -> FramePacket:
    """Return sample FramePacket."""
    return FramePacket(frame=sample_frame, timestamp=1000.0, frame_idx=1)
