"""How a detection box meets the pad, measured per frame for threshold tuning.

The existing zone test asks whether a point of the box falls inside the pad
polygon. That carries no depth: a large dog passing in front of the pad covers
the pad's image position and trips the test from mid-body, which is how a
pass-by gets recorded as a visit.

These metrics carry the depth instead. In this camera the bottom of the frame is
the side nearest the camera, so the box's bottom edge is a contact line and the
gap between it and the pad's near edge says whether the dog stood on the pad or
in front of it.

Nothing here changes a verdict. The numbers are recorded so real events can say
where the thresholds belong, and replayable afterwards.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

EDGE_SAMPLES = 64
LOG_NAME = "zone_contact.jsonl"


@dataclass(frozen=True)
class ContactMetrics:
    """Depth and width of a box's contact line against the pad."""

    box: tuple
    box_height: int
    pad_top: int
    pad_bottom: int
    margin: float   # (bottom_y - pad_bottom) / box_height; >0 means nearer than the pad
    overlap: float  # fraction of the pad's width at bottom_y that the bottom edge crosses


class PadGeometry:
    """Precomputed pad mask lookups, shared by every measurement."""

    def __init__(self, mask: np.ndarray):
        self.mask = mask
        rows = np.nonzero(mask.any(axis=1))[0]
        self.pad_top = int(rows.min()) if rows.size else 0
        self.pad_bottom = int(rows.max()) if rows.size else 0
        self.row_width = mask.sum(axis=1)

    def measure(self, box: Sequence[float]) -> Optional[ContactMetrics]:
        """Contact metrics for one box, or None when the box is degenerate."""
        x0, y0, x1, y1 = (int(round(float(v))) for v in box)
        height = y1 - y0
        if height <= 0 or x1 <= x0:
            return None

        row = int(np.clip(y1, 0, self.mask.shape[0] - 1))
        columns = np.clip(
            np.linspace(x0, x1, EDGE_SAMPLES).astype(int), 0, self.mask.shape[1] - 1
        )
        hits = int(self.mask[row, columns].sum())
        pad_width = int(self.row_width[row])
        return ContactMetrics(
            box=(x0, y0, x1, y1),
            box_height=height,
            pad_top=self.pad_top,
            pad_bottom=self.pad_bottom,
            margin=(y1 - self.pad_bottom) / height,
            overlap=hits / pad_width if pad_width else 0.0,
        )

    def largest(self, detections) -> Optional[ContactMetrics]:
        """Contact metrics for the biggest box, which is the dog."""
        if detections is None or len(detections) == 0:
            return None
        boxes = detections.xyxy
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        return self.measure(boxes[int(np.argmax(areas))])


class ZoneContactLog:
    """Append-only JSONL of per-frame contact metrics, one line per frame."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8")

    def record(
        self,
        frame_idx: int,
        timestamp: float,
        status: str,
        track_ids: Sequence[int],
        metrics: Optional[ContactMetrics],
        in_zone: bool,
    ) -> None:
        """Write one frame. Frames without a detection are skipped."""
        if metrics is None:
            return
        row = {
            "t": round(timestamp, 3),
            "f": frame_idx,
            "st": status,
            "ids": list(track_ids),
            "in": bool(in_zone),
            **asdict(metrics),
        }
        row["box"] = list(row["box"])
        row["margin"] = round(row["margin"], 4)
        row["overlap"] = round(row["overlap"], 4)
        self._handle.write(json.dumps(row) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()
