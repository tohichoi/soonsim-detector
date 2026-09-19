"""Interactive pee pad polygon calibration tool."""

from pathlib import Path
import cv2
import numpy as np
from rich.console import Console
from src.config import load_config

console = Console()


def draw_grid(frame: np.ndarray, step: int = 50) -> np.ndarray:
    """Draw a coordinate grid on frame for visual calibration."""
    grid_frame = frame.copy()
    height, width = frame.shape[:2]

    # Vertical lines
    for x in range(0, width, step):
        color = (0, 255, 255) if x % 100 == 0 else (100, 100, 100)
        cv2.line(grid_frame, (x, 0), (x, height), color, 1)
        cv2.putText(grid_frame, str(x), (x + 2, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    # Horizontal lines
    for y in range(0, height, step):
        color = (0, 255, 255) if y % 100 == 0 else (100, 100, 100)
        cv2.line(grid_frame, (0, y), (width, y), color, 1)
        cv2.putText(grid_frame, str(y), (5, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    return grid_frame


def calibrate():
    """Run calibration utility."""
    config = load_config()
    console.print(f"[cyan]Connecting to video source:[/cyan] {config.camera.source}")

    cap = cv2.VideoCapture(config.camera.source)
    if not cap.isOpened():
        console.print(f"[red]Error:[/red] Could not open camera/video source: {config.camera.source}")
        return

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        console.print("[red]Error:[/red] Failed to capture frame from source.")
        return

    grid_img = draw_grid(frame)
    output_path = Path("snapshot_grid.jpg")
    cv2.imwrite(str(output_path), grid_img)

    console.print(f"[green]Saved coordinate grid snapshot to:[/green] [bold]{output_path}[/bold]")
    console.print("Open [bold]snapshot_grid.jpg[/bold] to check coordinates of the 4 corners of the potty pad.")
    console.print("[yellow]Current polygon in config:[/yellow]", config.zone.polygon)


if __name__ == "__main__":
    calibrate()
