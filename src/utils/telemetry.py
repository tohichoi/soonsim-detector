"""Structured telemetry logging and CPU/inference performance metrics."""

from dataclasses import dataclass
from pathlib import Path
from loguru import logger


@dataclass
class TelemetryStats:
    total_frames: int = 0
    inferences_run: int = 0
    frames_skipped: int = 0
    total_inference_time_ms: float = 0.0

    @property
    def skip_ratio_percent(self) -> float:
        if self.total_frames == 0:
            return 0.0
        return (self.frames_skipped / self.total_frames) * 100.0

    @property
    def avg_inference_latency_ms(self) -> float:
        if self.inferences_run == 0:
            return 0.0
        return self.total_inference_time_ms / self.inferences_run


class InferenceTelemetry:
    """Collects and reports inference telemetry with structured file logging."""

    def __init__(self, log_dir: Path = Path("./records")):
        self.stats = TelemetryStats()
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Configure file logging for detection decisions
        self.log_file = self.log_dir / "detection.log"
        logger.add(
            str(self.log_file),
            rotation="10 MB",
            retention="7 days",
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {message}",
        )

    def record_skip(self, frame_idx: int, reason: str, diff_score: float) -> None:
        """Record skipped frame."""
        self.stats.total_frames += 1
        self.stats.frames_skipped += 1
        logger.debug(f"[Frame #{frame_idx}] SKIP | {reason} | Diff: {diff_score:.2f}")

    def record_inference(
        self,
        frame_idx: int,
        reason: str,
        latency_ms: float,
        num_detected: int,
        detected_summary: str,
        top_score: float = 0.0,
    ) -> None:
        """Record executed inference."""
        self.stats.total_frames += 1
        self.stats.inferences_run += 1
        self.stats.total_inference_time_ms += latency_ms
        logger.info(
            f"[Frame #{frame_idx}] INFER | {reason} | Latency: {latency_ms:.1f}ms | Found: {num_detected} [{detected_summary}] | Top: {top_score:.2f}"
        )
