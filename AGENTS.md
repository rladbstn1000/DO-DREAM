# DO:DREAM phase 1 작업 지침

- 팀 구현 기준: `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`. 개인 개선은 `docs/portfolio/`에 구분한다.
- 범위: 격리된 로컬 실행 복원, 빌드/인증/영속성 검증, 보안 기준선 기록. 보안 전면 수정·RAG 고도화·UI 개편·공개 배포는 별도 단계다.
- 사용자 승인 없이 stage/commit/push/PR/merge, remote 변경, 이력 재작성, reset/clean/stash를 하지 않는다.
- 기존 컨테이너/볼륨/네트워크/DB 삭제·초기화, prune, `down -v`, 타 프로젝트 프로세스 종료 금지.
- 실제 LLM/GMS/OCR/AWS/Firebase, 운영 서비스 호출, 비공개 데이터 복사·외부 전송 금지. 비밀값 출력 금지.
- `.local/env`는 생성된 로컬 비밀만 담는다. 기존 `.env`를 읽거나 가져오지 않는다. Compose는 `dodream-phase1`, loopback 포트, 내부 네트워크를 사용한다.
- 인증·DB·Spring/FastAPI를 가짜 서버로 바꾸지 않는다. 외부 공급자 경계의 local 대역만 허용한다. 안전 정책 위반 재현은 FAIL이다.
- 실제 검증 명령: `python3 scripts/local/manage.py check`, `config`, `build`, `up`, `test`, `smoke`, `security`, `persistence`, `isolation`, `status`, `stop`.
- 미실행은 NOT_RUN, 환경 차단은 BLOCKED로 기록한다. 원인이 같은 재시도를 반복하지 않는다.
- `fe_app` 전체 설치/네이티브 빌드는 범위 밖이다. 전역 도구·대형 모델을 설치하지 않는다.
