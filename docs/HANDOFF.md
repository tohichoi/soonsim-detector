# Soonsim Detector 인수인계서 (HANDOFF)

- 작성일: 2026-09-20
- 최종 갱신: 2026-09-23 (커밋 `5ddc7f2` 기준)
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
9. **단위/통합 테스트 100% 통과**: 56개 테스트 케이스 전원 패스.
10. **추적 진단 텔레메트리 HUD**: 내보내는 이벤트 영상 우측 상단에 `dog#`/`track`/`state`/`stay` 4행 HUD 를 XOR 텍스트 + 바 그래프로 표시. `track` 은 ByteTrack 내부 카운트다운(추적 유실까지 남은 프레임)을 직접 읽어 0에 가까울수록 빨강으로 시각화.
11. **lost_track_buffer 설정화 및 시맨틱 교정**: 추적 유지 시간을 `detector.lost_track_buffer_sec`(초)로 설정화. supervision 의 `frame_rate/30` 정규화로 설정값이 실제 절반으로 동작하던 버그를 `frame_rate=30` 으로 교정해 1:1 대응.
12. **놓침 영상 자동 보존**: 2026-09-22 에 실제 배변 1건을 놓친 사건(07:47:02~07:47:58, 56초간 움직임은 감지됐고 추론 30회가 전부 0검출) 이후 도입. `SignalRecorder` 가 "움직임은 있는데 검출이 0인 구간"을 이벤트와 같은 전후 버퍼 창으로 `records/signal_<시각>.mp4` 에 저장한다. 텔레그램 알림은 보내지 않는다. 놓침은 이벤트가 아니라서 클립이 남지 않던 문제를 없앤다.
13. **0검출 프레임의 최고 점수 기록**: `model.py` 가 `conf=0.01` 까지 상자를 모아 파이썬에서 자르고, 모든 INFER 로그에 `Top: 0.42` 를 남긴다. 놓침이 임계값 문제(0.24 근처)인지 조명·회전 문제(0.02 근처)인지 가르는 유일한 데이터.
14. **클립 자동 정리**: `recorder.retention_days`(기본 30일)를 넘긴 클립을 삭제. `soonsim_*.mp4` 와 `signal_*.mp4` 만 대상이고 같은 폴더의 로그는 건드리지 않는다. 정리가 없으면 볼륨이 차서 감시 자체가 멈춘다.
15. **캘리브레이션 잔차 보고**: 도구 화면이 이미 `roll_deg` 만큼 보정된 뒤라 표시되는 각도는 잔차다. `roll_verdict()` 가 절대값을 합성해 붙여넣을 값을 하나로 확정하고, 두 추정치(세계 수직선 / 배변판 소실선)가 허용치 2도를 넘게 벌어지면 갱신을 거부한다. 잘못된 각도로 덮어쓰면 이후 모든 프레임이 어긋나기 때문이다.

---

## 2. 컴포넌트 아키텍처 및 모듈 맵

