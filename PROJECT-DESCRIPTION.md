# 프로젝트 명세서: Soonsim Detector

## 1. Goal & Vision (목표 및 비전)

- 비디오 상시 감시 기반 반려견(순심이) 배변판 감지 및 텔레그램 실시간 영상 알람 시스템.
- 극심한 조명 변화(주/야간 IR 및 실내 5~6개 조명 임의 조합) 환경에서 오탐을 원천 차단하고 고정밀 탐지 보장.
- Synology NAS(DS923+) 대상 초경량 다중 컨테이너 배포 및 프레임 차분 모션 게이팅 기반 초저전력 CPU(평상시 1% 미만) 유지.
- SK 모뎀/공유기 포트포워딩 불가 환경에서 ngrok 영구 정적 도메인 터널링 및 PIN 보안 인증을 통한 외부 상시 관제 지원.

## 2. Domain & System Mission (도메인 및 시스템 핵심 미션)

- 입력 영상: Tapo C100 서브 스트림(640x360 @ 15fps H.264).
- 관심 영역(ROI): 배변판 고정 좌표 영역 감시.
- 4단계 검증 및 모션 최적화 엔진:
  1. 프레임 차분 모션 게이팅(Motion Gating): 배변판 주변 움직임 부재 시 딥러닝 추론 0회(CPU 점유율 극소화).
  2. 조도 급변(Global Flash) 필터: 전등 스위칭 오탐 차단.
  3. YOLOv8n ONNX CPU 추론: 'dog'/'cat' 클래스 시맨틱 검증 (신뢰도 >= 0.50, 배변판 PolygonZone 앵커 IoU 검증).
  4. ByteTrack 시계열 상태 머신: 다중 프레임 연속 검출 시 진입 확정, 15프레임 미검출 시 이탈 판정.
- 녹화 및 알람:
  - 메모리 링 버퍼 기반 탐지 전 5초 + 체류 시간 + 탐지 후 5초 MP4 합성.
  - 고대비 바운딩 박스(두께 3px, 형광 라임/시안) 및 타임스탬프 오버레이.
  - 텔레그램 봇 API(`sendVideo`) 비동기 전송.
- 관제 및 뷰어:
  - Rich 기반 실시간 상태 콘솔 대시보드 및 Loguru 로깅.
  - PIN 보안 잠금 화면 및 HttpOnly 세션 쿠키 인증.
  - 5초 주기 스냅샷 캔버스 오버레이, 5분(60개) 롤링 큐, 녹화 영상 브라우징, Web Audio 강아지 소리 알림 FastAPI 웹 뷰어.
  - ngrok 영구 정적 도메인(`blend-replay-canary.ngrok-free.dev`) 기반 외부 HTTPS 관제.

## 3. Workflows & Architecture (핵심 워크플로우 및 체계)

- 실행 환경:
  - 로컬 개발/테스트 환경: 본 시스템 (비디오 파일 모의 스트림 및 단위/통합 테스트).
  - 운영 배포 환경: Synology NAS DS923+ (`ssh soonsim`, Docker Compose host network).
- 배포 파이프라인:
  - `docker-compose.yml`: `soonsim-detector`, `soonsim-viewer`, `soonsim-ngrok` 3중 서비스 구성.
  - 원터치 배포 스크립트(`scripts/deploy.sh`): SSH 소스 동기화, Docker 빌드/재시작, 서비스 헬스체크 자동화.
- 에이전트 협업 체계:
  - 총괄/승인: Mike (Managing Director), Atlas (최고 전략 참모)
  - 설계 (Leo): 아키텍처, 인터페이스, 인수인계 총괄.
  - 백엔드 구현 (Kai): RTSP 수신, 모션 게이팅, ONNX 추론, 상태 머신, 인코더, 텔레그램 봇 모듈 개발.
  - 프론트엔드 (Maya): 웹 뷰어 PIN 보안 화면, 캔버스 오버레이, 롤링 큐 UI.
  - 품질 감사 (Elena): 정적 분석, 보안 인증, 리소스 최적화 무관용 감사.
  - 테스트 및 검증 (Noah): 14개 단위/통합 테스트 스위트 검증 및 회귀 방지.
  - 배포/운영 (Axel/Chloe): Docker, Host Network, ngrok 영구 터널링, Synology 원격 배포 자동화.

## 4. Architecture Roadmap (아키텍처 로드맵)

- [x] 마일스톤 1: uv 프로젝트 구성 및 모의 비디오/설정 모듈 구축.
- [x] 마일스톤 2: Ultralytics YOLOv8 + Roboflow Supervision 기반 고정밀 감지 및 링 버퍼 오버레이 MP4 합성 완성.
- [x] 마일스톤 3: Telegram 비동기 영상 알림 및 Rich CLI 실시간 텔레메트리 대시보드, 캘리브레이션 도구 구현.
- [x] 마일스톤 4: 5초 주기 캡처 & 5분 롤링 큐 & 실시간 사운드 웹 뷰어 UI 구축.
- [x] 마일스톤 5: Pytest 단위/통합 테스트 전원 통과(14/14) 및 Docker 컨테이너 사전 검증 완료.
- [x] 마일스톤 6: 모션 게이팅 CPU 최적화(평상시 CPU 1% 미만) 및 배변판 ROI 전용 감시 고도화.
- [x] 마일스톤 7: 웹 뷰어 PIN 보안 잠금 화면 및 세션 인증 체계 구축.
- [x] 마일스톤 8: Synology NAS DS923+ 실서버 다중 컨테이너 배포 및 ngrok 영구 고정 도메인(`blend-replay-canary.ngrok-free.dev`) 외부 관제 연동 완료.
