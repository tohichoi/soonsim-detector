"""Interactive pad calibration: camera roll and zone polygon in one pass.

Step 1 draws a red line along something the world knows is vertical -- a wall
seam, a door frame. Its tilt is the camera roll, shown live. Step 2 draws the
green pad polygon. Both come out of one session and go into config.toml together.

Run:  uv run python -m src.cli.calibrate
Keys: u undo, r reset, g grid, c recapture, s save, q quit
"""

import argparse
from typing import List, Optional, Tuple

import cv2
import tkinter as tk
from rich.console import Console

from src.cli.calibration_app import CalibrationApp
from src.cli.frame_view import (
    GRID_PATH,
    PREVIEW_PATH,
    draw_grid,
    grab_frame,
    polygon_toml,
)
from src.cli.quad_geometry import CORNER_COUNT, is_bowtie
from src.config import load_config
from src.utils.masking import mask_url_credentials
from src.utils.rotation import FrameRotator

console = Console()

WINDOW_TITLE = "soonsim pad calibration"


def report(points: List[Tuple[int, int]], roll: Optional[float]) -> None:
    """Print the result the user pastes into config.toml."""
    if is_bowtie(points):
        console.print("[red]Corners cross over. Press r and click around the pad.[/red]")
        return
    console.print(f"[green]Preview saved:[/green] {PREVIEW_PATH}")
    console.print(f"[cyan]camera roll:[/cyan] {'unknown' if roll is None else f'{roll:+.2f} deg'}")
    console.print("\nPaste this into the [zone] section of config.toml:\n")
    console.print(polygon_toml(points))
    console.print("\nThen apply it with [bold]./scripts/reload_config.sh[/bold]")


def save_snapshot(source: str, roll_deg: float) -> None:
    """Write the grid overlay only, for coordinate reading without a display."""
    frame = grab_frame(source)
    if frame is None:
        console.print(f"[red]Could not read a frame from:[/red] {mask_url_credentials(source)}")
        return
    cv2.imwrite(str(GRID_PATH), draw_grid(FrameRotator(roll_deg).apply(frame)))
    console.print(f"[green]Saved grid snapshot:[/green] {GRID_PATH}")


def open_window(frame, source: str, roll_deg: float) -> None:
    """Run the picker until the window closes."""
    root = tk.Tk()
    root.title(WINDOW_TITLE)
    app = CalibrationApp(root, frame, source, roll_deg=roll_deg, on_save=report)
    root.mainloop()
    if len(app.polygon) != CORNER_COUNT:
        console.print("[yellow]Closed without saving a polygon.[/yellow]")


def calibrate(source: Optional[str], snapshot_only: bool) -> None:
    """Run the calibration utility."""
    config = load_config()
    source = source or config.camera.source
    roll_deg = config.camera.roll_deg

    if snapshot_only:
        save_snapshot(source, roll_deg)
        console.print("[yellow]Current polygon in config:[/yellow]", config.zone.polygon)
        return

    console.print(f"[cyan]Capturing a frame from:[/cyan] {mask_url_credentials(source)}")
    frame = grab_frame(source)
    if frame is None:
        console.print(f"[red]Could not read a frame from:[/red] {mask_url_credentials(source)}")
        return

    if roll_deg:
        console.print(f"[cyan]De-rolling the view by[/cyan] {roll_deg:+.2f} deg")
    console.print("[yellow]Current polygon in config:[/yellow]", config.zone.polygon)
    open_window(frame, source, roll_deg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive pad and camera-roll calibration")
    parser.add_argument("--source", help="RTSP URL, video path, or image path (default: config camera)")
    parser.add_argument("--snapshot", action="store_true", help="Save a grid image instead of opening a window")
    args = parser.parse_args()
    calibrate(args.source, args.snapshot)


if __name__ == "__main__":
    main()
