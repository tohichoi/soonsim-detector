"""Generate synthetic test video with lighting switches and dog movement."""

from pathlib import Path
import cv2
import numpy as np


def generate_mock_video(output_path: str = "sample.mp4", duration_sec: int = 16, fps: int = 15):
    """Generate 640x360 MP4 with pad, moving dog, and lighting pulses."""
    width, height = 640, 360
    total_frames = duration_sec * fps
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # Potty pad coords
    pad_pts = np.array([[180, 140], [460, 140], [460, 330], [180, 330]], np.int32)

    for i in range(total_frames):
        t = i / fps
        # Background floor
        base_color = 50
        # Simulate light switches (flashes)
        if 2.0 <= t <= 2.5 or 12.0 <= t <= 12.5:
            base_color = 180
        elif 3.5 <= t <= 4.0 or 14.0 <= t <= 14.5:
            base_color = 20

        frame = np.full((height, width, 3), base_color, dtype=np.uint8)

        # Draw Potty Pad (light blue/gray)
        cv2.fillPoly(frame, [pad_pts], (180, 200, 200))
        cv2.polylines(frame, [pad_pts], True, (100, 120, 120), 2)

        # Dog behavior:
        # 0s - 4s: Dog outside
        # 4s - 6s: Dog enters pad
        # 6s - 10s: Dog on pad
        # 10s - 12s: Dog exits pad
        # 12s - 16s: Dog gone
        if 4.0 <= t <= 12.0:
            if t < 6.0:
                # Entering
                alpha = (t - 4.0) / 2.0
                cx = int(50 + alpha * (320 - 50))
                cy = int(50 + alpha * (235 - 50))
            elif t <= 10.0:
                # Stationary on pad
                cx, cy = 320, 235
            else:
                # Exiting
                alpha = (t - 10.0) / 2.0
                cx = int(320 + alpha * (600 - 320))
                cy = int(235 + alpha * (50 - 235))

            # Draw white dog body & head
            cv2.ellipse(frame, (cx, cy), (40, 25), 0, 0, 360, (240, 240, 240), -1)
            cv2.circle(frame, (cx + 25, cy - 15), 18, (240, 240, 240), -1)
            # Dog ears
            cv2.circle(frame, (cx + 20, cy - 25), 8, (180, 180, 180), -1)
            cv2.circle(frame, (cx + 32, cy - 25), 8, (180, 180, 180), -1)
            # Eyes & nose
            cv2.circle(frame, (cx + 28, cy - 16), 3, (20, 20, 20), -1)
            cv2.circle(frame, (cx + 35, cy - 12), 3, (20, 20, 20), -1)
            # Tail
            cv2.line(frame, (cx - 35, cy), (cx - 50, cy - 20), (240, 240, 240), 5)

        out.write(frame)

    out.release()
    print(f"Generated mock video at {output_path} ({duration_sec}s, {total_frames} frames)")


if __name__ == "__main__":
    generate_mock_video()
