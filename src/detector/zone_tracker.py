"""Zone trigger and ByteTrack multi-object tracking."""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
import numpy as np
import supervision as sv
from src.capture.stream import FramePacket
from src.detector.zone_contact import ContactMetrics, PadGeometry, ZoneContactLog


class EventStatus(str, Enum):
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    COOLDOWN = "COOLDOWN"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True)
class FrameTelemetry:
    """Per-frame diagnostic state captured during an event."""
    status: EventStatus
    in_zone: bool
    stay_sec: float
    tracked_ids: Tuple[int, ...]
    lost_remaining: Tuple[Tuple[int, int], ...]
    lost_buffer_total: int
    # Contact metrics, measured for tuning and not yet part of the verdict.
    margin: Optional[float] = None
    overlap: float = 0.0


@dataclass
class CompletedEvent:
    start_time: float
    end_time: float
    duration_sec: float
    frames: List[FramePacket]
    detections: List[sv.Detections]
    telemetry: List[FrameTelemetry]


class ZoneTracker:
    """Manages PolygonZone triggering, ByteTrack tracking, and event buffers."""

    def __init__(
        self,
        polygon: List[Tuple[int, int]],
        track_thresh: float = 0.25,
        match_thresh: float = 0.8,
        fps: int = 15,
        lost_track_buffer_sec: float = 2.0,
        post_buffer_sec: int = 5,
        min_stay_duration_sec: float = 1.0,
        contact_log: Optional[ZoneContactLog] = None,
    ):
        self.polygon_np = np.array(polygon, dtype=np.int32)
        self.zone = sv.PolygonZone(
            polygon=self.polygon_np,
            triggering_anchors=(sv.Position.CENTER, sv.Position.BOTTOM_CENTER),
            require_all_anchors=False,
        )
        # Measured every frame, recorded to contact_log, not yet part of the verdict.
        self.pad_geometry = PadGeometry(self.zone.mask)
        self.contact_log = contact_log
        self.tracker = sv.ByteTrack(
            track_activation_threshold=track_thresh,
            # supervision scales lost_track_buffer against a 30fps reference
            # (max_time_lost = frame_rate/30 * lost_track_buffer). Passing
            # frame_rate=30 makes lost_track_buffer literal frames, so
            # lost_track_buffer_sec maps 1:1 to seconds at our real fps.
            lost_track_buffer=max(1, int(round(lost_track_buffer_sec * fps))),
            minimum_matching_threshold=match_thresh,
            frame_rate=30,
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
        self._current_event_telemetry: List[FrameTelemetry] = []

        # Diagnostic state of the most recent frame, so callers that only render
        # the live frame (the viewer) can overlay the same HUD as exported clips.
        self.last_telemetry: FrameTelemetry = self._empty_telemetry()
        self.last_contact: Optional[ContactMetrics] = None

    def _lost_track_remaining(self) -> List[Tuple[int, int]]:
        """Read ByteTrack internals for lost tracks' remaining frames before drop."""
        try:
            bt = self.tracker
            return [
                (int(t.external_track_id), max(0, int(bt.max_time_lost - (bt.frame_id - t.frame_id))))
                for t in bt.lost_tracks
            ]
        except Exception:
            return []

    def _lost_buffer_total(self) -> int:
        """Return the tracker's effective lost-track buffer size (frames)."""
        return int(getattr(self.tracker, "max_time_lost", 0))

    def _build_telemetry(
        self,
        packet: FramePacket,
        tracked_detections: sv.Detections,
        dog_in_zone: bool,
    ) -> FrameTelemetry:
        stay_sec = (packet.timestamp - self.stay_start_time) if self.stay_start_time is not None else 0.0
        tracker_ids = (
            tuple(int(i) for i in tracked_detections.tracker_id)
            if tracked_detections.tracker_id is not None
            else ()
        )
        return FrameTelemetry(
            status=self.status,
            in_zone=dog_in_zone,
            stay_sec=stay_sec,
            tracked_ids=tracker_ids,
            lost_remaining=tuple(self._lost_track_remaining()),
            lost_buffer_total=self._lost_buffer_total(),
            margin=self.last_contact.margin if self.last_contact else None,
            overlap=self.last_contact.overlap if self.last_contact else 0.0,
        )

    @staticmethod
    def _empty_telemetry() -> FrameTelemetry:
        return FrameTelemetry(
            status=EventStatus.IDLE,
            in_zone=False,
            stay_sec=0.0,
            tracked_ids=(),
            lost_remaining=(),
            lost_buffer_total=0,
        )

    def _record_frame(
        self,
        packet: FramePacket,
        tracked_detections: sv.Detections,
    ) -> None:
        """Append frame, detections, and telemetry in lockstep."""
        self._current_event_frames.append(packet)
        self._current_event_detections.append(tracked_detections)
        self._current_event_telemetry.append(self.last_telemetry)

    def update(
        self,
        packet: FramePacket,
        detections: sv.Detections,
        pre_buffer_frames: List[FramePacket],
    ) -> Tuple[sv.Detections, bool, Optional[CompletedEvent]]:
        """Update tracker/zone; return (tracked_detections, in_zone, completed_event)."""
        tracked_detections = self.tracker.update_with_detections(detections)
        is_in_zone = self.zone.trigger(detections=tracked_detections)
        dog_in_zone = bool(np.any(is_in_zone)) if len(is_in_zone) > 0 else False
        self.last_contact = self.pad_geometry.largest(tracked_detections)
        if self.contact_log is not None:
            self.contact_log.record(
                frame_idx=packet.frame_idx,
                timestamp=packet.timestamp,
                status=self.status.value,
                track_ids=(
                    tuple(int(i) for i in tracked_detections.tracker_id)
                    if tracked_detections.tracker_id is not None
                    else ()
                ),
                metrics=self.last_contact,
                in_zone=dog_in_zone,
            )
        self.last_telemetry = self._build_telemetry(packet, tracked_detections, dog_in_zone)

        completed_event: Optional[CompletedEvent] = None

        if self.status == EventStatus.IDLE:
            if dog_in_zone:
                self.status = EventStatus.ACTIVE
                self.stay_start_time = packet.timestamp
                self.event_start_time = pre_buffer_frames[0].timestamp if pre_buffer_frames else packet.timestamp
                self._current_event_frames = list(pre_buffer_frames) + [packet]
                self._current_event_detections = [sv.Detections.empty()] * len(pre_buffer_frames) + [tracked_detections]
                self._current_event_telemetry = [self._empty_telemetry()] * len(pre_buffer_frames) + [self.last_telemetry]
        elif self.status == EventStatus.ACTIVE:
            if not dog_in_zone:
                self.status = EventStatus.COOLDOWN
                self.stay_end_time = packet.timestamp
                self.cooldown_counter = 0
            self._record_frame(packet, tracked_detections)
        elif self.status == EventStatus.COOLDOWN:
            self._record_frame(packet, tracked_detections)
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
                            telemetry=list(self._current_event_telemetry),
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
        self._current_event_telemetry.clear()
