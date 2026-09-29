# 03. 1차 작업 결과 — 2026-09-29

## 범위와 판정

팀 구현 기준 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`, 실제 작업 `/Users/yoonsu/Desktop/projects/DO-DREAM`, 개인 브랜치 `codex/dodream-phase1-runtime`. 시작 시 변경이 없었고 HEAD는 그대로 유지했다. 기존 팀 문서/기능과 모바일 소스는 보존했다. 후속 보안 전면 수정·RAG 고도화·웹 전환·공개 배포는 시작하지 않았다.

| 항목 | 최종 상태 | 근거 / 한계 |
|---|---|---|
| BUILD | **PASS** | Spring compile/bootJar 및 5 tests, 웹 typecheck/build, AI 7 tests, PDF 6 tests, Compose config. |
| LOCAL_RUNTIME | **PASS** | 실제 Spring/FastAPI×2, MySQL, Redis, Celery, nginx 기동·헬스. 검증 후 전용 컨테이너 7개 중지. |
| AUTH_SMOKE | **PASS** | 합성 계정/보호 API/무토큰·잘못된 토큰/웹 Origin 경로 포함 27개. token kind 안전성은 아래 별도 FAIL. |
| CLEAN_START | **PASS** | 최초 inventory에 전용 볼륨 없음 → 신규 4개 생성 → 실제 서버 healthy. 첫 호스트 연결은 내부망 포트 제약으로 BLOCKED였고 게이트웨이 수정 후 PASS. |
| RESTART_PERSISTENCE | **PASS** | stop/up 후 앱 seed가 만들지 않는 MySQL·Redis 표식, 도메인 수, 기존 SQLite 세션·대역 인덱스 보존: 7/7. |
| SECURITY_BASELINE | **FAIL** | 안전 기대 위반 9개. 만료시간 측정 1개는 관측 PASS이며 안전성 통과를 뜻하지 않음. |
| REAL_AI_INTEGRATION | **NOT_RUN** | 실제 GMS/LLM/임베딩/OCR/AWS/Firebase 호출 없음. |
| PUBLIC_DEPLOYMENT_READY | **false** | 알려진 보안 결함과 실공급자/브라우저 전체 흐름/배포 검증이 남음. |

## 수정 파일과 이유

전체 파일 목록은 [phase1-changed-files.md](phase1-changed-files.md). 새 파일과 수정 파일 모두 stage하지 않았다.

| 파일/영역 | 이번 개인 개선 |
|---|---|
| `compose.local.yml`, `.env.example`, `.gitignore`, `AGENTS.md`, `scripts/local/*` | 전용 프로젝트·새 비밀·내부 네트워크·loopback 게이트웨이·새 볼륨·자원 상한, 기동/검증/보존 증거 수집. |
| `be/Dockerfile.local`, `.dockerignore`, `build.gradle` | Java17 build/test/runtime, 테스트 runtime 의존성 사전 다운로드로 내부망에서 offline 기존 테스트 실행. Spring/Gradle 버전 유지. |
| `be/src/main/resources/application.yml`, `application-local.yml` | 기존 Vault 문서를 `!local`에 한정하고 로컬 프로필 분리. 기존 배포 설정 내용/인증 규칙 유지. |
| `be/.../local/*`, `resources/local/lesson.json` | 실제 DB 합성 seed, 외부 storage read-only adapter와 unavailable 경계, local 응답 표시. |
| `be/.../config/{AWSConfig,WebClientConfig}.java`, `file/service/{CloudFrontService,ClovaOcrService}.java`, `fcm/service/FcmService.java` | 기존 외부 bean을 local에서 제외하고 local 경계 bean만 사용. |
| `be/.../material/entity/Material.java` | 운영 소스의 미사용 JUnit import 제거. 기준 코드에서 발견한 컴파일 의존성 결함이며 기준 HEAD 전체 빌드를 그대로 실행한 것은 아님. |
| `be/src/test/...` | 기존 contextLoads 보존+local 프로필; storage 읽기범위/쓰기차단/HTTP 경계 4개 테스트 추가. |
| `ai/Dockerfile.local`, `requirements.local*`, `.dockerignore`, `tests/*` | 없던 local 의존성/전체 freeze lock과 경계/JWT/DB 검증 7개. 대형 모델 미설치. |
| `ai/app/{config,main,local_providers}.py`, `rag/*`, `document_processor/*` | 원래 라우터/DB/태스크 유지. heavy provider 지연 import·local 대역, SQLite 경로 분리, health/대역 표시, local/test guard 및 필수 키 fail-closed. |
| `ai/app/security/auth.py` | 실제 검증 과정에서 JWT/payload/사용자 이름을 로그에 남기지 않도록 출력 제거. 토큰 종류/자료 권한은 후속. |
| `python-service/Dockerfile.local`, `requirements.local*`, `.dockerignore`, `tests/*` | 기존 3.9/heavy Dockerfile 보존, 별도 Python3.11 경량 local 명세·lock. DTO source까지 제외되던 models/ 규칙 예외. |
| `python-service/main.py`, `app/utils/config.py`, `app/routers/pdf_structure.py`, `app/services/{gemini_pdf_parser,local_provider,table_extractor}.py` | 실제 텍스트 PDF 파이프라인 보존, 공급자/다운로드 경계 대역과 lazy import. 중복 서비스 삭제/통합 없음. |
| `fe-web/Dockerfile.local`, `nginx.local.conf`, `vite.config.ts`, `local-env/*`, `package.json`, `.env.example`, `.dockerignore`, `.gitignore`, TS 설정 | phase1에서 기존 env 미로딩·API same-origin 강제, 운영 주소 제거, local proxy/CSP, 빌드 명령 명확화와 typecheck 추가. |
| `fe-web/src/pages/{AdvancedEditor,ChatHistory,StudentRoom,Join}.tsx` | AI 주소를 설정값으로 분리, 로그인 토큰/응답 console 출력 제거. UI 개편 없음. |
| `docs/portfolio/*` | 기준 감사·13개 지적 근거·단계별 완료 조건·실행 문서·실제 결과. |

버전: BE Spring3.5.7/Gradle8.14.3/Java17 요구 유지. 웹 package-lock 유지(호스트 Node22.14.0, 이미지 Node22.22.0 선택). ai는 이전에 추적된 requirements가 없어서 새 local 명세를 만들었고 실제 설치 전이 의존성까지 freeze했다. python-service 기존 `python:3.9-slim` 및 기존 requirements는 그대로 두고 local만 3.11로 분리하여 ARM에서 경량 패키지 설치와 AI 공통 환경을 사용했다. FastAPI0.104.1/Pydantic2.5.0/PyMuPDF1.23.8 등 기존 직접 버전은 유지했다. 실제 이미지 Python3.11.16, Java17.0.20.1, MySQL8.4.11, Redis7.4.11, nginx1.28.0 확인. 베이스 이미지 태그 자체는 digest 고정이 아니므로 향후 새 pull의 패치 버전 차이는 별도 관리가 필요하다.

## 실행 명령·종료 코드·증거

표의 `manage.py` 명령은 루트에서 `python3 scripts/local/manage.py <인자>`로 실행했다. 출력 파일은 Git에서 제외한 `.local/results/`에 있다. 여기에는 민감 원문 대신 검사명/HTTP 코드/개수만 기록했다. Gradle 호스트 로그는 `.local/be-*.log`다.

| 명령 | exit / 상태 | 실제 결과·파일 |
|---|---|---|
| `git status --short --branch`, `git rev-parse HEAD`, `git symbolic-ref refs/remotes/origin/HEAD`, `git remote -v` | 0 / PASS | 루트·remote·main·HEAD·clean 확인. remote 인증정보 여부 마스킹 고려. |
| `git switch -c codex/dodream-phase1-runtime` | 최초128/BLOCKED → 승인 후0/PASS | Git 참조 쓰기 권한 제한 해결. stash/stage/commit 없음. |
| `manage.py init`, `check`, `config` | 0 / PASS | 새 비밀 생성·포트 확인·`compose config --quiet`. `check-*.json`, `compose-config.json`. |
| Java17 `sh be/gradlew -p be --no-daemon compileJava testClasses` | 0 / PASS | `.local/be-compile.log`. 최초 DNS 차단은 승인된 네트워크로 해결. |
| Java17 `... compileJava test --tests '*LocalExternalConfigurationTests'` | 0 / PASS | 4 tests/0 실패/0 오류, `.local/be-unit-tests.log`. 최초 sandbox socket 제한 및 대문자 패키지 test filter 미일치 수정. |
| `cd fe-web && npm ci --ignore-scripts --no-audit --no-fund --cache /private/tmp/dodream-phase1-npm-cache --fetch-retries=0 --fetch-timeout=30000` | 0 / PASS | 승인된 다운로드 302 packages. 앞선 캐시 권한/DNS 시도 exit1/BLOCKED. 자세한 시도는 security-evidence.md. |
| `npm run typecheck`; `npm run build -- --mode phase1` | 각0 / PASS | TS 오류0, 1,767 modules. 대형 chunk 경고 남음. Docker build log에도 실제 같은 빌드 기록. |
| `docker compose ... --progress plain build ai web`; `build be`; `build python-service` | 각0 / PASS | `ai-web-build`, `be-build`, `pdf-build` JSON/log. 최초 직접 의존성 설치 후 freeze lock 생성. |
| `manage.py build`; `docker compose ... --profile test --progress plain build be-test` | 각0 / PASS | `compose-build.*`, `be-test-build.log`. 최종 lock 기반 설치/모듈 포함. |
| `manage.py up` (최초) | 0 / PASS | `first-compose-up.*`. 새 4개 볼륨과 내부 네트워크에서 실제 서버 healthy. |
| `manage.py smoke` (최초) | 1 / BLOCKED | `first-smoke*`: URLError. Docker28 internal 네트워크 단독으로 published port가 비어 있음을 inspect로 확인. 이번 구성에서 발생한 결함. |
| `docker compose ... build web`; `manage.py up` (게이트웨이 수정) | 각0 / PASS | `web-gateway-build.log`, `compose-up.*`. nginx만 gateway 연결, 앱/DB는 내부망 유지. |
| `manage.py test` | 0 / PASS | 실제 Spring context1+경계4=5, AI7, PDF6, 합계18 tests. `be-tests.log`, `ai-tests.log`, `pdf-tests.log`. Spring 결과요약 출력 보완 후 Spring5개 재실행도0. |
| `manage.py smoke` (수정 후) | 0 / PASS | **27/27**, `smoke-checks.json`, `smoke.json`. |
| `manage.py security` | 1 / **FAIL** | 안전정책 **9 FAIL**, 만료시간 관측1 PASS, `security-checks.json`. 취약 동작을 통과라고 표시하지 않음. |
| `manage.py persistence` | 0 / PASS | **7/7**, `persistence-checks.json`. stop/up의 exit도 각각0. |
| 자원/격리/이번 로그 비밀 존재 여부 검사 | 0 / PASS | `resource-isolation-checks.json`; 값·로그 원문 출력 없음. 재실행 명령 `manage.py isolation`. |
| `PYTHONPYCACHEPREFIX=/private/tmp/dodream-phase1-pycache python3 -m compileall ...` 및 `py_compile scripts/local/*.py` | 0 / PASS | 호스트 Python 기본 캐시 경로의 최초 권한 오류 후 writable 전용 캐시로 해결. |
| `git diff --check` | 0 / PASS | 공백/충돌 마커 점검. |
| `manage.py stop`; `isolation`; `status` | 0 / PASS | 검증 종료 후 전용 자원 중지 및 보존 확인. |

초기 차단 원인이 바뀐 경우에만 재시도했다. 같은 실패를 반복하거나 검증 없이 PASS로 바꾸지 않았다. 기준 HEAD 그대로의 전체 테스트는 NOT_RUN이고, 알려진 기존 결함은 정적 근거 또는 별도 보안 재현으로 구분했다.

## 실제 인증·자료·보안 결과

- Spring/FastAPI/독립 PDF/nginx 헬스 HTTP200.
- 합성 교사·학생 로그인200. 잘못된 비밀번호401.
- `/api/teacher/me`, `/users/users/me`의 유효 Access Token200, 무토큰403, 잘못된 토큰401. nginx `/api`, `/ai` 경유도 동일.
- 웹 Origin 헤더를 포함한 `/api/auth/teacher/login` POST200: same-origin Host/포트 보존 확인. 실제 브라우저 전체 클릭 E2E는 NOT_RUN.
- 발행/공유 목록과 합성 JSON200. 실제 Redis/Celery queue에 작업202 → SUCCESS, local provider chat200 및 SQLite 저장. 이 결과는 실임베딩/LLM 품질 확인이 아니다.
- Redis refresh 정상 교체200. HTTP 테스트는 Secure 쿠키를 수동 헤더로 메모리에서만 전달했다. 동시성 안전성은 NOT_RUN.

안전 기대값 위반 재현:

| 검사 | 실제 결과 | 판정 |
|---|---|---|
| Refresh Token을 BE 보호 API Bearer로 사용 | HTTP200 | FAIL |
| Refresh Token을 AI 보호 API Bearer로 사용 | HTTP200 | FAIL |
| Access Token 종류 claim | 구분 claim 없음 | FAIL |
| 학생 퀴즈 조회의 정답 제거 | `correct_answer` 필드 존재 | FAIL |
| 무인증 파일 URL 발급 거부 | HTTP200, 합성 로컬 URL | FAIL |
| 비공유 파일의 학생 URL 발급 거부 | HTTP200, 합성 로컬 URL | FAIL |
| 비공유 document_id의 학생 RAG 거부 | HTTP200, local provider | FAIL |
| 기존 session_id와 다른 document_id 거부 | HTTP200, local provider | FAIL |
| 담당관계 없는 교사의 학생 대화 목록 거부 | HTTP200, 합성 세션2개 | FAIL |

발급 토큰 `exp - iat`는 **86400초**였다. 토큰 원문은 기록하지 않았다. 이 값은 원래 application 설정 및 이를 유지한 local 프로필에서 관측했으며 운영 서버/Vault 실효값을 조사한 것은 아니다.

13개 지적의 정적 원본 줄 번호/영향은 [security-evidence.md](security-evidence.md). 토큰 종류·파일·RAG·정답 노출은 위처럼 접근정책 경계를 재현했다. Redis 경쟁조건, 외부 AI 채점과 DB 트랜잭션/중복 제출, 임베딩 선삭제 실패복구, 운영 URL 리다이렉트/SSRF 공격, 운영 로그 전체는 **추가 검증 필요 / 런타임 NOT_RUN**이다. 실제 공격·운영 사고·비공개 교재 유출을 재현했다고 주장하지 않는다.

JWT 인증 출력·웹 로그인 토큰 출력, local 환경 분리와 실행 명세 일부는 이번에 해소했다. 운영 경로의 공급자 주소/중복 설정·다른 사용자/서명 URL 로그까지 전면 수정한 것은 아니다.

## 자원·보존·최종 상태

처음 실행 중이던 기존 컨테이너18개 및 중지 컨테이너6개, 총24개의 ID/이름/실행 상태를 보존했다. 기존 볼륨·네트워크 이름도 모두 남아 있다. 타 프로젝트 DB·로그·환경·파일 내용을 읽거나 수정하지 않았으며, 기존 서비스를 대상으로 테스트하지 않았다. read-only inventory는 자원 이름/ID/상태/포트에 한정했다.

이번 생성 자원:

- 컨테이너7개: `dodream-phase1-{mysql,redis,be,ai,worker,python-service,web}-1`. 검증 후 **모두 중지**. Spring의 종료143은 `compose stop`의 SIGTERM 종료이며 명령 자체는 exit0이다. 구성 수정 과정의 재생성은 이 프로젝트 신규 컨테이너에만 수행했고 데이터 볼륨은 재사용했다.
- 볼륨4개: `dodream-phase1_mysql-data`, `dodream-phase1_redis-data`, `dodream-phase1_be-data`, `dodream-phase1_ai-data`. **삭제·초기화 없이 유지**.
- 네트워크2개: `dodream-phase1_default`(internal), `dodream-phase1_gateway`(nginx 전용 ingress). 유지.
- 이미지6개: `dodream-phase1-{be,be-test,ai,worker,python-service,web}:latest` 및 필요한 베이스 이미지/빌드 캐시. 유지.
- pip freeze용 `--network none` 일회성 컨테이너2개와 Spring 테스트용 일회성 컨테이너2개는 해당 실행이 끝난 뒤 `--rm`으로 제거. 기존 컨테이너를 제거한 것이 아니다.
- 프로젝트 내 `.local`에 생성 비밀/Gradle cache/검증 결과, `fe-web/node_modules`/`dist`, `be/build`; 전용 임시 npm/Python cache가 남아 있다. 다른 프로젝트 cache/설정은 변경하지 않음.

`.local/env`는 ignore/0600이며 변경 파일에서 생성 비밀값 일치0건을 확인했다. 최종 `git status --porcelain --untracked-files=all`은 기존 파일 수정33개, 신규 미추적38개, stage0개다. 전체 상태는 `.local/results/final-git-status.txt`에 기록했다. 최종 HEAD 동일. **git stage/commit/push/PR/merge/공개 배포 미수행**. 배포·터널·클라우드 자원·과금 요청 없음.

다음 승인된 작업은 로드맵 2단계의 token kind·파일/자료 권한·정답 DTO·RAG 담당관계부터 시작한다. 이번 요청으로 자동 착수하지 않는다.
