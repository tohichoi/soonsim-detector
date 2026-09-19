"""Tests for ring buffer and frame packets."""

import numpy as np
from src.capture.stream import FramePacket, RingBuffer


def test_ring_buffer_maxlen():
    """Verify ring buffer sliding window maintains max length."""
    buffer = RingBuffer(max_frames=3)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)

    for i in range(5):
        buffer.append(FramePacket(frame=frame, timestamp=float(i), frame_idx=i))

    assert len(buffer) == 3
    all_packets = buffer.get_all()
    assert len(all_packets) == 3
    assert all_packets[0].frame_idx == 2
    assert all_packets[-1].frame_idx == 4


def test_ring_buffer_clear():
    """Verify ring buffer clear functionality."""
    buffer = RingBuffer(max_frames=5)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    buffer.append(FramePacket(frame=frame, timestamp=1.0, frame_idx=1))
    assert len(buffer) == 1
    buffer.clear()
    assert len(buffer) == 0
