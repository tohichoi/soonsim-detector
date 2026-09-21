"""Tests for the camera-roll frame correction."""

import cv2
import numpy as np

from src.cli.quad_geometry import line_roll_deg
from src.utils.rotation import FrameRotator


def measure_lean_deg(frame: np.ndarray) -> float:
    """Tilt of the drawn line in the frame, in degrees from vertical."""
    ys, xs = np.nonzero(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    points = np.column_stack([xs, ys]).astype(np.float32)
    _mean, eigenvectors = cv2.PCACompute(points, mean=None)
    vx, vy = (float(v) for v in eigenvectors[0])
    if vy > 0:
        vx, vy = -vx, -vy
    return float(np.degrees(np.arctan2(vx, -vy)))


def leaning_line(lean_deg: float) -> tuple:
    """Frame with a world-vertical line drawn at the given lean."""
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    angle = np.radians(lean_deg)
    start = (320, 300)
    end = (int(320 + 200 * np.sin(angle)), int(300 - 200 * np.cos(angle)))
    cv2.line(frame, start, end, (255, 255, 255), 3)
    return frame, start, end


def test_frame_rotator_straightens_a_drawn_line():
    """The whole point of the correction: a leaned frame comes back upright."""
    for lean in (25.0, -18.0, 0.0):
        frame, start, end = leaning_line(lean)
        assert abs(measure_lean_deg(frame) - lean) < 1.5
        straightened = FrameRotator(line_roll_deg(start, end)).apply(frame)
        assert abs(measure_lean_deg(straightened)) < 1.5, f"lean {lean} did not come back"


def test_rotator_disabled_returns_the_same_frame():
    """roll_deg 0 must leave the pipeline exactly as it was before this option."""
    frame = np.zeros((40, 60, 3), dtype=np.uint8)
    rotator = FrameRotator(0.0)
    assert not rotator.enabled
    assert rotator.apply(frame) is frame


def test_credentials_are_masked_but_the_rest_of_the_url_survives():
    """A camera URL reaches the log on every reconnect; the password must not."""
    from src.utils.masking import mask_url_credentials

    masked = mask_url_credentials("rtsp://soonsim:secret@192.168.45.208/stream2")
    assert masked == "rtsp://<credentials>@192.168.45.208/stream2"
    assert "secret" not in masked

    # A password containing '@' must be masked whole, not only up to the first one.
    assert "ss@host" not in mask_url_credentials("rtsp://u:p@ss@host/s")
    assert mask_url_credentials("rtsp://u:p@ss@host/s") == "rtsp://<credentials>@host/s"


def test_masking_leaves_credential_free_sources_alone():
    from src.utils.masking import mask_url_credentials

    assert mask_url_credentials("./sample.mp4") == "./sample.mp4"
    assert mask_url_credentials("rtsp://192.168.45.208/stream2") == "rtsp://192.168.45.208/stream2"
