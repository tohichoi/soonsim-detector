"""Integration test for full pipeline (Capture, Zone, Exporter, Notifier)."""

from pathlib import Path
import numpy as np
import supervision as sv
from src.capture.stream import FramePacket
from src.config import TelegramConfig
from src.detector.zone_tracker import ZoneTracker
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
