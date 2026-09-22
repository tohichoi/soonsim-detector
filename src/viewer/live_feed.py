"""What the web viewer shows, and how often.

Split out of the daemon because none of it decides anything about detection: it
takes the frame the pipeline already produced and decides what to push at the
viewer, and when. The daemon keeps the pipeline; this keeps the presentation.

The live frame is throttled while the dog is out of the zone but never while it
is in it, so the one moment worth watching live is never sampled away.
"""

import time
from typing import List, Optional, Tuple

import cv2
import supervision as sv

from src.capture.stream import FramePacket
from src.recorder.annotator import HighContrastAnnotator
from src.viewer.state import ViewerStateStore

LIVE_UPDATE_INTERVAL_SEC = 0.5
BASELINE_INTERVAL_SEC = 600.0
JPEG_QUALITY = 80


class LiveFeed:
    """Pushes the annotated live frame and history entries into the viewer store."""

    def __init__(
        self,
        state: ViewerStateStore,
        annotator: HighContrastAnnotator,
        motion_threshold: float,
        update_interval_sec: float = LIVE_UPDATE_INTERVAL_SEC,
        baseline_interval_sec: float = BASELINE_INTERVAL_SEC,
    ):
        self._state = state
        self._annotator = annotator
        self._motion_threshold = motion_threshold
        self._update_interval_sec = update_interval_sec
        self._baseline_interval_sec = baseline_interval_sec
        self._last_update_t = 0.0
        self._last_baseline_t = 0.0
        self._prev_animal_count = 0

    def push(
        self,
        packet: FramePacket,
        detections: sv.Detections,
        in_zone: bool,
        diff: float,
        telemetry: Optional[object] = None,
    ) -> None:
        """Publish one frame to the viewer, throttled unless the dog is in the zone."""
        now = time.time()
        is_motion = diff >= self._motion_threshold
        if not in_zone and (now - self._last_update_t) < self._update_interval_sec:
            return
        self._last_update_t = now

        title, desc, stype = self._status(in_zone, is_motion, diff)
        labels = [
            f"class_{c}"
            for c in (detections.class_id if detections.class_id is not None else [])
        ]
        image = self._encode(packet, detections, in_zone, telemetry)
        self._state.update_live(title, desc, stype, labels, in_zone, diff, image)
        self._push_event_if_needed(now, in_zone, len(detections), is_motion, labels, diff, image)

    @staticmethod
    def _status(in_zone: bool, is_motion: bool, diff: float) -> Tuple[str, str, str]:
        if in_zone:
            return (
                "순심이 배변판 진입 확인!",
                "순심이가 배변판 영역 안에 위치하고 있습니다.",
                "dog_on_pad",
            )
        if is_motion:
            return (
                "움직임/조도 변화 감지됨",
                f"화면 내 움직임 감지 (변화 점수: {diff:.1f})",
                "motion",
            )
        return (
            "현재 변화 없음 (정적 상태)",
            "실시간 감시 중이며 배변판에 유의미한 변화가 없습니다.",
            "no_change",
        )

    def _encode(
        self,
        packet: FramePacket,
        detections: sv.Detections,
        in_zone: bool,
        telemetry: Optional[object],
    ) -> bytes:
        annotated = self._annotator.annotate(
            packet.frame,
            detections,
            timestamp=packet.timestamp,
            is_dog_in_zone=in_zone,
            telemetry=telemetry,
        )
        _, encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        return encoded.tobytes()

    def _push_event_if_needed(
        self,
        now: float,
        in_zone: bool,
        count: int,
        is_motion: bool,
        labels: List[str],
        diff: float,
        image: bytes,
    ) -> None:
        """Record periodic or discrete events into viewer history."""
        event_type: Optional[str] = None
        if in_zone:
            event_type = "DOG_ON_PAD"
        elif count > 0 and count != self._prev_animal_count:
            event_type = "ANIMAL_DETECTED"
        elif is_motion:
            event_type = "MOTION_CHANGE"
        elif (now - self._last_baseline_t) >= self._baseline_interval_sec:
            event_type = "PERIODIC_BASELINE"
            self._last_baseline_t = now

        self._prev_animal_count = count
        if event_type:
            self._state.push_event(event_type, labels, in_zone, diff, image)
