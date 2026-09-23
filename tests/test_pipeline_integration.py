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


def _wait_for(step: str, order: list, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while step not in order and time.monotonic() < deadline:
        time.sleep(0.01)


def _service_with_order_spies(tmp_path: Path, order: list) -> SoonsimService:
    """A service whose export/notify/prune/transcode only record their call order."""
    clip = tmp_path / "records" / "soonsim_20260923_010000.mp4"
    clip.parent.mkdir(parents=True, exist_ok=True)
    clip.write_bytes(b"clip")

    service = object.__new__(SoonsimService)
    service.exporter = SimpleNamespace(
        export=lambda event, prefix="soonsim": order.append("export") or clip,
        output_dir=tmp_path / "records",
    )
    service.config = SimpleNamespace(recorder=SimpleNamespace(retention_days=30))
    service.notifier = SimpleNamespace(send_video=lambda *a, **k: order.append("notify") or True)
    service.alerts_count = 0
    service.last_alert_time = "None"
    return service


def test_the_alert_never_waits_on_the_transcode(tmp_path: Path, monkeypatch):
    """Order is export, prune, notify, transcode.

    Telegram plays mp4v fine and the conversion only exists for the browser, so
    an alert must not sit behind ffmpeg (which can take minutes, or time out).
    The prune also protects the disk, so it stays ahead of the conversion.
    """
    order: list = []
    service = _service_with_order_spies(tmp_path, order)
    monkeypatch.setattr("src.main.prune_old_clips", lambda *a, **k: order.append("prune") or 0)
    monkeypatch.setattr("src.main.to_h264", lambda path: order.append("transcode") or True)

    service._export_async(
        SimpleNamespace(duration_sec=1.0, start_time=time.time()),
        prefix="soonsim",
        notify=True,
    )
    _wait_for("transcode", order)

    assert order == ["export", "prune", "notify", "transcode"]
    assert service.alerts_count == 1


def test_a_signal_clip_is_still_transcoded_without_an_alert(tmp_path: Path, monkeypatch):
    """notify=False skips only the alert; a miss must still end up playable."""
    order: list = []
    service = _service_with_order_spies(tmp_path, order)
    monkeypatch.setattr("src.main.prune_old_clips", lambda *a, **k: 0)
    monkeypatch.setattr("src.main.to_h264", lambda path: order.append("transcode") or True)

    service._export_async(
        SimpleNamespace(duration_sec=1.0, start_time=time.time()),
        prefix="signal",
        notify=False,
    )
    _wait_for("transcode", order)

    assert order == ["export", "transcode"]
    assert service.alerts_count == 0


def _stub_service(tmp_path: Path, sent: list, dog_until: float = 2.0) -> SoonsimService:
    """Build a SoonsimService without running __init__, with the detector stubbed.

    The real tracker, annotator and exporter are kept so the export wiring is
    exercised; only inference and the network are replaced.
    """
    fps = 10
    tracker = ZoneTracker(
        polygon=[(50, 50), (200, 50), (200, 200), (50, 200)],
        fps=fps,
        post_buffer_sec=1,
        min_stay_duration_sec=0.1,
    )
    dog_det = sv.Detections(
        xyxy=np.array([[70.0, 70.0, 150.0, 150.0]]),
        confidence=np.array([0.95]),
        class_id=np.array([16]),
    )
    empty_det = sv.Detections.empty()

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
    service._evaluate_detector = lambda packet, is_active: (
        dog_det if packet.timestamp < dog_until else empty_det,
        0.0,
        False,
    )
    return service


def test_completed_event_reaches_exporter_and_notifier(tmp_path: Path):
    """A completed event must survive the service wiring and reach the notifier.

    Regression: `_step_pipeline` called `_export_async` without its required
    `prefix`, so the daemon raised TypeError and died the moment any event
    completed. Above test drives the tracker/exporter directly and never
    touches that call site.
    """
    sent: list = []
    service = _stub_service(tmp_path, sent)

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for i, ts in enumerate([1.0, 1.5] + [2.0 + i * 0.1 for i in range(20)]):
        service._step_pipeline(FramePacket(frame=frame.copy(), timestamp=ts, frame_idx=i))

    deadline = time.monotonic() + 5.0
    while not sent and time.monotonic() < deadline:
        time.sleep(0.05)

    assert sent, "completed event never reached the notifier"
    assert service.alerts_count == 1
    assert Path(sent[0][0]).name.startswith("soonsim_")
