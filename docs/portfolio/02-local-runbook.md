# 02. 격리 로컬 실행

아래에서 서버 없는 showcase와 실제 백엔드 통합 실행을 구분한다. phase1 통합 구성은 저장소 루트에서 실행하며 공개 배포용이 아니다. 팀의 기존 배포 설정과 비밀 파일을 재사용하지 않는다.

## 서버 없는 공개 샘플 체험 (showcase)

[공개 샘플 체험](https://rladbstn1000.github.io/DO-DREAM/)은 Docker·DB·계정·API 키 없이 사용할 수 있다. 기존 로컬 통합 실행과 다른 진입점이며, 실제 인증·저장·RAG·공급자 호출을 대신 검증하는 경로가 아니다. 구현과 로컬 인수 증거는 [19 결과](19-static-showcase-results.md), 원격 CI·배포·공개 접속 검증은 [20 결과](20-publication-and-pages-results.md)에 기록한다.

로컬 재현은 저장소 루트에서 시작한다.

```bash
cd fe-web
# 의존성이 없는 환경에서만, 기존 lock 기준 설치
npm ci --ignore-scripts --no-audit --no-fund
npm run build:showcase
npm run preview:showcase
# 별도 터미널에서 단일 인수 실행
npm run verify:showcase
```

호스트 Node 22 계열과 독립 테스트용 Chrome이 필요하다. 검증 시 호스트 Node는 22.14.0, 기존 CI 고정값은 22.22.0이다. 테스트 도구는 같은 lock의 `playwright-core`를 사용하며 브라우저나 모델을 자동 설치하지 않는다. 브라우저 검사는 Playwright의 `chrome` 채널에서 찾는 기본 설치 Chrome을 사용한다. 사용자 프로필이나 기존 탭을 사용하지 않는다.

`preview:showcase`는 `127.0.0.1`의 빈 포트를 골라 주소를 출력한다. 같은 `dist-showcase/`를 `/`와 `/DO-DREAM/`에서 제공하며 API proxy·SPA rewrite는 없다. 예: 출력 주소 뒤 `DO-DREAM/#/learn/water-journey?section=water-2`. 종료는 해당 터미널의 Ctrl+C이며 공개 운영용 서버가 아니다. 이 절차는 기존 백엔드 서비스를 시작하거나 종료하지 않는다.

`verify:showcase`는 타입·showcase 계약·합성 환경값 빌드·기존 phase1 빌드·모듈/산출물 검사·정적 서버 경계·독립 브라우저 인수를 한 실행으로 묶는다. `.local/static-showcase/results/`에 실행별 증거를 남기고 실행 중 소스·산출물 불변을 확인한다. 단독 명령은 `test:showcase`, `test:showcase-browser`다. 기존 auth/authorization/grading/indexing/student/hardening 단위 검사는 별도로 유지한다.

공개 배포는 검증한 `fe-web/dist-showcase/`만 게시하는 [수동 Pages workflow](../../.github/workflows/showcase-pages.yml)를 사용한다. 원격 산출물 대조·공개 인수·재배포 절차는 [20 결과](20-publication-and-pages-results.md)를 따른다.

학생 화면의 **데모 초기화**는 `dodream.showcase.v1.state`만 제거한다. 다른 저장소 키를 지우지 않는다. 기록은 같은 탭의 임시 상태이고 실제 로그인·권한·서버 동기화가 아니다. 저장소 오류 시 제한을 안내하며 메모리로 체험한다.

## 실제 백엔드 로컬 통합 실행 (phase1)

아래 4~5단계의 미배포·미실행 판정은 당시 실행 기록이며, 현재 공개된 정적 showcase의 배포 결과와 구분한다.

이하 절차는 키 없는 `LOCAL_FAKE`와 실제 자체 백엔드/DB를 사용한다. 실제 AI 호출·모델 평가·비용 측정은 현재 완료 조건이 아니며 `REAL_AI_INTEGRATION=NOT_RUN`이다. 공급자 adapter·오프라인 계약·평가셋과 과거 재개 절차를 보존한다. 키 탐색·읽기·설정·live 활성화는 이번 showcase 작업에서 수행하지 않았다. live 오류를 대역 성공으로 숨기거나 키 존재로 자동 전환하지 않는다.

18번 리뷰 증거는 `.local/portfolio-hardening/results`에 보존한다. showcase 작업의 증거는 별도 경로이며 DB·Docker·기존 서비스에 접근하지 않았다(`BACKEND_DATA=NOT_TOUCHED`). 이전 방문자 카운터 strict FAIL과 별도 대조 PASS는 [18 코드 리뷰](18-portfolio-code-review.md)의 당시 판정 그대로다.

## 준비와 첫 기동

호스트 필수: Docker Desktop/Compose v2, Python3. Node/Java를 호스트에 추가 설치할 필요는 없다. 이미지 안에서 Java17/Node22/Python3.11을 사용한다. 최초 빌드에는 명세의 공개 의존성/이미지 다운로드가 필요하다. 전역 설치, sudo, 모델 다운로드는 하지 않는다.

```bash
cd /Users/yoonsu/Desktop/projects/DO-DREAM
python3 scripts/local/manage.py init
python3 scripts/local/manage.py check
python3 scripts/local/manage.py config
python3 scripts/local/manage.py build
python3 scripts/local/manage.py data-up
python3 scripts/local/manage.py grading-migrate
python3 scripts/local/manage.py indexing-migrate
python3 scripts/local/manage.py up
python3 scripts/local/manage.py status
```

`init`은 `.local/env`를 없을 때만 새로 만들고 0600 권한을 설정한다. 기존 파일을 덮어쓰지 않는다. `.env.example`은 변수 설명용이고 실제 비밀이 없다. `.local/env`는 Git에서 제외된다. 기존 `.env`, Vault 설정, 사용자 자격증명을 읽어오지 않는다. wrapper는 지정 파일과 전용 프로젝트 이름을 강제하고 같은 이름의 shell/Compose 변수 간섭을 제거한다.

`data-up`은 자체 MySQL·Redis·Chroma만 시작한다. 새 DB에서 V003/V004를 Spring보다 먼저 적용하기 위한 순서다. `grading-migrate`/`indexing-migrate`는 기존 데이터를 삭제하지 않는 전진 SQL이며 재실행 안정성을 검사한다. JPA는 나머지 팀 도메인을 `ddl-auto=update`로 만들고 schema guard가 필수 제약을 확인한다. 이미 적용한 기존 볼륨의 평소 재시작에는 `up`만 사용한다. 빈 환경 검사는 기존 볼륨 검사와 별개이며 [18 리뷰](18-portfolio-code-review.md)의 전용 새 schema 절차를 따른다.

`check`에서 포트 충돌이 나면 `.local/env`의 `*_PORT`를 비어 있는 번호로 변경한 뒤 실행한다. 기존 프로세스를 종료하지 않는다. 표준 frontend는 same-origin이므로 web 포트 변경을 자동으로 따른다. 선택적인 Vite 개발 프록시의 backend 포트를 변경했다면 `vite.config.ts`도 맞춰야 한다.

## 접속과 계정

| 대상 | 주소 |
|---|---|
| 교사 웹 | `http://127.0.0.1:15173` |
| Spring | `http://127.0.0.1:18082/actuator/health` |
| AI FastAPI | `http://127.0.0.1:18000/health` |
| 독립 PDF FastAPI | `http://127.0.0.1:18001/health` |

4개 loopback 포트는 **nginx만** 게시한다. `/api`는 실제 Spring, `/ai`는 실제 AI FastAPI로 전달한다. 직접 API 포트도 고정 upstream으로 프록시한다. Spring·AI·worker·PDF·MySQL·Redis는 인터넷 연결이 없는 `dodream-phase1_default` 내부 네트워크에만 연결한다. nginx는 추가로 `dodream-phase1_gateway`를 사용한다. nginx는 임의 URL을 전달하는 프록시가 아니다. Docker28 내부망 단독 구성에서는 호스트 포트가 게시되지 않아 이 구조를 사용한다.

- 교사: `teacher@local.dodream.invalid`
- 담당관계 없는 교사: `other-teacher@local.dodream.invalid`
- 두 교사 비밀번호: `.local/env`의 `LOCAL_TEACHER_PASSWORD` 값. 출력·문서·Git에 복사하지 않는다. 필요하면 로컬 편집기에서 사용자 본인이 확인한다.
- 학생 로그인 API: `deviceId=dodream-local-student`, `deviceSecret=LOCAL_STUDENT_SECRET` 값. 실제 기기 생체인증/모바일 빌드를 의미하지 않는다.
- 합성 교실 1개, 교사 2명, 학생 1명, 자료/퀴즈 각 2개. 자료 하나만 학생에게 공유한다. 고정 ID를 외부 데이터에 가정하지 말고 목록 API로 조회한다.

1차에서는 Secure 쿠키를 스크립트가 메모리에서 전달했다. 2-A부터 local/test HTTP만 Secure=false이고 배포 기본은 Secure=true다. Refresh 쿠키는 HttpOnly/SameSite=Lax/Path=/api/auth이며 웹 body에 RT를 반환하지 않는다. 이전 형식 토큰은 재로그인이 필요하다. 기존 Redis 키를 지우지 말고 새 로그인으로 v2 세션을 만든다. 쿠키 login/refresh/logout POST 전 `/api/auth/csrf`를 호출하고 응답 token을 `X-XSRF-TOKEN`에 넣는다. native 전용 계약은 [04 설계](04-auth-security-design.md)를 따른다.

## 검증

```bash
python3 scripts/local/manage.py test
python3 scripts/local/manage.py auth
python3 scripts/local/manage.py startup
python3 scripts/local/manage.py smoke
python3 scripts/local/manage.py security
python3 scripts/local/manage.py persistence
python3 scripts/local/manage.py isolation
```

- `test`: 보존한 Spring `contextLoads`와 인증·권한·채점·색인·입력 경계 회귀, AI/PDF 회귀를 실행한다. 단계별로 누적된 검사 수와 이번 실제 결과는 [18 리뷰](18-portfolio-code-review.md)를 따른다. Spring 테스트는 실제 MySQL/Redis, Python 단위테스트는 별도 임시 SQLite와 원래 JWT 인증을 사용한다. 실제 공유 MySQL 연결은 smoke/health에서 확인한다. 테스트용 Spring 컨테이너만 일회성으로 생성/종료/제거한다.
- `auth`: 실제 Spring/FastAPI JWT 계약, 실제 Redis 회전·12개 독립 HTTP 클라이언트 동시성·logout 경쟁, CSRF/cookie/native 계약. 합성 계정/키만 사용한다. 마지막에는 전용 Redis만 잠시 중지해 503 오류를 검사하고 finally에서 시작한다. 다른 테스트와 동시에 실행하지 않는다.
- `startup`: 별도 일회성 컨테이너에서 빈/오류/짧은 키의 실제 기동 실패 검사. 원문 로그/키를 저장하지 않는다.
- `smoke`: 헬스, 합성 로그인, 웹 Origin/CORS, 정상·무토큰·위조토큰, 자료, 실제 Celery queue, 대역 채팅/SQLite, Redis refresh 흐름.
- `security`: 역할별 새 로그인과 양성 대조군 뒤 인증·현재 객체권한의 안전 기대값을 확인한다. 1차와 2-A 당시의 객체권한 FAIL은 과거 기록으로 보존하며, 현재 코드는 2-B에서 수정한 정책을 검사한다. 이 묶음의 PASS가 모든 보안 영역의 완전성을 뜻하지 않는다. 실제 외부 파일/AI에 요청하지 않는다.
- `persistence`: MySQL 전용 probe table과 Redis probe key를 생성하고 검증한 자체 컨테이너만 stop/start한다. 현재 자료와 활성 원본이 일치하는 새 대화 세션을 실제 API로 만들고, 같은 컨테이너 ID·이미지, marker, SQLite 연결·대화, MySQL 활성 포인터, 실제 Chroma 내용의 재시작 보존을 확인한다. 먼저 smoke와 현재 공유 자료의 색인 완료가 필요하다. 검증 전제가 충족되지 않으면 원인을 기록하고 재시작을 진행하지 않는다.

1차 증거는 `.local/results/`에 보존한다. 2-A 당시 명령/종료코드와 민감값을 제거한 출력은 `.local/phase2a/results/`에 보존한다. 현재 wrapper 기본값은 `.local/phase5/results/`이며 이번에는 위 override를 사용한다. `DODREAM_RESULTS_DIR`로 이후 검증의 새 증거 폴더를 지정할 수 있다. 새 폴더에서는 시작 전 `resources-before`를 기록해야 isolation 비교가 가능하다. `commands.jsonl`은 기록 기능 도입 이후 실행 이력이고, 이전 시도는 별도 JSON/log와 결과 문서에 보존했다. 테스트 HTTP body·토큰·cookie는 저장하지 않는다. 일반 `docker compose config`는 비밀을 펼치므로 출력하지 말고 wrapper의 `config --quiet`를 쓴다. 원문 컨테이너 로그를 공유하지 않는다.

호스트 웹 검증(선택):

```bash
cd fe-web
npm ci --ignore-scripts --no-audit --no-fund --cache /private/tmp/dodream-phase1-npm-cache
npm run typecheck
npm run build -- --mode phase1
```

실제 Chrome 인증 검증은 `python3 scripts/local/manage.py auth-test-up` 후 `cd fe-web && npm run test:browser-auth`를 실행한다. 기존 Chrome과 Playwright가 필요하며 harness 상단의 경로/환경변수 설정을 확인한다. 별도 테스트 서버만 AT2초이며 일반 서버는900초다. 15174 포트를 다른 프로세스가 쓰면 종료하지 말고 테스트 profile 포트를 바꾼다. 이 테스트는 인증 흐름이며 전체 학습 E2E가 아니다. 장애 주입 항목은 실제 happy path와 결과에서 구분한다.

`phase1`은 `local-env`만 읽고 API base를 same-origin으로 고정한다. 빌드 mode를 생략한 기존 배포 명령과 구분한다. 로컬 CSP는 원격 폰트/이미지/API를 차단한다.

## 종료·재시작·데이터 위치

```bash
python3 scripts/local/manage.py stop
python3 scripts/local/manage.py up
# 실행 중인 이번 프로젝트만 재시작할 경우
python3 scripts/local/manage.py restart
```

`stop`은 기본 서비스와 auth-test 프로필의 컨테이너만 멈추며 볼륨·네트워크·이미지를 삭제하지 않는다. `up`은 같은 데이터로 시작한다. **down -v/prune/reset/clean/기존 자원 삭제를 사용하지 않는다.**

| 볼륨 | 컨테이너 위치 / 내용 |
|---|---|
| `dodream-phase1_mysql-data` | `/var/lib/mysql`: 새 `dodream_local` DB, 합성 도메인, persistence probe |
| `dodream-phase1_redis-data` | `/data`: AOF, refresh·Celery·probe |
| `dodream-phase1_ai-data` | `/app/db_data`: `rag.db` SQLite, `local_provider` 대역 인덱스 |
| `dodream-phase1_be-data` | `/app/local-data`: 로컬 upload/temp 경로 (외부 업로드 비활성) |
| `dodream-phase1_chroma-data` | `/chroma/chroma`: 검증 후보와 활성 검색 컬렉션 |

새 local DB는 위 현행 초기화 절차의 V003/V004를 먼저 적용하고 JPA `ddl-auto=update`로 나머지 팀 도메인을 만든다. AI SQLite는 `create_all`과 명시적 additive 확장을 사용한다. seed는 하나의 트랜잭션에서 최초 한 번 생성하며 교사 fixture가 존재하면 수정·비밀번호 재설정 없이 종료한다. seed가 이미 있다고 새 필드를 자동으로 덮어쓰지 않는다. 이후 추가된 채점·색인 스키마는 버전 관리 SQL을 적용한다. 환경 파일의 비밀번호만 바꾸면 기존 DB 사용자나 합성 계정 비밀번호가 자동 변경되지 않는다. 초기화나 볼륨 삭제로 우회하지 말고 별도 데이터 관리 작업으로 처리한다.

CPU/메모리 상한을 지정했다. 기본 서비스 9개 컨테이너 합계 메모리 상한 4GiB, 테스트 컨테이너는 일시 1.25GiB 추가다. 별도 auth-test 프로필의 2개는 이 합계에 포함하지 않는다. 검증 종료 뒤 전용 컨테이너는 중지하여 다른 작업의 자원을 돌려준다.

## 외부 경계와 미지원 기능

| 영역 | local 동작 | 실제 수행 여부 |
|---|---|---|
| 인증·Spring/JPA·MySQL·Redis·FastAPI·Celery·SQLite | 원래 서비스/로직, 새 합성 계정/DB | 실제 수행 |
| 파일 저장소/서명 | 합성 JSON read-only adapter, 인증된 local fixture URL | AWS/CloudFront 호출 안 함 |
| 업로드·발행·OCR·FCM | 명시적 503/disabled 또는 알림 실패 표시 | 실제 외부 호출 안 함 |
| AI PDF/LLM/임베딩/퀴즈 | 예약 fixture URL만 허용, 결정적 local provider | 실제 모델/공급자 호출 안 함 |
| 독립 PDF 텍스트 레이어 | 생성한 공개 합성 PDF를 PyMuPDF·읽기순서·TipTap으로 처리 | 실제 파서 수행; Gemini/OCR는 대역/미사용 |

AI/PDF 응답에는 `X-DO-DREAM-External-Provider: local_stub`, Spring에는 `X-DO-DREAM-Mode`가 있다. AI 본문에도 LOCAL STUB를 표시한다. 전역 permitAll 확대나 무조건 성공 응답으로 검증을 통과시키지 않는다.

## 변수 이름

루트 생성 파일: `COMPOSE_PROJECT_NAME`, `BE_PORT`, `AI_PORT`, `PDF_PORT`, `WEB_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `JWT_SECRET_BASE64`, `LOCAL_TEACHER_PASSWORD`, `LOCAL_STUDENT_SECRET`.

Compose가 local 전용으로 주입: `SPRING_PROFILES_ACTIVE`, `JWT_SECRET`(공유 JWT 변수 매핑), `AI_BASE_URL`, `JAVA_TOOL_OPTIONS`, `APP_ENV`, `LOCAL_EXTERNAL_STUBS`, `DATABASE_URL`, `JWT_ISSUER`, `CELERY_BROKER_URL`, `RAG_DATABASE_URL`, `LOCAL_PROVIDER_DATA_DIR`, `ENVIRONMENT`, `DEBUG`. 외부 공급자 키는 주입하지 않는다. local/test가 아닌 환경에서 대역 사용 또는 필수 키 누락은 실패하도록 한다.

## 2-B 이후 실행과 검증

2-B 당시 증거 기본 경로는 `.local/phase2b/results/`였다. 위 1차/2-A 설명과 원본 결과는 당시 상태이며, 2-B 결과는 [08](08-phase2b-results.md)를 따른다. 새 단계용 폴더에서는 먼저 `resources-before`, `scope`를 실행한다. 최초 snapshot은 덮어쓰지 않는다. `scope-test`는 Docker 없이 합성 명령/metadata를 검사한다. 실제 자원 변경은 고정 Compose/project/directory와 라벨·서비스·볼륨·마운트·이미지·네트워크 검사를 통과해야 한다. 검사 실패 시 우회 실행하지 않는다.

```bash
python3 scripts/local/manage.py resources-before
python3 scripts/local/manage.py scope-test
python3 scripts/local/manage.py scope
python3 scripts/local/manage.py build
python3 scripts/local/manage.py up
python3 scripts/local/manage.py test
python3 scripts/local/manage.py auth
python3 scripts/local/manage.py startup
python3 scripts/local/manage.py smoke
python3 scripts/local/manage.py security
python3 scripts/local/manage.py authorization
```

`authorization`은 새 AUTHZ 전용 계정의 실제 로그인과 MySQL/JPA·FastAPI 조회를 사용한다. 같은 학교 비담당 교사·타학교 교사·직접/CLASS 공유 학생·같은 반 비공유 학생·타반/타학교 학생을 구분한다. 거부 요청의 DB checksum/행 수, SQLite 행 digest, 합성 객체 digest를 대조한다. 공급자 호출 횟수는 별도 서비스 테스트에서 검사한다. 공유 회수/담당 관계 변경/soft-delete 검사는 전용 합성 행에만 적용하고 finally에서 복구한다. 일반 사용자 자료의 소유권을 재설정하지 않는다.

웹: `npm run test:auth`, `npm run test:authorization`, `npm run typecheck`, `npm run build -- --mode phase1`. 실제 Chrome은 `auth-test-up` 뒤 `npm run test:browser-auth`, 일반 웹15173에서 `npm run test:browser-authorization` 순으로 실행한다. 실제 사용자 프로필을 사용하지 않는다. API 도구 검사는 Chrome 결과와 별도다. 인증 장애/영속성/브라우저/권한 검사는 서로 순차 실행한다. 동일 합성 계정의 로그인과 공유 회수가 겹치지 않게 한다.

그 다음 `persistence`, `stop`, `isolation`을 실행하되 시작 상태가 모두 중지가 아니었다면 시작 snapshot에 맞춰 **이번에 시작한 서비스만** 원래 상태로 되돌린다. 볼륨은 유지한다. 실행별 로그는 시각별 파일로 보존하고 최신 요약 파일과 구분한다.

2-B local 저장소는 `local/synthetic/authz/<uuid>.json`만 쓰기/읽기를 허용한다. 원래 합성 fixture는 읽기 전용이다. 실제 AWS 업로드/서명/삭제는 실행하지 않는다. `be-data:/app/be-local-data:ro`를 ai/worker에 연결하고 `LOCAL_OBJECT_STORAGE_DIR`를 주입해 같은 합성 JSON을 읽는다. 외부 FCM은 계속 disabled이며 공유 성공과 실제 알림 전송 성공은 다르다.

추가 fixture는 idempotent하게 별도 계정/자료만 만든다. 원래 fixture의 암호·내용을 덮어쓰지 않는다. SQL의 파일 컬럼 `s3key/jsons3key`는 기존 Java 물리명에 Python을 맞춘다. 새 SQLite `embedding_tasks`는 additive하게 생성하고 과거 작업에 추측한 소유자를 넣지 않는다. 일반 운영에서는 AI의 `OBJECT_STORAGE_HOST`를 실제 허용 객체 호스트로 설정해야 한다. 미설정은 실패하며 운영 설정·SSRF 전체 검증은 수행하지 않았다.

## 3-A 추가형 채점 스키마와 전용 검사

3-A 당시 기본 증거 디렉터리는 `.local/phase3a/results`였다. 앞선 1차/2-A/2-B 결과와 snapshot은 덮어쓰지 않는다. 실행 대상은 `dodream-phase1`, 당시 네 볼륨, loopback 포트, 내부 네트워크였다. 3-B 이후 Chroma 볼륨이 추가되어 현재는 다섯 볼륨이다. 기존 범위 gate를 모든 변경 명령에 그대로 적용한다.

보존된 자체 MySQL이 실행 중인 상태에서 새 Spring 이미지의 최초 기동 **전에** 다음 명령으로 버전 관리 SQL을 적용한다. 기존 Spring은 이 작업 동안 중지한다. SQL은 테이블을 삭제하거나 기존 풀이의 정답을 역채움하지 않는다.

```bash
python3 scripts/local/manage.py grading-migrate
python3 scripts/local/manage.py build
python3 scripts/local/manage.py up
python3 scripts/local/manage.py grading
```

`grading-migrate`는 `V003__grading_attempts.sql`을 자체 MySQL에 적용하고 재실행 후 구조가 같은지, 실제 NOT NULL·binary collation·unique 제약이 있는지 확인한다. 새 DB 검증은 같은 자체 MySQL 안의 **새** `dodream_phase3a_fresh_v2` 스키마에서 migration→JPA 최초 기동→migration 재실행 순서로 별도 수행한다. 기존 DB를 신규 검증용으로 재생성하지 않는다.

최초 3-A 검증 때 `grading_data.py before`로 원래 MySQL/RAG 행들의 해시 기준선을 만든다. 파일이 있으면 덮어쓰지 않는다. `grading_fixtures.py`는 `[AUTHZ LOCAL]` 합성 자료에서 `[AUTHZ 3A]` 새 행·객체를 만들며 기존 행에 쓰지 않는다. 따라서 기존 2-B 회귀의 수정·공유 회수·복구도 이번에 만든 전용 사례에서 수행한다. 기준선 증거 재현용 `grading_baseline.py`는 **2-B 이미지에서만 한 번** 실행하는 도구이며 새 구현의 일상 회귀 명령이 아니다.

```bash
python3 scripts/local/manage.py scope-test
python3 scripts/local/manage.py test
python3 scripts/local/manage.py auth
python3 scripts/local/manage.py startup
python3 scripts/local/manage.py smoke
python3 scripts/local/manage.py security
python3 scripts/local/manage.py authorization
python3 scripts/local/manage.py persistence
python3 scripts/local/manage.py isolation
```

학생 제출은 이제 UUID `Idempotency-Key`와 조회한 `answers[].version`이 필수다. FastAPI 직접 채점은 클라이언트 문제/정답이 아닌 서버가 접수한 attempt 실행 capability만 받는다. `verify_authorization.py`의 기존 공격 식별자는 유지하고 새 입력 계약을 반영했다. 이전 직접 AI 자료/문항 대입 본문은 스키마 단계 422로 거부되며, 문제 소속 검사 자체의 400 단위 테스트도 보존한다. 정상 제출의 서버 정답·학생 본인 판정 양성 대조군은 유지한다.

웹 helper 추가 회귀는 `npm run test:grading`, 실제 Chrome API 계약 검사는 `npm run test:browser-grading`이다. 기존 `test:auth`, `test:authorization`, `typecheck`, `build -- --mode phase1`, 두 Chrome 인증·권한 검사를 함께 유지한다. 이는 모바일 전체 빌드·실기기 결과가 아니다.

오류 주입 파일과 호출 카운터는 전용 로컬 볼륨에만 둔다. 공개 조작 API는 없다. `grading`은 자체 Spring의 실제 중지·재기동을 포함하므로 인증 장애 검사/브라우저 검사와 동시에 실행하지 않는다. 끝나면 이번에 시작한 서비스만 시작 전 상태로 돌리고 볼륨과 DB는 유지한다. 과거 ETCH 보존 FAIL/원인 UNVERIFIED는 그대로 남긴다.

실행 순서는 채점/서버 회귀 → `auth-test-up`과 Chrome → `persistence` → 시작 상태 복구 → `isolation`으로 잡는다. main 서비스만 재기동하는 영속성 검사 동안 auth-short는 계속 실행될 수 있다. 3-A에서는 그 순서를 거꾸로 실행한 뒤 short BE의 Redis 타임아웃/로그인503을 관측했고, 기존 범위 gate의 `restart be-auth-short`로 해당 테스트 프로세스만 재기동한 뒤 브라우저 검사를 재검증했다. 실패를 인증 허용이나 기대값 변경으로 우회하지 않는다.

## 3-B 실제 Chroma·영속 색인 작업

3-B 당시 증거 기본 경로는 `.local/phase3b/results/`였다. 현재 4단계 기본 경로는 아래 절을 따른다. 이전 단계의 결과를 덮어쓰지 않는다. 3-B 시작 HEAD는 `705c2a440e6e2d84fb26effc792e4ddd733f23d4`, 작업 브랜치는 `codex/dodream-phase3b-indexing`이다. 설계는 [11](11-indexing-reliability-design.md), 실제 실행 판정은 [12](12-phase3b-results.md)를 따른다.

Compose에 `chroma`와 `index-dispatcher`, 전용 `dodream-phase1_chroma-data` 볼륨을 추가했다. Chroma는 내부 HTTP8000만 사용하며 호스트 포트가 없다. AI/워커에는 Chroma 파일 경로를 마운트하지 않는다. 기존 네 볼륨은 그대로 유지한다. 최초 생성이 확인된 Chroma 볼륨의 이름·생성 시각도 고정해 이후 사라진 볼륨을 조용히 재생성하지 않는다. 모든 작업은 기존 고정 project/file/directory와 metadata gate를 거친다.

새 단계의 시작 기준선은 기존 워커를 시작하기 전에 만든다. 3-B 워커는 새 `indexing-v3` 큐만 소비한다. 과거 default 큐, SQLite 작업·대화 및 local 인덱스는 그대로 보존하며 자동 승격하지 않는다. 기준선 파일이 있으면 `before`를 반복해 덮어쓰지 않는다.

```bash
python3 scripts/local/indexing_data.py before
python3 scripts/local/indexing_fixtures.py
python3 scripts/local/manage.py indexing-migrate
python3 scripts/local/manage.py build
python3 scripts/local/manage.py up
```

`indexing-migrate`는 V004 신규 세 테이블을 현재 자체 DB에 추가하고 재실행·필수 컬럼·unique를 확인한다. 첫 설치 검증은 `indexing_migration.py fresh-prepare`로 **새** `dodream_phase3b_fresh`를 만들고 `verify_fresh_indexing_schema.py`로 실제 Spring을 기동한다. 이미 존재하면 초기화하지 않는다. V003과 V004를 JPA 최초 기동 전에 적용하며 시험 스키마와 볼륨을 보존한다.

이번 AUTHZ/GRADING 회귀 자료는 `[AUTHZ 3B]`, `[GRADING LOCAL] phase3b`의 새 복제 행이다. 기존 3-A 자료와 원래 문제 버전·풀이를 수정하지 않는다. 색인 장애 검사는 실제 local 전용 합성 PDF 업로드에서 얻은 새 파일과 `[INDEXING LOCAL]` 자료만 사용한다. PDF/JSON 객체는 새 UUID 경로에 준비하고 기존 객체를 덮어쓰지 않는다. 원본 PDF 페이지 해석·OCR은 실제 검증 범위가 아니다.

```bash
python3 scripts/local/manage.py scope-test
python3 scripts/local/manage.py test
python3 scripts/local/manage.py indexing
python3 scripts/local/manage.py auth-test-up
python3 scripts/local/manage.py auth
python3 scripts/local/manage.py startup
python3 scripts/local/manage.py smoke
python3 scripts/local/manage.py security
python3 scripts/local/manage.py authorization
python3 scripts/local/manage.py grading
```

`manage.py test`는 전달기가 DB 시험 중간 상태를 소비하지 않도록 실행 중인 자체 `index-dispatcher`만 잠시 중지하고, 실패나 예외 때도 같은 컨테이너 ID를 직접 시작해 복원한다. 원래 중지됐거나 없었다면 시작하지 않는다. Compose의 의존 서비스 자동 시작을 이용하지 않으며, ID가 바뀌거나 범위 gate를 통과하지 못하면 차단한다. DB 단위 fixture의 합성 pointer는 실제 Chroma 활성화 증거로 집계하지 않는다. 색인 검사는 첫 정상 경로가 실패하면 후속 장애 검사를 중단한다. 개별 재검증은 `manage.py indexing happy`처럼 해당 시나리오 이름을 지정한다. 실제 SIGKILL은 관측된 gate 뒤의 자체 `be`, `worker`, `index-dispatcher`에만 허용한다. 실제 응답 timeout 검사는 자체 Chroma만 pause/unpause하며 finally에서 복구한다. 별도 독립 워커도 고정 project/service/task 라벨을 확인한 일회용 컨테이너이고 기존 워커·볼륨을 삭제하지 않는다. 이 검사는 인증/채점/Chrome 검사와 동시 실행하지 않는다.

`grading`에는 3-A의 공급자 대기 중 독립 DB 조회 검사가 포함되어 있다. 별도 보조 실행 수를 중복 합산하지 않는다. 모든 회귀는 이미지 build가 끝난 후 시작한다. Redis/MySQL을 재시작한 뒤에는 실제 health와 합성 로그인을 확인하고 `auth-test-up` 또는 필요한 자체 `be-auth-short` 재기동 후 Chrome 인증 검사를 실행한다.

웹은 기존 `test:auth`, `test:authorization`, `test:grading`, `typecheck`, `build -- --mode phase1`과 새 `test:indexing`을 실행한다. 기존 Chrome 세 종류에 새 `test:browser-indexing`을 더한다. 새 교사 UI 검사는 `verify_indexing.py browser`가 새 합성 자료와 ignored manifest/checkpoint를 준비해 시작하며, 준비 없이 단독 하네스를 실행하지 않는다. 학생 UI 전체·모바일 전체는 이번 범위가 아니다.

```bash
python3 scripts/local/manage.py persistence
python3 scripts/local/indexing_data.py after
python3 scripts/local/indexing_retention.py
python3 scripts/local/manage.py stop
python3 scripts/local/manage.py isolation
```

`persistence`는 원래 probe 행을 바꾸지 않고 새 3-B probe를 사용한다. 회귀 중 자료가 개정되면 과거 smoke 세션은 정상적으로409가 될 수 있으므로, 이전 세션/로그를 보존한 채 현재 공유 자료의 활성 원본에 연결한 새 세션을 시험한다. 재시작 전후 재색인 요청 없이 같은 pointer·source·세션·메시지·Chroma count/digest를 비교한다. 이미지 태그를 다시 적용하는 `up` 대신 검증한 기존 컨테이너 ID를 시작하고, 준비 상태 확인에는240초 재시도 예산과 개별 HTTP2초 제한을 적용한다(전체 명령의 엄격한240초 상한을 뜻하지 않음).

마지막에는 시작 snapshot의 **실제 서비스별 상태**로 복구하고 새 서비스는 중지한다. 시작 상태가 모두 중지가 아니라면 무조건 전체 `stop`하지 않는다. 원래 행의 모든 컬럼과 기존 객체 digest, 과거 SQLite 인덱스 행을 대조한다. `indexing_retention.py`는 상태·이름·해시 파일명만 읽는 보존 검토용 dry-run이며 삭제 모드가 없다. 미참조 후보·객체의 분류가 삭제 안전성 보증은 아니다.

실제 외부 AI, 외부 저장소·OCR·알림, 공개 배포는 실행하지 않는다. 과거 ETCH와 3-A 외부 변화의 FAIL/UNVERIFIED는 유지하고 이번 before/after 판정은 별도로 기록한다.

## 4단계 학생 웹 체험

3-B의 검증된 서버 기능에 학생 웹을 연결한 개인 개선이다. 4단계 당시 기본 증거 디렉터리는 `.local/phase4/results/`, Chrome 실행별 준비 파일·원본 캡처는 `.local/phase4/browser-ui/`였다. 현재 5단계 명령의 경로·새 합성 자료는 아래 절을 따른다. 이전 실패·후속 실행·보존 증거를 덮어쓰지 않는다. 설계는 [13](13-student-web-design.md), 당시 실제 결과는 [14](14-phase4-results.md), 화면별 시연은 [15](15-demo-walkthrough.md)를 따른다.

보존된 로컬 환경에서 아래 명령을 저장소 루트에서 실행한다. 처음 환경을 만드는 경우 앞 절의 생성·추가형 migration 절차를 먼저 따른다. 소스를 변경했다면 시작 전에 `build`로 해당 이미지를 갱신한다.

```bash
cd /Users/yoonsu/Desktop/projects/DO-DREAM
python3 scripts/local/manage.py check
python3 scripts/local/manage.py config
python3 scripts/local/manage.py build
python3 scripts/local/manage.py demo-up
python3 scripts/local/manage.py demo-prepare
python3 scripts/local/manage.py status
```

접속 경로는 [학생 체험 /demo](http://127.0.0.1:15173/demo), [기존 교사 로그인](http://127.0.0.1:15173/)이다. 기본 웹 포트는 15173이며 기존 `.local/env`의 `WEB_PORT`를 바꾼 경우 그 포트를 사용한다. `demo-up`이 `DODREAM_DEMO_ENABLED=true`를 명시적으로 설정한다. 서버 `local` 프로필과 이 opt-in이 모두 필요하며 일반 `up`의 기본값은 체험 비활성이다. 프런트엔드 flag나 요청 주소가 서버 기능을 켜지 않는다. 체험용 비밀을 기존 `.env`에서 가져오거나 JS 번들에 넣지 않는다.

`demo-prepare`는 전용 합성 교사로 실제 인증한 뒤 준비 API를 호출한다. 직접 작성한 **물의 여행**, **생활 속 분리배출**과 각 2문제는 `student-web-v1` 버전으로 준비된다. 실제 발행·작업 원장·Celery·Chroma를 거쳐 현재 원본을 읽을 수 있어야 준비가 완료된다. 같은 버전의 준비를 두 번 호출해 식별자와 논리 개수가 바뀌지 않는지 확인한다. 기존 발행본을 삭제하거나 SQL로 ACTIVE 포인터를 조작하지 않는다. 준비 결과의 `student-demo-plan.json`은 비밀·정답을 포함하지 않는 자동 검사 입력이다.

독립 브라우저 방문자는 각각 새 합성 학생을 배정받고, 같은 visitor는 기존 학생을 재사용한다. 샘플 본문을 함께 읽어도 대화·풀이·진도는 다른 사용자와 공유하지 않는다. 현재 로그인은 자동 교체하지 않는다. 교사·학생 동시 시연은 독립 context를 사용하고 역할 전환은 명시적으로 로그아웃한 뒤 한다. 이것은 공개 가능한 게스트 인증이나 실제 학생 등록·생체 인증의 검증이 아니다.

학생 웹 전체 흐름의 재현 명령은 다음과 같다. 짧은 AT용 자체 서비스만 별도 설정하며 일반 서비스의 토큰 수명을 변경하지 않는다.

```bash
DODREAM_DEMO_ENABLED=true python3 scripts/local/manage.py auth-test-up
python3 scripts/local/manage.py student-web
```

`student-web`은 앞선 `demo-prepare`의 plan을 읽어 독립 Chrome context에서 시작 버튼·교재 선택·본문/단원·질문/참고 자료·퀴즈·결과/새로고침·교사 결과 화면을 실제 조작한다. 준비용 API/DB 확인, 서비스 장애, 응답 유실·오류 주입은 정상 화면 흐름과 구분한다. 시작/종료 앱 소스 해시가 같아야 하며 실패 원본을 보존한 뒤 수정 시 새로운 전체 실행으로 시작한다. 실행별 `phase4-acceptance-<runId>.json`과 Chrome 결과를 확인하며 다른 실행의 부분 PASS 수를 합산하지 않는다. `npm run test:browser-student` 하네스만 준비 없이 직접 실행하지 않는다. API 전용 검사 `python3 scripts/local/manage.py demo-api`도 UI E2E 결과와 구분한다.

웹 단위검사는 기존 auth/authorization/grading/indexing과 함께 `npm --prefix fe-web run test:student`, 타입 검사는 `npm --prefix fe-web run typecheck`, 빌드는 `npm --prefix fe-web run build -- --mode phase1`로 수행한다. 실제 서비스 장애·인증·채점·Chrome 검사는 같은 합성 계정이나 서비스 상태가 겹치지 않도록 순차 실행한다. 기존 3-B 전체 명령의 FAIL과 후속 coverage PASS를 이번 결과로 다시 집계하지 않는다.

로컬 대역 답변·8차원 로컬 임베딩·로컬 채점은 로그인 후 서버의 `/rag/mode` 응답으로 표시한다. 실제 외부 AI·OCR·저장소·음성 서비스는 호출하지 않는다. 로컬 한국어 voice가 없는 브라우저는 안내 후 텍스트 학습을 계속한다. **TTS_AUDIBLE_CHECK=NOT_RUN**, **SCREEN_READER_MANUAL=NOT_RUN**이며 합성 speech 단위검사와 브라우저 API 관측으로 실제 청취·VoiceOver·접근성 인증을 주장하지 않는다. **REAL_AI_INTEGRATION=NOT_RUN**, **PUBLIC_DEPLOYMENT_READY=false**다. 공개 데모 URL은 없고 배포·터널·다음 모델 연결에는 착수하지 않는다.

시연을 종료할 때는 다음 명령을 사용한다.

```bash
python3 scripts/local/manage.py stop
python3 scripts/local/manage.py isolation
```

이번 4단계처럼 시작 시 자체 서비스가 모두 중지였을 때의 종료 명령이다. 이미 실행 중인 자체 서비스가 있었다면 시작 snapshot에 맞춰 이번에 시작한 서비스만 원래 상태로 돌린다. 다른 프로젝트 자원은 변경하지 않는다. 새 샘플·합성 학생 기록·영속 볼륨은 보존하며 `down -v`, prune, DB/Chroma reset을 사용하지 않는다. 재체험은 `demo-up` → `demo-prepare` → `/demo` 순서다.

## 5단계 공급자·평가 준비와 승인 후 재개

현재 증거 기본 경로는 `.local/phase5/results/`, 고정 평가 출력은 `.local/phase5/evaluation/`다. **LIVE_API_AUTHORIZED=false, 실제 공급자 요청0회, REAL_AI_INTEGRATION=NOT_RUN, PUBLIC_DEPLOYMENT_READY=false**다. 실제 호출 승인과 전용 키가 없어 유료 연동·모델 품질·실제 비용은 미실행이다. 오프라인 계약 PASS를 실제 모델 통과로 해석하지 않는다. 설계·결과는 [16](16-live-ai-and-evaluation-design.md), [17](17-phase5-results.md)를 따른다.

기존 보존 기준선을 새로 확보한 뒤 일반 `demo-up`·`demo-prepare`로 준비하는 로컬 체험 자료의 버전은 `student-web-phase5-v1`, 합성 교사는 `demo-phase5-v1@local.dodream.invalid`다. 4단계 교재·학생 기록을 덮어쓰지 않는다. 아래 명령은 키와 외부 요청 없이 고정 평가셋·양식·신규 평가 자료만 준비한다. `phase5_prepare.py`는 준비된 로컬 체험 서버가 필요하며 전용 합성 학생 한 명을 재사용한다.

```bash
python3 scripts/evaluation/phase5.py validate
python3 -m unittest discover -s scripts/evaluation/tests -v
python3 scripts/evaluation/phase5.py export
python3 scripts/evaluation/phase5.py review
python3 scripts/local/live_ai.py template
DODREAM_PHASE5_PREPARE_ENABLED=true python3 scripts/local/manage.py demo-up
python3 scripts/local/manage.py demo-prepare
python3 scripts/local/phase5_prepare.py
```

새 자료4개는 기존 직접 작성 교재의 스모크 복사본2개와 평가 교재2개다. 서버의 실제 초기 준비·발행·색인 원장을 사용하며 live 작업은 승인 전 소비하지 않는다. 준비 영수증은 `.local/phase5/results/phase5-prepared.json`에 자료/문제/작업 ID와 원본 hash를 기록한다. **준비 접수는 실제1536차원 임베딩 저장 성공이 아니다.** SQL로 ACTIVE를 바꾸지 않는다. 평가 자료는 각8개 본문 구간, 질문24개와 채점답안16개이며 gold는 evaluator에만 남는다. [평가 도구 설명](../../scripts/evaluation/README.md)을 참고한다.

키 없는 양식은 `.local/phase5/live/provider-live.env.example`, 승인 양식은 같은 폴더의 `manifest.template.json`이다. 기존 파일을 덮어쓰지 않는다. 전용 키 파일 `~/.config/dodream/provider-live.env`는 사용자만 로컬에서 준비하고 권한0600으로 둔다. 허용 변수는 `OPENAI_API_KEY` 하나이며 스크립트로 실행하지 않는다. 키를 대화·명령 인자·브라우저·VITE·`.local/env`에 넣지 않는다. 런처는 전용 파일의 존재·권한만 확인하고 필요한 AI 프로세스에 읽기 전용 파일로 연결한다.

아래는 **사용자가 이번 실행을 명시적으로 승인하고 예산·요청 수·모델·신규 자료/사용자 범위를 지정한 이후에만** 쓰는 재개 명령이다. 현재 실행하라는 지시나 승인 문구가 아니다. 사용자가 승인 양식을 `.local/phase5/live/manifest.json`으로 완성해야 한다. 모델은 `text-embedding-3-small`1536차원과 `gpt-4.1-mini-2025-04-14`로 고정한다. manifest에는 고정 dataset hash, 준비 영수증의 허용 자료·원본·합성 사용자, 현재 소스와 일치하는 `live-offline-contract.json` 증거 hash, 만료 시각, 양수 예산/요청 상한이 필요하다. 코드나 고정 자료가 바뀌면 기존 검증 영수증을 재사용하지 않는다. `open`은 검증 영수증의 AI·Spring·웹 이미지 ID와 실행 중 이미지, 새 AI 실행에 쓸 태그의 이미지 ID까지 대조한다.

```bash
LIVE_API_AUTHORIZED=true python3 scripts/local/live_ai.py preflight
LIVE_API_AUTHORIZED=true python3 scripts/local/live_ai.py open
LIVE_API_AUTHORIZED=true python3 scripts/local/live_ai.py job '<승인한 준비 영수증의 job_id>'
```

`job`은 해당 작업 하나만 실행한다. 각 작업 결과와 후보 검증·활성 전환을 확인한 뒤 다음 승인 작업을 선택하며 반복 루프로 자동 소비하지 않는다. `open`은 기존 local worker·dispatcher를 중지하고 key를 가진 AI를 순차 실행한다. 별도 live broker 소비자는 없으며 승인 자료/source/spec/사용자를 벗어나면 공급자 전에 거부한다. 공통 영속 예산은 CLI·API·작업과 실패·스모크·UI 요청을 모두 세며 재시작해도 초기화하지 않는다.

모든 승인 자료의 실제 색인을 확인한 뒤 `app-smoke`로 두 스모크 복사본에서 정상·후속·답 없음 질문과 간단한 채점을 실제 앱 경로로 확인한다. 이 영수증을 통과해야 후속 평가를 시작할 수 있다. `phase5_evaluate.py smoke`는 추가 평가 교재의 R01-A/G01 두 문항을 확인하는 **작은 평가 실행 gate**이며 두 복사본 앱 스모크와 구분한다. 실제 학생 웹의 작은 정상 흐름은 별도 수동 검증이며 이번에는 NOT_RUN이다. 같은 원인의 실패가 나오면 후속 평가를 계속하지 않는다.

```bash
LIVE_API_AUTHORIZED=true python3 scripts/local/phase5_evaluate.py app-smoke
LIVE_API_AUTHORIZED=true python3 scripts/local/phase5_evaluate.py smoke
LIVE_API_AUTHORIZED=true python3 scripts/local/phase5_evaluate.py development
LIVE_API_AUTHORIZED=true python3 scripts/local/phase5_evaluate.py final
LIVE_API_AUTHORIZED=true python3 scripts/local/phase5_evaluate.py report
python3 scripts/local/live_ai.py close
```

개발·최종 분리와 고정 대화를 유지하고 A/B의 유일한 차이는 대화가 있는 경우의 검색 질문 재작성이다. 성공한 기존 문항은 재사용하고 실패·중단 문항은 자동 재요청하지 않는다. 관측·시작 marker·usage는 실행 ID별로 보존한다. RAG CLI는 문항마다 새 프로세스의 cold 실행이며 공급자·Chroma cache까지 초기화됐다는 뜻은 아니다. 채점 서버의 cold/warm을 관측하지 못하면 null/unknown으로 남기고 warm으로 추정하지 않는다. `report`는 열린 승인 세션에서 사용하며, 닫은 뒤에는 `python3 scripts/evaluation/phase5.py review --records '<저장된 실행별 observations JSON>'`으로 외부 요청 없이 다시 검토한다. 구조/ID·고정 판정 일치와 자연어 의미 검토를 구분하고 사람이 보지 않은 항목은 사람 평가 NOT_RUN으로 남긴다. 청구 확인은 프로그램 계산 비용과 별개다.

`close`는 승인 만료나 키 부재와 관계없이 live AI 중지를 먼저 시도하고, 검증된 local 상태로 복원한다. 복원 단계가 차단되면 기록을 보존하고 임의 새 컨테이너를 시작하지 않는다. 키 마운트나 외부 연결이 남아 있는 AI에서는 기존 local 회귀와 local AI 실행이 거부된다. 키 없는 상태를 확인한 뒤 앞 절의 인증·권한·채점·학생 웹 회귀, 새 데이터/물리 색인 보존 대조, retention dry-run, 시작 상태 복구와 isolation을 수행한다. 기존55개 장애 suite 전체를 live로 돌리지 않는다. OCR·TTS·파일 저장소의 실제 외부 연동과 공개 배포는 계속 미실행이다.
