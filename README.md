# Soonsim Detector (순심이 배변판 상시 감시 및 텔레그램 알림 시스템)

Tapo C100 카메라의 실시간 RTSP 스트림을 분석하여 반려견(순심이)의 배변판 영역 진입 및 체류를 고정밀로 탐지하고, 전후 5초 버퍼를 포함한 고대비 바운딩 박스 오버레이 MP4 영상을 텔레그램으로 자동 전송하는 초경량 감시 시스템입니다.

---

## 1. 주요 특징 및 설계 원칙

- **DRY & 표준 오픈소스 극대화**: 자체 컴퓨터 비전 알고리즘을 지양하고, Roboflow `supervision`(`PolygonZone`, `ByteTrack`, `BoxAnnotator`, `LabelAnnotator`, `VideoSink`) 및 `ultralytics` YOLOv8n ONNX CPU 추론 엔진을 유기적으로 결합.
- **조명 변동 및 오탐 원천 차단**: 5~6개 실내 조명 점소등 및 주/야간 적외선(IR) 흑백 전환 시에도 시맨틱 딥러닝 객체 판별과 시계열 연속 프레임 추적으로 픽셀 노이즈 오탐 0건 보장.
- **TOML 단일 설정 일원화**: `.env` 파일 없이 `config/config.toml` 단일 파일로 카메라 RTSP 계정, 배변판 Polygon 다각형 좌표, 텔레그램 봇 토큰, 임계값을 통합 관리.
- **전후 5초 링 버퍼 녹화**: 메모리 큐 슬라이딩 윈도우를 통해 배변판 진입 전 5초 + 체류 구간 + 이탈 후 5초를 합성하여 MP4 영상 생성.
- **실시간 디버그 웹 뷰어**: 5초 주기 스냅샷, 5분(60개) 롤링 큐, 배변판 진입 시 브라우저 실시간 강아지 짖는 소리("멍멍!") Web Audio 재생.
- **Synology NAS (DS923+) 최적화**: AMD Ryzen R1600 CPU 기준 평상시 CPU 점유율 5% 이하, 메모리 150MB 이하 단일 Docker 컨테이너 배포.

---

## 2. 프로젝트 디렉터리 구조

```
soonsim-detector/
├── config/
│   ├── config.example.toml     # 기본 설정 템플릿
│   └── config.toml             # 실제 실행용 설정 (.gitignore 대상)
├── src/
│   ├── __init__.py
│   ├── config.py               # tomllib + Pydantic 설정 파서
│   ├── capture/
│   │   ├── __init__.py
│   │   └── stream.py           # RTSP 자동 재연결 및 5초 메모리 링 버퍼
│   ├── detector/
│   │   ├── __init__.py
│   │   ├── model.py            # Ultralytics YOLOv8n 다중 동물 추론 엔진
│   │   └── zone_tracker.py     # sv.PolygonZone 진입 감지 & sv.ByteTrack 상태 관리
│   ├── recorder/
│   │   ├── __init__.py
│   │   ├── annotator.py        # sv.BoxAnnotator/LabelAnnotator 고대비 오버레이
│   │   └── exporter.py         # sv.VideoSink 기반 전후 5초 H.264 MP4 합성기
│   ├── notifier/
│   │   ├── __init__.py
│   │   └── telegram.py         # python-telegram-bot 비동기 영상 전송
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── calibrate.py        # 배변판 좌표 눈금 격자 생성기
│   │   ├── dashboard.py        # Rich 실시간 콘솔 텔레메트리 대시보드
│   │   └── debug_view.py       # 단일 프레임 정밀 객체/신뢰도 디버거
│   ├── viewer/
│   │   ├── __init__.py
│   │   └── app.py              # 5초 주기 캡처 & 5분 큐 & 사운드 웹 뷰어 (FastAPI)
│   └── main.py                 # 상시 감시 통합 데몬 엔트리포인트
├── tests/
│   ├── test_config.py
│   ├── test_stream.py
│   ├── test_zone_tracker.py
│   └── test_pipeline_integration.py
├── scripts/
│   ├── deploy.sh               # Synology NAS(ssh soonsim) 원격 배포 자동화
│   ├── test_local.sh           # 로컬 합성 비디오 파이프라인 전수 검증
│   └── run_viewer.sh           # 실시간 디버그 웹 뷰어 실행 스크립트
├── pyproject.toml              # uv 패키지 및 종속성 관리
├── Dockerfile                  # Synology DS923+ 최적화 다단계 빌드
└── docker-compose.yml          # 단일 컨테이너 볼륨 마운트 정의
```

