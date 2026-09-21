"""High-contrast frame annotation using Supervision."""

import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo
import cv2
import numpy as np
import supervision as sv

from src.detector.zone_tracker import FrameTelemetry
from src.recorder.hud import TelemetryHud

KST = ZoneInfo("Asia/Seoul")


class HighContrastAnnotator:
    """High contrast box, label, and zone visualizer."""

    def __init__(
        self,
        zone: sv.PolygonZone,
        min_stay_duration_sec: float = 1.0,
        fps: int = 15,
    ):
        self.zone = zone
        self.box_annotator = sv.BoxAnnotator(
            thickness=3,
            color=sv.Color.from_hex("#00FF00")
        )
        self.label_annotator = sv.LabelAnnotator(
            text_scale=0.5,
            text_thickness=1,
            text_padding=4,
            color=sv.Color.from_hex("#00FF00"),
            text_color=sv.Color.from_hex("#000000"),
        )
        self.zone_annotator = sv.PolygonZoneAnnotator(
            zone=zone,
            color=sv.Color.from_hex("#00FFFF"),
            thickness=2,
            text_thickness=1,
            text_scale=0.5,
        )
        self.hud = TelemetryHud(min_stay_sec=min_stay_duration_sec, fps=fps)

    def annotate(
        self,
        frame: np.ndarray,
        detections: Optional[sv.Detections],
        timestamp: float,
        is_dog_in_zone: bool = False,
        telemetry: Optional[FrameTelemetry] = None,
    ) -> np.ndarray:
        """Annotate frame with polygon zone, boxes, and timestamp."""
        annotated = frame.copy()
        annotated = self.zone_annotator.annotate(scene=annotated)

        if detections is not None and len(detections) > 0:
            labels: List[str] = []
            for i in range(len(detections)):
                conf = float(detections.confidence[i]) if detections.confidence is not None else 0.0
                track_id = detections.tracker_id[i] if detections.tracker_id is not None else "N/A"
                labels.append(f"Dog #{track_id} ({conf:.2f})")

            annotated = self.box_annotator.annotate(scene=annotated, detections=detections)
            annotated = self.label_annotator.annotate(scene=annotated, detections=detections, labels=labels)

        # Draw timestamp header
        dt_str = datetime.datetime.fromtimestamp(timestamp, tz=KST).strftime("%Y-%m-%d %H:%M:%S")
        status_text = "DOG IN ZONE" if is_dog_in_zone else "MONITORING"
        status_color = (0, 255, 0) if is_dog_in_zone else (200, 200, 200)

        cv2.putText(
            annotated,
            f"{dt_str} | {status_text}",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            f"{dt_str} | {status_text}",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            status_color,
            1,
            cv2.LINE_AA,
        )

        if telemetry is not None:
            self.hud.draw(annotated, telemetry)

        return annotated
