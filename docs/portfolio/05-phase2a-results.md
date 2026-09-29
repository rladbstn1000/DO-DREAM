# 05. 2-A 인증 보안 실제 결과

실행일: 2026-09-29 (KST). 저장소 `/Users/yoonsu/Desktop/projects/DO-DREAM`.

## 기준과 로컬 체크포인트

- 작업 시작 브랜치: `codex/dodream-phase1-runtime`, 시작 HEAD: `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`.
- 실제 시작 변경: unstaged 추적33개, 신규38개, staged0개. 이전 보고의 파일 목록과 일치했고, 별도 사용자 변경이나 진행 중 Git 작업은 없었다. 초기화/stash하지 않았다.
- 적용 `AGENTS.md`와 감사/로드맵/runbook/1차 결과/보안 근거 및 실행 스크립트를 읽고, 담당 영역별 전체 diff와 신규 파일을 검토했다. 규칙 원문은 변경하지 않았다. 이번 사용자 요청이 검토한 로컬 stage/commit만 별도 허용한다.
- 실제1차 증거: Spring5 + AI7 + PDF6, smoke27, persistence7 PASS; 보안9 FAIL/exit1. 로그와 XML을 대조했으며 문서의 PASS 표기만 믿지 않았다.
- 최소 재확인: web typecheck, Compose config --quiet, diff check, Java17 compile 및 local boundary4 테스트 모두 exit0.
- 검토된71개 경로만 명시하여 stage하고 파일 hash와 staged blob을 대조했다. 1차 체크포인트: **`8414eec66d7acb5d37794b6f0fcb6f31d3acb48c`**, `chore: establish isolated local runtime and security baseline`.
- 그 다음 새 `codex/dodream-phase2a-auth` 브랜치로 진행했다. 2-A는 인증 검증을 완료했으나 아래 외부 자원 ID 보존 검사 때문에 현재 미커밋이다. 최종 HEAD는 위1차 체크포인트와 같다.

## 변경과 범위

- `JwtUtil`, FastAPI auth/models/config: HS256·canonical Base64 키·동일 issuer/audience·필수 strict claims·AT/RT·jti·수명900/1209600·5초 오차. 레거시 토큰 fallback 없이 재로그인.
- `AuthSessionService`/`RefreshTokenService`/인증 컨트롤러: Redis `refresh:v2:<id>` SHA256, Lua compare-and-rotate/PXAT, 로그인 저장 확인, 401/503 구분, 사용자 단일 세션 logout. 실패한 경쟁 응답은 성공한 쿠키/새 해시를 지우지 않는다.
- `CookieUtil`/`SecurityConfig`/`CsrfController`: Spring CSRF bootstrap/header, HttpOnly/Lax/Path 동일 발급·삭제, 배포 Secure=true와 local HTTP 예외. decoded path로 인코딩 경로도 보호.
- web auth 공통 모듈과 기존 호출부: 요청별 최대1회 재시도, 동시 refresh 하나,403 유지, 늦은 응답/새 로그인/logout 보호, 진행 중 요청 취소 및 재로그인 안내. 기존 localStorage 유지. 설정된 API/RAG origin과 path prefix를 보존한다.
- native 최소 계약: 별도 body RT 경로, 기존 MMKV 저장, refresh/logout 처리, Axios 오류의 원문 body/header 제거. 전체 설치/기기 실행 없이 helper 계약만 검사.
- 전용 auth-test 프로필은 동일 실제 웹/Spring 이미지로 AT2초만 사용한다. 일반 서비스 AT는900초다. 외부 경계 local 대역과 기존 자료 인가 코드는 유지했다.

설계/보장 범위는 [04-auth-security-design.md](04-auth-security-design.md)에 명시했다. 파일/자료/학생/학급 객체 인가, 학생 정답 DTO, RAG 문서·세션·담당관계, AI 트랜잭션/임베딩/SSRF 전체 개편은 하지 않았다.

## 실행 환경과 증거

기존 Docker Desktop/Compose, Java17, Node22.14/npm10.9.2, Python3.11 컨테이너를 사용했다. 실제 Spring/MySQL8.4/Redis7.4/FastAPI/Celery/SQLite, loopback nginx이다. AI/PDF의 실제 외부 LLM/OCR/AWS/Firebase는 호출하지 않았다. 의존성 일괄 업그레이드와 모바일 의존성 설치는 없다.

