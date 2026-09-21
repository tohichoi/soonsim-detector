"""Tests for the interactive pad calibration tool."""

import tomllib

import numpy as np

from src.cli.calibrate import is_bowtie, polygon_toml, roll_from_quad

PROPER = [(170, 50), (400, 40), (550, 320), (210, 350)]
CROSSED = [(170, 50), (550, 320), (400, 40), (210, 350)]


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
