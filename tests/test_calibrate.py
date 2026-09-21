"""Tests for the interactive pad calibration tool."""

import tomllib

from src.cli.calibrate import is_bowtie, polygon_toml

PROPER = [(170, 50), (400, 40), (550, 320), (210, 350)]
CROSSED = [(170, 50), (550, 320), (400, 40), (210, 350)]


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
