"""Main service orchestrating capture, detection, recording, and alerting."""

import argparse
import datetime
from pathlib import Path
import signal
import sys
import threading
import time
from loguru import logger
from rich.live import Live
import supervision as sv
from src.capture.stream import RingBuffer, VideoStreamReader
from src.cli.dashboard import Dashboard
from src.config import load_config
from src.detector.model import DogDetector
from src.detector.motion_gate import MotionGate
from src.detector.zone_tracker import CompletedEvent, EventStatus, ZoneTracker
from src.notifier.telegram import TelegramNotifier
from src.recorder.annotator import HighContrastAnnotator
from src.recorder.exporter import VideoClipExporter
from src.utils.telemetry import InferenceTelemetry


class SoonsimService:
    """Core daemon managing video ingestion, detection, and alerting."""

    def __init__(self, config_path: str | Path = "config/config.toml"):
        self.config = load_config(config_path)
        logger.remove()
        logger.add(sys.stderr, level=self.config.logging.level)

        self.stream_reader = VideoStreamReader(
            source=self.config.camera.source,
            target_fps=self.config.camera.fps,
            reconnect_interval=self.config.camera.reconnect_interval_sec,
        )

        pre_buffer_frames = self.config.recorder.pre_buffer_sec * self.config.camera.fps
        self.ring_buffer = RingBuffer(max_frames=pre_buffer_frames)

        self.detector = DogDetector(
            model_name=self.config.detector.model_name,
            confidence_threshold=self.config.detector.confidence_threshold,
            class_ids=[15, 16],  # COCO cat (15) and dog (16)
            max_threads=self.config.detector.max_threads,
        )

        self.motion_gate = MotionGate(
            motion_threshold=self.config.detector.motion_threshold,
            failsafe_interval_sec=self.config.detector.failsafe_interval_sec,
            enabled=self.config.detector.motion_gate_enabled,
        )
        self.telemetry = InferenceTelemetry(log_dir=self.config.recorder.output_dir)
        self.cached_detections = sv.Detections.empty()

        self.tracker = ZoneTracker(
            polygon=self.config.zone.polygon,
            track_thresh=self.config.detector.track_thresh,
            match_thresh=self.config.detector.match_thresh,
            fps=self.config.camera.fps,
            post_buffer_sec=self.config.recorder.post_buffer_sec,
            min_stay_duration_sec=self.config.recorder.min_stay_duration_sec,
        )

        self.annotator = HighContrastAnnotator(zone=self.tracker.zone)
        self.exporter = VideoClipExporter(
            output_dir=self.config.recorder.output_dir,
            annotator=self.annotator,
            fps=self.config.camera.fps,
        )
        self.notifier = TelegramNotifier(config=self.config.telegram)
        self.dashboard = Dashboard()

        self.is_running = False
        self.alerts_count = 0
        self.last_alert_time = "None"

    def _process_completed_event_async(self, event: CompletedEvent) -> None:
        """Export video clip and send alert asynchronously."""
        def worker():
            try:
                output_path = self.exporter.export(event)
                if output_path is not None:
                    self.notifier.send_video(
                        video_path=output_path,
                        stay_duration_sec=event.duration_sec,
                        start_time=event.start_time,
                    )
                    self.alerts_count += 1
                    self.last_alert_time = datetime.datetime.fromtimestamp(event.start_time).strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                logger.error(f"Error processing completed event: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def run(self, enable_dashboard: bool = True) -> None:
        """Run main processing loop."""
        self.is_running = True
        logger.info("Starting Soonsim Detector Service...")

        fps_calc_time = time.monotonic()
        fps_counter = 0
        current_fps = 0.0

        def shutdown_handler(signum, frame):
            logger.info("Shutdown signal received. Stopping service...")
            self.is_running = False
            self.stream_reader.stop()

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

        live_context = Live(self.dashboard.generate_table({}), refresh_per_second=4) if enable_dashboard else None

        try:
            if live_context:
                live_context.start()

            for packet in self.stream_reader.frames():
                if not self.is_running:
                    break

                # Update pre-buffer when idle
                pre_frames = self.ring_buffer.get_all()
                if self.tracker.status == EventStatus.IDLE:
                    self.ring_buffer.append(packet)

                # Motion Gating & Frame Decimation
                is_active = (self.tracker.status == EventStatus.ACTIVE)
                should_decimate = (packet.frame_idx % self.config.detector.inference_interval_frames == 0)

                if is_active or should_decimate:
                    should_infer, reason, diff_score = self.motion_gate.evaluate(
                        packet.frame, is_active_event=is_active
                    )
                    if should_infer:
                        t0 = time.monotonic()
                        detections = self.detector.detect(packet.frame)
                        latency_ms = (time.monotonic() - t0) * 1000.0
                        self.cached_detections = detections
                        summary = f"{len(detections)} box(es)" if len(detections) > 0 else "none"
                        self.telemetry.record_inference(
                            frame_idx=packet.frame_idx,
                            reason=reason,
                            latency_ms=latency_ms,
                            num_detected=len(detections),
                            detected_summary=summary,
                        )
                    else:
                        detections = self.cached_detections
                        self.telemetry.record_skip(packet.frame_idx, reason, diff_score)
                else:
                    detections = self.cached_detections
                    self.telemetry.record_skip(packet.frame_idx, "FRAME_DECIMATED", 0.0)

                # Tracking & State Machine
                tracked_dets, dog_in_zone, completed_event = self.tracker.update(
                    packet=packet,
                    detections=detections,
                    pre_buffer_frames=pre_frames,
                )

                if completed_event is not None:
                    self.ring_buffer.clear()
                    self._process_completed_event_async(completed_event)

                # FPS Telemetry
                fps_counter += 1
                now = time.monotonic()
                if now - fps_calc_time >= 1.0:
                    current_fps = fps_counter / (now - fps_calc_time)
                    fps_counter = 0
                    fps_calc_time = now

                # Dashboard update
                if live_context:
                    status_colors = {
                        EventStatus.IDLE: "white",
                        EventStatus.ACTIVE: "bold green",
                        EventStatus.COOLDOWN: "yellow",
                    }
                    stats = {
                        "connected": True,
                        "fps": current_fps,
                        "skip_ratio": self.telemetry.stats.skip_ratio_percent,
                        "avg_latency_ms": self.telemetry.stats.avg_inference_latency_ms,
                        "frame_idx": packet.frame_idx,
                        "status": self.tracker.status.value,
                        "status_color": status_colors.get(self.tracker.status, "white"),
                        "dog_in_zone": dog_in_zone,
                        "buffer_size": len(self.ring_buffer),
                        "alerts_count": self.alerts_count,
                        "last_alert_time": self.last_alert_time,
                    }
                    live_context.update(self.dashboard.generate_table(stats))

        finally:
            if live_context:
                live_context.stop()
            self.stream_reader.stop()
            logger.info("Soonsim Detector Service stopped cleanly.")


def main():
    parser = argparse.ArgumentParser(description="Soonsim Detector Daemon")
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default="config/config.toml",
        help="Path to TOML configuration file",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Disable Rich live dashboard",
    )
    args = parser.parse_args()

    service = SoonsimService(config_path=args.config)
    service.run(enable_dashboard=not args.no_dashboard)


if __name__ == "__main__":
    main()