1차 `.local/results/`와 결과 문서는 그대로 보존했다. 이번 증거는 Git ignored **`.local/phase2a/results/`**이다. `commands.jsonl`과 명령별JSON에 command/exit/time, 시각별 log에 실패를 포함한 시도 이력을 저장한다. `manage.compose(...)`는 `docker compose --env-file .local/env -p dodream-phase1 -f compose.local.yml`의 wrapper이며 비밀값을 명령 출력에 펼치지 않는다.

| 실제 명령 | exit / 최종 결과 | 증거 (이번 results 폴더 기준) |
|---|---|---|
| `python3 scripts/local/manage.py config` | 0 / PASS | compose-config.json/log |
| `manage.compose(..., '--profile','test','--progress','plain','build','be','be-test','web')` 및 후속 수정 build | 0 / PASS | final-verified-build, decoded-route-build.json/log |
| 최종 `build be-test web` | 1 / Docker image export snapshot 오류 (web 성공, Java compile 성공) | final-test-web-build.json/log |
| `build --no-cache be-test` 후 실제 be-test 실행 | 0 / PASS, 최신 Spring53 PASS | be-test-snapshot-recovery-build.json/log |
| `build web` (same-origin guard 수정) + 일반/test 웹 재기동 | 0 / PASS, 두 서버 동일 index SHA256 | web-same-origin-build.json/log, normal-web-final-up.json/log, web-image-consistency.json |
| AI/worker local 이미지 build | 0 / PASS | ai-build.log |
| `python3 scripts/local/manage.py up` | 0 / PASS | compose-up.json/log |
| `python3 scripts/local/manage.py test` + 최종 `be-test` 재실행 | 0 / **Spring53 + AI24 + PDF6 PASS**, skip0 | be-tests/ai-tests/pdf-tests.json/log |
| 최신 AI source readonly mount의 `python -m unittest discover -s tests -v` (`--network none`) | 0 / 24 PASS, 정상서명 길이경계 보강 포함 | ai-contract-unit-signed-size.json/log |
| `cd fe-web && npm run test:auth` | 0 / **25 PASS** (web15/native10) | web-unit.json/log |
| `cd fe-web && npm run typecheck` | 0 / PASS | web-typecheck.json/log |
| `cd fe-web && npm run build -- --mode phase1` | 0 / PASS,1769 modules | web-build.json/log |
| `node fe-web/node_modules/typescript/bin/tsc --noEmit --skipLibCheck --target ES2020 --lib ES2020,DOM fe_app/src/api/nativeTokenSession.ts` | 0 / PASS, helper만 | native-session-typecheck.json/log |
| `python3 scripts/local/manage.py auth` | 0 / **131 PASS** | auth-checks.json, auth-regression.json/log |
| `python3 scripts/local/manage.py startup` | 0 / **6 PASS** | startup-key-checks.json, startup-key-regression.json/log |
| `python3 scripts/local/manage.py smoke` | 0 / **27 PASS** | smoke-checks.json/log |
| `python3 scripts/local/manage.py security` | **1 / 10 PASS,6 FAIL** | security-checks.json/log |
| `python3 scripts/local/manage.py persistence` | 0 / **7 PASS** | persistence-checks.json/log |
| auth-test profile up + `cd fe-web && npm run test:browser-auth` | 0 / **17 PASS** | browser-checks.json 및 시각별 사본 |
| stop + resources-after + isolation | 1 /14 PASS·2 FAIL (외부6개 ID 교체) | resource-isolation-checks.json |
| `git diff --check` 및 전체 파일/hash 검토 | 0 / PASS; 2-A staged 검사는 NOT_RUN (stage 보류) | .local/phase2a/ 검토 기록 |

Spring53은 기존 context1+경계4, JWT35, cookie/Redis error2, encoded routing8, 실제 Redis integration3이다. AI24는 기존7+인증17, PDF6은 기존 테스트다. Web/native는 synthetic transport 단위 테스트이며 아래 Chrome의 실제 서버 흐름과 구분한다. 대형 JS chunk 경고는 기존 경고로 남는다.

