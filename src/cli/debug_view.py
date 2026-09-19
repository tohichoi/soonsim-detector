"""Visual debugging tool for inspecting YOLO detections and confidence scores."""

from pathlib import Path
import cv2
from loguru import logger
import numpy as np
from src.config import load_config
from ultralytics import YOLO
import supervision as sv


def debug_camera(save_dir: str = "debug_output"):
    """Capture single frame and run low-threshold multi-class inspection."""
    config = load_config()
    out_dir = Path(save_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(config.camera.source)
    if not cap.isOpened():
        logger.error(f"Cannot open stream: {config.camera.source}")
        return

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        logger.error("Failed to read frame.")
        return

    model = YOLO(config.detector.model_name)
    # Run with very low threshold (0.15) and without class filtering to see all candidates
    results = model(frame, conf=0.15, verbose=False)[0]
    detections = sv.Detections.from_ultralytics(results)

    logger.info(f"Total raw objects detected: {len(detections)}")

    # Annotate all detected objects with class names and confidences
    annotated = frame.copy()

    # Draw ROI polygon
    poly_pts = np.array(config.zone.polygon, np.int32).reshape((-1, 1, 2))
    cv2.polylines(annotated, [poly_pts], True, (0, 255, 255), 2)

    labels = []
    for i in range(len(detections)):
        cls_id = int(detections.class_id[i])
        cls_name = model.names.get(cls_id, str(cls_id))
        conf = float(detections.confidence[i])
        labels.append(f"{cls_name} ({conf:.2f})")
        logger.info(f"Detected: {cls_name} (Class {cls_id}) | Confidence: {conf:.2f} | Box: {detections.xyxy[i].tolist()}")

    box_annotator = sv.BoxAnnotator(thickness=2, color=sv.Color.from_hex("#FF00FF"))
    label_annotator = sv.LabelAnnotator(text_scale=0.5, text_thickness=1, color=sv.Color.from_hex("#FF00FF"))

    annotated = box_annotator.annotate(scene=annotated, detections=detections)
    annotated = label_annotator.annotate(scene=annotated, detections=detections, labels=labels)

    out_file = out_dir / "debug_detection.jpg"
    cv2.imwrite(str(out_file), annotated)

    # Copy to artifact dir
    artifact_dir = Path("/home/x/.gemini/antigravity-cli/brain/a16f7b96-6562-4aee-a4f5-5a08c52bb6b5")
    cv2.imwrite(str(artifact_dir / "debug_detection.jpg"), annotated)

    print(f"\n[Debug Output] Saved detection visualization to: {out_file}")
    if len(detections) == 0:
        print("Warning: No objects detected even at 0.15 confidence threshold.")


if __name__ == "__main__":
    debug_camera()
