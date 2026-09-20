# Soonsim Detector 인수인계서 (HANDOFF)

- 작성일: 2026-09-20
- 최종 갱신: 2026-09-20 (커밋 `3ae3cc0` 기준)
- 총괄: Mike (Managing Director)
- 참여 에이전트:
  - Executive Staff: Atlas (전략 조율 및 파이프라인 총괄)
  - S.P.I.R.E.: Leo (아키텍처/설계), Kai (백엔드/영상 파이프라인), Maya (웹 뷰어 UI), Noah (QA/테스트 검증), Elena (품질/보안 감사)
  - O.R.B.I.T.: Chloe (CI/CD 보안 및 터널링 파이프라인), Axel (Synology NAS 플랫폼 인프라)

---

## 1. 프로젝트 요약 및 핵심 성과

Tapo C100 카메라의 RTSP 서브스트림(640x360 @ 15fps)을 감시하여 배변판 영역 내 반려견(순심이)의 진입 및 체류를 고정밀로 탐지하고, 전후 5초를 포함한 고대비 바운딩 박스 오버레이 MP4 영상을 텔레그램으로 자동 전송하는 시스템입니다.
Synology NAS(DS923+)에 상시 가동 컨테이너로 배포되었으며, 외부 인터넷에서 PIN 보안 잠금 화면을 통해 언제 어디서나 고정 도메인으로 실시간 뷰어에 접속할 수 있습니다.

### 주요 달성 내역
1. **모션 게이팅 기반 초저전력 CPU 최적화**: 프레임 차분 기반 모션 게이팅을 적용하여 배변판 주변 움직임이 없을 때는 YOLO 추론을 0회로 제한(평상시 CPU 1% 미만).
2. **조명 변동 오탐 방지**: 시맨틱 딥러닝 객체 분류 및 ByteTrack 시계열 연속 프레임 추적으로 조명 점소등 노이즈 완전 배제.
3. **PIN 잠금 화면 및 세션 인증**: 웹 뷰어 접근 시 PIN 인증 및 HttpOnly 세션 쿠키 보호 적용.
4. **ngrok 고정 정적 도메인 터널링**: SK 모뎀의 포트포워딩 불가 환경을 극복하고 영구 정적 도메인(`blend-replay-canary.ngrok-free.dev`)으로 외부 접속 구축.
5. **Synology NAS 원터치 배포 파이프라인**: `scripts/deploy.sh`를 통해 이미지 빌드, 다중 컨테이너 재생성, 헬스체크를 1회 명령으로 자동 수행.
6. **한국 표준시(KST) 타임존 동기화**: 도커 컨테이너(`tzdata`, `TZ=Asia/Seoul`) 및 백엔드 전반에 `ZoneInfo("Asia/Seoul")` 강제 적용으로 디버그 화면 및 영상 타임스탬프 일치.
7. **단일 RTSP 통합 파이프라인**: 감시 데몬과 웹 뷰어가 각각 RTSP를 열던 이중 연결 구조를 `ViewerStateStore` 기반 단일 파이프라인으로 통합. 카메라 연결 1회, 상태는 스레드 세이프 저장소로 공유.
8. **넷플릭스식 시어터 모달 UI**: 실시간/이력 스냅샷 클릭 시 전체화면·시어터 모달 전환, 30분 이벤트 타임라인 썸네일 2배 확대(16:9 비율 유지), 신호등 방식 상태 인디케이터, 키보드 내비게이션(ESC / F / 방향키) 지원.
9. **단위/통합 테스트 100% 통과**: 20개 테스트 케이스 전원 패스.

---

## 2. 컴포넌트 아키텍처 및 모듈 맵

