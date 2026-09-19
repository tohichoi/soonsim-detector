"""Lightweight OpenCV motion gating engine to prevent unnecessary YOLO inferences."""

import time
from typing import Optional, Tuple
import cv2
import numpy as np


class MotionGate:
    """Evaluates frame-to-frame pixel difference for motion gating and failsafe heartbeat."""

    def __init__(
        self,
        motion_threshold: float = 4.0,
        failsafe_interval_sec: float = 30.0,
        enabled: bool = True,
    ):
        self.motion_threshold = motion_threshold
        self.failsafe_interval_sec = failsafe_interval_sec
        self.enabled = enabled
        self._prev_gray: Optional[np.ndarray] = None
        self._last_inference_time: float = 0.0

    def evaluate(
        self,
        frame: np.ndarray,
        is_active_event: bool = False,
    ) -> Tuple[bool, str, float]:
        """
        Evaluate if YOLO inference should be executed for the frame.
        Returns: (should_infer, reason, diff_score).
        """
        now = time.time()

        # Failsafe 1: While dog is active in zone, always run inference
        if is_active_event:
            self._last_inference_time = now
            return True, "ACTIVE_EVENT_IN_PROGRESS", 0.0

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

        diff_score = 0.0
        if self._prev_gray is not None:
            diff = cv2.absdiff(gray_blur, self._prev_gray)
            diff_score = float(np.mean(diff))
        self._prev_gray = gray_blur

        if not self.enabled:
            self._last_inference_time = now
            return True, "GATE_DISABLED", diff_score

        # Check motion threshold
        if diff_score >= self.motion_threshold:
            self._last_inference_time = now
            return True, f"MOTION_TRIGGERED (diff:{diff_score:.2f})", diff_score

        # Failsafe 2: Heartbeat periodic forced inference to prevent false negatives
        if (now - self._last_inference_time) >= self.failsafe_interval_sec:
            self._last_inference_time = now
            return True, f"FAILSAFE_HEARTBEAT ({self.failsafe_interval_sec}s)", diff_score

        return False, f"GATE_SKIPPED (diff:{diff_score:.2f})", diff_score

    def reset(self) -> None:
        """Reset internal history."""
        self._prev_gray = None
        self._last_inference_time = 0.0