---

## 3. 설치 및 빠른 시작

### 1) 사전 준비
- Python 3.11+ 및 `uv` 패키지 관리자 설치

```bash
# uv 설치 (미설치 시)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2) 가상환경 구성 및 패키지 설치
```bash
uv sync
```

### 3) 설정 파일 작성 (`config/config.toml`)
`config/config.example.toml`을 복사하여 생성합니다:
```bash
cp config/config.example.toml config/config.toml
```

`config/config.toml` 주요 항목:
```toml
[camera]
source = "rtsp://username:password@192.168.0.50:554/stream2"
fps = 15
reconnect_interval_sec = 3.0

[zone]
# 배변판 모서리 4개 좌표
polygon = [
    [180, 90],
    [400, 80],
    [480, 300],
    [200, 300]
]

[detector]
model_name = "yolov8n.pt"
confidence_threshold = 0.30
track_thresh = 0.20
match_thresh = 0.8

[recorder]
pre_buffer_sec = 5
post_buffer_sec = 5
output_dir = "./records"
min_stay_duration_sec = 1.0

[telegram]
enabled = true
bot_token = "YOUR_TELEGRAM_BOT_TOKEN"
chat_id = "YOUR_TELEGRAM_CHAT_ID"
```

---

## 4. 도구 및 실행 가이드

### 1) 배변판 영역 캘리브레이션
카메라 스트림에서 50px 좌표 눈금이 그려진 `snapshot_grid.jpg`를 생성합니다:
```bash
uv run python -m src.cli.calibrate
```
생성된 이미지를 열어 배변판 4개 모서리 좌표를 확인 후 `config/config.toml`의 `polygon`에 반영합니다.

### 2) 실시간 디버그 웹 뷰어 (5분 큐 + 브라우저 강아지 소리 알림)
```bash
uv run python -m src.viewer.app
```
- 브라우저 접속: `http://localhost:8080` (또는 가용 포트 8082 등 자동 할당 URL)
- 상단 우측 `소리 알림: OFF` 버튼을 클릭하여 `ON (멍멍!)`으로 전환하면 순심이가 배변판에 올라올 때마다 실시간 짖는 소리가 재생됩니다.

### 3) 상시 감시 메인 데몬 구동
- Rich 실시간 콘솔 대시보드 모드:
```bash
uv run python -m src.main
```
- 백그라운드/로그 모드:
```bash
uv run python -m src.main --no-dashboard
```

### 4) 단위 및 통합 테스트 실행
```bash
uv run pytest -v
```

---

## 5. Synology NAS (`ssh soonsim`) 원격 배포

로컬에서 설정 및 검증을 완료한 후, 단일 명령어로 Synology DS923+ NAS에 자동 배포합니다:

```bash
./scripts/deploy.sh
```

배포 스크립트 자동 수행 내역:
1. `ssh soonsim` 연결 상태 점검.
2. NAS 원격 디렉터리(`~/soonsim-detector`)에 소스코드 및 설정 Rsync 동기화.
3. 원격 Docker Compose 빌드 및 백그라운드 컨테이너 실행(`restart: unless-stopped`).
4. 컨테이너 구동 상태 및 초기 로그 자동 출력.