## 인증 실제 검증과 발견한 문제

- 양 서버 정상 AT200/RT401, AT로refresh401, 잘못된 종류·서명·alg·iss/aud·기간·필수 claim 누락/형식 거부. 기존 형식은 거부한다. 실제 발급 AT900초/RT1209600초, 같은초의 연속RT 고유성, Redis TTL과 RT exp 정합성을 확인했다.
- 독립 HTTP 클라이언트12개가 barrier로 동시에 같은RT를 보낸3라운드 모두 **200 한 개/401 열한 개**. 실패한11개 응답은 Set-Cookie를 변경하지 않고 승자 해시도 보존한다. 별도 Lettuce connection factory2개를 쓰는 실제 Redis 통합 검사도3라운드 수행했다.
- logout/refresh 경쟁3라운드 후 세션 없음/기존RT 재사용401. 정상 logout 후 RT 폐기와 기존 AT200을 각각 확인했다. AT 즉시 폐기를 구현했다고 주장하지 않는다.
- 전용 Redis만 stop→login/refresh/logout 모두503·성공토큰 없음·쿠키 변이 없음. 잘못된 비밀번호401. finally에서 Redis 복구 후 logout200. 원자 회전 성공응답을 버린 상황을 시뮬레이션하면 이전RT는401이며 재로그인이 필요하다.
- 필수 키 빈값/잘못된Base64/짧은키로 BE/AI 총6회 실제 기동 exit1, 정확한 key 오류 marker 확인. 각 고유명 일회성 컨테이너가 제거되었는지도 확인했다. 키/원문 로그는 저장하지 않았다.
- 처음 새 CSRF matcher의 raw URI 비교는 encoded refresh/logout에서 CSRF 없는200을 허용했다. decoded servlet path로 고쳤고6개 역할/동작 경로는403, 유효 CSRF encoded refresh는200으로 재검증했다. 첫 실패 로그(11:40:52 UTC 시작)는 보존한다.
- 실제 Chrome에서 빈 `VITE_API_BASE`를 미설정으로 판단한 기존 화면 guard 때문에 same-origin 보호 API 호출이0인 문제가 드러났다. 빈base를 유효한 same-origin으로 처리하고 최초 보호 API200·실제 요청 도달 assertion을 보강했다. 토큰만 존재하는 화면을 API 성공으로 간주하지 않으며 첫 브라우저FAIL을 보존한다.
- 처음 smoke는 같은 교사로 두 번째 웹로그인 뒤 첫 RT를 사용해401이었다. 이전에는 같은초 토큰이 같아 가려진 입력 문제다. 두 번째 응답의 현재RT로 검사하도록 수정했고 기존27개 기대값은 유지했다. 첫 실패(11:39:42 UTC 시작)를 보존한다.
- 약12KB signed token은 nginx 헤더 상한에서400이었다. 처음401 고정 기대는 validator에 도달한다고 가정한 검사 오류였다. 최종 `token_oversized_be/ai`는 정확한 nginx400/토큰 미반환을 요구하며, 양 서버 단위검사에는 정상 서명/필수claim의8192자 초과 JWT 직접 거부를 보강했다. AI의 길이 이내 동일조건 양성대조도200이다. 넓은400/401 허용이나 보호 완화로 통과시키지 않았다.
- 최종 be-test 이미지 export 중 Docker `parent snapshot does not exist`가 발생했다. 기존 자원/캐시 삭제 없이 해당 이미지 하나를 `--no-cache`로 다시 빌드하고 실제 테스트로 확인했다. 최초 실패를 숨기지 않고 별도 log로 보존한다.
- 독립 리뷰에서 늦은 재시도401이 더새AT를 지우는 경우와 native Axios 오류가RT body를 로그로 전파하는 경우를 발견하고 수정·회귀를 추가했다. API/RAG base prefix 지원도 보호 범위 안에서 유지했다.

## 기존9개 보안 기준선

