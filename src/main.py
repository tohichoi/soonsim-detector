"""Main service orchestrating capture, detection, recording, alerting, and web viewing."""

import argparse
import datetime
from pathlib import Path
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo
import cv2
from loguru import logger
from rich.live import Live
import supervision as sv
from src.capture.stream import FramePacket, RingBuffer, VideoStreamReader
from src.cli.dashboard import Dashboard
from src.config import load_config
from src.detector.model import DogDetector
from src.detector.motion_gate import MotionGate
from src.detector.zone_tracker import CompletedEvent, EventStatus, ZoneTracker
from src.notifier.telegram import TelegramNotifier
from src.recorder.annotator import HighContrastAnnotator
from src.recorder.exporter import VideoClipExporter
from src.utils.telemetry import InferenceTelemetry
from src.viewer.server import ViewerServer
from src.viewer.state import ViewerStateStore

KST = ZoneInfo("Asia/Seoul")


class SoonsimService:
    """Core daemon managing video ingestion, detection, alerting, and live web viewing."""

    def __init__(self, config_path: str | Path = "config/config.toml"):
        self.config = load_config(config_path)
        logger.remove()
        logger.add(sys.stderr, level=self.config.logging.level)

        self._init_stream_and_detector()
        self._init_recorder_and_viewer()

        self.is_running = False
        self.alerts_count = 0
        self.last_alert_time = "None"
        self._last_viewer_update_t = 0.0
        self._last_baseline_t = 0.0
        self._prev_animal_count = 0

    def _init_stream_and_detector(self) -> None:
        """Initialize stream reader, ring buffer, detector, and motion gate."""
        self.stream_reader = VideoStreamReader(
            source=self.config.camera.source,
            target_fps=self.config.camera.fps,
            reconnect_interval=self.config.camera.reconnect_interval_sec,
        )
        pre_frames = self.config.recorder.pre_buffer_sec * self.config.camera.fps
        self.ring_buffer = RingBuffer(max_frames=pre_frames)
        self.detector = DogDetector(
            model_name=self.config.detector.model_name,
            confidence_threshold=self.config.detector.confidence_threshold,
            class_ids=self.config.detector.animal_class_ids,
            max_threads=self.config.detector.max_threads,
        )
        self.motion_gate = MotionGate(
            motion_threshold=self.config.detector.motion_threshold,
            failsafe_interval_sec=self.config.detector.failsafe_interval_sec,
            enabled=self.config.detector.motion_gate_enabled,
        )
        self.telemetry = InferenceTelemetry(log_dir=self.config.recorder.output_dir)
        self.cached_detections = sv.Detections.empty()

    def _init_recorder_and_viewer(self) -> None:
        """Initialize tracker, annotator, exporter, notifier, and web viewer."""
        self.tracker = ZoneTracker(
            polygon=self.config.zone.polygon,
            track_thresh=self.config.detector.track_thresh,
            match_thresh=self.config.detector.match_thresh,
            fps=self.config.camera.fps,
            lost_track_buffer_sec=self.config.detector.lost_track_buffer_sec,
            post_buffer_sec=self.config.recorder.post_buffer_sec,
            min_stay_duration_sec=self.config.recorder.min_stay_duration_sec,
        )
        self.annotator = HighContrastAnnotator(
            zone=self.tracker.zone,
            min_stay_duration_sec=self.config.recorder.min_stay_duration_sec,
            fps=self.config.camera.fps,
        )
        self.exporter = VideoClipExporter(
            output_dir=self.config.recorder.output_dir,
            annotator=self.annotator,
            fps=self.config.camera.fps,
        )
        self.notifier = TelegramNotifier(config=self.config.telegram)
        self.dashboard = Dashboard()
        self.viewer_state = ViewerStateStore(retention_sec=self.config.viewer.retention_sec)
        self.viewer_server = (
            ViewerServer(state_store=self.viewer_state, config=self.config)
            if self.config.viewer.enabled
            else None
        )

    def _process_completed_event_async(self, event: CompletedEvent) -> None:
        """Export video clip and send alert asynchronously."""
        def worker():
            try:
                path = self.exporter.export(event)
                if path is not None:
                    self.notifier.send_video(path, event.duration_sec, event.start_time)
                    self.alerts_count += 1
                    self.last_alert_time = datetime.datetime.fromtimestamp(
                        event.start_time, tz=KST
                    ).strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                logger.error(f"Error processing completed event: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _evaluate_detector(self, packet: FramePacket, is_active: bool) -> tuple[sv.Detections, float]:
        """Perform motion gating and optional YOLO inference."""
        should_decimate = (packet.frame_idx % self.config.detector.inference_interval_frames == 0)
        if not (is_active or should_decimate):
            self.telemetry.record_skip(packet.frame_idx, "FRAME_DECIMATED", 0.0)
            return self.cached_detections, 0.0

        should_infer, reason, diff_score = self.motion_gate.evaluate(packet.frame, is_active_event=is_active)
        if should_infer:
            t0 = time.monotonic()
            detections = self.detector.detect(packet.frame)
            latency_ms = (time.monotonic() - t0) * 1000.0
            self.cached_detections = detections
            summary = f"{len(detections)} box(es)" if len(detections) > 0 else "none"
            self.telemetry.record_inference(packet.frame_idx, reason, latency_ms, len(detections), summary)
        else:
            detections = self.cached_detections
            self.telemetry.record_skip(packet.frame_idx, reason, diff_score)
        return detections, diff_score

    def _update_viewer(self, packet: FramePacket, dets: sv.Detections, in_zone: bool, diff: float) -> None:
        """Synchronize frame and status to integrated ViewerStateStore."""
        now = time.time()
        is_motion = diff >= self.config.detector.motion_threshold
        if in_zone:
            title, desc, stype = "순심이 배변판 진입 확인!", "순심이가 배변판 영역 안에 위치하고 있습니다.", "dog_on_pad"
        elif is_motion:
            title, desc, stype = "움직임/조도 변화 감지됨", f"화면 내 움직임 감지 (변화 점수: {diff:.1f})", "motion"
        else:
            title, desc, stype = "현재 변화 없음 (정적 상태)", "실시간 감시 중이며 배변판에 유의미한 변화가 없습니다.", "no_change"

        if not in_zone and (now - self._last_viewer_update_t) < 0.5:
            return

        self._last_viewer_update_t = now
        annotated = self.annotator.annotate(
            packet.frame,
            dets,
            timestamp=packet.timestamp,
            is_dog_in_zone=in_zone,
            telemetry=self.tracker.last_telemetry,
        )
        _, img_encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        img_bytes = img_encoded.tobytes()
        labels = [f"class_{c}" for c in (dets.class_id if dets.class_id is not None else [])]

        self.viewer_state.update_live(title, desc, stype, labels, in_zone, diff, img_bytes)
        self._record_viewer_event_if_needed(now, in_zone, len(dets), is_motion, labels, diff, img_bytes)

    def _record_viewer_event_if_needed(
        self, now: float, in_zone: bool, count: int, is_motion: bool,
        labels: list[str], diff: float, img_bytes: bytes
    ) -> None:
        """Record periodic or discrete events into viewer history."""
        event_type: Optional[str] = None
        if in_zone:
            event_type = "DOG_ON_PAD"
        elif count > 0 and count != self._prev_animal_count:
            event_type = "ANIMAL_DETECTED"
        elif is_motion:
            event_type = "MOTION_CHANGE"
        elif (now - self._last_baseline_t) >= 600.0:
            event_type = "PERIODIC_BASELINE"
            self._last_baseline_t = now

        self._prev_animal_count = count
        if event_type:
            self.viewer_state.push_event(event_type, labels, in_zone, diff, img_bytes)

    def _step_pipeline(self, packet: FramePacket) -> tuple[bool, bool]:
        """Execute single frame pipeline step and return (is_active, in_zone)."""
        pre = self.ring_buffer.get_all()
        if self.tracker.status == EventStatus.IDLE:
            self.ring_buffer.append(packet)

        is_active = (self.tracker.status == EventStatus.ACTIVE)
        detections, diff = self._evaluate_detector(packet, is_active)
        _, in_zone, completed = self.tracker.update(packet, detections, pre)

        if completed:
            self.ring_buffer.clear()
            self._process_completed_event_async(completed)

        self._update_viewer(packet, detections, in_zone, diff)
        return is_active, in_zone

    def _update_dashboard(self, live: Live, packet: FramePacket, is_active: bool, in_zone: bool, fps: float) -> None:
        """Render Rich live dashboard table."""
        stats: Dict[str, Any] = {
            "connected": True,
            "fps": fps,
            "skip_ratio": self.telemetry.stats.skip_ratio_percent,
            "avg_latency_ms": self.telemetry.stats.avg_inference_latency_ms,
            "frame_idx": packet.frame_idx,
            "status": self.tracker.status.value,
            "status_color": "bold green" if is_active else "white",
            "dog_in_zone": in_zone,
            "buffer_size": len(self.ring_buffer),
            "alerts_count": self.alerts_count,
            "last_alert_time": self.last_alert_time,
        }
        live.update(self.dashboard.generate_table(stats))

    def run(self, enable_dashboard: bool = True) -> None:
        """Run main processing loop."""
        self.is_running = True
        logger.info("Starting Soonsim Detector Service...")
        if self.viewer_server:
            self.viewer_server.start()

        fps_calc_t, fps_count, current_fps = time.monotonic(), 0, 0.0

        def on_shutdown(signum, frame):
            self.is_running = False
            self.stream_reader.stop()

        signal.signal(signal.SIGINT, on_shutdown)
        signal.signal(signal.SIGTERM, on_shutdown)
        live = Live(self.dashboard.generate_table({}), refresh_per_second=4) if enable_dashboard else None

        try:
            if live:
                live.start()
            for packet in self.stream_reader.frames():
                if not self.is_running:
                    break
                is_active, in_zone = self._step_pipeline(packet)
                fps_count += 1
                now = time.monotonic()
                if now - fps_calc_t >= 1.0:
                    current_fps, fps_count, fps_calc_t = fps_count / (now - fps_calc_t), 0, now
                if live:
                    self._update_dashboard(live, packet, is_active, in_zone, current_fps)
        finally:
            if live:
                live.stop()
            if self.viewer_server:
                self.viewer_server.stop()
            self.stream_reader.stop()
            logger.info("Soonsim Detector Service stopped cleanly.")


def main():
    parser = argparse.ArgumentParser(description="Soonsim Detector Daemon")
    parser.add_argument("-c", "--config", default="config/config.toml", help="Path to TOML config")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable Rich dashboard")
    args = parser.parse_args()

    service = SoonsimService(config_path=args.config)
    service.run(enable_dashboard=not args.no_dashboard)


if __name__ == "__main__":
    main()
