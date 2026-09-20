"""Thread-safe state repository for Soonsim Detector Web Viewer."""

from collections import deque
import datetime
import threading
import time
from typing import List, Optional
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict

KST = ZoneInfo("Asia/Seoul")


class SnapshotRecord(BaseModel):
    """Historical snapshot event record."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int
    timestamp_str: str
    timestamp_epoch: float
    detected_objects: List[str]
    dog_in_zone: bool
    event_type: str
    change_score: float
    image_bytes: bytes


class LiveState(BaseModel):
    """Real-time monitoring state."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    last_poll_str: str = "대기 중"
    last_poll_epoch: float = 0.0
    status_title: str = "감시 대기 중"
    status_desc: str = "카메라 연결 대기 중입니다."
    status_type: str = "idle"
    detected_objects: List[str] = []
    dog_in_zone: bool = False
    change_score: float = 0.0
    total_events_30m: int = 0
    interval_sec: float = 5.0
    latest_image_bytes: bytes = b""


class ViewerStateStore:
    """Thread-safe in-memory store for real-time state and 30m event history."""

    def __init__(self, retention_sec: float = 1800.0, max_history: int = 200):
        self.retention_sec = retention_sec
        self.history: deque[SnapshotRecord] = deque(maxlen=max_history)
        self.live_state = LiveState()
        self.lock = threading.Lock()
        self.current_id = 0

    def update_live(
        self,
        status_title: str,
        status_desc: str,
        status_type: str,
        detected_objects: List[str],
        dog_in_zone: bool,
        change_score: float,
        image_bytes: bytes,
        interval_sec: float = 5.0,
    ) -> None:
        """Update live telemetry state."""
        now = time.time()
        dt_str = datetime.datetime.fromtimestamp(now, tz=KST).strftime("%Y-%m-%d %H:%M:%S")

        with self.lock:
            self._prune_history(now)
            self.live_state = LiveState(
                last_poll_str=dt_str,
                last_poll_epoch=now,
                status_title=status_title,
                status_desc=status_desc,
                status_type=status_type,
                detected_objects=detected_objects,
                dog_in_zone=dog_in_zone,
                change_score=change_score,
                total_events_30m=len(self.history),
                interval_sec=interval_sec,
                latest_image_bytes=image_bytes,
            )

    def push_event(
        self,
        event_type: str,
        detected_objects: List[str],
        dog_in_zone: bool,
        change_score: float,
        image_bytes: bytes,
    ) -> int:
        """Append a new snapshot event to the historical queue."""
        now = time.time()
        dt_str = datetime.datetime.fromtimestamp(now, tz=KST).strftime("%Y-%m-%d %H:%M:%S")

        with self.lock:
            self.current_id += 1
            record = SnapshotRecord(
                id=self.current_id,
                timestamp_str=dt_str,
                timestamp_epoch=now,
                detected_objects=detected_objects,
                dog_in_zone=dog_in_zone,
                event_type=event_type,
                change_score=change_score,
                image_bytes=image_bytes,
            )
            self.history.append(record)
            self._prune_history(now)
            return record.id

    def _prune_history(self, current_time: float) -> None:
        """Remove events older than the retention window."""
        cutoff = current_time - self.retention_sec
        while self.history and self.history[0].timestamp_epoch < cutoff:
            self.history.popleft()

    def get_live_state(self) -> LiveState:
        """Get a copy of the current live state."""
        with self.lock:
            return self.live_state

    def get_history(self) -> List[SnapshotRecord]:
        """Get all historical snapshot events."""
        with self.lock:
            return list(self.history)

    def get_snapshot(self, record_id: int) -> Optional[SnapshotRecord]:
        """Get a specific snapshot record by ID."""
        with self.lock:
            for item in self.history:
                if item.id == record_id:
                    return item
            return None
