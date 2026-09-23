"""Integration test for full pipeline (Capture, Zone, Exporter, Notifier)."""

from pathlib import Path
from types import SimpleNamespace
import time
import numpy as np
import supervision as sv
from src.capture.stream import FramePacket, RingBuffer
from src.config import TelegramConfig
from src.detector.zone_tracker import ZoneTracker
from src.main import SoonsimService
from src.notifier.telegram import TelegramNotifier
from src.recorder.annotator import HighContrastAnnotator
from src.recorder.exporter import VideoClipExporter


def test_full_export_and_notify_dry_run(tmp_path: Path):
    """Test full event lifecycle, video rendering to MP4, and dry-run telegram alert."""
    polygon = [(50, 50), (200, 50), (200, 200), (50, 200)]
    fps = 10
    tracker = ZoneTracker(
        polygon=polygon,
        fps=fps,
        post_buffer_sec=1,
        min_stay_duration_sec=0.1,
    )
    annotator = HighContrastAnnotator(zone=tracker.zone)
    exporter = VideoClipExporter(output_dir=tmp_path / "records", annotator=annotator, fps=fps)
    notifier = TelegramNotifier(config=TelegramConfig(enabled=False))

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    dog_det = sv.Detections(
        xyxy=np.array([[70.0, 70.0, 150.0, 150.0]]),
        confidence=np.array([0.95]),
        class_id=np.array([16]),
    )
    empty_det = sv.Detections.empty()

    # Pre-buffer
    pre_frames = [
        FramePacket(frame=frame.copy(), timestamp=1.0 + i * 0.1, frame_idx=i)
        for i in range(5)
    ]

    # Enter zone
    p_enter = FramePacket(frame=frame.copy(), timestamp=1.5, frame_idx=5)
    tracker.update(p_enter, dog_det, pre_frames)

    # Stay
    p_stay = FramePacket(frame=frame.copy(), timestamp=1.6, frame_idx=6)
    tracker.update(p_stay, dog_det, [])

    # Exit
    completed_event = None
    for i in range(11):
        p_exit = FramePacket(frame=frame.copy(), timestamp=1.7 + i * 0.1, frame_idx=7 + i)
        _, _, completed_event = tracker.update(p_exit, empty_det, [])
        if completed_event is not None:
            break

    assert completed_event is not None
    output_path = exporter.export(completed_event)
    assert output_path is not None
    assert output_path.exists()
    assert output_path.suffix == ".mp4"
    assert output_path.stat().st_size > 0

    # Dry-run Telegram send
    sent = notifier.send_video(
        video_path=output_path,
        stay_duration_sec=completed_event.duration_sec,
        start_time=completed_event.start_time,
    )
    assert sent is True


def test_completed_event_reaches_exporter_and_notifier(tmp_path: Path):
    """A completed event must survive the service wiring and reach the notifier.

    Regression: `_step_pipeline` called `_export_async` without its required
    `prefix`, so the daemon raised TypeError and died the moment any event
    completed. Above test drives the tracker/exporter directly and never
    touches that call site.
    """
    fps = 10
    tracker = ZoneTracker(
        polygon=[(50, 50), (200, 50), (200, 200), (50, 200)],
        fps=fps,
        post_buffer_sec=1,
        min_stay_duration_sec=0.1,
    )
    sent: list = []

    service = object.__new__(SoonsimService)
    service.tracker = tracker
    service.ring_buffer = RingBuffer(max_frames=5)
    service.exporter = VideoClipExporter(
        output_dir=tmp_path / "records",
        annotator=HighContrastAnnotator(zone=tracker.zone),
        fps=fps,
    )
    service.signal_recorder = None
    service.live_feed = SimpleNamespace(push=lambda *a, **k: None)
    service.alerts_count = 0
    service.last_alert_time = "None"
    service.config = SimpleNamespace(recorder=SimpleNamespace(retention_days=30))
    service.notifier = SimpleNamespace(send_video=lambda *a, **k: sent.append(a) or True)

    dog_det = sv.Detections(
        xyxy=np.array([[70.0, 70.0, 150.0, 150.0]]),
        confidence=np.array([0.95]),
        class_id=np.array([16]),
    )
    empty_det = sv.Detections.empty()
    service._evaluate_detector = lambda packet, is_active: (
        dog_det if packet.timestamp < 2.0 else empty_det,
        0.0,
        False,
    )

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for i, ts in enumerate([1.0, 1.5] + [2.0 + i * 0.1 for i in range(20)]):
        service._step_pipeline(
            FramePacket(frame=frame.copy(), timestamp=ts, frame_idx=i)
        )

    deadline = time.monotonic() + 5.0
    while not sent and time.monotonic() < deadline:
        time.sleep(0.05)

    assert sent, "completed event never reached the notifier"
    assert service.alerts_count == 1
    assert Path(sent[0][0]).name.startswith("soonsim_")