식별자와 안전 기대값은 [security-evidence.md](security-evidence.md)의 2-A 표에 모두 보존했다. **인증3개 FAIL→PASS, 객체권한6개 FAIL→FAIL**이다. 교사·학생·비담당 교사 각각 새 로그인 후 Spring/AI 양성대조6개는200이었다. 보조 수명 관측900초까지 포함해 security 명령은 총16개(10PASS/6FAIL), exit1이며 전체 보안통과가 아니다.

## 실제 브라우저와 모바일 경계

첫 Chrome 시작은 샌드박스 실행 제한으로 assertion0개/BLOCKED였으며 시각별 증거를 보존했다. 승인된 로컬 Chrome 실행 권한으로 별도 임시 프로필에서 재실행했다. 사용자 브라우저 프로필을 열거나 기존 탭을 변경하지 않았다.

Chrome 154.0.8037.58의 별도 headless 프로필에서 `http://127.0.0.1:15174`에 접속했다. CSP를 유지했고 17개 PASS / exit0이다. 초기 로그인 뒤 실제 보호 API 200 응답 3개를 확인했다. 자연 만료(AT 2초 + skew 5초 후 8초 대기) 뒤 동시 401이 2개 발생했고, refresh는 정확히 1회, 보호 API들은 다시 200이었다. 유효 CSRF·쿠키·만료 AT를 함께 보낸 refresh 200, RT의 JS 비노출과 발급·전달·삭제를 실제 브라우저에서 확인했다.

지연 401은 실제 서버 응답의 브라우저 전달을 늦췄다. logout/refresh 경쟁도 실제 refresh 성공 후 응답 전달을 지연시켜 UI와 서버 세션이 복원되지 않는지 검사했다. 403/503 분기는 브라우저 transport 응답 주입이며, 실제 권한 오류/Redis 장애 실험과 구분한다. Redis 503의 실제 서버 증거는 별도 auth suite에 있다. 주입 항목을 결과에 명시했고 원시 body/토큰/쿠키·trace/HAR/screenshot은 저장하지 않았다. 외부 요청 관측은 0이며 프로젝트의 외부 AI/운영 서버를 호출하지 않았다. 이 결과는 전체 학습 E2E나 모든 화면 기능 검증을 뜻하지 않는다.

native는 helper10개, 단독 TypeScript 검사, 실제 API의 명시적AT/RT login/rotate/reuse/logout 검증을 수행했다. React Native 전체 설치/빌드·시뮬레이터·실기기·생체인증·OS보안저장소·FCM은 **NOT_RUN**이다. MMKV/localStorage의 탈취 위험, 탭 간 refresh coordination, production HTTPS/SameSite 배포 통합 검증은 남는다.

## 자원·비밀정보와 최종 상태

시작 시 이 프로젝트의 7개 컨테이너는 모두 exited였다. 검증 후 원래 7개를 exited로 복원했고 추가 auth-test 2개도 exited다. 전용 볼륨 4개와 네트워크 2개를 포함한 모든 기존 볼륨·네트워크 이름을 보존했으며 새 볼륨/네트워크는 0개다. MySQL 도메인 수·probe, Redis probe, SQLite 기존 session·대역 인덱스의 재시작 보존 검사 7개가 PASS다. 전용 서비스 전체 로그에서 JWT 및 생성된 secret은 관측되지 않았다. 삭제/초기화/prune/FLUSH를 사용하지 않았다.

다만 엄격한 외부 컨테이너 ID 보존 검사는 FAIL이다. 시작 외부 33개 중 27개 ID는 그대로이고, `etch-phase6-rc-{backend,elasticsearch,mysql}-1` 및 `etch-phase6-rc-verify-{logstash,backend,elasticsearch}-1`의 6개 ID가 같은 이름의 새 ID로 바뀌었다. 이름과 실행/중지 상태는 33개 모두 시작과 같다. 이번 작업의 변경 명령은 `dodream-phase1`과 고유명이 붙은 자체 일회성 검사 컨테이너만 대상으로 했고 ETCH 변경 명령은 없다. 재생성 주체는 이 검사만으로 확정할 수 없다. 다른 프로젝트를 임의로 복원/재시작하지 않고 사용자에게 동시 ETCH 작업 여부를 확인 요청했다. 검사 기대값이나 원본 snapshot을 바꿔 PASS로 만들지 않았다.

