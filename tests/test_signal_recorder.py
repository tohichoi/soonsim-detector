"""Tests for keeping footage of motion the detector never explained."""

from typing import Optional
import numpy as np
import pytest
import supervision as sv
from pydantic import ValidationError
from src.capture.stream import FramePacket
from src.config import RecorderConfig
from src.recorder.signal_recorder import MAX_SIGNAL_SEC, CompletedEvent, SignalRecorder

FPS = 10
PRE_FRAMES = 20  # 2s
POST_FRAMES = 20  # 2s
MIN_SIGNAL_SEC = 1.0
COOLDOWN_FRAMES = 10  # 1s


@pytest.fixture
def recorder() -> SignalRecorder:
    """A 2s pre-roll, 2s post-roll, 1s minimum and 1s cooldown."""
    return SignalRecorder(
        fps=FPS,
        min_signal_sec=MIN_SIGNAL_SEC,
        pre_buffer_sec=2,
        post_buffer_sec=2,
        cooldown_sec=1.0,
    )


def feed(recorder: SignalRecorder, count: int, start_idx: int, is_signal: bool) -> Optional[CompletedEvent]:
    """Push `count` frames one FPS tick apart and return the last episode closed."""
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    finished = None
    for i in range(count):
        idx = start_idx + i
        packet = FramePacket(frame=frame, timestamp=1000.0 + idx / FPS, frame_idx=idx)
        result = recorder.observe(packet, sv.Detections.empty(), is_signal=is_signal)
        if result is not None:
            finished = result
    return finished


def test_config_ceiling_never_exceeds_the_recorder_cap() -> None:
    """A minimum above the cap can never be met, so the clip is dropped in silence.

    An episode is closed at MAX_SIGNAL_SEC, so min_signal_sec must stay at or
    under it or the feature records nothing at all and says nothing.
    """
    assert RecorderConfig(signal_min_sec=MAX_SIGNAL_SEC).signal_min_sec == MAX_SIGNAL_SEC
    with pytest.raises(ValidationError):
        RecorderConfig(signal_min_sec=MAX_SIGNAL_SEC + 1.0)


def test_short_motion_is_dropped(recorder: SignalRecorder) -> None:
    """A flicker shorter than the minimum leaves no clip."""
    feed(recorder, PRE_FRAMES, 0, is_signal=False)
    feed(recorder, 5, PRE_FRAMES, is_signal=True)  # 0.4s of motion
    assert feed(recorder, POST_FRAMES, PRE_FRAMES + 5, is_signal=False) is None


def test_kept_episode_spans_the_pre_roll(recorder: SignalRecorder) -> None:
    """A long episode comes back with the frames before it and the quiet tail."""
    feed(recorder, PRE_FRAMES, 0, is_signal=False)
    signal_frames = 20  # 1.9s of motion
    feed(recorder, signal_frames, PRE_FRAMES, is_signal=True)
    event = feed(recorder, POST_FRAMES, PRE_FRAMES + signal_frames, is_signal=False)

    assert event is not None
    assert event.duration_sec == pytest.approx((signal_frames - 1) / FPS)
    # Pre-roll up to the arming frame, the rest of the motion, then the quiet
    # tail. The arming frame is the last of the pre-roll and the first signal.
    assert len(event.frames) == PRE_FRAMES + signal_frames - 1 + POST_FRAMES
    assert event.start_time == pytest.approx(1000.0 + 1 / FPS)


def test_sparse_signals_still_measure_their_real_span(recorder: SignalRecorder) -> None:
    """Inference runs every few frames, so signals arrive far apart.

    The 2026-09-22 miss gave roughly one signal every two seconds. Counting
    frames instead of reading timestamps would have scored it as a fraction of
    a second and thrown the clip away.
    """
    feed(recorder, PRE_FRAMES, 0, is_signal=False)
    idx = PRE_FRAMES
    for _ in range(6):  # six signals, 2s apart = a 10s span
        assert feed(recorder, 1, idx, is_signal=True) is None
        feed(recorder, 19, idx + 1, is_signal=False)
        idx += 20

    event = feed(recorder, POST_FRAMES, idx, is_signal=False)
    assert event is not None
    assert event.duration_sec == pytest.approx(10.0)


def test_cooldown_blocks_an_immediate_second_episode(recorder: SignalRecorder) -> None:
    """One kept episode does not let the next one start on the very next frame."""
    feed(recorder, PRE_FRAMES, 0, is_signal=False)
    feed(recorder, 20, PRE_FRAMES, is_signal=True)
    assert feed(recorder, POST_FRAMES, PRE_FRAMES + 20, is_signal=False) is not None

    later = PRE_FRAMES + 20 + POST_FRAMES
    assert feed(recorder, COOLDOWN_FRAMES, later, is_signal=True) is None

    # Past the cooldown it arms again, provided the motion still lasts.
    later += COOLDOWN_FRAMES
    feed(recorder, 20, later, is_signal=True)
    assert feed(recorder, POST_FRAMES, later + 20, is_signal=False) is not None
