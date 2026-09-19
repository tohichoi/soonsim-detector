"""Zone trigger and ByteTrack multi-object tracking."""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
import numpy as np
import supervision as sv
from src.capture.stream import FramePacket


class EventStatus(str, Enum):
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    COOLDOWN = "COOLDOWN"
    COMPLETED = "COMPLETED"


@dataclass
class CompletedEvent:
    start_time: float
    end_time: float
    duration_sec: float
    frames: List[FramePacket]
    detections: List[sv.Detections]


class ZoneTracker:
    """Manages PolygonZone triggering, ByteTrack tracking, and event buffers."""

    def __init__(
        self,
        polygon: List[Tuple[int, int]],
        track_thresh: float = 0.25,
        match_thresh: float = 0.8,
        fps: int = 15,
        post_buffer_sec: int = 5,
        min_stay_duration_sec: float = 1.0,
    ):
        self.polygon_np = np.array(polygon, dtype=np.int32)
        self.zone = sv.PolygonZone(
            polygon=self.polygon_np,
            triggering_anchors=(sv.Position.CENTER, sv.Position.BOTTOM_CENTER),
            require_all_anchors=False,
        )
        self.tracker = sv.ByteTrack(
            track_activation_threshold=track_thresh,
            lost_track_buffer=fps * 2,
            minimum_matching_threshold=match_thresh,
            frame_rate=fps,
        )
        self.fps = fps
        self.post_buffer_frames = post_buffer_sec * fps
        self.min_stay_duration_sec = min_stay_duration_sec

        self.status = EventStatus.IDLE
        self.event_start_time: Optional[float] = None
        self.stay_start_time: Optional[float] = None
        self.stay_end_time: Optional[float] = None
        self.cooldown_counter = 0

        self._current_event_frames: List[FramePacket] = []
        self._current_event_detections: List[sv.Detections] = []

    def update(
        self,
        packet: FramePacket,
        detections: sv.Detections,
        pre_buffer_frames: List[FramePacket],
    ) -> Tuple[sv.Detections, bool, Optional[CompletedEvent]]:
        """
        Update tracker and zone.
        Returns (tracked_detections, is_dog_in_zone, completed_event_or_None).
        """
        tracked_detections = self.tracker.update_with_detections(detections)
        is_in_zone = self.zone.trigger(detections=tracked_detections)
        dog_in_zone = bool(np.any(is_in_zone)) if len(is_in_zone) > 0 else False

        completed_event: Optional[CompletedEvent] = None

        if self.status == EventStatus.IDLE:
            if dog_in_zone:
                self.status = EventStatus.ACTIVE
                self.stay_start_time = packet.timestamp
                self.event_start_time = pre_buffer_frames[0].timestamp if pre_buffer_frames else packet.timestamp
                self._current_event_frames = list(pre_buffer_frames) + [packet]
                self._current_event_detections = [sv.Detections.empty()] * len(pre_buffer_frames) + [tracked_detections]
        elif self.status == EventStatus.ACTIVE:
            self._current_event_frames.append(packet)
            self._current_event_detections.append(tracked_detections)
            if not dog_in_zone:
                self.status = EventStatus.COOLDOWN
                self.stay_end_time = packet.timestamp
                self.cooldown_counter = 0
        elif self.status == EventStatus.COOLDOWN:
            self._current_event_frames.append(packet)
            self._current_event_detections.append(tracked_detections)
            if dog_in_zone:
                self.status = EventStatus.ACTIVE
                self.cooldown_counter = 0
            else:
                self.cooldown_counter += 1
                if self.cooldown_counter >= self.post_buffer_frames:
                    duration = (self.stay_end_time or packet.timestamp) - (self.stay_start_time or packet.timestamp)
                    if duration >= self.min_stay_duration_sec:
                        completed_event = CompletedEvent(
                            start_time=self.event_start_time or packet.timestamp,
                            end_time=packet.timestamp,
                            duration_sec=duration,
                            frames=list(self._current_event_frames),
                            detections=list(self._current_event_detections),
                        )
                    self.reset()

        return tracked_detections, dog_in_zone, completed_event

    def reset(self) -> None:
        """Reset state to IDLE."""
        self.status = EventStatus.IDLE
        self.event_start_time = None
        self.stay_start_time = None
        self.stay_end_time = None
        self.cooldown_counter = 0
        self._current_event_frames.clear()
        self._current_event_detections.clear()
