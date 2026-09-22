"""Interactive pad calibration: camera roll and zone polygon in one pass.

Step 1 draws a red line along something the world knows is vertical -- a wall
seam, a door frame. Its tilt is the camera roll, shown live. Step 2 draws the
green pad polygon. Both come out of one session and go into config.toml together.

The view is already de-rolled by camera.roll_deg before it reaches you, so every
angle on screen and in the report is a *residual*: near zero when the config
still matches the camera, and the amount it moved by when it no longer does.
Skipping step 1 is how you re-click only the pad -- roll is then left alone, or
corrected from the pad rectangle alone if that says the camera did move.

Run:  uv run python -m src.cli.calibrate
Keys: u undo, r reset, g grid, c recapture, s save, q quit
"""

import argparse
from functools import partial
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

# Clicking is worth about a degree either way, so a residual inside this is noise.
# It is also the widest two independent estimates may sit apart and still both
# be believed.
ROLL_TOLERANCE_DEG = 2.0


def roll_verdict(
    base_roll: float,
    line_residual: Optional[float],
    pad_residual: Optional[float],
) -> Tuple[List[str], Optional[float]]:
    """Read the two residuals and say what [camera].roll_deg should become.

    Both are measured on the already de-rolled view, so both are corrections on
    top of the configured angle, never an absolute roll. They come from
    independent features -- a world-vertical line, and the pad rectangle's
    vanishing line -- and both are unbiased, so they should agree. A wide gap
    means the measurement is wrong, not that the camera moved twice.
    """
    notes = []
    if line_residual is not None:
        notes.append(f"빨간선(세계 수직) 잔차: {line_residual:+.2f} deg")
    if pad_residual is not None:
        notes.append(
            f"배변판 사각형 잔차: {pad_residual:+.2f} deg "
            "[dim](배변판이 돌아 놓였다면 이 값도 흔들립니다)[/dim]"
        )

    estimates = [r for r in (line_residual, pad_residual) if r is not None]
    if not estimates:
        notes.append(
            f"roll 을 재지 않았습니다. [camera].roll_deg = {base_roll:.2f} 를 그대로 두세요."
        )
        return notes, None

    if len(estimates) == 2 and abs(estimates[0] - estimates[1]) > ROLL_TOLERANCE_DEG:
        notes.append(
            f"[red]두 추정치가 {abs(estimates[0] - estimates[1]):.1f} deg 벌어집니다.[/red] "
            "배변판 네 모서리가 실제 배변판인지, 빨간선이 실제 수직(벽 이음선/문틀)인지 확인하세요. "
            f"[camera].roll_deg = {base_roll:.2f} 를 그대로 두는 편이 안전합니다."
        )
        return notes, None

    residual = sum(estimates) / len(estimates)
    if abs(residual) <= ROLL_TOLERANCE_DEG:
        notes.append(f"카메라가 그대로입니다. [camera].roll_deg = {base_roll:.2f} 유지.")
        return notes, None

    corrected = base_roll + residual
    notes.append(
        f"카메라가 {residual:+.2f} deg 움직였습니다. "
        f"roll_deg = {corrected:.2f} 로 갱신하세요 (기존 {base_roll:+.2f} + 잔차 {residual:+.2f})."
    )
    return notes, corrected


def report(
    points: List[Tuple[int, int]],
    line_residual: Optional[float],
    pad_residual: Optional[float],
    base_roll: float,
) -> None:
    """Print the result the user pastes into config.toml."""
    if is_bowtie(points):
        console.print("[red]Corners cross over. Press r and click around the pad.[/red]")
        return
    console.print(f"[green]Preview saved:[/green] {PREVIEW_PATH}")

    notes, corrected = roll_verdict(base_roll, line_residual, pad_residual)
    for note in notes:
        console.print(f"[cyan]{note}[/cyan]")

    console.print("\nPaste this into the [zone] section of config.toml:\n")
    console.print(polygon_toml(points))
    if corrected is not None:
        console.print("\nAnd this into [camera]:\n")
        console.print(f"roll_deg = {corrected:.2f}")
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
    app = CalibrationApp(
        root, frame, source, roll_deg=roll_deg, on_save=partial(report, base_roll=roll_deg)
    )
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
        console.print(
            f"[dim]아래 화면의 각도는 이미 {roll_deg:+.2f} deg 보정된 뒤의 잔차입니다. "
            "카메라가 그대로면 0 근처, 움직였으면 그만큼 벌어집니다.[/dim]"
        )
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
