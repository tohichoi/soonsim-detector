"""Frame rotation used to cancel a rolled camera.

Zone entry is decided by points on the axis-aligned detection box, so a camera
that is rolled puts those points off the dog's feet. Rotating every incoming
frame by the measured roll restores the assumption, and the pad polygon is then
drawn in the rotated view.

The angle is the same one the calibration tool reports: positive follows
cv2.getRotationMatrix2D, i.e. counter-clockwise, and it is the angle that brings
a drawn world-vertical line back to vertical.
"""

from typing import Optional, Tuple

import cv2
import numpy as np

MAX_ROLL_DEG = 45.0


def rotation_matrix(size: Tuple[int, int], roll_deg: float) -> np.ndarray:
    """Rotation matrix that de-rolls a frame of the given (height, width)."""
    height, width = size
    return cv2.getRotationMatrix2D((width / 2.0, height / 2.0), roll_deg, 1.0)


class FrameRotator:
    """Applies one fixed rotation to every frame, caching the matrix.

    Rotating about the centre keeps the frame size, so the corners give up a
    little content; bordering by replication smears them instead of showing
    black bars that would read as motion to the frame-difference gate.
    """

    def __init__(self, roll_deg: float = 0.0):
        self.roll_deg = float(roll_deg)
        self._matrix: Optional[np.ndarray] = None
        self._size: Optional[Tuple[int, int]] = None

    @property
    def enabled(self) -> bool:
        return abs(self.roll_deg) > 1e-9

    def apply(self, frame: np.ndarray) -> np.ndarray:
        """Return the de-rolled frame, or the input unchanged when roll is 0."""
        if not self.enabled:
            return frame
        size = frame.shape[:2]
        if self._matrix is None or self._size != size:
            self._matrix = rotation_matrix(size, self.roll_deg)
            self._size = size
        height, width = size
        return cv2.warpAffine(
            frame,
            self._matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
