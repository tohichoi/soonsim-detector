"""Frame loading and the drawing primitives shared by the calibration tools."""

from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import tkinter as tk

GRID_STEP = 50
GRID_COLOR = (0, 255, 255)
TEXT_COLOR = (255, 255, 255)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}
PREVIEW_PATH = Path("snapshot_calibration.jpg")
GRID_PATH = Path("snapshot_grid.jpg")


def draw_grid(frame: np.ndarray, step: int = GRID_STEP) -> np.ndarray:
    """Draw a coordinate grid on frame for visual calibration."""
    grid_frame = frame.copy()
    height, width = frame.shape[:2]

    for x in range(0, width, step):
        color = GRID_COLOR if x % 100 == 0 else (100, 100, 100)
        cv2.line(grid_frame, (x, 0), (x, height), color, 1)
        cv2.putText(grid_frame, str(x), (x + 2, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, GRID_COLOR, 1)

    for y in range(0, height, step):
        color = GRID_COLOR if y % 100 == 0 else (100, 100, 100)
        cv2.line(grid_frame, (0, y), (width, y), color, 1)
        cv2.putText(grid_frame, str(y), (5, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, GRID_COLOR, 1)

    return grid_frame


def grab_frame(source: str) -> Optional[np.ndarray]:
    """Read one frame from a stream/video, or load it when source is an image file."""
    if Path(source).suffix.lower() in IMAGE_SUFFIXES:
        return cv2.imread(source)

    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        return None
    ok, frame = capture.read()
    capture.release()
    return frame if ok else None


def frame_to_photo(frame_bgr: np.ndarray, scale: float) -> tk.PhotoImage:
    """Hand the frame to Tk as a raw PPM, since PIL's ImageTk is broken here."""
    if scale != 1.0:
        height, width = frame_bgr.shape[:2]
        frame_bgr = cv2.resize(
            frame_bgr, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA
        )
    rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
    header = f"P6\n{rgb.shape[1]} {rgb.shape[0]}\n255\n".encode("ascii")
    return tk.PhotoImage(data=header + rgb.tobytes())


def put_label(frame: np.ndarray, text: str, row: int, color=TEXT_COLOR) -> None:
    """Draw one line of the on-image readout with a dark outline."""
    origin = (10, 26 + row * 22)
    cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)


def polygon_toml(points: List[Tuple[int, int]]) -> str:
    """Format the corners as the polygon block used in config.toml."""
    rows = ",\n".join(f"    [{x}, {y}]" for x, y in points)
    return f"polygon = [\n{rows}\n]"
