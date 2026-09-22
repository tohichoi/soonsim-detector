from typing import List, Tuple, Union
import numpy as np
import supervision as sv
from ultralytics import YOLO

# Boxes are collected down to this score and then judged in Python, so a frame
# that finds nothing still reports how close it came. Without that number a
# missed animal and an empty room look identical in the log.
SCORE_FLOOR = 0.01


class DogDetector:
    """Dog detector filtering for animal classes (dog, cat)."""

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        confidence_threshold: float = 0.30,
        class_ids: Union[int, List[int]] = [15, 16],
        max_threads: int = 2,
    ):
        try:
            import torch
            torch.set_num_threads(max_threads)
        except Exception:
            pass
        self.model = YOLO(model_name)
        self.confidence_threshold = confidence_threshold
        self.class_ids = [class_ids] if isinstance(class_ids, int) else class_ids

    def detect(self, frame: np.ndarray) -> Tuple[sv.Detections, float]:
        """Run inference; return the kept detections and the best score seen.

        The second value is the highest animal score on the frame whether or not
        it cleared the threshold, so a near-miss (0.24) reads differently from a
        frame the model saw nothing in (0.02).
        """
        results = self.model(frame, conf=SCORE_FLOOR, classes=self.class_ids, verbose=False)[0]
        detections = sv.Detections.from_ultralytics(results)
        if len(detections) == 0:
            return detections, 0.0
        keep = detections.confidence >= self.confidence_threshold
        return detections[keep], float(detections.confidence.max())
