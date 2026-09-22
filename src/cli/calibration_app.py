"""Tk window for pad calibration: a red vertical reference, then a green pad.

Tk rather than OpenCV's highgui, whose bundled Qt ships no fonts and renders its
menus, tooltips and save dialogs blank. Two traps on this stack: PIL's ImageTk
is broken so frames go to Tk as raw PPM, and plain tk.Button aborts the process
while ttk.Button is fine.
"""

import tkinter as tk
from typing import List, Optional, Tuple

import cv2
import numpy as np
from tkinter import ttk

from src.cli.frame_view import (
    PREVIEW_PATH,
    TEXT_COLOR,
    draw_grid,
    frame_to_photo,
    grab_frame,
    put_label,
)
from src.cli.quad_geometry import (
    CORNER_COUNT,
    VERTICAL_POINT_COUNT,
    is_bowtie,
    line_roll_deg,
    roll_from_quad,
)
from src.utils.rotation import FrameRotator

VERTICAL_COLOR = (0, 0, 255)
PAD_COLOR = (0, 200, 0)


class CalibrationApp:
    """Two-phase picker: a red vertical reference, then the green pad polygon."""

    def __init__(
        self,
        root: tk.Tk,
        frame: np.ndarray,
        source: str,
        roll_deg: float = 0.0,
        on_save=None,
    ):
        self.root = root
        self.source = source
        self.on_save = on_save
        self.roll_deg = float(roll_deg)
        self._rotator = FrameRotator(self.roll_deg)
        self.frame = self._rotator.apply(frame)
        self.vertical: List[Tuple[int, int]] = []
        self.polygon: List[Tuple[int, int]] = []
        self.cursor: Optional[Tuple[int, int]] = None
        self.show_grid = True
        self.scale = self._fit_scale(root, self.frame)
        self.photo: Optional[tk.PhotoImage] = None
        self._build_widgets()
        self.refresh()

    @staticmethod
    def _fit_scale(root: tk.Tk, frame: np.ndarray) -> float:
        height, width = frame.shape[:2]
        room_w = root.winfo_screenwidth() - 80
        room_h = root.winfo_screenheight() - 260
        return max(0.2, min(1.0, room_w / width, room_h / height))

    def _build_widgets(self) -> None:
        self.canvas = tk.Canvas(
            self.root,
            width=int(self.frame.shape[1] * self.scale),
            height=int(self.frame.shape[0] * self.scale),
            highlightthickness=0,
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Button-3>", lambda _event: self.undo())
        self.canvas.bind("<Motion>", self.on_motion)

        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=8, pady=6)
        for label, command in (
            ("Undo (u)", self.undo),
            ("Reset (r)", self.reset),
            ("Grid (g)", self.toggle_grid),
            ("Recapture (c)", self.recapture),
            ("Save (s)", self.save),
        ):
            ttk.Button(bar, text=label, command=command).pack(side="left", padx=2)

        self.status = ttk.Label(self.root, anchor="w", justify="left")
        self.status.pack(fill="x", padx=10, pady=(0, 8))

        for key, command in (
            ("u", self.undo),
            ("r", self.reset),
            ("g", self.toggle_grid),
            ("c", self.recapture),
            ("s", self.save),
            ("q", self.root.destroy),
        ):
            self.root.bind(key, lambda _event, fn=command: fn())
        self.root.bind("<Escape>", lambda _event: self.root.destroy())

    # -- input ----------------------------------------------------------

    def _to_frame_coords(self, event) -> Tuple[int, int]:
        return int(event.x / self.scale), int(event.y / self.scale)

    def on_click(self, event) -> None:
        point = self._to_frame_coords(event)
        if len(self.vertical) < VERTICAL_POINT_COUNT:
            self.vertical.append(point)
        elif len(self.polygon) < CORNER_COUNT:
            self.polygon.append(point)
        self.refresh()

    def on_motion(self, event) -> None:
        self.cursor = self._to_frame_coords(event)
        self.refresh(redraw_image=False)

    def undo(self) -> None:
        if self.polygon:
            self.polygon.pop()
        elif self.vertical:
            self.vertical.pop()
        self.refresh()

    def reset(self) -> None:
        self.vertical.clear()
        self.polygon.clear()
        self.refresh()

    def toggle_grid(self) -> None:
        self.show_grid = not self.show_grid
        self.refresh()

    def recapture(self) -> None:
        frame = grab_frame(self.source)
        if frame is not None:
            self.frame = self._rotator.apply(frame)
        self.refresh()

    # -- rendering ------------------------------------------------------

    def _draw_vertical(self, canvas: np.ndarray) -> None:
        if len(self.vertical) == VERTICAL_POINT_COUNT:
            start, end = self.vertical
            # Extend past both clicks so the line can be judged against the frame edge.
            dx, dy = end[0] - start[0], end[1] - start[1]
            norm = float(np.hypot(dx, dy)) or 1.0
            reach = int(np.hypot(*canvas.shape[:2]))
            far = (int(start[0] - dx / norm * reach), int(start[1] - dy / norm * reach))
            near = (int(start[0] + dx / norm * reach), int(start[1] + dy / norm * reach))
            cv2.line(canvas, far, near, VERTICAL_COLOR, 2, cv2.LINE_AA)
        for index, point in enumerate(self.vertical):
            cv2.circle(canvas, point, 5, VERTICAL_COLOR, -1)
            cv2.putText(canvas, f"R{index + 1}", (point[0] + 7, point[1] - 7),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, VERTICAL_COLOR, 2, cv2.LINE_AA)

    def _draw_polygon(self, canvas: np.ndarray) -> None:
        if len(self.polygon) > 1:
            closed = len(self.polygon) == CORNER_COUNT
            cv2.polylines(canvas, [np.array(self.polygon, np.int32)], closed, PAD_COLOR, 2, cv2.LINE_AA)
        for index, point in enumerate(self.polygon):
            cv2.circle(canvas, point, 5, PAD_COLOR, -1)
            cv2.putText(canvas, f"P{index + 1}", (point[0] + 7, point[1] - 7),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, PAD_COLOR, 2, cv2.LINE_AA)

    def _roll_word(self) -> str:
        """What the red line measures depends on whether the view is de-rolled."""
        return "residual roll (should be 0)" if self._rotator.enabled else "camera roll"

    def _labels(self) -> List[Tuple[str, tuple]]:
        line = self.roll_from_line()
        line_text = f"{self._roll_word()}: {'-' if line is None else f'{line:+.1f} deg'}"
        if len(self.vertical) < VERTICAL_POINT_COUNT:
            rows = [("STEP 1 RED: click two points on a world-vertical edge", VERTICAL_COLOR),
                    ("(wall seam, door frame) - its tilt becomes the camera roll", TEXT_COLOR)]
        elif len(self.polygon) < CORNER_COUNT:
            rows = [(line_text, VERTICAL_COLOR),
                    (f"STEP 2 GREEN: click pad corner {len(self.polygon) + 1} of {CORNER_COUNT}", PAD_COLOR)]
        else:
            pad = self.roll_from_pad()
            rows = [(line_text, VERTICAL_COLOR),
                    (f"roll from green pad: {'-' if pad is None else f'{pad:+.1f} deg'}", PAD_COLOR)]
        if is_bowtie(self.polygon):
            rows.append(("BOWTIE: corners cross over - press r and go around", VERTICAL_COLOR))
        if self.cursor is not None:
            rows.append((f"cursor {self.cursor[0]}, {self.cursor[1]}", TEXT_COLOR))
        return rows

    def composed(self) -> np.ndarray:
        """The frame with grid, both shapes and the readout burned in."""
        canvas = draw_grid(self.frame) if self.show_grid else self.frame.copy()
        self._draw_vertical(canvas)
        self._draw_polygon(canvas)
        for row, (text, color) in enumerate(self._labels()):
            put_label(canvas, text, row, color)
        return canvas

    def refresh(self, redraw_image: bool = True) -> None:
        if redraw_image:
            self.photo = frame_to_photo(self.composed(), self.scale)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.status.config(text=self._status_text())

    def _status_text(self) -> str:
        line = self.roll_from_line()
        pad = self.roll_from_pad()
        view = (
            f"view de-rolled by {self.roll_deg:+.2f} deg - draw the polygon on this view"
            if self._rotator.enabled
            else "view not de-rolled (camera.roll_deg = 0)"
        )
        return (f"red vertical points {len(self.vertical)}/{VERTICAL_POINT_COUNT}   |   "
                f"green pad corners {len(self.polygon)}/{CORNER_COUNT}\n"
                f"{self._roll_word()}: {'none' if line is None else f'{line:+.2f} deg'}      "
                f"roll from green pad: {'need 4 corners' if pad is None else f'{pad:+.2f} deg'}\n"
                f"{view}")

    # -- results --------------------------------------------------------

    def roll_from_line(self) -> Optional[float]:
        if len(self.vertical) != VERTICAL_POINT_COUNT:
            return None
        return line_roll_deg(*self.vertical)

    def roll_from_pad(self) -> Optional[float]:
        if len(self.polygon) != CORNER_COUNT or is_bowtie(self.polygon):
            return None
        return roll_from_quad(self.polygon)

    def is_savable(self) -> bool:
        return len(self.polygon) == CORNER_COUNT and not is_bowtie(self.polygon)

    def save(self) -> None:
        if not self.is_savable():
            return
        cv2.imwrite(str(PREVIEW_PATH), self.composed())
        if self.on_save is not None:
            # Both angles are residuals against the de-rolled view, from two
            # independent features: a world-vertical line, and the pad rectangle's
            # vanishing line. They estimate the same quantity and should agree.
            self.on_save(list(self.polygon), self.roll_from_line(), self.roll_from_pad())
