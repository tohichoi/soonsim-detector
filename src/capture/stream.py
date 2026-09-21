"""RTSP stream reader and memory ring buffer."""

from collections import deque
from dataclasses import dataclass
import threading
import time
from typing import Generator, List, Optional
import cv2
from loguru import logger
import numpy as np

from src.utils.masking import mask_url_credentials
from src.utils.rotation import FrameRotator


@dataclass
class FramePacket:
    """Frame packet containing image data, timestamp and index."""
    frame: np.ndarray
    timestamp: float
    frame_idx: int


class RingBuffer:
    """Thread-safe memory ring buffer for sliding window frames."""

    def __init__(self, max_frames: int):
        self._max_frames = max_frames
        self._buffer: deque[FramePacket] = deque(maxlen=max_frames)
        self._lock = threading.Lock()

    def append(self, packet: FramePacket) -> None:
        """Add a frame packet to the ring buffer."""
        with self._lock:
            self._buffer.append(packet)

    def get_all(self) -> List[FramePacket]:
        """Get a shallow copy list of all current frames in buffer."""
        with self._lock:
            return list(self._buffer)

    def clear(self) -> None:
        """Clear the buffer."""
        with self._lock:
            self._buffer.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)


class VideoStreamReader:
    """Robust video stream reader supporting RTSP reconnect and file loops."""

    def __init__(
        self,
        source: str,
        target_fps: int = 15,
        reconnect_interval: float = 3.0,
        roll_deg: float = 0.0,
    ):
        self.source = source
        self.target_fps = target_fps
        self.reconnect_interval = reconnect_interval
        self._is_running = False
        self._cap: Optional[cv2.VideoCapture] = None
        self._is_file = not source.startswith("rtsp://") and not source.startswith("http://")
        # De-rolled here, at the one point every frame is created, so the motion
        # gate, tracker, annotator, exporter and viewer all share one geometry.
        self._rotator = FrameRotator(roll_deg)

    def _open_stream(self) -> bool:
        """Attempt to open video capture source."""
        if self._cap is not None:
            self._cap.release()
        self._cap = cv2.VideoCapture(self.source)
        if not self._cap.isOpened():
            logger.warning(f"Failed to open video source: {mask_url_credentials(self.source)}")
            return False
        logger.info(f"Successfully opened video source: {mask_url_credentials(self.source)}")
        return True

    def frames(self) -> Generator[FramePacket, None, None]:
        """Generate frame packets indefinitely with auto-reconnect."""
        self._is_running = True
        frame_idx = 0
        frame_delay = 1.0 / self.target_fps

        while self._is_running:
            if self._cap is None or not self._cap.isOpened():
                if not self._open_stream():
                    time.sleep(self.reconnect_interval)
                    continue

            start_time = time.monotonic()
            ret, frame = self._cap.read()

            if not ret or frame is None:
                if self._is_file:
                    logger.debug("Video file reached end. Looping from start.")
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    time.sleep(0.05)
                    continue
                else:
                    logger.warning("Stream read failed. Attempting reconnect...")
                    self._cap.release()
                    self._cap = None
                    time.sleep(self.reconnect_interval)
                    continue

            frame_idx += 1
            yield FramePacket(
                frame=self._rotator.apply(frame), timestamp=time.time(), frame_idx=frame_idx
            )

            if self._is_file:
                elapsed = time.monotonic() - start_time
                sleep_time = max(0.0, frame_delay - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

    def stop(self) -> None:
        """Stop stream reader."""
        self._is_running = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info("Video stream reader stopped.")
