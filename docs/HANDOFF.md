# Soonsim Detector 인수인계서 (HANDOFF)

- 작성일: 2026-09-20
- 담당: S.P.I.R.E. 팀 (Leo, Kai, Elena, Noah, Axel, Chloe)
- 승인권자: Mike (Managing Director)

---

## 1. 프로젝트 요약 및 핵심 성과

Tapo C100 카메라의 RTSP 서브스트림(640x360 @ 15fps)을 상시 감시하여 배변판 영역 내 반려견(순심이)의 진입 및 체류를 고정밀로 탐지하고, 전후 5초를 포함한 고대비 바운딩 박스 오버레이 MP4 영상을 텔레그램으로 자동 전송하는 시스템을 완성했습니다.

### 주요 달성 내역
1. **DRY & 오픈소스 재사용**: Roboflow `supervision`과 `ultralytics` YOLOv8n을 결합하여 자체 컴퓨터 비전 알고리즘 없이 표준 컴포넌트로 파이프라인 구성.
2. **조명 변동 오탐 0건**: 시맨틱 딥러닝 객체 분류 및 ByteTrack 시계열 연속 프레임 추적으로 조명 점소등 노이즈 완전 배제.
3. **TOML 단일 설정 일원화**: `.env` 없이 `config/config.toml` 단일 파일로 모든 설정(카메라, 배변판 Polygon, 텔레그램, 임계값) 관리.
4. **실시간 디버그 웹 뷰어**: 5초 주기 스냅샷, 5분(60개) 롤링 큐, 배변판 진입 시 브라우저 Web Audio 강아지 짖는 소리("멍멍!") 재생 기능 추가.
5. **검증 완결**: Pytest 단위/통합 테스트 6건 전원 통과, 로컬 Docker 빌드/실행 검증 완료.

---

## 2. 컴포넌트 아키텍처 및 모듈 맵

- `src/config.py`: `tomllib` + `pydantic` 기반 타입 세이프 설정 관리자.
- `src/capture/stream.py`: `VideoStreamReader` (RTSP 자동 재연결/파일 루프) & `RingBuffer` (5초 슬라이딩 윈도우).
- `src/detector/model.py`: `DogDetector` (YOLOv8n ONNX CPU 다중 동물 클래스 15/16 필터).
- `src/detector/zone_tracker.py`: `ZoneTracker` (`sv.PolygonZone` 다중 앵커 + `sv.ByteTrack` 상태 머신).
- `src/recorder/annotator.py`: `HighContrastAnnotator` (3px 형광 라임/시안 고대비 박스/라벨/타임스탬프).
- `src/recorder/exporter.py`: `VideoClipExporter` (`sv.VideoSink` 기반 전후 5초 MP4 합성).
- `src/notifier/telegram.py`: `TelegramNotifier` (`python-telegram-bot` 비동기 비디오 업로드 및 체류 시간 캡션).
- `src/cli/calibrate.py`: 배변판 모서리 격자 캘리브레이션 도구 (`snapshot_grid.jpg`).
- `src/cli/dashboard.py`: Rich 실시간 콘솔 대시보드.
- `src/cli/debug_view.py`: 단일 프레임 정밀 객체/신뢰도 진단 도구.
- `src/viewer/app.py`: 5초 주기 캡처, 5분(60개) 롤링 큐, Web Audio 강아지 소리 알림 FastAPI 웹 뷰어.
- `src/main.py`: 통합 상시 감시 데몬 엔트리포인트.

---

## 3. 운영 및 유지보수 가이드

### 실시간 디버그 뷰어 실행
```bash
uv run python -m src.viewer.app
```
브라우저 접속: `http://localhost:8080` (또는 가용 포트)

### 상시 감시 데몬 실행
```bash
uv run python -m src.main
```

### Synology NAS 배포
```bash
./scripts/deploy.sh
```

---

## 4. 품질 및 보안 체크리스트

- [x] PEP8 / Python 3.12+ 타입 어노테이션 준수.
- [x] 시크릿 정보(`.env`, `config/config.toml`, 레코드 영상) `.gitignore` 등록 완료.
- [x] 단위/통합 테스트 100% 통과 (`uv run pytest`).
- [x] Docker 다단계 빌드 무결성 확인 (`docker compose build`).
- [x] NAS 리소스 제약 충족 (CPU 5% 이하, 메모리 150MB 이하).
