"""Clips of motion that inference never turns into an animal.

A miss leaves nothing behind. It produces no event, so no clip is written and
the only evidence is a log line. On 2026-09-22 07:47 a real defecation gave 56
seconds of motion-triggered inference with zero detections, and there was
nothing to review afterwards.

This keeps the same pre/post window as an event, armed by motion-without-
detection instead of a zone verdict. It judges nothing and alerts no one; it
only leaves footage behind.

Signal frames are sparse — inference runs every few frames and only while
something moves, so the 2026-09-22 miss produced about 30 of them across 56
seconds. Everything here is therefore timed by timestamp, never by counting
frames, or a real miss would read as far shorter than it was.
"""

from collections import deque
from typing import List, Optional

import supervision as sv
from src.capture.stream import FramePacket
from src.detector.zone_tracker import CompletedEvent

# ponytail: episode frames are held in RAM, as an event's already are. This cap
# bounds the worst case; stream into the VideoSink instead if RAM gets tight.
MAX_SIGNAL_SEC = 45.0
COOLDOWN_SEC = 30.0


class SignalRecorder:
    """Collects frames around motion that the detector never explains.

    Feed every processed frame to ``observe``. Returns a CompletedEvent once an
    episode closes and it was long enough to be worth keeping.
    """

    def __init__(
        self,
        fps: int,
        min_signal_sec: float = 10.0,
        pre_buffer_sec: int = 5,
        post_buffer_sec: int = 5,
        max_signal_sec: float = MAX_SIGNAL_SEC,
        cooldown_sec: float = COOLDOWN_SEC,
    ):
        self.fps = fps
        self._min_signal_sec = min_signal_sec
        self._post_sec = post_buffer_sec
        self._max_sec = max_signal_sec
        self._cooldown_sec = cooldown_sec
        self._pre: deque[FramePacket] = deque(maxlen=pre_buffer_sec * fps)
        self._frames: List[FramePacket] = []
        self._detections: List[sv.Detections] = []
        self._signal_start: Optional[float] = None
        self._last_signal: Optional[float] = None
        self._cooldown_left = 0.0

    def observe(
        self,
        packet: FramePacket,
        detections: sv.Detections,
        is_signal: bool,
    ) -> Optional[CompletedEvent]:
        """Advance one frame; return the finished episode, or None if still open."""
        if not self._frames:
            self._pre.append(packet)
            if self._cooldown_left > 0:
                self._cooldown_left -= 1.0 / self.fps
            elif is_signal:
                # The arming frame is the last of the pre-roll and the first
                # signal, so it appears once in the episode.
                self._frames = list(self._pre)
                self._detections = [sv.Detections.empty()] * len(self._frames)
                self._signal_start = packet.timestamp
                self._last_signal = packet.timestamp
            return None

        self._frames.append(packet)
        self._detections.append(detections)
        if is_signal:
            self._last_signal = packet.timestamp

        duration = self._last_signal - self._signal_start
        quiet_for = packet.timestamp - self._last_signal
        open_for = packet.timestamp - self._signal_start
        if quiet_for >= self._post_sec or open_for >= self._max_sec:
            return self._close(packet.timestamp, duration)
        return None

    def _close(self, end_time: float, duration: float) -> Optional[CompletedEvent]:
        """Drop the episode, keeping it only if the motion lasted long enough."""
        frames, detections = self._frames, self._detections
        keep = duration >= self._min_signal_sec
        self._frames, self._detections = [], []
        self._signal_start = self._last_signal = None
        self._pre.clear()
        self._cooldown_left = self._cooldown_sec if keep else 0.0
        if not keep:
            return None
        return CompletedEvent(
            start_time=frames[0].timestamp,
            end_time=end_time,
            duration_sec=duration,
            frames=frames,
            detections=detections,
            telemetry=[],
        )
