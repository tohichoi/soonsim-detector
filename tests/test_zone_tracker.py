"""Tests for zone tracker state machine."""

import numpy as np
import supervision as sv
from src.capture.stream import FramePacket
from src.detector.zone_tracker import EventStatus, ZoneTracker


def test_zone_tracker_lifecycle():
    """Verify zone tracker enters ACTIVE, transitions to COOLDOWN, then completes event."""
    polygon = [(100, 100), (300, 100), (300, 300), (100, 300)]
    tracker = ZoneTracker(
        polygon=polygon,
        fps=10,
        post_buffer_sec=1,  # 10 frames post buffer
        min_stay_duration_sec=0.2,
    )

    frame = np.zeros((360, 640, 3), dtype=np.uint8)

    # 1. Idle state with no detections
    empty_det = sv.Detections.empty()
    p1 = FramePacket(frame=frame, timestamp=1.0, frame_idx=1)
    _, in_zone, event = tracker.update(p1, empty_det, [])
    assert not in_zone
    assert tracker.status == EventStatus.IDLE
    assert event is None

    # 2. Dog appears inside polygon (ByteTrack initializes on first frame, confirms on second frame)
    dog_det = sv.Detections(
        xyxy=np.array([[150.0, 150.0, 250.0, 250.0]]),
        confidence=np.array([0.9]),
        class_id=np.array([16]),
    )
    pre_frames = [FramePacket(frame=frame, timestamp=0.5, frame_idx=0)]
    p2 = FramePacket(frame=frame, timestamp=1.1, frame_idx=2)
    tracker.update(p2, dog_det, pre_frames)

    p3 = FramePacket(frame=frame, timestamp=1.2, frame_idx=3)
    _, in_zone, event = tracker.update(p3, dog_det, pre_frames)
    assert in_zone
    assert tracker.status == EventStatus.ACTIVE
    assert event is None

    # 3. Dog stays in zone for 3 more frames
    for i in range(3):
        t = 1.3 + i * 0.1
        pk = FramePacket(frame=frame, timestamp=t, frame_idx=4 + i)
        _, in_zone, event = tracker.update(pk, dog_det, [])
        assert in_zone
        assert tracker.status == EventStatus.ACTIVE

    # 4. Dog leaves zone -> transitions to COOLDOWN
    p7 = FramePacket(frame=frame, timestamp=1.6, frame_idx=7)
    _, in_zone, event = tracker.update(p7, empty_det, [])
    assert not in_zone
    assert tracker.status == EventStatus.COOLDOWN
    assert event is None

    # 5. Advance cooldown counter (post_buffer_frames = 10)
    for i in range(10):
        t = 1.7 + i * 0.1
        pk = FramePacket(frame=frame, timestamp=t, frame_idx=8 + i)
        _, in_zone, event = tracker.update(pk, empty_det, [])
        if i == 9:
            assert event is not None
            assert event.duration_sec >= 0.2
            assert len(event.frames) > 0
            assert tracker.status == EventStatus.IDLE
        else:
            assert event is None
            assert tracker.status == EventStatus.COOLDOWN


def test_last_telemetry_is_available_outside_events():
    """The viewer renders every frame, including IDLE ones, so telemetry must exist there."""
    polygon = [(100, 100), (300, 100), (300, 300), (100, 300)]
    tracker = ZoneTracker(polygon=polygon, fps=10, lost_track_buffer_sec=2.0)

    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    packet = FramePacket(frame=frame, timestamp=1.0, frame_idx=1)
    tracker.update(packet, sv.Detections.empty(), [])

    assert tracker.last_telemetry.status == EventStatus.IDLE
    # A zero buffer total means the frame was never handed to _build_telemetry(),
    # which is exactly how the HUD silently vanished from the live view.
    assert tracker.last_telemetry.lost_buffer_total > 0


def test_pooping_pose_teddy_bear_recovery():
    """Verify that when a dog shifts to teddy bear (class 77) during pooping, tracking stays ACTIVE."""
    polygon = [(100, 100), (300, 100), (300, 300), (100, 300)]
    tracker = ZoneTracker(
        polygon=polygon,
        fps=10,
        post_buffer_sec=1,
        min_stay_duration_sec=0.2,
    )
    frame = np.zeros((360, 640, 3), dtype=np.uint8)

    dog_det = sv.Detections(
        xyxy=np.array([[150.0, 150.0, 250.0, 250.0]]),
        confidence=np.array([0.8]),
        class_id=np.array([16]),
    )
    teddy_det = sv.Detections(
        xyxy=np.array([[150.0, 150.0, 250.0, 250.0]]),
        confidence=np.array([0.5]),
        class_id=np.array([77]),
    )

    # 1. Dog enters zone
    p1 = FramePacket(frame=frame, timestamp=1.0, frame_idx=1)
    tracker.update(p1, dog_det, [])
    p2 = FramePacket(frame=frame, timestamp=1.1, frame_idx=2)
    tracker.update(p2, dog_det, [])
    assert tracker.status == EventStatus.ACTIVE

    # 2. Dog poses into teddy bear (class 77) on pad -> stays ACTIVE
    p3 = FramePacket(frame=frame, timestamp=1.2, frame_idx=3)
    _, in_zone, event = tracker.update(p3, teddy_det, [])
    assert in_zone
    assert tracker.status == EventStatus.ACTIVE
    assert event is None


def test_instant_alert_stay_sec_gating():
    """Verify instant alert triggers only after instant_alert_stay_sec and only once per event."""
    polygon = [(100, 100), (300, 100), (300, 300), (100, 300)]
    tracker = ZoneTracker(
        polygon=polygon,
        fps=10,
        instant_alert_stay_sec=1.0,
        min_stay_duration_sec=1.0,
    )
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    dog_det = sv.Detections(
        xyxy=np.array([[150.0, 150.0, 250.0, 250.0]]),
        confidence=np.array([0.9]),
        class_id=np.array([16]),
    )

    # 1. Dog enters zone at t=1.0s
    p1 = FramePacket(frame=frame, timestamp=1.0, frame_idx=1)
    tracker.update(p1, dog_det, [])
    assert tracker.pop_instant_alert() is None

    # 2. Dog stays in zone at t=1.5s (0.5s stay < 1.0s) -> no alert yet
    p2 = FramePacket(frame=frame, timestamp=1.5, frame_idx=2)
    tracker.update(p2, dog_det, [])
    assert tracker.pop_instant_alert() is None

    # 3. Dog stays in zone at t=2.0s (1.0s stay >= 1.0s) -> triggers alert!
    p3 = FramePacket(frame=frame, timestamp=2.0, frame_idx=3)
    tracker.update(p3, dog_det, [])
    alert_duration = tracker.pop_instant_alert()
    assert alert_duration is not None
    assert alert_duration >= 1.0

    # 4. Next frame in same event -> does NOT trigger again
    p4 = FramePacket(frame=frame, timestamp=2.5, frame_idx=4)
    tracker.update(p4, dog_det, [])
    assert tracker.pop_instant_alert() is None


