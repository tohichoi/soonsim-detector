"""Unit tests for MotionGate and InferenceTelemetry."""

import numpy as np
import pytest
from src.detector.motion_gate import MotionGate
from src.utils.telemetry import InferenceTelemetry


def test_motion_gate_static_scene():
    gate = MotionGate(motion_threshold=4.0, failsafe_interval_sec=30.0, enabled=True)
    frame = np.zeros((360, 640, 3), dtype=np.uint8)

    # First frame establishes baseline
    should_infer1, reason1, _ = gate.evaluate(frame)
    # Subsequent identical frame should be skipped
    should_infer2, reason2, diff2 = gate.evaluate(frame)

    assert not should_infer2
    assert "GATE_SKIPPED" in reason2
    assert diff2 == 0.0


def test_motion_gate_motion_triggered():
    gate = MotionGate(motion_threshold=4.0, failsafe_interval_sec=30.0, enabled=True)
    frame1 = np.zeros((360, 640, 3), dtype=np.uint8)
    frame2 = np.ones((360, 640, 3), dtype=np.uint8) * 100

    gate.evaluate(frame1)
    should_infer, reason, diff = gate.evaluate(frame2)

    assert should_infer
    assert "MOTION_TRIGGERED" in reason
    assert diff > 4.0


def test_motion_gate_active_event_override():
    gate = MotionGate(motion_threshold=4.0, failsafe_interval_sec=30.0, enabled=True)
    frame = np.zeros((360, 640, 3), dtype=np.uint8)

    gate.evaluate(frame)
    should_infer, reason, _ = gate.evaluate(frame, is_active_event=True)

    assert should_infer
    assert reason == "ACTIVE_EVENT_IN_PROGRESS"


def test_telemetry_stats_calculation(tmp_path):
    telemetry = InferenceTelemetry(log_dir=tmp_path)
    telemetry.record_skip(1, "SKIPPED", 0.0)
    telemetry.record_skip(2, "SKIPPED", 0.0)
    telemetry.record_inference(3, "INFER", 50.0, 1, "dog")

    assert telemetry.stats.total_frames == 3
    assert telemetry.stats.frames_skipped == 2
    assert telemetry.stats.inferences_run == 1
    assert abs(telemetry.stats.skip_ratio_percent - 66.66) < 0.1
    assert telemetry.stats.avg_inference_latency_ms == 50.0
