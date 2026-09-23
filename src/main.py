"""Main service orchestrating capture, detection, recording, alerting, and web viewing."""

import argparse
import datetime
from pathlib import Path
import signal
import sys
import threading
import time
from typing import Any, Dict
from zoneinfo import ZoneInfo
from loguru import logger
from rich.live import Live
import supervision as sv
from src.capture.stream import FramePacket, RingBuffer, VideoStreamReader
from src.cli.dashboard import Dashboard
from src.config import load_config
from src.detector.model import DogDetector
from src.detector.motion_gate import MotionGate
from src.detector.zone_contact import LOG_NAME, ZoneContactLog
from src.detector.zone_tracker import CompletedEvent, EventStatus, ZoneTracker
from src.notifier.telegram import TelegramNotifier
from src.recorder.annotator import HighContrastAnnotator
from src.recorder.exporter import VideoClipExporter, prune_old_clips
from src.recorder.signal_recorder import SignalRecorder
from src.recorder.transcode import to_h264
from src.utils.telemetry import InferenceTelemetry
from src.viewer.live_feed import LiveFeed
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

    def _init_stream_and_detector(self) -> None:
        """Initialize stream reader, ring buffer, detector, and motion gate."""
        self.stream_reader = VideoStreamReader(
            source=self.config.camera.source,
            target_fps=self.config.camera.fps,
            reconnect_interval=self.config.camera.reconnect_interval_sec,
            roll_deg=self.config.camera.roll_deg,
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
        self.contact_log = ZoneContactLog(
            Path(self.config.recorder.output_dir) / LOG_NAME
        )
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
            contact_log=self.contact_log,
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
        self.signal_recorder = (
            SignalRecorder(
                fps=self.config.camera.fps,
                min_signal_sec=self.config.recorder.signal_min_sec,
                pre_buffer_sec=self.config.recorder.pre_buffer_sec,
                post_buffer_sec=self.config.recorder.post_buffer_sec,
            )
            if self.config.recorder.signal_clip_enabled
            else None
        )
        self.notifier = TelegramNotifier(config=self.config.telegram)
        self.dashboard = Dashboard()
        self.viewer_state = ViewerStateStore(retention_sec=self.config.viewer.retention_sec)
        self.live_feed = LiveFeed(
            state=self.viewer_state,
            annotator=self.annotator,
            motion_threshold=self.config.detector.motion_threshold,
        )
        self.viewer_server = (
            ViewerServer(state_store=self.viewer_state, config=self.config)
            if self.config.viewer.enabled
            else None
        )

    def _export_async(self, event: CompletedEvent, prefix: str, notify: bool) -> None:
        """Export a clip in the background. Only a real event alerts anyone."""
        def worker():
            try:
                path = self.exporter.export(event, prefix=prefix)
                if path is None:
                    return
                self._prune_clips()
                if notify:
                    self.notifier.send_video(path, event.duration_sec, event.start_time)
                    self.alerts_count += 1
                    self.last_alert_time = datetime.datetime.fromtimestamp(
                        event.start_time, tz=KST
                    ).strftime("%Y-%m-%d %H:%M:%S")
                # Conversion serves browser playback only, and Telegram plays
                # mp4v fine, so it runs last: the alert and the prune never wait
                # on ffmpeg. A clip that fails to convert is kept as exported.
                if not to_h264(path):
                    logger.warning(f"{path.name} is not H.264; keeping it as exported.")
            except Exception as e:
                logger.error(f"Error exporting clip: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _prune_clips(self) -> None:
        """Drop clips past the retention window; a full volume stops the service."""
        removed = prune_old_clips(
            self.exporter.output_dir, self.config.recorder.retention_days
        )
        if removed:
            logger.info(
                f"Pruned {removed} clip(s) older than "
                f"{self.config.recorder.retention_days:.0f} days."
            )

    def _evaluate_detector(self, packet: FramePacket, is_active: bool) -> tuple[sv.Detections, float, bool]:
        """Perform motion gating and YOLO inference; report unexplained motion.

        The third value is True when the frame moved enough to trigger inference
        yet no animal came back — the shape of a miss, and what arms the signal
        recorder. Heartbeats score below the threshold by definition, so they
        never read as signals.
        """
        should_decimate = (packet.frame_idx % self.config.detector.inference_interval_frames == 0)
        if not (is_active or should_decimate):
            self.telemetry.record_skip(packet.frame_idx, "FRAME_DECIMATED", 0.0)
            return self.cached_detections, 0.0, False

        should_infer, reason, diff_score = self.motion_gate.evaluate(packet.frame, is_active_event=is_active)
        is_signal = False
        if should_infer:
            t0 = time.monotonic()
            detections, top_score = self.detector.detect(packet.frame)
            latency_ms = (time.monotonic() - t0) * 1000.0
            self.cached_detections = detections
            summary = f"{len(detections)} box(es)" if len(detections) > 0 else "none"
            self.telemetry.record_inference(
                packet.frame_idx, reason, latency_ms, len(detections), summary, top_score
            )
            is_signal = (
                len(detections) == 0
                and diff_score >= self.config.detector.motion_threshold
            )
        else:
            detections = self.cached_detections
            self.telemetry.record_skip(packet.frame_idx, reason, diff_score)
        return detections, diff_score, is_signal

    def _step_pipeline(self, packet: FramePacket) -> tuple[bool, bool]:
        """Execute single frame pipeline step and return (is_active, in_zone)."""
        pre = self.ring_buffer.get_all()
        if self.tracker.status == EventStatus.IDLE:
            self.ring_buffer.append(packet)

        is_active = (self.tracker.status == EventStatus.ACTIVE)
        detections, diff, is_signal = self._evaluate_detector(packet, is_active)
        _, in_zone, completed = self.tracker.update(packet, detections, pre)

        if completed:
            self.ring_buffer.clear()
            self._export_async(completed, prefix="soonsim", notify=True)

        if self.signal_recorder is not None:
            unexplained = self.signal_recorder.observe(packet, detections, is_signal)
            if unexplained is not None:
                logger.warning(
                    f"Unexplained motion ran {unexplained.duration_sec:.1f}s; keeping a clip."
                )
                self._export_async(unexplained, prefix="signal", notify=False)

        self.live_feed.push(
            packet, detections, in_zone, diff, telemetry=self.tracker.last_telemetry
        )
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
