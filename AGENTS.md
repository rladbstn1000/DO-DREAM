# DO:DREAM 유지보수·검증 지침

- 팀 구현 기준: `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`. 이후 개인 개선은 `docs/portfolio/`에서 구분하고, 팀원·원본 UI 기여와 과거 실행 증거를 보존한다.
- 범위는 현재 사용자 요청을 따른다. 실제 백엔드·학생 웹과 공개 정적 showcase를 구분하며, 새 기능·대규모 리팩터링·실제 공급자 연결·공개 배포로 임의 확장하지 않는다. 실행 방법은 `docs/portfolio/02-local-runbook.md`, 코드 검토는 `docs/portfolio/18-portfolio-code-review.md`, 원본 UI·배포 기록은 `docs/portfolio/21-original-ui-showcase-results.md`를 참고한다.
- 사용자 승인 없이 stage/commit/push/PR/merge, remote 변경, 이력 재작성, reset/clean/stash를 하지 않는다. 로컬 stage·commit 승인을 원격 변경·배포 승인으로 확대하지 않는다. 검토한 파일만 명시 경로로 stage하고 staged diff를 확인한다.
- 기존 사용자 변경·팀 기여·과거 PASS/FAIL/NOT_RUN과 원본 증거를 보존한다. `docs/.DS_Store`는 읽기·삭제·stage에서 제외한다.
- 기존 컨테이너/볼륨/네트워크/DB 삭제·초기화, prune, `down -v`, 타 프로젝트 프로세스 종료 금지. 필요한 자체 서비스는 기존 scope gate를 통과한 범위에서만 사용하고, 이번에 시작한 자원만 종료해 시작 상태로 복구한다.
- 실제 LLM/GMS/OCR/AWS/Firebase·마이크·운영 서비스 호출, 비공개 데이터 복사·외부 전송 금지. API 키를 탐색·읽기·설정하지 않고 비밀값을 출력하지 않는다.
- `.local/env`는 생성된 로컬 비밀만 담는다. 기존 `.env`를 읽거나 가져오지 않는다. 실제 서버 검증의 Compose는 `dodream-phase1`, loopback 포트, 내부 네트워크를 사용한다.
- 인증·DB·Spring/FastAPI를 가짜 서버로 바꾸지 않는다. 실제 서버 검증은 외부 공급자 경계의 local 대역만 허용한다. showcase는 별도 build mode의 명시적 샘플이며 실제 API 실패를 데모 성공으로 숨기지 않는다. 안전 정책 위반 재현은 FAIL이다.
- UI·문서 검증만을 위해 Docker·DB를 실행하지 않는다. showcase는 기존 `npm --prefix fe-web run build:showcase`, `preview:showcase`, `verify:showcase`를 사용하고 빌드 산출물을 독립 브라우저로 검사한다. 실제 모드 typecheck/build와 영향받는 회귀를 구분하며 금지 API·마이크 요청/CSP 위반 0 기대값을 유지한다.
- 실제 서버 검증은 runbook과 변경 영향에 따라 기존 `python3 scripts/local/manage.py check`, `config`, `build`, `up`, `test`, `smoke`, `security`, `persistence`, `isolation`, `status`, `stop` 및 해당 단계 명령을 선택한다. 변경하지 않은 전체 과거 검사를 관성적으로 반복하지 않는다.
- 미실행은 NOT_RUN, 환경 차단은 BLOCKED로 기록한다. 과거 PASS를 현재 실행으로 대체하거나 테스트 삭제·skip·기대값 약화로 통과시키지 않는다. 원인이 같은 재시도를 반복하지 않는다. 실제 음성·스크린리더·실기기·공급자 품질·운영 준비는 직접 실행한 범위만 주장한다.
- `fe_app` 전체 설치/네이티브 빌드는 별도 범위다. 전역 도구·대형 모델을 설치하지 않는다.
