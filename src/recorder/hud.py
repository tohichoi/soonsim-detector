"""Right-corner diagnostic HUD for exported event videos.

Renders four rows (dog id, track countdown bar, state, stay bar) using
XOR text so the background is preserved rather than overwritten.
"""

from typing import Optional

import cv2
import numpy as np

from src.detector.zone_tracker import EventStatus, FrameTelemetry


class TelemetryHud:
    """Bar-graph overlay exposing tracker internals for diagnosis."""

    def __init__(self, min_stay_sec: float = 1.0, fps: int = 15) -> None:
        self.min_stay_sec = max(min_stay_sec, 0.1)
        self.fps = max(fps, 1)
        self.bar_w = 110
        self.bar_h = 8
        self.row_h = 16
        self.margin = 10
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.scale = 0.38
        self.thickness = 1
        self.good = (0, 200, 0)
        self.warn = (0, 200, 200)
        self.muted = (170, 170, 170)

    def draw(self, frame: np.ndarray, telemetry: Optional[FrameTelemetry]) -> np.ndarray:
        """Draw the HUD onto the frame in place and return it."""
        if telemetry is None:
            return frame
        x = frame.shape[1] - self.bar_w - self.margin
        y = self.margin

        y = self._row(frame, x, y, "dog", self._dog_value(telemetry), self._dog_color(telemetry), None)
        ratio, label, color = self._track(telemetry)
        y = self._row(frame, x, y, "track", label, color, ratio)
        y = self._row(frame, x, y, "state", telemetry.status.value, self._state_color(telemetry.status), None)
        y = self._row(frame, x, y, "pad", self._pad_value(telemetry), self._pad_color(telemetry), None)
        ratio, label, color = self._stay(telemetry)
        self._row(frame, x, y, "stay", label, color, ratio)
        return frame

    # -- per-row value builders ----------------------------------------

    def _dog_value(self, t: FrameTelemetry) -> str:
        return "#" + ",".join(str(i) for i in t.tracked_ids) if t.tracked_ids else "-"

    def _dog_color(self, t: FrameTelemetry):
        return self.good if t.tracked_ids else self.muted

    def _track(self, t: FrameTelemetry):
        if t.lost_remaining:
            _, remaining = max(t.lost_remaining, key=lambda p: p[1])
            total = max(int(t.lost_buffer_total), 1)
            ratio = remaining / total
            return ratio, f"lost {remaining / self.fps:.1f}s", self._ratio_color(ratio)
        if t.tracked_ids:
            return 1.0, "tracked", self.good
        return 0.0, "-", self.muted

    def _stay(self, t: FrameTelemetry):
        ratio = min(t.stay_sec / self.min_stay_sec, 1.0)
        color = self.good if t.stay_sec >= self.min_stay_sec else self.warn
        return ratio, f"{t.stay_sec:.1f}s", color

    def _pad_value(self, t: FrameTelemetry) -> str:
        """Contact line against the pad: margin above overlap, both for tuning."""
        if t.margin is None:
            return "-"
        return f"{t.margin:+.2f}/{t.overlap:.2f}"

    def _pad_color(self, t: FrameTelemetry):
        if t.margin is None:
            return self.muted
        return self.good if t.margin <= 0.0 else self.warn

    def _state_color(self, status: EventStatus):
        if status == EventStatus.ACTIVE:
            return self.good
        if status == EventStatus.COOLDOWN:
            return self.warn
        return self.muted

    # -- primitives -----------------------------------------------------

    def _row(self, frame, x, y, label, value, color, ratio):
        if ratio is not None:
            self._draw_bar(frame, x, y, ratio, color)
            y += self.bar_h + 2
        self._put_xor(frame, f"{label} {value}", x, y, color)
        return y + self.row_h

    def _draw_bar(self, frame, x, y, ratio, color) -> None:
        ratio = float(np.clip(ratio, 0.0, 1.0))
        cv2.rectangle(frame, (x, y), (x + self.bar_w, y + self.bar_h), self.muted, 1)
        if ratio > 0.0:
            fill_w = max(1, int(self.bar_w * ratio))
            cv2.rectangle(frame, (x, y), (x + fill_w, y + self.bar_h), color, -1)

    def _put_xor(self, frame, text, x, y, color) -> None:
        (w, h), baseline = cv2.getTextSize(text, self.font, self.scale, self.thickness)
        x = max(0, x)
        y = max(h, y)
        if x + w > frame.shape[1] or y + baseline > frame.shape[0]:
            return
        roi = frame[y - h:y + baseline, x:x + w]
        canvas = np.zeros_like(roi)
        cv2.putText(canvas, text, (0, h), self.font, self.scale, color, self.thickness, cv2.LINE_AA)
        mask = (canvas > 0).any(axis=2)
        color_arr = np.array(color, dtype=np.uint8)
        roi[mask] = roi[mask] ^ color_arr

    @staticmethod
    def _ratio_color(ratio: float):
        # green (ratio 1) -> red (ratio 0)
        ratio = float(np.clip(ratio, 0.0, 1.0))
        return (0, int(ratio * 255), int((1.0 - ratio) * 255))