**2-A local commit은 현재 보류**한다. 인증 기능 검사는 모두 통과했지만, 사용자 요청의 “검증 실패·차단이 남으면 변경을 보존하고 미커밋 상태와 이유 보고” 조건에 따라 외부 자원 보존 FAIL의 출처가 확인되기 전에는 stage/commit하지 않는다. 현재 HEAD는 1차 체크포인트이며 2-A 소스·테스트·문서는 작업 트리에 보존한다. 최종 Git 상태는 추적 수정33개, 신규 파일21개, staged0개다. 전체54개 파일 목록은 아래에 있으며 `.local/phase2a/final-git-status.txt`와 `final-review.json`에 상세 상태를 저장했다.

1차 변경과2-A 변경 각각의 전체 파일 내용·환경 활성화·명세·로그를 검토했다. 변경 파일에 private-key marker/JWT literal/AWS key/credential URL 패턴, 생성된 로컬 secret 값의 포함 여부,1MiB 초과 파일을 검사했다. 1차의2개 후보는 기존PEM marker parser문자열과환경변수URL placeholder였고 실제키가 아니었다. 2-A 최종 후보/큰파일은없다. `.local/env`는ignored/0600이며 기존 `.env`는열거나변경하지 않았다. 빌드/cache/DB/volume/원문로그는커밋하지 않는다. 이것은 변경파일과이번실행로그검사이지 저장소전체·이력·외부의존성의비밀/취약점부재 보장이 아니다.

| 상태 | 결과 |
|---|---|
| PHASE1_CHECKPOINT | PASS |
| BUILD | PASS |
| LOCAL_RUNTIME | PASS |
| AUTH_TOKEN_CONTRACT | PASS |
| REFRESH_ROTATION_ATOMICITY | PASS (정상 단일Redis, 독립 클라이언트) |
| REFRESH_FAILURE_HANDLING | PASS |
| AUTH_BROWSER_FLOW | PASS (Chrome 실제 서버 인증 흐름) |
| COOKIE_CSRF | PASS (local실제검증, production속성unit) |
| SECURITY_REGRESSION_ALL | **FAIL** (2-B6개) |
| RESTART_PERSISTENCE | PASS |
| REAL_AI_INTEGRATION | **NOT_RUN** |
| PUBLIC_DEPLOYMENT_READY | **false** |

1차 `SECURITY_BASELINE=FAIL`은 과거 결과로 보존한다. 다음2-B는 익명/비공유 파일 접근, 학생정답DTO, RAG 자료·세션·담당관계 순서로 별도 승인 후 진행한다. 실제AI, 배포HTTPS·운영secret·rate limit·관측/백업·비용검증도 남는다. push/PR/merge/remote변경/이력재작성/공개배포/터널을 수행하지 않았다.

## 검토된2-A 파일 목록

