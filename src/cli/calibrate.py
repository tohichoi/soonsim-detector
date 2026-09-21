"""Interactive pee pad polygon calibration tool.

Shows a live frame, lets you click the four corners of the pad, and prints the
polygon block to paste into config.toml.

Keys:  left click = add corner, right click / u = undo, r = reset, g = grid,
       s = save preview + print polygon, q / ESC = quit
"""

import argparse
import shutil
import sysconfig
from pathlib import Path
from typing import List, Optional, Tuple

# OpenCV's bundled Qt no longer ships fonts, so a fresh install has no
# cv2/qt/fonts and every Qt-drawn string in the window comes out blank
# ("QFontDatabase: Cannot find font directory ..."). Lend it a system font.
# QT_QPA_FONTDIR does not help: the plugin looks in cv2/qt/fonts regardless.
# This has to run before cv2 initialises the Qt plugin, hence before the import.
SYSTEM_FONT_DIRS = (
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/Library/Fonts"),
)
QT_FONT_DIR = Path(sysconfig.get_paths()["purelib"]) / "cv2" / "qt" / "fonts"


def ensure_qt_fonts() -> bool:
    """Copy a system font into cv2's Qt font directory when it is missing."""
    if any(QT_FONT_DIR.glob("*.ttf")):
        return False
    for source in SYSTEM_FONT_DIRS:
        fonts = sorted(source.glob("*.ttf"))[:2] if source.is_dir() else []
        if fonts:
            QT_FONT_DIR.mkdir(parents=True, exist_ok=True)
            for font in fonts:
                shutil.copy2(font, QT_FONT_DIR / font.name)
            return True
    return False


ensure_qt_fonts()

import cv2  # noqa: E402  (must follow ensure_qt_fonts)
import numpy as np
from rich.console import Console

from src.cli.quad_geometry import CORNER_COUNT, is_bowtie, roll_from_quad
from src.config import load_config

console = Console()

WINDOW = "soonsim pad calibration"
GRID_STEP = 50
GRID_COLOR = (0, 255, 255)
POINT_COLOR = (0, 0, 255)
EDGE_COLOR = (255, 0, 255)
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


class PolygonPicker:
    """Collects four clicks on a frame and renders the polygon as it grows."""

    def __init__(self, frame: np.ndarray):
        self.frame = frame
        self.points: List[Tuple[int, int]] = []
        self.cursor: Optional[Tuple[int, int]] = None
        self.show_grid = True

    def on_mouse(self, event: int, x: int, y: int, _flags: int, _param) -> None:
        if event == cv2.EVENT_MOUSEMOVE:
            self.cursor = (x, y)
        elif event == cv2.EVENT_LBUTTONDOWN and len(self.points) < CORNER_COUNT:
            self.points.append((x, y))
        elif event == cv2.EVENT_RBUTTONDOWN:
            self.undo()

    def undo(self) -> None:
        if self.points:
            self.points.pop()

    def reset(self) -> None:
        self.points.clear()

    def render(self) -> np.ndarray:
        canvas = draw_grid(self.frame) if self.show_grid else self.frame.copy()

        if len(self.points) > 1:
            cv2.polylines(canvas, [np.array(self.points, np.int32)], True, EDGE_COLOR, 2)
        for index, point in enumerate(self.points):
            cv2.circle(canvas, point, 5, POINT_COLOR, -1)
            cv2.putText(
                canvas, str(index + 1), (point[0] + 7, point[1] - 7),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, POINT_COLOR, 1, cv2.LINE_AA,
            )

        lines = [
            f"corners {len(self.points)}/{CORNER_COUNT}   click the pad corners in order",
            "u undo | r reset | g grid | s save | q quit",
        ]
        if self.cursor is not None:
            lines.append(f"cursor {self.cursor[0]}, {self.cursor[1]}")
        if is_bowtie(self.points):
            lines.append("BOWTIE: corners cross over - reset and click around the pad")
        elif len(self.points) == CORNER_COUNT:
            roll = roll_from_quad(self.points)
            lines.append(
                "pad rect gives no roll" if roll is None
                else f"pad rect implies camera roll {roll:+.1f} deg"
            )

        for row, text in enumerate(lines):
            origin = (10, 30 + row * 22)
            color = (0, 0, 255) if text.startswith("BOWTIE") else (255, 255, 255)
            cv2.putText(canvas, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(canvas, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)

        return canvas


def polygon_toml(points: List[Tuple[int, int]]) -> str:
    """Format the corners as the polygon block used in config.toml."""
    rows = ",\n".join(f"    [{x}, {y}]" for x, y in points)
    return f"polygon = [\n{rows}\n]"


def run_interactive(picker: PolygonPicker) -> Optional[List[Tuple[int, int]]]:
    """Show the picker window until the user saves or quits."""
    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW, picker.on_mouse)

    saved: Optional[List[Tuple[int, int]]] = None
    while True:
        cv2.imshow(WINDOW, picker.render())
        key = cv2.waitKey(20) & 0xFF

        if key in (27, ord("q")):
            break
        if key == ord("u"):
            picker.undo()
        elif key == ord("r"):
            picker.reset()
        elif key == ord("g"):
            picker.show_grid = not picker.show_grid
        elif key == ord("s"):
            if len(picker.points) != CORNER_COUNT:
                console.print(f"[yellow]Need {CORNER_COUNT} corners before saving.[/yellow]")
            elif is_bowtie(picker.points):
                console.print("[red]Corners cross over. Fix the order before saving.[/red]")
            else:
                saved = list(picker.points)
                break

    cv2.destroyAllWindows()
    return saved


