"""Tests for the interactive pad calibration tool."""

import tomllib

import cv2
import numpy as np
import pytest

from src.cli.calibrate import roll_verdict
from src.cli.frame_view import polygon_toml
from src.cli.quad_geometry import is_bowtie, line_roll_deg, roll_from_quad

PROPER = [(170, 50), (400, 40), (550, 320), (210, 350)]
CROSSED = [(170, 50), (550, 320), (400, 40), (210, 350)]
BASE_ROLL = 24.86


def project_pad(roll_deg: float):
    """Image of a flat pad rectangle seen by a camera with the given roll."""
    pitch = np.radians(30.0)
    roll = np.radians(roll_deg)
    r_x = np.array([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)], [0, np.sin(pitch), np.cos(pitch)]])
    r_z = np.array([[np.cos(roll), -np.sin(roll), 0], [np.sin(roll), np.cos(roll), 0], [0, 0, 1]])
    rotation = r_z @ r_x

    camera = np.array([0.0, 0.0, 1.5])
    corners = [(-0.35, 1.0, 0.0), (0.35, 1.0, 0.0), (0.35, 1.7, 0.0), (-0.35, 1.7, 0.0)]
    image = []
    for corner in corners:
        p = rotation @ (np.array(corner) - camera)
        image.append((500.0 * p[0] / p[2] + 320.0, 500.0 * p[1] / p[2] + 180.0))
    return image


def test_bowtie_detection():
    """A crossed corner order fills the wrong region, so it must be rejected."""
    assert not is_bowtie(PROPER)
    assert is_bowtie(CROSSED)
    # Fewer than four corners cannot be a bowtie yet.
    assert not is_bowtie(PROPER[:3])


def test_polygon_toml_round_trips():
    """The printed block must load back as the same corner list."""
    parsed = tomllib.loads("[zone]\n" + polygon_toml(PROPER))
    assert parsed["zone"]["polygon"] == [[x, y] for x, y in PROPER]


def test_roll_from_quad_recovers_a_known_tilt():
    """The whole point of the measurement: a rolled camera must read back exactly."""
    for truth in (0.0, 9.0, -14.5):
        measured = roll_from_quad(project_pad(truth))
        assert measured is not None
        assert abs(measured - truth) < 0.01, f"roll {truth} measured as {measured}"


def test_roll_from_quad_needs_four_corners():
    assert roll_from_quad(PROPER[:3]) is None


def test_line_roll_deg_is_the_angle_cv2_needs():
    """Rotating the frame by the reported angle must leave the drawn line vertical."""
    for lean in (20.0, -20.0, 7.5, 0.0):
        start = (100.0, 200.0)
        end = (100.0 + 120.0 * np.sin(np.radians(lean)), 200.0 - 120.0 * np.cos(np.radians(lean)))
        angle = line_roll_deg(start, end)
        # Click order must not flip the sign.
        assert abs(line_roll_deg(end, start) - angle) < 1e-9
        matrix = cv2.getRotationMatrix2D((0.0, 0.0), angle, 1.0)
        rotated = matrix[:, :2] @ np.array([end[0] - start[0], end[1] - start[1]], dtype=float)
        assert abs(rotated[0]) < 1e-6, f"lean {lean} left {rotated[0]} horizontal component"


# -- what the tool tells the user to write into config ---------------------


def test_no_measurement_leaves_the_roll_alone():
    """A pad click with no angles read must not overwrite the camera angle."""
    notes, corrected = roll_verdict(BASE_ROLL, None, None)
    assert corrected is None
    assert any("그대로 두세요" in note for note in notes)


def test_unchanged_camera_keeps_the_roll():
    for line, pad in ((0.3, 0.9), (None, 0.4), (0.2, None)):
        notes, corrected = roll_verdict(BASE_ROLL, line, pad)
        assert corrected is None, f"line={line} pad={pad}"
        assert any("유지" in note for note in notes)


def test_a_nudged_camera_composes_the_residual():
    """The residual is a correction on top of the config, not an absolute angle."""
    _, corrected = roll_verdict(BASE_ROLL, 2.31, 2.31)
    assert corrected == pytest.approx(BASE_ROLL + 2.31)


def test_negative_residual_composes_too():
    _, corrected = roll_verdict(BASE_ROLL, -3.0, None)
    assert corrected == pytest.approx(BASE_ROLL - 3.0)


def test_disagreeing_estimates_are_refused():
    """Both measure the same angle, so a wide gap means a bad measurement."""
    notes, corrected = roll_verdict(BASE_ROLL, 6.0, -1.0)
    assert corrected is None
    assert any("벌어집니다" in note for note in notes)


def test_pad_estimate_alone_still_composes():
    """The pad rectangle is a valid second opinion when no red line was drawn."""
    _, corrected = roll_verdict(BASE_ROLL, None, -4.0)
    assert corrected == pytest.approx(BASE_ROLL - 4.0)


def test_agreeing_estimates_are_averaged():
    """Both are unbiased readings of one angle, so averaging cuts click noise."""
    _, corrected = roll_verdict(BASE_ROLL, 4.0, 6.0)
    assert corrected == pytest.approx(BASE_ROLL + 5.0)