- `src/config.py`: `tomllib` + `pydantic` 기반 설정 관리자 (카메라, 배변판, 텔레그램, 뷰어 `enabled`/`host`/`port`/`pin`/`session_secret`/`retention_sec`).
- `src/capture/stream.py`: `VideoStreamReader` (RTSP 자동 재연결/파일 루프) & `RingBuffer` (5초 슬라이딩 윈도우).
- `src/detector/model.py`: `DogDetector` (YOLOv8n ONNX CPU 다중 동물 클래스 15/16 필터).
- `src/detector/motion_gate.py`: `MotionGate` (프레임 차분 기반 2단계 모션 게이팅, 무동작 시 YOLO 추론 0회).
- `src/detector/zone_tracker.py`: `ZoneTracker` (`sv.PolygonZone` 다중 앵커 + `sv.ByteTrack` 상태 머신 + 모션 게이팅).
- `src/recorder/annotator.py`: `HighContrastAnnotator` (3px 형광 라임/시안 고대비 박스/라벨/타임스탬프).
- `src/recorder/exporter.py`: `VideoClipExporter` (`sv.VideoSink` 기반 전후 5초 MP4 합성).
- `src/notifier/telegram.py`: `TelegramNotifier` (`python-telegram-bot` 비동기 비디오 업로드 및 체류 시간 캡션).
- `src/viewer/state.py`: `ViewerStateStore` — 감시 데몬 ↔ 뷰어 간 스레드 세이프 공유 상태 저장소. `LiveState`(실시간 텔레메트리) + `SnapshotRecord`(30분 보존 이벤트 큐, `retention_sec` 프루닝).
- `src/viewer/server.py`: `ViewerServer` — 데몬과 동일 프로세스 내 데몬 스레드로 uvicorn 기동. 포트 점유 시 `find_available_port()`가 최대 100 포트까지 자동 대체.
- `src/viewer/app.py`: FastAPI 라우팅 (PIN 인증, 실시간 스냅샷/이력 조회 API) — 상태 관리는 `state.py`, 마크업은 `templates.py`로 분리.
- `src/viewer/templates.py`: 넷플릭스식 시어터 모달, 30분 이벤트 타임라인, 신호등 상태 인디케이터, 키보드 내비게이션을 포함한 뷰어 UI 템플릿.
- `src/utils/telemetry.py`: 폴링 주기/추론 시간 등 런타임 텔레메트리 수집.
- `src/cli/`: 운영 보조 도구 — `calibrate.py`(배변판 좌표 캘리브레이션), `debug_view.py`(단독 디버그 뷰어), `dashboard.py`.
- `src/main.py`: 통합 상시 감시 데몬 엔트리포인트 (감시 루프 + 뷰어 서버 단일 프로세스).
- `docker-compose.yml`: `soonsim-detector`(감시+뷰어 통합), `ngrok` 2중 서비스 구성. `./src` 읽기 전용 볼륨 마운트로 재빌드 없이 UI 즉시 반영.
- `scripts/deploy.sh`: NAS 원격 자동 빌드 및 배포 스크립트.
- `scripts/reload_config.sh`: `config.toml`만 rsync 후 컨테이너 restart (약 2초, 재빌드 불필요).
- `scripts/benchmark_cpu.py`: CPU 사용률 벤치마크.

---

## 3. 운영 및 접속 가이드

### 외부 인터넷 접속 (영구 고정 도메인)
- URL: `https://blend-replay-canary.ngrok-free.dev`
- 인증: PIN 잠금 화면 (config.toml 설정값 사용)
- 참고: 최초 접속 시 ngrok 무료 계정 안내 화면에서 `Visit Site` 클릭 후 PIN 입력

### 로컬 LAN 접속 (집 내부 Wi-Fi)
- URL: `http://192.168.45.63:8080`

### NAS 재배포 및 업데이트 명령어

**코드/설정 변경 시 (전체 재빌드)**
```bash
./scripts/deploy.sh
```

**`config.toml` 값만 바꿀 때 (재빌드 없이 약 2초)**
```bash
./scripts/reload_config.sh
```
`src/`는 읽기 전용 볼륨으로 마운트되어 있으므로 소스만 수정한 경우에도 재빌드 없이 `docker compose restart soonsim-detector`로 반영됩니다.

### 테스트 실행
```bash
uv run pytest
```

---

## 4. Git 형상 관리 상태

- 원격 저장소: `git@github.com:tohichoi/soonsim-detector.git`
- 기본 브랜치: `main`
- 최신 커밋: `3ae3cc0` (`feat: integrate unified RTSP architecture and Netflix-style theater modal UI`)
- 작업 트리 상태: Clean (모든 소스 및 설정 동기화 완료)

### 미해결 보안 항목
- `docker-compose.yml`의 `NGROK_AUTHTOKEN`이 평문으로 커밋되어 있음. `.env` + `env_file` 또는 NAS 측 환경변수 주입으로 이전 필요. 토큰이 이미 Git 히스토리에 남아 있으므로 ngrok 대시보드에서 재발급(rotate) 후 교체할 것.
