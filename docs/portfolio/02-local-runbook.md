# 02. 격리 로컬 실행

저장소 루트에서 실행한다. 이 구성은 공개 배포용이 아니다. 팀의 기존 배포 설정과 비밀 파일을 재사용하지 않는다.

## 준비와 첫 기동

호스트 필수: Docker Desktop/Compose v2, Python3. Node/Java를 호스트에 추가 설치할 필요는 없다. 이미지 안에서 Java17/Node22/Python3.11을 사용한다. 최초 빌드에는 명세의 공개 의존성/이미지 다운로드가 필요하다. 전역 설치, sudo, 모델 다운로드는 하지 않는다.

```bash
cd /Users/yoonsu/Desktop/projects/DO-DREAM
python3 scripts/local/manage.py init
python3 scripts/local/manage.py check
python3 scripts/local/manage.py config
python3 scripts/local/manage.py build
python3 scripts/local/manage.py up
python3 scripts/local/manage.py status
```

`init`은 `.local/env`를 없을 때만 새로 만들고 0600 권한을 설정한다. 기존 파일을 덮어쓰지 않는다. `.env.example`은 변수 설명용이고 실제 비밀이 없다. `.local/env`는 Git에서 제외된다. 기존 `.env`, Vault 설정, 사용자 자격증명을 읽어오지 않는다. wrapper는 지정 파일과 전용 프로젝트 이름을 강제하고 같은 이름의 shell/Compose 변수 간섭을 제거한다.

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

- `test`: 보존한 Spring `contextLoads`와 경계 테스트에 JWT/쿠키/Redis 회귀를 추가하고, AI 기존7개에 인증17개를 추가했다. PDF 기존6개를 보존했다. Spring 테스트는 실제 MySQL/Redis, Python 단위테스트는 별도 임시 SQLite와 원래 JWT 인증을 사용한다. 실제 공유 MySQL 연결은 smoke/health에서 확인한다. 테스트용 Spring 컨테이너만 일회성으로 생성/종료/제거한다.
- `auth`: 실제 Spring/FastAPI JWT 계약, 실제 Redis 회전·12개 독립 HTTP 클라이언트 동시성·logout 경쟁, CSRF/cookie/native 계약. 합성 계정/키만 사용한다. 마지막에는 전용 Redis만 잠시 중지해 503 오류를 검사하고 finally에서 시작한다. 다른 테스트와 동시에 실행하지 않는다.
- `startup`: 별도 일회성 컨테이너에서 빈/오류/짧은 키의 실제 기동 실패 검사. 원문 로그/키를 저장하지 않는다.
- `smoke`: 헬스, 합성 로그인, 웹 Origin/CORS, 정상·무토큰·위조토큰, 자료, 실제 Celery queue, 대역 채팅/SQLite, Redis refresh 흐름.
- `security`: 안전 기대값을 검증한다. 2-A 인증3개와 범위 밖 객체권한6개를 분리한다. 역할별 새 로그인과 양성 대조군을 먼저 확인한다. 남은 객체권한 때문에 **exit1/FAIL이 예상되며 전체 보안 통과가 아니다**. 원래1차FAIL 증거는 그대로 보존한다. 실제 외부 파일/AI에 요청하지 않는다.
- `persistence`: MySQL 전용 probe table과 Redis probe key를 생성하고 이번 프로젝트만 stop/up한다. 앱이 seed하지 않는 marker, 도메인 수, 기존 SQLite session과 대역 인덱스를 확인한다. 먼저 smoke가 필요하다. 세션 부재는 BLOCKED다.

1차 증거는 `.local/results/`에 보존한다. 현재 명령/종료코드와 민감값을 제거한 출력은 `.local/phase2a/results/`에 저장한다. `DODREAM_RESULTS_DIR`로 이후 검증의 새 증거 폴더를 지정할 수 있다. 새 폴더에서는 시작 전 `resources-before`를 기록해야 isolation 비교가 가능하다. `commands.jsonl`은 기록 기능 도입 이후 실행 이력이고, 이전 시도는 별도 JSON/log와 결과 문서에 보존했다. 테스트 HTTP body·토큰·cookie는 저장하지 않는다. 일반 `docker compose config`는 비밀을 펼치므로 출력하지 말고 wrapper의 `config --quiet`를 쓴다. 원문 컨테이너 로그를 공유하지 않는다.

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

스키마는 **새 local DB에서만** 기존 JPA `ddl-auto=update`와 AI SQLite `create_all`로 만든다. seed는 하나의 트랜잭션에서 최초 한 번 생성하며 교사 fixture가 존재하면 수정·비밀번호 재설정 없이 종료한다. 이후 seed 구조를 바꾸는 마이그레이션은 이 단계에 없다. 환경 파일의 비밀번호만 바꾸면 기존 DB 사용자나 합성 계정 비밀번호가 자동 변경되지 않는다. 초기화나 볼륨 삭제로 우회하지 말고 별도 데이터 관리 작업으로 처리한다.

CPU/메모리 상한을 지정했다. 상시 7개 컨테이너 합계 메모리 상한 약 3.25GiB, 테스트 컨테이너는 일시 1.25GiB 추가다. 검증 종료 뒤 전용 컨테이너는 중지하여 다른 작업의 자원을 돌려준다.

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

현재 증거 기본 경로는 `.local/phase2b/results/`다. 위 1차/2-A 설명과 원본 결과는 당시 상태이며, 2-B 결과는 [08](08-phase2b-results.md)를 따른다. 새 단계용 폴더에서는 먼저 `resources-before`, `scope`를 실행한다. 최초 snapshot은 덮어쓰지 않는다. `scope-test`는 Docker 없이 합성 명령/metadata를 검사한다. 실제 자원 변경은 고정 Compose/project/directory와 라벨·서비스·볼륨·마운트·이미지·네트워크 검사를 통과해야 한다. 검사 실패 시 우회 실행하지 않는다.

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

현재 기본 증거 디렉터리는 `.local/phase3a/results`다. 앞선 1차/2-A/2-B 결과와 snapshot은 덮어쓰지 않는다. 실행 대상은 계속 `dodream-phase1`, 기존 네 볼륨, loopback 포트, 내부 네트워크다. 기존 범위 gate를 모든 변경 명령에 그대로 적용한다.

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
