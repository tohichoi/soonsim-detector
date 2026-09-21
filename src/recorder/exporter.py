"""Video clip exporter producing H.264 MP4 files."""

import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo
from loguru import logger
import supervision as sv
from src.detector.zone_tracker import CompletedEvent
from src.recorder.annotator import HighContrastAnnotator

KST = ZoneInfo("Asia/Seoul")


class VideoClipExporter:
    """Exports completed events to MP4 video files with annotations."""

    def __init__(self, output_dir: Path, annotator: HighContrastAnnotator, fps: int = 15):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.annotator = annotator
        self.fps = fps

    def export(self, event: CompletedEvent) -> Optional[Path]:
        """Render and write all event frames into an MP4 file."""
        if not event.frames:
            logger.warning("No frames to export for completed event.")
            return None

        first_frame = event.frames[0].frame
        height, width = first_frame.shape[:2]
        video_info = sv.VideoInfo(width=width, height=height, fps=self.fps, total_frames=len(event.frames))

        timestamp_str = datetime.datetime.fromtimestamp(event.start_time, tz=KST).strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"soonsim_{timestamp_str}.mp4"

        try:
            with sv.VideoSink(target_path=str(output_file), video_info=video_info) as sink:
                for idx, packet in enumerate(event.frames):
                    dets = event.detections[idx] if idx < len(event.detections) else None
                    telemetry = event.telemetry[idx] if idx < len(event.telemetry) else None
                    # Annotate frame
                    annotated_frame = self.annotator.annotate(
                        frame=packet.frame,
                        detections=dets,
                        timestamp=packet.timestamp,
                        is_dog_in_zone=telemetry.in_zone if telemetry else False,
                        telemetry=telemetry,
                    )
                    sink.write_frame(annotated_frame)

            logger.info(f"Exported event video ({len(event.frames)} frames, {event.duration_sec:.1f}s stay) to {output_file}")
            return output_file
        except Exception as e:
            logger.error(f"Failed to export video {output_file}: {e}")
            return None
