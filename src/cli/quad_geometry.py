"""Quad geometry for the pad zone: corner order checks and camera roll.

Pure math with no I/O, split out of the calibration CLI so both stay small and
the geometry can be tested on its own.
"""

from typing import List, Optional, Tuple

import numpy as np

CORNER_COUNT = 4
VERTICAL_POINT_COUNT = 2


def _scalar_cross(origin: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Sign of the turn from origin->a to origin->b.

    numpy 2 dropped 2-D np.cross, so this is done by hand.
    """
    oa, ob = a - origin, b - origin
    return float(oa[0] * ob[1] - oa[1] * ob[0])


def segments_cross(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> bool:
    """True when segment ab crosses segment cd, ignoring shared endpoints."""
    if {tuple(a), tuple(b)} & {tuple(c), tuple(d)}:
        return False
    d1, d2 = _scalar_cross(c, d, a), _scalar_cross(c, d, b)
    d3, d4 = _scalar_cross(a, b, c), _scalar_cross(a, b, d)
    return d1 * d2 < 0 and d3 * d4 < 0


def is_bowtie(points: List[Tuple[int, int]]) -> bool:
    """True when the four corners cross over, which fills the wrong region."""
    if len(points) != CORNER_COUNT:
        return False
    a, b, c, d = (np.array(p, dtype=float) for p in points)
    return segments_cross(a, b, c, d) or segments_cross(b, c, d, a)


def _line_through(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Homogeneous line through two points."""
    (ax, ay), (bx, by) = a, b
    return np.array([ay - by, bx - ax, ax * by - ay * bx], dtype=float)


def line_roll_deg(start: Tuple[int, int], end: Tuple[int, int]) -> float:
    """Angle to feed cv2.getRotationMatrix2D to make a drawn line vertical.

    Draw the line along something the world knows is vertical -- a wall seam, a
    door frame -- and its tilt is the camera roll. Positive leans right at the
    top and the returned angle is the counter-clockwise correction, which is
    exactly the convention getRotationMatrix2D uses.
    """
    dx = float(end[0] - start[0])
    dy = float(end[1] - start[1])
    if dy > 0:  # orient the vector upward so the sign does not depend on click order
        dx, dy = -dx, -dy
    if dx == 0.0 and dy == 0.0:
        return 0.0
    return float(np.degrees(np.arctan2(dx, -dy)))


def roll_from_quad(points: List[Tuple[int, int]]) -> Optional[float]:
    """Camera roll implied by a photograph of the pad, in degrees.

    The pad is a flat rectangle, so its two pairs of opposite edges converge to
    two vanishing points. Both lie on the horizon, and the horizon is level in
    the image exactly when the camera is not rolled -- so the horizon's tilt is
    the roll, with no known-vertical reference needed in the scene.

    Built from the vanishing line rather than from two divided points, because a
    camera with no yaw puts one of the vanishing points at infinity.

    Corners must be the pad's real corners, in perimeter order; a hand-drawn
    region that is not the pad gives a meaningless answer.
    """
    if len(points) != CORNER_COUNT:
        return None
    p0, p1, p2, p3 = (np.asarray(p, dtype=float) for p in points)
    vp1 = np.cross(_line_through(p0, p1), _line_through(p2, p3))
    vp2 = np.cross(_line_through(p1, p2), _line_through(p3, p0))
    if np.allclose(vp1, 0) or np.allclose(vp2, 0):
        return None
    a, b, _ = np.cross(vp1, vp2)
    if abs(a) < 1e-9 and abs(b) < 1e-9:
        return None
    angle = float(np.degrees(np.arctan2(a, -b)))
    return (angle + 90.0) % 180.0 - 90.0