- `src/config.py`: `tomllib` + `pydantic` 기반 설정 관리자 (카메라, 배변판, 텔레그램, 뷰어 `enabled`/`host`/`port`/`pin`/`retention_sec`, `detector.lost_track_buffer_sec`, `recorder.signal_clip_enabled`/`signal_min_sec`/`retention_days`).
- `src/capture/stream.py`: `VideoStreamReader` (RTSP 자동 재연결/파일 루프) & `RingBuffer` (5초 슬라이딩 윈도우).
- `src/detector/model.py`: `DogDetector` (YOLOv8n ONNX CPU 다중 동물 클래스 15/16 필터).
- `src/detector/motion_gate.py`: `MotionGate` (프레임 차분 기반 2단계 모션 게이팅, 무동작 시 YOLO 추론 0회).
- `src/detector/zone_tracker.py`: `ZoneTracker` (`sv.PolygonZone` 다중 앵커 + `sv.ByteTrack` 상태 머신 + 모션 게이팅) + `FrameTelemetry`(프레임별 진단 상태 기록).
- `src/recorder/annotator.py`: `HighContrastAnnotator` (3px 형광 라임/시안 고대비 박스/라벨/타임스탬프).
- `src/recorder/exporter.py`: `VideoClipExporter` (`sv.VideoSink` 기반 전후 5초 MP4 합성) + `prune_old_clips()` (retention 경과 클립 삭제 — `soonsim_*`/`signal_*` 만, 로그는 보존).
- `src/recorder/signal_recorder.py`: `SignalRecorder` — 움직임은 있는데 검출이 0인 구간을 클립으로 남긴다. **시간을 반드시 벽시계(타임스탬프)로 재야 한다** — 추론이 5프레임마다·움직임 있을 때만 돌아 시그널 프레임이 초당 0.5회꼴이라, 프레임 수로 세면 56초짜리 놓침이 2초로 계산돼 버려진다. `MAX_SIGNAL_SEC = 45` 가 에피소드 상한이고 `recorder.signal_min_sec` 도 같은 값으로 잘린다(어긋나면 클립이 조용히 하나도 안 남아 테스트가 두 값을 묶어둔다).
- `src/recorder/hud.py`: `TelemetryHud` (우측 상단 진단 HUD — dog#/track/state/stay 바 그래프, XOR 텍스트).
- `src/notifier/telegram.py`: `TelegramNotifier` (`python-telegram-bot` 비동기 비디오 업로드 및 체류 시간 캡션).
- `src/viewer/state.py`: `ViewerStateStore` — 감시 데몬 ↔ 뷰어 간 스레드 세이프 공유 상태 저장소. `LiveState`(실시간 텔레메트리) + `SnapshotRecord`(30분 보존 이벤트 큐, `retention_sec` 프루닝).
- `src/viewer/server.py`: `ViewerServer` — 데몬과 동일 프로세스 내 데몬 스레드로 uvicorn 기동. 포트 점유 시 `find_available_port()`가 최대 100 포트까지 자동 대체.
- `src/viewer/app.py`: FastAPI 라우팅 (PIN 인증, 실시간 스냅샷/이력 조회 API) — 상태 관리는 `state.py`, 마크업은 `templates.py`로 분리.
- `src/viewer/templates.py`: 넷플릭스식 시어터 모달, 30분 이벤트 타임라인, 신호등 상태 인디케이터, 키보드 내비게이션을 포함한 뷰어 UI 템플릿.
- `src/viewer/live_feed.py`: `LiveFeed` — 뷰어에 무엇을 언제 밀지 결정. 검출에 대해 아무것도 판단하지 않아 `main.py` 에서 분리했다(파일 300줄 규칙). 강아지가 영역 밖일 때만 갱신을 0.5초로 제한한다.
- `src/utils/telemetry.py`: 폴링 주기/추론 시간 등 런타임 텔레메트리 수집. INFER 로그에 `Found` 와 함께 `Top: <0검출 프레임 최고 점수>` 를 남긴다.
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
- 기본 브랜치: `main` (최신 `5ddc7f2`) — `feat/missed-detection-capture`, `docs/calibration-theory` 병합 후 삭제됨
- 남은 브랜치: `origin/feat/lost-track-buffer-config` (`94083f4`) 원격 전용. 내용(`lost_track_buffer_sec` 설정화, `tzdata` 의존성)은 이미 `main` 에 들어가 있으나 브랜치 tip 이 별도 — 실제 미병합 커밋이 있는지 확인 후 정리 필요.
- 작업 트리: `.serena/` 와 `.claude/.headroom_wrap_*` 가 untracked 로 남아 있다. 프로젝트 코드가 아니라 도구 산출물이므로 `.gitignore` 등록 검토.

### 최우선 — 배변판 접촉 임계값 미정 (2026-09-23 현재, 계측 1단계 정지)

진입 판정은 여전히 `require_all_anchors=False`(`zone_tracker.py:61`)라 CENTER 하나만 들어와도 진입이다. 몸통 중점이 스치는 통과 동작도 오탐이 된다.

Mike 라벨(2026-09-22 이벤트 14건): 진짜 배변 = `07:33:23`, `07:48:55`, `23:59:35`. `13:08:25` 는 "발만 살짝 올림", `19:20:21` 은 "배변판 위를 걸어감".

- **확정 가능**: 오탐 11건 중 9건은 `overlap_max` 가 정확히 0.0000(배변판 접촉이 전혀 없음 = 앞을 지나가는 통과). `overlap >= 0.10` 게이트로 제거되고 진짜 3건은 무손실(진짜 최소 `overlap_max` = 0.2384). 임계값이 0.0 군집과 0.2384 사이 빈 구간에 놓인다.
- **확정 불가**: 오탐 `13:08:25`(접촉 1.1초) / `19:20:21`(접촉 6.2초, 횡이동 164px) 이 진짜 `23:59:35`(접촉 6.6초, 횡이동 172px) 와 거의 동일한 서명이다. 위치·접촉·이동량·margin 어느 축으로도 안 갈린다. 진짜가 3건뿐이라 지금 체류 임계값을 정하면 곡선맞춤이다.

**다음 단계:** 며칠 돌려 `records/signal_*.mp4` 를 모은 뒤, 그 시각의 `Top:` 값이 0.24 근처면 임계값 문제(내리면 됨), 0.02 근처면 조명·회전 문제다. 접촉 게이트는 그 뒤에 적용한다.

### 재캘리브레이션 권장 (운영)

현재 config 폴리곤으로 `roll_from_quad()` 를 돌리면 **−3.67°** 가 나온다. 적용된 보정은 24.86° 이므로 배변판 기준 잔차가 3.67° 이고, 이는 `ROLL_TOLERANCE_DEG = 2.0` 을 넘는다. 도구를 열면 "roll_deg = 21.19 로 갱신하세요"가 뜰 값이다. `snapshot_grid.jpg` 가 2026-09-21 03:37 촬영이라 그 뒤 카메라나 배변판이 움직였을 수 있다 — 단정하지 말고 도구로 재측정할 것.

### 차기 세션 백로그 (감사 PASS, 비차단 항목)
1. `zone_tracker.py` `_lost_track_remaining()` 의 `except Exception: return []` — 무로그 침묵 열화. 최초 1회 `logger.warning` 권장.
2. `hud.py` `_track()` 의 lost 우선 분기 — 다중 트랙 시 개가 정상 추적 중이어도 "lost"로 오표기 가능.
3. `hud.py` 간격 상수 `2` 미명명.
4. 검증 게이트(`ruff`, `scripts/check-code-quality.sh`) 부재 — 프로젝트 차원 복구 필요. 변경 파일은 ruff clean 이나 기존 위반 3건(`src/viewer/app.py:11`, `src/viewer/server.py:5`, `tests/test_viewer_unified.py:5`, F401)이 남아 있다. `mypy` 미설치로 타입 검증은 미확인.
5. (범위 외 잠재 버그) `zone_tracker.py` `(self.stay_start_time or packet.timestamp)` — `stay_start_time == 0.0` 일 때 falsy 평가로 이벤트 폐기. `is not None` 비교 권장.
6. 포트폴리오 publisher 가 **삭제된 자산을 전파하지 않는다** — `portfolio-contribute.sh` 는 `scp -r`, `build_portfolio.py` `_copy_assets()` 는 파일별 `shutil.copy2` 라 병합만 한다. `roi_overlay.jpg` 를 지웠는데도 서버 `sources/`·`html/` 에 그대로 남아 URL 로 받아진다(페이지에서는 미참조). 허브 렌더 코드 변경이라 별도 커밋 + `bootstrap-publisher.sh` 필요.

### 보안 항목 이력
- **해결됨**: `docker-compose.yml`에 평문으로 커밋되어 있던 `NGROK_AUTHTOKEN`을 ngrok 대시보드에서 재발급(rotate)하고, `.env`(gitignore 대상) + `env_file` 방식으로 이전했습니다. 추적 파일에는 더 이상 토큰이 없습니다.
- 옛 토큰은 Git 히스토리에 남아 있으나 **대시보드에서 폐기(revoke)** 하여 무효화했습니다. 주의: 재발급만으로는 옛 토큰이 무효화되지 않습니다(재발급 직후에도 옛 토큰으로 터널이 동작했음). 반드시 별도로 폐기해야 합니다.
- 폐기 후 검증: 기존 터널이 HTTP 200으로 유지되고 ngrok 로그에 인증 오류가 없음 → NAS가 새 토큰으로 터널링 중임을 확인.

### 인증 취약점 수정 이력 (2026-09-20)
- **문제**: 세션 쿠키가 `sha256("<PIN>:<session_secret>")` 로 계산되어, PIN(4자리 = 10,000가지)과 공개된 기본 `session_secret` 만 알면 **로그인 요청 없이 오프라인에서 쿠키를 위조**할 수 있었습니다. `check_auth` 의 `==` 비교도 상수시간이 아니었습니다.
- **수정**: 세션을 `secrets.token_urlsafe(32)` 로 생성한 불투명 토큰으로 교체하고 서버 메모리(`SessionStore`)에 보관합니다. PIN 에서 파생되는 값이 없어져 위조 경로가 사라집니다. PIN 비교는 `secrets.compare_digest` 로 변경했습니다.
- **추가**: `LoginThrottle` 로 연속 5회 실패 시 5분간 잠급니다(전역 카운터 — 단일 가구용이라 per-IP 보다 단순하면서 우회가 어렵습니다). 429 응답은 로그인 화면에 그대로 표시됩니다.
- **설정 변경**: `session_secret` 필드는 더 이상 쓰이지 않아 `config.py` 와 설정 파일에서 제거했습니다. 기존 `config.toml` 에 남아 있어도 pydantic 이 무시하므로 그대로 동작합니다.
- **동작 변경**: 세션이 메모리에만 있으므로 **재시작(배포) 후 다시 로그인**해야 합니다. 기존에는 쿠키가 결정적이라 재시작 후에도 유지됐습니다.

### `.env` 관리
- `NGROK_AUTHTOKEN`은 루트의 `.env`에 있습니다. `.gitignore`의 `*.env` 규칙으로 제외되므로 커밋되지 않습니다.
- `scripts/deploy.sh`의 rsync는 `.env`를 제외하지 않으므로 NAS로 함께 전송됩니다. 토큰을 바꾼 뒤에는 `reload_config.sh`가 아니라 **`deploy.sh`** 를 실행해야 반영됩니다.