- `ai/app/config.py`
- `ai/app/security/auth.py`
- `ai/app/security/models.py`
- `ai/tests/runtime_fixture.py`
- `ai/tests/test_auth_contract.py`
- `ai/tests/test_local_runtime.py`
- `be/src/main/java/A704/DODREAM/auth/controller/CsrfController.java`
- `be/src/main/java/A704/DODREAM/auth/controller/StudentAuthController.java`
- `be/src/main/java/A704/DODREAM/auth/controller/TeacherAuthController.java`
- `be/src/main/java/A704/DODREAM/auth/exception/AuthException.java`
- `be/src/main/java/A704/DODREAM/auth/exception/AuthExceptionHandler.java`
- `be/src/main/java/A704/DODREAM/auth/filter/JwtAuthFilter.java`
- `be/src/main/java/A704/DODREAM/auth/service/AuthSessionService.java`
- `be/src/main/java/A704/DODREAM/auth/service/RefreshTokenService.java`
- `be/src/main/java/A704/DODREAM/auth/util/CookieUtil.java`
- `be/src/main/java/A704/DODREAM/auth/util/JwtUtil.java`
- `be/src/main/java/A704/DODREAM/config/SecurityConfig.java`
- `be/src/main/resources/application-local.yml`
- `be/src/main/resources/application.yml`
- `be/src/test/java/A704/DODREAM/auth/AuthFailureAndCookieTests.java`
- `be/src/test/java/A704/DODREAM/auth/AuthRoutingTests.java`
- `be/src/test/java/A704/DODREAM/auth/JwtContractTests.java`
- `be/src/test/java/A704/DODREAM/auth/RefreshTokenRedisTests.java`
- `compose.local.yml`
- `docs/portfolio/01-roadmap.md`
- `docs/portfolio/02-local-runbook.md`
- `docs/portfolio/04-auth-security-design.md`
- `docs/portfolio/05-phase2a-results.md`
- `docs/portfolio/security-evidence.md`
- `fe-web/package.json`
- `fe-web/src/App.tsx`
- `fe-web/src/auth/client.ts`
- `fe-web/src/auth/session.ts`
- `fe-web/src/pages/AdvancedEditor.tsx`
- `fe-web/src/pages/ChatHistory.tsx`
- `fe-web/src/pages/Classroom.tsx`
- `fe-web/src/pages/ClassroomList.tsx`
- `fe-web/src/pages/Join.tsx`
- `fe-web/src/pages/StudentRoom.tsx`
- `fe-web/tests/auth-session.test.ts`
- `fe-web/tests/browser-auth.mjs`
- `fe-web/tests/native-contract.test.ts`
- `fe_app/src/api/authApi.ts`
- `fe_app/src/api/interceptors.ts`
- `fe_app/src/api/nativeTokenSession.ts`
- `fe_app/src/services/authStorage.ts`
- `fe_app/src/stores/authStore.ts`
- `fe_app/src/types/api/authApiTypes.ts`
- `scripts/local/check_resources.py`
- `scripts/local/manage.py`
- `scripts/local/nginx.auth-test.conf`
- `scripts/local/verify.py`
- `scripts/local/verify_auth.py`
- `scripts/local/verify_startup.py`


## 후속 결정: 원인 미확인을 보존한 2-A 로컬 체크포인트

후속 사용자 요청은 과거 ETCH ID 변화의 원인 미확인을 명시한 2-A 체크포인트를 허용했다. 위의 과거 커밋 보류 기록, isolation FAIL과 원본 snapshot은 그대로 보존한다. 이를 PASS로 소급하지 않으며 변경 주체를 다른 작업으로 단정하지 않는다.

현재 54개 2-A 파일의 SHA256와 크기는 `.local/phase2a/phase2-inventory.json`과 모두 일치했다. BE17개, AI6개, web/native19개는 영역별 독립 검토에서 최종 실행 증거(53/24/25 및 Chrome17)와 대조했다. 나머지 실행 스크립트·Compose·문서도 검토했다. 이후 추가된 `docs/.DS_Store`는 출처가 구분되는 비코드 파일로 보존하고 커밋에서 제외한다. 이 후속 결정 문단을 추가했다. staged diff 검사에서 발견한 `nginx.auth-test.conf` 끝의 빈 줄 하나도 제거했다. nginx 지시문과 기존 기능 소스는 변경하지 않았다.

과거 기록에서는 ETCH6개가 같은 이름·상태의 새 ID로 바뀌었으므로 `HISTORICAL_EXTERNAL_ID_STABILITY=FAIL`, `EXTERNAL_CHANGE_ATTRIBUTION=UNVERIFIED`다. 이번 제한된 metadata 및 since/until 이벤트 조회는 Docker 데몬 연결 불가로 BLOCKED였다. 이벤트가 없었다고 판단한 것이 아니다. 다른 프로젝트의 Env·명령 인자·로그·파일·셸 이력·다른 대화를 조사하지 않았다.

현재 Docker 연결 불가는 이미 검증한 동일 소스의 2-A 체크포인트를 무효로 하지 않는다. 후속 실행 전에는 별도 before snapshot과 프로젝트 라벨·서비스 허용 목록·마운트/이미지/네트워크의 대상 범위 검증을 반드시 수행한다. 그 전에는 Docker 변경을 실행하지 않는다. 원인 미확인과 기존 2-B 보안 실패6개를 보존한 상태로 검토된54개 경로만 stage하고 staged diff/hash를 확인하여 로컬 체크포인트를 생성한다. 정확한 SHA는 후속 결과 문서와 최종 보고에 기록한다.
