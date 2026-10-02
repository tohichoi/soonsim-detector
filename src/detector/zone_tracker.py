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
    # Contact metrics for the episode verdict below, plus the pose channel.
    margin: Optional[float] = None
    overlap: float = 0.0
    class_id: int = -1


# A median and a spread need a few samples before either means anything, and a
# shorter episode has not been judged, not been cleared. Episodes that never
# reach this many detected frames fail the verdict.
MIN_VERDICT_FRAMES = 5


@dataclass
class CompletedEvent:
    start_time: float
    end_time: float
    duration_sec: float
    frames: List[FramePacket]
    detections: List[sv.Detections]
    telemetry: List[FrameTelemetry]
    # Whether the episode's own geometry judged it a visit. False for signal
    # clips, which no one should ever be alerted about.
    is_visit: bool = False


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
        instant_alert_stay_sec: float = 1.0,
        contact_log: Optional[ZoneContactLog] = None,
        max_box_area: float = 55000.0,
        max_box_width: float = 380.0,
        max_ground_margin: float = 0.10,
        verdict_margin_max: float = 0.16,
        verdict_margin_std_min: float = 0.12,
    ):
        self.polygon_np = np.array(polygon, dtype=np.int32)
        self.zone = sv.PolygonZone(
            polygon=self.polygon_np,
            triggering_anchors=(sv.Position.BOTTOM_CENTER,),
            require_all_anchors=False,
        )
        self.max_box_area = max_box_area
        self.max_box_width = max_box_width
        self.max_ground_margin = max_ground_margin
        self.verdict_margin_max = verdict_margin_max
        self.verdict_margin_std_min = verdict_margin_std_min
        # Measured every frame, recorded to contact_log, and checked in verdict.
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
        self.instant_alert_stay_sec = instant_alert_stay_sec

        self.status = EventStatus.IDLE
        self.event_start_time: Optional[float] = None
        self.stay_start_time: Optional[float] = None
        self.stay_end_time: Optional[float] = None
        self.cooldown_counter = 0
        self.instant_alert_pending: bool = False
        self.instant_alert_triggered: bool = False

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
            class_id=self.last_contact.class_id if self.last_contact else -1,
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

    def episode_verdict(self) -> bool:
        """Judge the visit so far as a whole, not one frame at a time.

        ``_is_valid_contact`` asks whether *a* frame put the box on the pad,
        and one such frame is all a pass-by needs: while the dog walks in front
        of the pad its box crosses the pad's image position for a moment. The
        depth lives in the episode instead. On 192 hand-labelled events the
        median contact margin was -0.245 for real visits and +0.261 for
        pass-bys, and its spread 0.169 against 0.048.

        Either shape is a visit: a dog that stands on the pad (low median), or
        one that works around on it (wide spread). A box sweeping past keeps a
        large positive margin and an almost constant one. Measured 0.92 recall
        at 0.60 precision, against 1.00 at 0.32 for alerting on every episode
        the per-frame test accepts.
        """
        margins = [
            t.margin for t in self._current_event_telemetry if t.margin is not None
        ]
        if len(margins) < MIN_VERDICT_FRAMES:
            return False
        return (
            float(np.median(margins)) <= self.verdict_margin_max
            or float(np.std(margins)) >= self.verdict_margin_std_min
        )

    def _is_valid_contact(self, detections: sv.Detections, in_zone_mask: np.ndarray) -> bool:
        """Validate whether any in-zone detection meets perspective size and depth constraints."""
        if not np.any(in_zone_mask) or detections.xyxy is None or len(detections.xyxy) == 0:
            return False
        for i, in_zone in enumerate(in_zone_mask):
            if not in_zone:
                continue
            box = detections.xyxy[i]
            x0, y0, x1, y1 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
            w = x1 - x0
            h = y1 - y0
            area = w * h
            if area > self.max_box_area or w > self.max_box_width:
                continue
            metrics = self.pad_geometry.measure(box)
            if metrics is not None and metrics.margin > self.max_ground_margin:
                continue
            return True
        return False

    def update(
        self,
        packet: FramePacket,
        detections: sv.Detections,
        pre_buffer_frames: List[FramePacket],
        diff_score: float = 0.0,
    ) -> Tuple[sv.Detections, bool, Optional[CompletedEvent]]:
        """Update tracker/zone; return (tracked_detections, in_zone, completed_event)."""
        tracked_detections = self.tracker.update_with_detections(detections)
        is_in_zone = self.zone.trigger(detections=tracked_detections)
        dog_in_zone = self._is_valid_contact(tracked_detections, is_in_zone)
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
                diff_score=diff_score,
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
            else:
                stay_sec = (packet.timestamp - self.stay_start_time) if self.stay_start_time is not None else 0.0
                # Long enough *and* judged a visit. Re-checked every frame until
                # it holds, so a dog that only settles later still gets its
                # alert rather than missing it at the one-second mark.
                if (
                    not self.instant_alert_triggered
                    and stay_sec >= self.instant_alert_stay_sec
                    and self.episode_verdict()
                ):
                    self.instant_alert_pending = True
                    self.instant_alert_triggered = True
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
                    is_visit = self.episode_verdict()
                    if duration >= self.min_stay_duration_sec:
                        completed_event = CompletedEvent(
                            start_time=self.event_start_time or packet.timestamp,
                            end_time=packet.timestamp,
                            duration_sec=duration,
                            frames=list(self._current_event_frames),
                            detections=list(self._current_event_detections),
                            telemetry=list(self._current_event_telemetry),
                            is_visit=is_visit,
                        )
                        if self.contact_log is not None:
                            self.contact_log.record_event(
                                completed_event.telemetry,
                                completed_event.start_time,
                                duration,
                                visit=is_visit,
                            )
                    self.reset()

        return tracked_detections, dog_in_zone, completed_event

    def pop_instant_alert(self) -> Optional[float]:
        """Return stay duration if instant alert is pending, and clear pending flag."""
        if self.instant_alert_pending:
            self.instant_alert_pending = False
            return self.last_telemetry.stay_sec if self.last_telemetry else self.instant_alert_stay_sec
        return None

    def reset(self) -> None:
        """Reset state to IDLE."""
        self.status = EventStatus.IDLE
        self.event_start_time = None
        self.stay_start_time = None
        self.stay_end_time = None
        self.cooldown_counter = 0
        self.instant_alert_pending = False
        self.instant_alert_triggered = False
        self._current_event_frames.clear()
        self._current_event_detections.clear()
        self._current_event_telemetry.clear()
