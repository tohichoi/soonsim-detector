"""Right-corner diagnostic HUD for exported event videos.

Renders a clean, high-contrast semi-transparent card containing tracking telemetry.
"""

from typing import Optional, Tuple
import cv2
import numpy as np

from src.detector.zone_tracker import EventStatus, FrameTelemetry


class TelemetryHud:
    """Semi-transparent card overlay exposing tracker internals for diagnosis."""

    def __init__(self, min_stay_sec: float = 1.0, fps: int = 15) -> None:
        self.min_stay_sec = max(min_stay_sec, 0.1)
        self.fps = max(fps, 1)
        self.card_w = 150
        self.card_h = 128
        self.margin = 10
        self.padding_x = 10
        self.font = cv2.FONT_HERSHEY_DUPLEX
        self.scale = 0.38
        self.thickness = 1
        self.good = (80, 235, 100)
        self.warn = (50, 195, 255)
        self.muted = (160, 160, 160)
        self.label_color = (160, 175, 190)
        self.bg_color = (18, 22, 30)
        self.border_color = (55, 65, 80)
        self.bar_bg = (35, 42, 55)

    def draw(self, frame: np.ndarray, telemetry: Optional[FrameTelemetry]) -> np.ndarray:
        """Draw the HUD onto the frame in place and return it."""
        if telemetry is None:
            return frame

        fh, fw = frame.shape[:2]
        x1 = fw - self.card_w - self.margin
        y1 = self.margin
        x2 = x1 + self.card_w
        y2 = y1 + self.card_h

        if x1 < 0 or y1 < 0 or x2 > fw or y2 > fh:
            return frame

        sub_img = frame[y1:y2, x1:x2]
        bg_rect = np.full(sub_img.shape, self.bg_color, dtype=np.uint8)
        cv2.addWeighted(bg_rect, 0.85, sub_img, 0.15, 0, sub_img)
        cv2.rectangle(frame, (x1, y1), (x2, y2), self.border_color, 1)

        cur_x = x1 + self.padding_x
        cur_y = y1 + 17
        bar_w = self.card_w - (self.padding_x * 2)

        cur_y = self._draw_text_row(
            frame, cur_x, cur_y, "DOG", self._dog_value(telemetry), self._dog_color(telemetry), bar_w
        )
        ratio, label, color = self._track(telemetry)
        cur_y = self._draw_bar_row(frame, cur_x, cur_y, "TRACK", label, color, ratio, bar_w)
        cur_y = self._draw_text_row(
            frame, cur_x, cur_y, "STATE", telemetry.status.value, self._state_color(telemetry.status), bar_w
        )
        cur_y = self._draw_text_row(
            frame, cur_x, cur_y, "PAD", self._pad_value(telemetry), self._pad_color(telemetry), bar_w
        )
        ratio, label, color = self._stay(telemetry)
        self._draw_bar_row(frame, cur_x, cur_y, "STAY", label, color, ratio, bar_w)
        return frame

    # -- per-row value builders ----------------------------------------

    def _dog_value(self, t: FrameTelemetry) -> str:
        return "#" + ",".join(str(i) for i in t.tracked_ids) if t.tracked_ids else "-"

    def _dog_color(self, t: FrameTelemetry):
        return self.good if t.tracked_ids else self.muted

    def _track(self, t: FrameTelemetry) -> Tuple[float, str, Tuple[int, int, int]]:
        if t.lost_remaining:
            _, remaining = max(t.lost_remaining, key=lambda p: p[1])
            total = max(int(t.lost_buffer_total), 1)
            ratio = remaining / total
            return ratio, f"lost {remaining / self.fps:.1f}s", self._ratio_color(ratio)
        if t.tracked_ids:
            return 1.0, "tracked", self.good
        return 0.0, "-", self.muted

    def _stay(self, t: FrameTelemetry) -> Tuple[float, str, Tuple[int, int, int]]:
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

    def _draw_text_row(
        self, frame: np.ndarray, x: int, y: int, label: str, val: str, color: Tuple[int, int, int], bar_w: int
    ) -> int:
        cv2.putText(frame, label, (x, y), self.font, self.scale, self.label_color, self.thickness, cv2.LINE_AA)
        (vw, _), _ = cv2.getTextSize(val, self.font, self.scale, self.thickness)
        val_x = x + bar_w - vw
        cv2.putText(frame, val, (val_x, y), self.font, self.scale, color, self.thickness, cv2.LINE_AA)
        return y + 19

    def _draw_bar_row(
        self,
        frame: np.ndarray,
        x: int,
        y: int,
        label: str,
        val: str,
        color: Tuple[int, int, int],
        ratio: float,
        bar_w: int,
    ) -> int:
        cv2.putText(frame, label, (x, y), self.font, self.scale, self.label_color, self.thickness, cv2.LINE_AA)
        (vw, _), _ = cv2.getTextSize(val, self.font, self.scale, self.thickness)
        val_x = x + bar_w - vw
        cv2.putText(frame, val, (val_x, y), self.font, self.scale, color, self.thickness, cv2.LINE_AA)
        bar_y = y + 4
        cv2.rectangle(frame, (x, bar_y), (x + bar_w, bar_y + 4), self.bar_bg, -1)
        if ratio > 0.0:
            fill_w = max(1, int(bar_w * float(np.clip(ratio, 0.0, 1.0))))
            cv2.rectangle(frame, (x, bar_y), (x + fill_w, bar_y + 4), color, -1)
        return y + 23

    @staticmethod
    def _ratio_color(ratio: float) -> Tuple[int, int, int]:
        ratio = float(np.clip(ratio, 0.0, 1.0))
        return (0, int(ratio * 255), int((1.0 - ratio) * 255))
