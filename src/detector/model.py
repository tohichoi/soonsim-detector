from typing import List, Union
import numpy as np
import supervision as sv
from ultralytics import YOLO


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

    def detect(self, frame: np.ndarray) -> sv.Detections:
        """Run inference and return supervision Detections for target classes only."""
        results = self.model(
            frame,
            conf=self.confidence_threshold,
            classes=self.class_ids,
            verbose=False,
        )[0]
        return sv.Detections.from_ultralytics(results)
