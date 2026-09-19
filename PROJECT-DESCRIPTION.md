# 프로젝트 명세서: Soonsim Detector

## 1. Goal & Vision (목표 및 비전)

- 비디오 상시 감시 기반 반려견(순심이) 배변판 감지 및 텔레그램 실시간 알람 시스템.
- 극심한 조명 변화(주/야간 IR 및 실내 5~6개 조명 임의 조합) 환경에서 오탐을 원천 차단하고 고정밀 탐지 보장.
- Synology NAS(DS923+) 대상 초경량 단일 컨테이너 배포 및 최소 리소스 점유.

## 2. Domain & System Mission (도메인 및 시스템 핵심 미션)

- 입력 영상: Tapo C100 서브 스트림(640x360 @ 15fps H.264).
- 관심 영역(ROI): 배변판 고정 좌표 영역 감시.
- 4단계 검증 엔진:
  1. 조도 급변(Global Flash) 필터: 전등 스위칭 오탐 차단.
  2. 적응형 영상 보정: 야간 IR 흑백 환경 CLAHE 대비 향상.
  3. YOLO ONNX CPU 추론: 'dog' 클래스 시맨틱 검증 (신뢰도 >= 0.50, 배변판 IoU >= 0.30).
  4. 시계열 상태 머신: 5프레임 중 3프레임 이상 연속 검출 시 진입 확정, 15프레임 미검출 시 이탈 판정.
- 녹화 및 알람:
  - 메모리 링 버퍼 기반 탐지 전 5초 + 체류 시간 + 탐지 후 5초 MP4 합성.
  - 고대비 바운딩 박스(두께 3px, 형광 라임/시안) 및 타임스탬프 오버레이.
  - 텔레그램 봇 API(`sendVideo`) 비동기 전송.
- 관제 및 뷰어:
  - Rich 기반 실시간 상태 콘솔 대시보드 및 Loguru 로깅.
  - 5초 주기 캡처 & 5분(60개) 롤링 큐 & Web Audio 강아지 짖는 소리 알림 FastAPI 실시간 웹 뷰어.

## 3. Workflows & Architecture (핵심 워크플로우 및 체계)

- 실행 환경:
  - 로컬 개발/테스트 환경: 본 시스템 (비디오 파일 모의 스트림 및 웹캠/RTSP 테스트).
  - 배포 대상 환경: Synology NAS DS923+ (`ssh soonsim`, Docker Compose).
- 배포 파이프라인:
  - 배포 스크립트(`scripts/deploy.sh`): SSH(`soonsim`) 기반 소스 동기화 및 Docker Compose 빌드/재시작.
- 에이전트 협업 체계:
  - 설계 (Leo): 아키텍처 및 설정/배포 인터페이스 확정.
  - 백엔드 구현 (Kai): RTSP 수신, ONNX 추론, 상태 머신, 인코더, 텔레그램 봇 모듈 개발.
  - 품질 감사 (Elena): 정적 분석, PEP8, 리소스 누수 및 예외 처리 감사.
  - 테스트 및 검증 (Noah): 가상 비디오 스트림 기반 단위/통합 테스트 검증.
  - 배포/운영 (Axel/Chloe): Dockerfile, Compose, SSH 배포 스크립트 작성 및 DS923+ 배포 점검.

## 4. Architecture Roadmap (아키텍처 로드맵)

- [x] 마일스톤 1: uv 프로젝트 구성 및 모의 비디오/설정 모듈 구축.
- [x] 마일스톤 2: Ultralytics YOLOv8 + Roboflow Supervision(PolygonZone, ByteTrack) 기반 고정밀 감지 및 링 버퍼 오버레이 MP4 합성 완성.
- [x] 마일스톤 3: Telegram 비동기 영상 알림 및 Rich CLI 실시간 텔레메트리 대시보드, 캘리브레이션 도구 구현.
- [x] 마일스톤 4: 5초 주기 캡처 & 5분 롤링 큐 & 실시간 사운드 웹 뷰어 UI 구축.
- [x] 마일스톤 5: Pytest 단위/통합 테스트 전원 통과 및 로컬 Docker 컨테이너 사전 검증 완료.
- [ ] 마일스톤 6: Synology NAS(`ssh soonsim`) 실서버 배포 및 실제 카메라(Tapo C100) 연동 최종 가동.


