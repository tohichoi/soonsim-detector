import os
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
import psutil
from src.config import load_config
from src.detector.model import DogDetector
from src.detector.motion_gate import MotionGate
from src.detector.zone_tracker import ZoneTracker
from src.utils.telemetry import InferenceTelemetry


def run_benchmark(duration_sec: float = 10.0):
    config = load_config("config/config.toml")
    process = psutil.Process(os.getpid())

    detector = DogDetector(
        model_name=config.detector.model_name,
        confidence_threshold=config.detector.confidence_threshold,
        class_ids=[15, 16],
        max_threads=config.detector.max_threads,
    )
    motion_gate = MotionGate(
        motion_threshold=config.detector.motion_threshold,
        failsafe_interval_sec=config.detector.failsafe_interval_sec,
        enabled=config.detector.motion_gate_enabled,
    )
    telemetry = InferenceTelemetry()

    # Generate synthetic stream (mostly static, with occasional motion)
    base_frame = np.zeros((360, 640, 3), dtype=np.uint8)
    cv2.rectangle(base_frame, (100, 100), (300, 300), (128, 128, 128), -1)

    print(f"Starting CPU Benchmark ({duration_sec}s)...")
    start_time = time.time()
    frame_idx = 0
    cpu_samples = []

    # Prime psutil
    process.cpu_percent(interval=None)

    while time.time() - start_time < duration_sec:
        frame = base_frame.copy()
        # Add slight motion every 45 frames (3s)
        if frame_idx % 45 == 0 and frame_idx > 0:
            cv2.circle(frame, (200, 200), 50, (255, 255, 255), -1)

        # Simulation loop
        should_decimate = (frame_idx % config.detector.inference_interval_frames == 0)
        if should_decimate:
            should_infer, reason, diff_score = motion_gate.evaluate(frame)
            if should_infer:
                t0 = time.monotonic()
                dets = detector.detect(frame)
                latency = (time.monotonic() - t0) * 1000.0
                telemetry.record_inference(frame_idx, reason, latency, len(dets), "benchmark")
            else:
                telemetry.record_skip(frame_idx, reason, diff_score)
        else:
            telemetry.record_skip(frame_idx, "DECIMATED", 0.0)

        frame_idx += 1
        time.sleep(1.0 / 15.0)  # Simulate 15 FPS camera stream

        if frame_idx % 15 == 0:
            cpu_samples.append(process.cpu_percent(interval=None))

    avg_cpu = sum(cpu_samples) / max(len(cpu_samples), 1)
    print("\n--- Benchmark Results ---")
    print(f"Total Frames Processed: {telemetry.stats.total_frames}")
    print(f"Inferences Executed:    {telemetry.stats.inferences_run}")
    print(f"Frames Skipped:         {telemetry.stats.frames_skipped} ({telemetry.stats.skip_ratio_percent:.1f}%)")
    print(f"Avg Inference Latency:  {telemetry.stats.avg_inference_latency_ms:.1f} ms")
    print(f"Average CPU Usage:      {avg_cpu:.1f}%")


if __name__ == "__main__":
    run_benchmark(10.0)
