"""FastAPI continuous 5-second debug viewer with 30-minute smart change filtering and live status UI."""

import argparse
from collections import deque
from contextlib import asynccontextmanager
import datetime
from pathlib import Path
import socket
import threading
import time
from typing import List, Optional
import cv2
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from loguru import logger
import numpy as np
from pydantic import BaseModel, ConfigDict
from src.config import load_config
import supervision as sv
from ultralytics import YOLO

ANIMAL_CLASS_IDS = {15, 16}  # COCO: 15=cat, 16=dog


class SnapshotRecord(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int
    timestamp_str: str
    timestamp_epoch: float
    detected_objects: List[str]
    dog_in_zone: bool
    event_type: str  # "DOG_ON_PAD", "ANIMAL_DETECTED", "MOTION_CHANGE", "PERIODIC_BASELINE"
    change_score: float
    image_bytes: bytes


class LiveState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    last_poll_str: str = "대기 중"
    last_poll_epoch: float = 0.0
    status_title: str = "감시 대기 중"
    status_desc: str = "카메라 연결 대기 중입니다."
    status_type: str = "idle"  # "no_change", "dog_on_pad", "motion", "idle"
    detected_objects: List[str] = []
    dog_in_zone: bool = False
    change_score: float = 0.0
    total_events_30m: int = 0
    interval_sec: float = 5.0
    latest_image_bytes: bytes = b""


class DebugViewerService:
    """Manages 5s polling, smart change detection, and 30-minute event timeline."""

    def __init__(self, retention_sec: float = 1800.0, interval_sec: float = 5.0, motion_threshold: float = 4.5):
        self.config = load_config()
        self.retention_sec = retention_sec  # 30 minutes
        self.interval_sec = interval_sec
        self.motion_threshold = motion_threshold

        self.history: deque[SnapshotRecord] = deque(maxlen=200)
        self.live_state = LiveState(interval_sec=interval_sec)
        self.lock = threading.Lock()
        self.is_running = False
        self.current_id = 0

        self.model = YOLO(self.config.detector.model_name)
        self.polygon_np = np.array(self.config.zone.polygon, dtype=np.int32)
        self.zone = sv.PolygonZone(
            polygon=self.polygon_np,
            triggering_anchors=(sv.Position.CENTER, sv.Position.BOTTOM_CENTER),
            require_all_anchors=False,
        )
        self.animal_box_annotator = sv.BoxAnnotator(thickness=3, color=sv.Color.from_hex("#00FF00"))
        self.other_box_annotator = sv.BoxAnnotator(thickness=1, color=sv.Color.from_hex("#64748B"))
        self.label_annotator = sv.LabelAnnotator(
            text_scale=0.5,
            text_thickness=1,
            color=sv.Color.from_hex("#00FF00"),
            text_color=sv.Color.from_hex("#000000"),
        )
        self.zone_annotator = sv.PolygonZoneAnnotator(
            zone=self.zone,
            color=sv.Color.from_hex("#00FFFF"),
            thickness=2,
        )

        self._prev_gray: Optional[np.ndarray] = None
        self._prev_animal_count = 0
        self._last_saved_time = 0.0

    def _evaluate_frame(self, frame: np.ndarray) -> tuple[np.ndarray, bool, List[str], float, Optional[str]]:
        """
        Evaluate frame with YOLO & motion diff.
        Returns (annotated_frame, dog_in_zone, detected_labels, change_score, event_type_or_None).
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

        change_score = 0.0
        if self._prev_gray is not None:
            diff = cv2.absdiff(gray_blur, self._prev_gray)
            change_score = float(np.mean(diff))
        self._prev_gray = gray_blur

        results = self.model(frame, conf=0.20, verbose=False)[0]
        detections = sv.Detections.from_ultralytics(results)

        is_in_zone = self.zone.trigger(detections=detections) if len(detections) > 0 else np.array([])

        dog_in_zone = False
        animal_count = 0
        detected_labels = []

        annotated = frame.copy()
        annotated = self.zone_annotator.annotate(scene=annotated)

        if len(detections) > 0:
            animal_indices = []
            other_indices = []
            labels = []

            for i in range(len(detections)):
                cls_id = int(detections.class_id[i])
                cls_name = self.model.names.get(cls_id, str(cls_id))
                conf = float(detections.confidence[i])
                in_z = bool(is_in_zone[i]) if i < len(is_in_zone) else False
                is_animal = cls_id in ANIMAL_CLASS_IDS

                if is_animal:
                    animal_count += 1
                    animal_indices.append(i)
                    if in_z:
                        dog_in_zone = True
                else:
                    other_indices.append(i)

                loc_tag = " [ON PAD]" if (in_z and is_animal) else (" [PAD IGNORED]" if in_z else "")
                tag = f"{cls_name} ({conf:.2f}){loc_tag}"
                labels.append(tag)
                detected_labels.append(tag)

            if animal_indices:
                animal_dets = detections[np.array(animal_indices)]
                annotated = self.animal_box_annotator.annotate(scene=annotated, detections=animal_dets)
            if other_indices:
                other_dets = detections[np.array(other_indices)]
                annotated = self.other_box_annotator.annotate(scene=annotated, detections=other_dets)

            annotated = self.label_annotator.annotate(scene=annotated, detections=detections, labels=labels)

        now_dt = datetime.datetime.now()
        dt_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        status_text = "DOG IN ZONE" if dog_in_zone else ("MOTION" if change_score > self.motion_threshold else "NO CHANGE")
        status_color = (0, 255, 0) if dog_in_zone else ((0, 200, 255) if change_score > self.motion_threshold else (180, 180, 180))

        cv2.putText(annotated, f"{dt_str} | {status_text} (diff:{change_score:.1f})", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(annotated, f"{dt_str} | {status_text} (diff:{change_score:.1f})", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 1, cv2.LINE_AA)

        now = time.time()
        event_type: Optional[str] = None

        if dog_in_zone:
            event_type = "DOG_ON_PAD"
        elif animal_count > 0 or animal_count != self._prev_animal_count:
            event_type = "ANIMAL_DETECTED"
        elif change_score >= self.motion_threshold:
            event_type = "MOTION_CHANGE"
        elif (now - self._last_saved_time) >= 600.0:
            event_type = "PERIODIC_BASELINE"

        self._prev_animal_count = animal_count
        return annotated, dog_in_zone, detected_labels, change_score, event_type

    def run_worker(self):
        """Main polling worker running every interval_sec."""
        logger.info(f"Starting Smart Debug Viewer worker (Interval: {self.interval_sec}s, Retention: {self.retention_sec}s / 30 mins)...")
        cap = cv2.VideoCapture(self.config.camera.source)

        while self.is_running:
            start_t = time.monotonic()
            if not cap.isOpened():
                logger.warning("Camera stream disconnected. Retrying...")
                cap.open(self.config.camera.source)
                time.sleep(2.0)
                continue

            try:
                ret, frame = cap.read()
                if ret and frame is not None:
                    annotated, dog_in_zone, detected_labels, change_score, event_type = self._evaluate_frame(frame)

                    now = time.time()
                    dt_str = datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")

                    _, img_encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                    img_bytes = img_encoded.tobytes()

                    with self.lock:
                        if event_type is not None:
                            self.current_id += 1
                            record = SnapshotRecord(
                                id=self.current_id,
                                timestamp_str=dt_str,
                                timestamp_epoch=now,
                                detected_objects=detected_labels,
                                dog_in_zone=dog_in_zone,
                                event_type=event_type,
                                change_score=change_score,
                                image_bytes=img_bytes,
                            )
                            self.history.append(record)
                            self._last_saved_time = now
                            logger.info(f"[Recorded Event #{record.id}] Type: {event_type} | Objects: {detected_labels} | Diff: {change_score:.1f}")

                        cutoff = now - self.retention_sec
                        while self.history and self.history[0].timestamp_epoch < cutoff:
                            self.history.popleft()

                        if dog_in_zone:
                            status_title = "순심이 배변판 진입 확인!"
                            status_desc = "순심이가 현재 배변판 영역 안에 위치하고 있습니다."
                            status_type = "dog_on_pad"
                        elif change_score >= self.motion_threshold:
                            status_title = "움직임/조도 변화 감지됨"
                            status_desc = f"화면 내 움직임 또는 조명 변화가 감지되었습니다. (변화 점수: {change_score:.1f})"
                            status_type = "motion"
                        else:
                            status_title = "현재 변화 없음 (정적 상태)"
                            status_desc = "실시간 감시 중이며 배변판 및 화면에 유의미한 변화가 없습니다."
                            status_type = "no_change"

                        self.live_state = LiveState(
                            last_poll_str=dt_str,
                            last_poll_epoch=now,
                            status_title=status_title,
                            status_desc=status_desc,
                            status_type=status_type,
                            detected_objects=detected_labels,
                            dog_in_zone=dog_in_zone,
                            change_score=change_score,
                            total_events_30m=len(self.history),
                            interval_sec=self.interval_sec,
                            latest_image_bytes=img_bytes,
                        )
                else:
                    logger.warning("Failed to grab frame from stream.")
            except Exception as e:
                logger.error(f"Error in capture loop: {e}")

            elapsed = time.monotonic() - start_t
            sleep_t = max(0.1, self.interval_sec - elapsed)
            time.sleep(sleep_t)

        cap.release()
        logger.info("Debug Viewer worker stopped.")

    def get_live_state(self) -> LiveState:
        with self.lock:
            return self.live_state

    def get_history(self) -> List[SnapshotRecord]:
        with self.lock:
            return list(self.history)

    def get_snapshot(self, record_id: int) -> Optional[SnapshotRecord]:
        with self.lock:
            for item in self.history:
                if item.id == record_id:
                    return item
            return None


viewer_service = DebugViewerService(retention_sec=1800.0, interval_sec=5.0, motion_threshold=4.5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    viewer_service.is_running = True
    thread = threading.Thread(target=viewer_service.run_worker, daemon=True)
    thread.start()
    yield
    viewer_service.is_running = False


app = FastAPI(title="Soonsim Detector - 30m Smart Debug Viewer", lifespan=lifespan)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>순심이 실시간 감시 뷰어 (30분 스마트 큐)</title>
    <style>
        :root {
            --bg-color: #0b1120;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --accent: #38bdf8;
            --alert: #ef4444;
            --success: #22c55e;
            --warning: #f59e0b;
            --border: #334155;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .header {
            width: 100%;
            max-width: 1240px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 14px;
        }
        .title-group {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .title { font-size: 1.45rem; font-weight: 700; color: var(--accent); }
        
        /* Header-sized Pulsating Circle and DateTime Text */
        .polling-indicator {
            display: flex;
            align-items: center;
            gap: 12px;
            background: #0f172a;
            border: 2px solid #334155;
            padding: 6px 18px;
            border-radius: 9999px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
        }
        .pulse-dot {
            width: 22px;
            height: 22px;
            border-radius: 50%;
            background: #22c55e;
            box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7);
            animation: pulse 1.6s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(0.92); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.8); }
            70% { transform: scale(1.12); box-shadow: 0 0 0 12px rgba(34, 197, 94, 0); }
            100% { transform: scale(0.92); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
        }
        .poll-text {
            font-size: 1.15rem;
            font-weight: 700;
            color: #f1f5f9;
            letter-spacing: -0.3px;
        }
        .poll-text span {
            color: #38bdf8;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        }

        .header-controls {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .audio-btn {
            background: #334155;
            color: #94a3b8;
            border: 1px solid var(--border);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.9rem;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.2s ease;
        }
        .audio-btn.active {
            background: #059669;
            color: white;
            border-color: #10b981;
        }
        .main-container {
            width: 100%;
            max-width: 1240px;
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
        }
        @media (max-width: 960px) {
            .main-container { grid-template-columns: 1fr; }
        }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }
        .card-title {
            font-size: 1.05rem;
            margin-bottom: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .live-preview {
            width: 100%;
            border-radius: 8px;
            border: 2px solid var(--border);
            aspect-ratio: 16 / 9;
            object-fit: cover;
            background: #000;
        }
        .status-banner {
            margin-top: 14px;
            padding: 14px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            gap: 14px;
            border: 1px solid var(--border);
            transition: all 0.3s ease;
        }
        .status-banner.no_change {
            background: rgba(30, 41, 59, 0.8);
            border-color: #475569;
        }
        .status-banner.motion {
            background: rgba(245, 158, 11, 0.15);
            border-color: var(--warning);
        }
        .status-banner.dog_on_pad {
            background: rgba(34, 197, 94, 0.2);
            border-color: var(--success);
            animation: padGlow 1.5s infinite alternate;
        }
        @keyframes padGlow {
            0% { box-shadow: 0 0 5px rgba(34, 197, 94, 0.3); }
            100% { box-shadow: 0 0 15px rgba(34, 197, 94, 0.8); }
        }
        .status-icon {
            font-size: 1.8rem;
        }
        .status-text-group { flex: 1; }
        .status-headline { font-size: 1.1rem; font-weight: 700; }
        .status-sub { font-size: 0.85rem; color: #94a3b8; margin-top: 3px; }

        .gallery-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .gallery {
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-height: 620px;
            overflow-y: auto;
            padding-right: 4px;
        }
        .gallery-item {
            display: flex;
            gap: 10px;
            padding: 8px;
            border-radius: 8px;
            background: #0f172a;
            border: 1px solid var(--border);
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .gallery-item:hover {
            border-color: var(--accent);
            transform: translateX(-2px);
        }
        .gallery-item.DOG_ON_PAD {
            border-color: var(--success);
            background: #064e3b;
        }
        .gallery-item.MOTION_CHANGE {
            border-color: #d97706;
            background: #451a03;
        }
        .gallery-thumb {
            width: 100px;
            height: 60px;
            border-radius: 6px;
            object-fit: cover;
        }
        .gallery-info {
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
            font-size: 0.85rem;
        }
        .time-tag { font-weight: 600; color: var(--accent); }
        .obj-tag { color: #94a3b8; margin-top: 2px; font-size: 0.78rem; }
        .badge-tag {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 0.72rem;
            width: fit-content;
            margin-top: 4px;
        }
        .badge-dog { background: var(--success); color: #000; }
        .badge-motion { background: var(--warning); color: #000; }
        .badge-baseline { background: #64748b; color: white; }
    </style>
</head>
<body>
    <div class="header">
        <div class="title-group">
            <div class="title">순심이 상시 감시 뷰어</div>
            <!-- Large Pulsating Circle and DateTime Text -->
            <div class="polling-indicator">
                <div class="pulse-dot"></div>
                <div class="poll-text">감시중: <span id="pollDatetimestamp">대기 중</span></div>
            </div>
        </div>
        <div class="header-controls">
            <button class="audio-btn" id="audioToggle" onclick="toggleAudio()">소리 알림: OFF (클릭하여 켜기)</button>
        </div>
    </div>

    <div class="main-container">
        <!-- Live Large View & Status -->
        <div class="card">
            <div class="card-title">
                <span>실시간 프레임 (NOW)</span>
                <span id="liveTimestamp" style="font-size: 0.88rem; color: #94a3b8;">대기 중...</span>
            </div>
            <img id="liveImage" class="live-preview" src="/api/snapshot/latest" alt="Live Stream Frame">

            <!-- Real-time Scene Status Banner -->
            <div class="status-banner no_change" id="statusBanner">
                <div class="status-icon" id="statusIcon">🟢</div>
                <div class="status-text-group">
                    <div class="status-headline" id="statusHeadline">현재 변화 없음 (정적 상태)</div>
                    <div class="status-sub" id="statusSub">5초마다 카메라를 능동 감시 중이며, 화면 및 배변판에 유의미한 변화가 없습니다.</div>
                </div>
            </div>
        </div>

        <!-- 30-Minute Significant Event Timeline -->
        <div class="card">
            <div class="gallery-header">
                <span style="font-weight: 600; font-size: 1.05rem;">최근 30분 이벤트 타임라인</span>
                <span id="eventCountBadge" style="font-size: 0.8rem; background: #0ea5e9; color: white; padding: 2px 8px; border-radius: 9999px;">0건</span>
            </div>
            <p style="font-size: 0.78rem; color: #64748b; margin-bottom: 10px;">
                * 미미한 변화는 저장하지 않고, 배변판 진입/움직임 이벤트만 기록합니다.
            </p>
            <div class="gallery" id="historyGallery">
                <div style="color: #64748b; text-align: center; padding: 30px;">최근 30분 내 감지된 이벤트가 없습니다.</div>
            </div>
        </div>
    </div>

    <script>
        let audioEnabled = false;
        let audioCtx = null;
        let lastAlertId = 0;

        function initAudio() {
            if (!audioCtx) {
                audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            if (audioCtx.state === 'suspended') {
                audioCtx.resume();
            }
        }

        function toggleAudio() {
            initAudio();
            audioEnabled = !audioEnabled;
            const btn = document.getElementById('audioToggle');
            if (audioEnabled) {
                btn.className = 'audio-btn active';
                btn.innerText = '소리 알림: ON (멍멍!)';
                playDogBark();
            } else {
                btn.className = 'audio-btn';
                btn.innerText = '소리 알림: OFF (클릭하여 켜기)';
            }
        }

        function playSingleBark(startTime) {
            if (!audioCtx) return;
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            const filter = audioCtx.createBiquadFilter();

            osc.type = 'sawtooth';
            filter.type = 'bandpass';
            filter.frequency.setValueAtTime(450, startTime);
            filter.Q.setValueAtTime(3.0, startTime);

            osc.frequency.setValueAtTime(350, startTime);
            osc.frequency.exponentialRampToValueAtTime(120, startTime + 0.18);

            gain.gain.setValueAtTime(0.01, startTime);
            gain.gain.linearRampToValueAtTime(0.8, startTime + 0.03);
            gain.gain.exponentialRampToValueAtTime(0.01, startTime + 0.20);

            osc.connect(filter);
            filter.connect(gain);
            gain.connect(audioCtx.destination);

            osc.start(startTime);
            osc.stop(startTime + 0.22);
        }

        function playDogBark() {
            if (!audioEnabled || !audioCtx) return;
            initAudio();
            const now = audioCtx.currentTime;
            playSingleBark(now);
            playSingleBark(now + 0.25);
        }

        async function fetchLiveStatus() {
            try {
                const res = await fetch('/api/live');
                const live = await res.json();

                // Display full datetimestamp (YYYY-MM-DD HH:MM:SS)
                document.getElementById('pollDatetimestamp').innerText = live.last_poll_str;
                document.getElementById('liveTimestamp').innerText = `최근 확인: ${live.last_poll_str}`;
                document.getElementById('liveImage').src = `/api/snapshot/latest?t=${Date.now()}`;

                const banner = document.getElementById('statusBanner');
                const icon = document.getElementById('statusIcon');
                const headline = document.getElementById('statusHeadline');
                const sub = document.getElementById('statusSub');

                banner.className = `status-banner ${live.status_type}`;
                headline.innerText = live.status_title;
                sub.innerText = live.status_desc;

                if (live.status_type === 'dog_on_pad') {
                    icon.innerText = '🐕';
                    if (live.last_poll_epoch !== lastAlertId) {
                        lastAlertId = live.last_poll_epoch;
                        playDogBark();
                    }
                } else if (live.status_type === 'motion') {
                    icon.innerText = '⚠️';
                } else {
                    icon.innerText = '🟢';
                }

                document.getElementById('eventCountBadge').innerText = `${live.total_events_30m}건`;

                const histRes = await fetch('/api/history');
                const history = await histRes.json();

                const gallery = document.getElementById('historyGallery');
                if (history.length === 0) {
                    gallery.innerHTML = '<div style="color: #64748b; text-align: center; padding: 30px;">최근 30분 내 감지된 이벤트가 없습니다. (정적 상태 유지 중)</div>';
                } else {
                    gallery.innerHTML = '';
                    [...history].reverse().forEach(item => {
                        const div = document.createElement('div');
                        div.className = `gallery-item ${item.event_type}`;
                        div.onclick = () => {
                            document.getElementById('liveImage').src = `/api/snapshot/${item.id}`;
                            document.getElementById('liveTimestamp').innerText = `과거 이벤트 기록: ${item.timestamp_str}`;
                        };

                        let badgeClass = 'badge-baseline';
                        let badgeText = '기준점';
                        if (item.event_type === 'DOG_ON_PAD') {
                            badgeClass = 'badge-dog';
                            badgeText = '순심이 배변판';
                        } else if (item.event_type === 'ANIMAL_DETECTED') {
                            badgeClass = 'badge-dog';
                            badgeText = '동물 감지';
                        } else if (item.event_type === 'MOTION_CHANGE') {
                            badgeClass = 'badge-motion';
                            badgeText = `움직임 (${item.change_score.toFixed(1)})`;
                        }

                        const objs = item.detected_objects.length > 0 ? item.detected_objects.join(', ') : '화면 변화';

                        div.innerHTML = `
                            <img class="gallery-thumb" src="/api/snapshot/${item.id}" alt="thumb">
                            <div class="gallery-info">
                                <div class="time-tag">${item.timestamp_str.split(' ')[1]}</div>
                                <div class="obj-tag">${objs}</div>
                                <div class="badge-tag ${badgeClass}">${badgeText}</div>
                            </div>
                        `;
                        gallery.appendChild(div);
                    });
                }
            } catch (err) {
                console.error("Error fetching live status:", err);
            }
        }

        setInterval(fetchLiveStatus, 2500);
        fetchLiveStatus();
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=HTML_TEMPLATE)


@app.get("/api/live")
async def get_live():
    state = viewer_service.get_live_state()
    return {
        "last_poll_str": state.last_poll_str,
        "last_poll_epoch": state.last_poll_epoch,
        "status_title": state.status_title,
        "status_desc": state.status_desc,
        "status_type": state.status_type,
        "detected_objects": state.detected_objects,
        "dog_in_zone": state.dog_in_zone,
        "change_score": state.change_score,
        "total_events_30m": state.total_events_30m,
        "interval_sec": state.interval_sec,
    }


@app.get("/api/history")
async def get_history():
    history = viewer_service.get_history()
    return [
        {
            "id": r.id,
            "timestamp_str": r.timestamp_str,
            "timestamp_epoch": r.timestamp_epoch,
            "detected_objects": r.detected_objects,
            "dog_in_zone": r.dog_in_zone,
            "event_type": r.event_type,
            "change_score": r.change_score,
        }
        for r in history
    ]


@app.get("/api/snapshot/latest")
async def get_latest_snapshot():
    state = viewer_service.get_live_state()
    if not state.latest_image_bytes:
        raise HTTPException(status_code=404, detail="No frames captured yet.")
    return Response(content=state.latest_image_bytes, media_type="image/jpeg")


@app.get("/api/snapshot/{record_id}")
async def get_snapshot(record_id: int):
    record = viewer_service.get_snapshot(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    return Response(content=record.image_bytes, media_type="image/jpeg")


def find_available_port(start_port: int = 8080, max_attempts: int = 100) -> int:
    """Find the first available TCP port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find an available port in range {start_port} - {start_port + max_attempts}")


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description="Soonsim Detector Live Debug Viewer (30m Smart Queue)")
    parser.add_argument("--port", "-p", type=int, default=8080, help="Starting port number")
    args = parser.parse_args()

    port = find_available_port(start_port=args.port)
    print(f"\n==================================================================")
    print(f" Soonsim Detector 30-Min Smart Live Viewer Started!")
    print(f" URL: http://localhost:{port}")
    print(f"==================================================================\n")
    uvicorn.run("src.viewer.app:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
