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

HTTP 로컬에서 기존 refresh 쿠키의 `Secure` 속성은 유지했다. smoke는 쿠키를 메모리에서 명시 전달하여 서버/Redis 흐름을 검증한다. 브라우저의 자동 refresh·전체 학습 E2E를 검증한 것은 아니다. 웹 로그인 POST와 Origin 헤더를 통한 nginx/CORS 경로, 인증 GET은 실제 검증했다.

## 검증

```bash
python3 scripts/local/manage.py test
python3 scripts/local/manage.py smoke
python3 scripts/local/manage.py security
python3 scripts/local/manage.py persistence
python3 scripts/local/manage.py isolation
```

- `test`: 보존한 Spring `contextLoads` + 경계 테스트 4개, AI 7개, PDF 6개. Spring 테스트는 실제 MySQL/Redis, Python 단위테스트는 별도 임시 SQLite와 원래 JWT 인증을 사용한다. 실제 공유 MySQL 연결은 smoke/health에서 확인한다. 테스트용 Spring 컨테이너만 일회성으로 생성/종료/제거한다.
- `smoke`: 헬스, 합성 로그인, 웹 Origin/CORS, 정상·무토큰·위조토큰, 자료, 실제 Celery queue, 대역 채팅/SQLite, Redis refresh 흐름.
- `security`: 안전 기대값을 검증한다. 현재 알려진 취약점 때문에 **exit1/FAIL이 예상되며 보안 통과가 아니다**. 해당 코드를 고친 다음 기준선을 PASS로 바꾼다. 실제 외부 파일/AI에 요청하지 않는다.
- `persistence`: MySQL 전용 probe table과 Redis probe key를 생성하고 이번 프로젝트만 stop/up한다. 앱이 seed하지 않는 marker, 도메인 수, 기존 SQLite session과 대역 인덱스를 확인한다. 먼저 smoke가 필요하다. 세션 부재는 BLOCKED다.

명령/종료코드와 민감값을 제거한 출력은 `.local/results/`에 저장한다. `commands.jsonl`은 기록 기능 도입 이후 실행 이력이고, 이전 시도는 별도 JSON/log와 결과 문서에 보존했다. 테스트 HTTP body·토큰·cookie는 저장하지 않는다. 일반 `docker compose config`는 비밀을 펼치므로 출력하지 말고 wrapper의 `config --quiet`를 쓴다. 원문 컨테이너 로그를 공유하지 않는다.

호스트 웹 검증(선택):

```bash
cd fe-web
npm ci --ignore-scripts --no-audit --no-fund --cache /private/tmp/dodream-phase1-npm-cache
npm run typecheck
npm run build -- --mode phase1
```

`phase1`은 `local-env`만 읽고 API base를 same-origin으로 고정한다. 빌드 mode를 생략한 기존 배포 명령과 구분한다. 로컬 CSP는 원격 폰트/이미지/API를 차단한다.

## 종료·재시작·데이터 위치

```bash
python3 scripts/local/manage.py stop
python3 scripts/local/manage.py up
# 실행 중인 이번 프로젝트만 재시작할 경우
python3 scripts/local/manage.py restart
```

`stop`은 컨테이너만 멈추며 볼륨·네트워크·이미지를 삭제하지 않는다. `up`은 같은 데이터로 시작한다. **down -v/prune/reset/clean/기존 자원 삭제를 사용하지 않는다.**

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