def save_snapshot(source: str) -> None:
    """Write the grid overlay only, for heads-up coordinate reading without a display."""
    frame = grab_frame(source)
    if frame is None:
        console.print(f"[red]Could not read a frame from:[/red] {source}")
        return
    cv2.imwrite(str(GRID_PATH), draw_grid(frame))
    console.print(f"[green]Saved grid snapshot:[/green] {GRID_PATH}")


def calibrate(source: Optional[str], snapshot_only: bool) -> None:
    """Run the calibration utility."""
    config = load_config()
    source = source or config.camera.source

    if snapshot_only:
        save_snapshot(source)
        console.print("[yellow]Current polygon in config:[/yellow]", config.zone.polygon)
        return

    console.print(f"[cyan]Capturing a frame from:[/cyan] {source}")
    frame = grab_frame(source)
    if frame is None:
        console.print(f"[red]Could not read a frame from:[/red] {source}")
        return

    console.print("[yellow]Current polygon in config:[/yellow]", config.zone.polygon)
    console.print("Click the four pad corners in order, then press s.")

    picker = PolygonPicker(frame)
    points = run_interactive(picker)
    if not points:
        console.print("[yellow]Nothing saved.[/yellow]")
        return

    cv2.imwrite(str(PREVIEW_PATH), picker.render())
    console.print(f"[green]Preview saved:[/green] {PREVIEW_PATH}")

    roll = roll_from_quad(points)
    if roll is not None:
        console.print(f"[cyan]Camera roll implied by the pad rectangle:[/cyan] {roll:+.1f} deg")
        console.print("[dim]Non-zero means the camera is tilted; the zone anchor points sit off the feet by that much.[/dim]")

    console.print("\nPaste this into the [zone] section of config.toml:\n")
    console.print(polygon_toml(points))
    console.print("\nThen apply it with [bold]./scripts/reload_config.sh[/bold]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive pee pad polygon calibration")
    parser.add_argument("--source", help="RTSP URL, video path, or image path (default: config camera)")
    parser.add_argument("--snapshot", action="store_true", help="Save a grid image instead of opening a window")
    args = parser.parse_args()
    calibrate(args.source, args.snapshot)


if __name__ == "__main__":
    main()
