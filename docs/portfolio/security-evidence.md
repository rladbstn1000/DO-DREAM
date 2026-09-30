# 보안 기준선 근거 — 1차 로컬 복원

기준 커밋: `4c763af` (수정 전 팀 구현). 아래 줄 번호는 **이 커밋의 원문 기준**이다. 개인 개선 후 파일의 줄 번호가 달라질 수 있으므로 `git show 4c763af:<경로>`로 원문을 확인한다. 비밀값·토큰·사용자 레코드·교재 원문은 이 문서에 포함하지 않는다.

`확인됨`은 코드에서 지적의 근거를 찾았다는 뜻이다. 정적 근거를 공격 재현 또는 운영 사고로 해석하지 않는다. `해소됨`은 해당 조건의 제거가 확인된 경우에만 사용한다. 운영 배포 환경의 실효 설정과 실제 악용 여부는 조사하지 않았다. 1차에서 보안 전면 수정은 하지 않는다.

## 13개 지적의 재확인

| # | 항목 / 판정 | 기준 코드 근거 (경로:줄) | 영향과 확인 범위 | 재현 상태 / 후속 검증 |
|---|---|---|---|---|
| 1 | Access/Refresh 종류 구분 — **확인됨** | `be/src/main/java/A704/DODREAM/auth/util/JwtUtil.java:35-60`: 두 생성 함수가 같은 claim·키·parser 사용. `be/src/main/java/A704/DODREAM/auth/filter/JwtAuthFilter.java:43-64`: subject와 role 검사만 수행. `ai/app/security/auth.py:32-42`: issuer는 검증하지만 token kind 검사 없음. | 토큰 종류를 명시하는 claim이 없고 리소스 서버가 Refresh Token을 Access Token과 구별하지 못하는 구조. Spring은 parser에서 issuer 요구도 하지 않음. 만료·서명 검증 자체가 없는 것은 아님. | 정적 확인. 실제 합성 Refresh Token의 보호 API 접근 결과는 `03-phase1-results.md`의 SECURITY_BASELINE 결과와 구분한다. 안전 기대값은 거부이며 수락되면 FAIL. |
| 2 | Redis Refresh 교체 경쟁조건 — **확인됨** | `be/src/main/java/A704/DODREAM/auth/service/RefreshTokenService.java:23-28` | GET → 비교 → SET이 각각 분리되어 동일 이전 토큰을 가진 동시 요청이 둘 다 검증을 통과할 수 있음. Lua/CAS/트랜잭션에 의한 원자적 교체 없음. | 정적 확인. 동시성 재현 NOT_RUN. 차기 단계에서 동일 이전 토큰의 병렬 교체 성공이 정확히 1개인지 검증. |
| 3 | 실제 Access 만료 설정 — **확인됨 + 실효값 추가 검증 필요** | `be/src/main/java/A704/DODREAM/auth/util/JwtUtil.java:26`: 코드 기본 900초. `be/src/main/resources/application.yml:105`: 설정 86400초. | 기본 application 설정으로는 코드 기본값 대신 24시간이 적용됨. 운영의 환경변수·Vault override 값은 읽거나 확인하지 않음. | 정적 설정 확인. 로컬 발급 토큰의 `exp - iat`만 계산해 결과를 기록하고 토큰 원문은 출력하지 않는다. 로컬 프로필 값과 기존 배포 값은 분리해서 판단. |
| 4 | 파일 URL·자료 인증/소유권 — **확인됨 (일부 검사 존재)** | `be/src/main/java/A704/DODREAM/config/SecurityConfig.java:54-56,64`: `/api/pdf/**`, `/api/files/**`, `/api/documents/**` permitAll. `be/src/main/java/A704/DODREAM/file/controller/FileUploadController.java:70-81,99-111`: URL 발급 시 principal/소유권 검사 없음. `be/src/main/java/A704/DODREAM/file/service/S3Service.java:51`: 업로더 1 고정. `be/src/main/java/A704/DODREAM/file/controller/PdfController.java:124-129,141-148`: 미인증 userId 1 대입. | 파일 ID로 다운로드 URL 생성 가능 구조. PDF JSON 서비스에는 업로더 검사(`file/service/PdfService.java:447-453,551-559`)가 있으나 controller 기본 사용자 처리로 인증 보장이 깨짐. 모든 자료 경로에 소유권 검사가 없다고 일반화하지 않음: `material/service/PublishService.java:321-335`의 라벨·삭제는 교사 소유권 검사 있음. | 정적 확인. 실제 S3/CloudFront 요청 NOT_RUN. 로컬 파일 대역의 합성 파일 ID에 대한 무토큰 URL 발급은 안전 기대값 401/403이며 200이면 FAIL. |
| 5 | RAG document_id 권한·세션 자료 일치 — **확인됨** | `ai/app/rag/router.py:261-329`: 요청 document_id 그대로 chain 생성; 기존 세션은 id/user_id 조건으로 조회(`281-282`)하나 document_id와 비교하지 않음. | 로그인은 요구하고 다른 사용자의 세션 조회는 제한하지만 자료 공유/소유권 확인이 없음. 자신의 기존 세션에 다른 자료 ID를 전달할 수 있는 구조. | 정적 확인. 실제 검색/LLM 공격 재현 NOT_RUN. 로컬 대역으로 접근정책 경계만 별도 검증 가능하며 실제 검색 유출 재현으로 보고하지 않음. |
| 6 | 교사 학생 대화 담당관계 — **확인됨** | `ai/app/rag/router.py:436-449,498-520`: TEACHER role와 호출자가 지정한 student_id만 사용. | 교사-반-학생 관계를 확인하지 않아 다른 교사의 학생 이력도 조회 가능한 구조. 상세 조회의 session/user 일치 확인은 있음. | 정적 확인. 실제 학생 대화 조회 NOT_RUN. 이후 합성 담당/비담당 교사 두 명과 학생 fixture로 차단 정책 검증 필요. |
| 7 | 학생 퀴즈 정답 포함 — **확인됨** | `be/src/main/java/A704/DODREAM/quiz/controller/QuizController.java:46-50`, `be/src/main/java/A704/DODREAM/quiz/service/QuizService.java:83-88`, `be/src/main/java/A704/DODREAM/quiz/dto/QuizDto.java:19-20,31` | 학생/교사 공용 조회가 `correct_answer`를 직렬화함. 제출 전에 정답을 알 수 있으며 조회에 자료 접근 범위 확인도 보이지 않음. | 정적 확인. 합성 학생으로 실제 퀴즈 JSON의 정답 필드 유무를 확인하여 있으면 안전 정책 FAIL. 모바일 API 계약도 이 공용 경로를 사용. |
| 8 | AI 채점·DB 트랜잭션 — **확인됨** | `be/src/main/java/A704/DODREAM/quiz/service/QuizService.java:94-151`: `@Transactional` 안에서 DB 조회 → WebClient `.block()` → 풀이 기록 저장. | 외부 지연 동안 트랜잭션 유지, 재요청 중복 저장·부분 실패 전략 부족. 저장이 외부 호출보다 먼저 commit된다는 뜻은 아님. | 정적 확인. 실제 AI 호출·지연/장애 주입 NOT_RUN. 트랜잭션 분리와 제출 idempotency는 후속 단계. |
| 9 | 임베딩 선삭제 — **확인됨** | `ai/app/rag/service.py:317-335`: 기존 컬렉션 delete 후 `Chroma.from_documents`. `ai/app/rag/tasks.py:102-110`: 실패 시 재시도. | 새 임베딩 실패 시 이전 검색 컬렉션이 이미 삭제될 수 있음. 활성 버전 전환/원자적 교체 또는 단일 작업 락 없음. | 정적 확인. 모델 적재·기존 컬렉션 삭제 실험 NOT_RUN. 차기 단계에 새 버전 생성 성공 후 전환, 실패 시 이전 자료 유지 검증. |
| 10 | 임의 URL·리다이렉트 — **확인됨** | `ai/app/rag/router.py:40-47`: HttpUrl만 검증. `ai/app/rag/tasks.py:18-33`, `ai/app/rag/service.py:124-133`, `ai/app/document_processor/router.py:63-108,122-157`: `follow_redirects=True`, 호스트/IP 허용목록 없음. `python-service/app/routers/pdf_structure.py:358-378`: 문자열 URL 다운로드. | AI 문서 파서에는 인증 dependency도 없음. 내부 주소/리다이렉트 목적지를 통제하지 않아 SSRF 위험. Content-Length 검사는 다운로드 후 수행되어 스트리밍 상한이 아님. python-service는 redirect를 명시 허용하지 않으므로 동일한 redirect 정책이라고 단정하지 않음. | 정적 확인. 내부 메타데이터/외부 주소 공격 요청 NOT_RUN. 1차 local 모드에서 외부 다운로드 경계 차단, 운영 SSRF 정책 수정은 미완료. |
| 11 | 운영·JWT·사용자 로그 — **확인됨 (1차 일부 제거)** | `ai/app/security/auth.py:30,40,65,74`: 토큰 prefix·전체 JWT payload·ID·이름 출력. `fe-web/src/pages/Join.tsx:93-95`: 토큰 prefix/응답 출력. `fe-web/src/pages/ClassroomList.tsx:1104`: 학생 배열 출력. `be/src/main/resources/application.yml:10,79-86`: 상세 health/DEBUG. `be/src/main/java/A704/DODREAM/file/service/PdfService.java:1240`: signed URL 로그. | 로그/브라우저 콘솔에 인증·개인정보·서명 URL이 남을 수 있음. 로그를 읽어 실제 노출 사실을 확인한 것은 아님. | 정적 확인. 기존 로그/실사용자 데이터 열람 NOT_RUN. 이번 웹 로그인 토큰/응답 로그 제거는 해소됨; 다른 debug 출력의 전면 점검은 남음. AI 인증 로그 제거 등 1차 변경은 최종 결과 문서 참조. |
| 12 | 공급자 주소·DB 경로·비밀 설정 결합 — **확인됨 (로컬 일부 분리)** | `ai/app/config.py:6,9-38`: dotenv·공유 JWT·외부 키, JWT 실패 시 빈 bytes. `ai/app/rag/service.py:31-42`: 공급자 주소·모델/Chroma 경로. `ai/app/rag/database.py:6`: 고정 컨테이너 SQLite 경로. `ai/app/document_processor/config.py:6-43`: 중복 설정/빈 키. `be/src/main/resources/application.yml:35-43`: Vault import. | 외부 키/특정 파일 경로 없이 기동이 어려운 결합. 키 디코드 오류를 빈 키로 계속 처리하는 경로는 fail-closed 검증 필요. 비밀값은 문서화하지 않음. | 정적 확인. 1차 local/test 공급자 분리·필수 키 검증·격리 볼륨은 복원 작업 결과로 따로 평가. 운영 전체 설정 정리는 미완료. |
| 13 | 실행 명세·테스트 부족 — **확인됨 (1차 보완)** | 기준 트리 `ai/`에 requirements/lock/Dockerfile 없음. `be/src/test/java/A704/DODREAM/DodreamApplicationTests.java:6-10` 단일 context test. `fe-web/package.json:6-10` dev/build/lint/preview만 있고 별도 test 없음. `python-service/test_y_coordinates.py:1`은 PDF 구조 수동 진단 스크립트. | 동일 환경 복원과 인증/접근정책 회귀 검증을 기존 명세만으로 보장하기 어려움. README/포팅 문서가 존재한다는 사실과 실행 재현 가능 여부는 구분. | 1차 lock 기반 npm 설치·타입검사·빌드 실제 실행 PASS. 나머지 신규 실행 명세/로컬 테스트 결과는 `03-phase1-results.md`. 포괄 보안/성능/정확도 검증은 미완료. |

## 판정 및 다음 단계

기준선은 위 정적 결함이 남아 있으므로 **SECURITY_BASELINE = FAIL**이다. 이 판정은 결함을 확인하는 테스트가 성공했다는 표현과 다르다. 보안 안전 정책을 충족했다는 PASS를 부여하지 않는다. 접근권한, token kind/수명, atomic refresh, 학생 응답 DTO 분리를 다음 단계의 선행 조건으로 둔다.

합성 로컬 데이터의 런타임 검증, 각 명령의 종료 코드, 첫 기동/재기동 결과는 [03-phase1-results.md](03-phase1-results.md)에 기록한다. 해당 결과에 실제 요청 증거가 없는 항목은 이 표의 정적 확인/NOT_RUN 상태를 유지한다. REAL_AI_INTEGRATION은 NOT_RUN, PUBLIC_DEPLOYMENT_READY는 false이다.

## 웹 복원 검증

검증 환경은 Node `22.14.0`, npm `10.9.2`, lockfile의 Vite `7.1.11`이다. 의존성 버전을 일괄 변경하지 않았다.

| 명령 | 종료 코드 / 상태 | 근거 |
|---|---|---|
| `cd fe-web && npm ci --ignore-scripts --no-audit --no-fund` | 1 / BLOCKED | sandbox의 기존 npm 로그 경로 쓰기 제한. |
| `npm ci --ignore-scripts --no-audit --no-fund --cache /private/tmp/dodream-phase1-npm-cache --fetch-retries=0 --fetch-timeout=15000` | 1 / BLOCKED | 전용 writable cache로 좁힌 뒤 npm registry DNS `ENOTFOUND` 확인. |
| 같은 명령의 `--fetch-timeout=30000` + 도구 network 승인 | 0 / PASS | lockfile 기반 302 packages 설치. 모델/서비스 호출 없음. |
| `npm run typecheck` | 0 / PASS | `tsc -b`; TypeScript 오류 0. |
| `npm run build -- --mode phase1` | 0 / PASS | 1,767 modules 변환. 기존 대형 chunk 경고는 남음 (오류 아님). |

`phase1` Vite 모드는 새 `fe-web/local-env/`만 envDir로 사용하여 기존 `.env*`를 읽지 않는다. `/api`와 `/ai`를 같은 origin으로 사용하고 `nginx.local.conf`가 Spring/FastAPI로 전달한다. local nginx와 local 개발 서버의 CSP는 외부 API·폰트·이미지 접속을 막는다. 따라서 로컬에서는 원격 폰트 대신 기존 CSS의 fallback 글꼴이 사용될 수 있다. UI 개편·모바일 설치/네이티브 빌드는 수행하지 않았다.


## 2-A 인증 수정과 실제 재검증 (2026-09-29)

위 1차 정적 근거와 `SECURITY_BASELINE=FAIL`은 당시 결과 그대로 보존한다. 체크포인트 `8414eec66d7acb5d37794b6f0fcb6f31d3acb48c` 이후 2-A 결과는 아래와 같고, 현재 전체 상태는 **SECURITY_REGRESSION_ALL=FAIL**이다.

| 기존 검사 식별자 | 1차 | 2-A | 실제 결과 |
|---|---|---|---|
| `be_refresh_must_not_authenticate_as_access` | FAIL | PASS | 새 RT로 Spring 보호 API →401 |
| `ai_refresh_must_not_authenticate_as_access` | FAIL | PASS | 새 RT로 FastAPI 보호 API →401 |
| `access_token_kind_claim` | FAIL | PASS | 새 AT의 token_use=access |
| `student_quiz_must_exclude_correct_answer` | FAIL | FAIL | 학생 응답200, correct_answer 존재 |
| `anonymous_file_url_must_be_denied` | FAIL | FAIL | 무토큰 파일 URL200 |
| `unshared_file_url_must_be_denied` | FAIL | FAIL | 비공유 파일 URL200 |
| `rag_unshared_document_must_be_denied` | FAIL | FAIL | 비공유 자료 RAG200, local provider |
| `rag_session_document_mismatch_must_be_denied` | FAIL | FAIL | 세션/자료 불일치 RAG200, local provider |
| `unrelated_teacher_history_must_be_denied` | FAIL | FAIL | 비담당 교사 이력 조회200 |

교사·학생·비담당 교사는 각각 **새 로그인**한 AT로 Spring/FastAPI 정상 접근 양성 대조군6개가 모두200이다. 잘못된 인증 때문에 객체권한 검사가 모두401인 결과를 개선으로 취급하지 않았다. 기존9개의 안전 기대값은 그대로이며, cookie POST에 CSRF bootstrap/header를 추가했다. 보조 수명 관측은86400→900초다. 기존3개 인증PASS, 남은6개FAIL, 양성대조6개PASS, 수명검사1개PASS로 security 실행 전체16개 중10PASS/6FAIL, exit1이다.

새 검증은 실제 JWT 파서/실제 Redis를 사용한다. HS256·키/claim 형식·issuer/audience·AT/RT 구분·5초 오차·jti, RT의 SHA256 v2 저장과 Lua 원자 회전, 12개 독립 HTTP 클라이언트×3라운드(매번200 한 개/401 열한 개), logout/refresh 경쟁3라운드, Redis 장애 시503/성공토큰 미반환, 유효하지 않은 비밀번호401, 쿠키/CSRF를 확인했다. 별도 Lettuce 클라이언트 두 개를 쓰는 Redis 통합 테스트도 포함한다. Web의 늦은401/로그아웃 경쟁과 native 오류의 RT 원문 전파를 회귀 테스트로 막았다.

검토 중 raw URI로 CSRF 경로를 비교하면 percent-encoded refresh/logout이 쿠키만으로200이 되는 새 구현 문제를 실제 재현했다. 최종 코드는 servlet의 decoded path로 CSRF/AT 필터 예외를 일치시켰고, 교사·학생 login/refresh/logout 인코딩 경로6개는 CSRF 없이403, 유효 CSRF가 있는 인코딩 refresh는200으로 재검증했다. 첫 실패 로그는 시각별 파일로 보존했다.

약12KB Authorization 헤더는 nginx에서400으로 거부되어 애플리케이션401까지 도달하지 않는다. 첫 테스트의401 고정 기대는 레이어 구분 오류였다. 최종 검사는 기존 식별자로 정확히 nginx400/토큰 미반환을 요구하고, 두 서버의 단위 테스트에서 정상 서명·정상 claim의8192자 초과 JWT가 직접 거부되는 것도 별도로 검증한다. 허용 응답 범위를 임의로 넓혀 통과시킨 것이 아니며 첫 FAIL 기록을 보존한다.

실제 명령·횟수·브라우저 범위·보장하지 않는 내용은 [05 결과](05-phase2a-results.md), 계약은 [04 설계](04-auth-security-design.md)를 따른다. 원시 JWT/RT/쿠키, DB 덤프, 기존 비밀 파일은 기록/커밋하지 않았다. 자료/RAG/정답/담당관계 수정, 실제 AI·외부 공급자 및 공개 배포는 수행하지 않았다.

## 2-B 객체권한 수정과 검증 (2026-09-29)

위 1차/2-A 표와 당시 FAIL은 그대로 보존한다. 2-A 체크포인트는 `ef91856cdc8a96c0e0d28a63e89f6efc8e85be3b`, 실행 범위 체크포인트는 `25466b6e2034038235bbd319871662499ecee205`다. 후속 객체 정책은 [07](07-authorization-policy.md), 최종 명령·브라우저·자원 판정은 [08](08-phase2b-results.md)에 기록한다.

| 기존 식별자 | 2-A | 2-B 최종 security | 응답/의미 |
|---|---|---|---|
| `be_refresh_must_not_authenticate_as_access` | PASS | PASS | RT →401 |
| `ai_refresh_must_not_authenticate_as_access` | PASS | PASS | RT →401 |
| `access_token_kind_claim` | PASS | PASS | token_use=access |
| `student_quiz_must_exclude_correct_answer` | FAIL | PASS | 유효 공유 학생200, correct_answer 없음 |
| `anonymous_file_url_must_be_denied` | FAIL | PASS | 무토큰401 |
| `unshared_file_url_must_be_denied` | FAIL | PASS | 학생의 교사용 파일 URL403 |
| `rag_unshared_document_must_be_denied` | FAIL | PASS | 비공유404 |
| `rag_session_document_mismatch_must_be_denied` | FAIL | PASS | 비공유 자료를 대입한 기존 검사404 |
| `unrelated_teacher_history_must_be_denied` | FAIL | PASS | 비담당 교사404 |

기존9개와 양성6개·수명1개를 유지한 security16개가 모두 PASS다. 원래 검사의 첫 실행은 목록 첫 항목을 공유 자료로 가정해 학생 퀴즈404로 FAIL이었다. 실제 공유 목록과 교사 목록의 교집합에서 합성 자료를 선택하도록 harness만 수정했다. 학생 응답200/정답 없음 기대와 기존9개 식별자·안전 기대 범위를 바꾸지 않았다. 두 자료 모두 접근 가능한 세션 교체는 추가 객체 검사에서 정확히409로 검증한다.

실제 객체 HTTP188개는 교사 소유/공유 학생 양성, User/Profile ID 구분, 비담당/타학교/같은 반 비공유, 원본·편집 JSON·정답 DTO·북마크·풀이/이력·공유 회수·담당 해제·삭제 자료 초기본·작업 소유권·문서 직접 처리 경계를 포함한다. 거부 요청 전후 MySQL checksum/행 수·SQLite 행 digest·합성 객체 digest가 같았다. Spring 실제 JPA 관계 테스트와 AI DB 테스트는 서명/저장소/FCM/채점/작업예약/검색 호출이 권한 거부 전에 발생하지 않는지 별도 검사한다. DB 조회 오류도 기본 허용으로 바꾸지 않는다.

확인한 범위에서 기존 지적4/5/6/7의 접근권한 조건을 수정했다. 실제 공급자 유출 공격을 수행했다는 뜻은 아니다. 운영 SSRF/redirect·전체 로그·배포 설정, LLM 품질, 서명 URL 즉시 철회는 미검증이다. 지적8(채점 트랜잭션/중복),9(임베딩 선삭제/복구),10(전체 SSRF),11(전체 로그),12(운영 설정),13(포괄 검증 부족)의 남은 부분과 모바일 저장매체/실기기는 별도 후속 작업이다. 과거 풀이 정답 버전과 원자적 업로드/발행/큐 복구도 보장하지 않는다.

`SECURITY_REGRESSION_ALL`은 **실행한 회귀 검사 범위의 통과만** 뜻하며 최종 상태는 08 문서를 따른다. `KNOWN_SECURITY_FINDINGS_OPEN=true`, `REAL_AI_INTEGRATION=NOT_RUN`, `PUBLIC_DEPLOYMENT_READY=false`를 유지한다.


## 3-A 채점 안정화 (2026-09-29~30)

과거 지적8과 당시 실패 증거는 보존하고 후속 채점 경로만 개선한다. [09 설계](09-grading-reliability-design.md)에 제출 키·고정 snapshot·버전·상태·복구·권한·DB 경계를, [10 결과](10-phase3a-results.md)에 최종 실제 명령·횟수·실패 원인과 미실행 범위를 기록한다.

기준2-B에서 새 합성2문항을 같은 본문으로 재전송하면 로그가2→4개가 됐고, 교사 정답 편집 뒤 기존 이력의 정답도 바뀌었다. 실제 재현과 정적 추론을 구분했다. 새 구현은 필수 UUID key와 실제 MySQL unique, 최초 정답/문제 snapshot, 버전 충돌, 트랜잭션 밖 공급자 호출, 엄격한 응답 검사, 결과·로그·상태의 원자 확정, 세대·기한 기반 제한 재시도를 사용한다. 모든 새 경로와 성공 replay는 현재2-B 권한을 재검사한다.

실제 경계 검사에서 NOT_SUPPORTED의 빈 synchronization 및 OSIV의 물리 연결 유지 문제를 발견해 호출을 차단했다. 안전 검사를 완화하거나 해당 요청을 PASS로 바꾸지 않았다. 채점 저장 작업의 EntityManager 수명을 분리하고 실제 물리 연결 상태까지 관측하는 수정과 재검증을 수행했다. 최종 채점 통합278개와 별도 공급자 대기 중 DB 조회6개가 PASS였다. 12개 클라이언트×3라운드에서 라운드별 attempt1/결과2/로그2/공급자 호출1을 확인했고 실제 Spring 재시작4구간도 통과했다.

기존 인증·권한 식별자와 양성 대조군을 유지한다. 학생 문제DTO에는 정답이 아닌 version만 추가한다. 직접 AI 채점의 이전 임의 자료/문항 본문은422로 거부되며, 내부 attempt 실행 capability와 고정 snapshot만 허용한다. 기존 입력 계약을 새 UUID/version에 맞춘 변경과 권한 기대 완화를 구분한다. 최종 Spring104/AI67/PDF6, 인증131/기동차단6/객체권한188/보안16, Chrome 인증17/교사UI권한18/채점API11이 PASS였다. 최초 Chrome 인증은 별도 short BE의 Redis 타임아웃으로 실패했으며 해당 프로세스 연결 복구 후 같은 검사로 통과했다. 실패·복구 근거를 포함한 실제 최종 판정은10문서 및 ignored 증거를 따른다.

대역 호출 횟수와 DB 확정 횟수를 분리한다. 정상 조건의 추가 채점 방지와 장애 복구 시 외부 중복 실행 가능성은 서로 다른 보장이다. 실제 AI 품질/요금/외부 exactly-once는 검증하지 않았다. `REAL_AI_INTEGRATION=NOT_RUN`, `KNOWN_SECURITY_FINDINGS_OPEN=true`, `PUBLIC_DEPLOYMENT_READY=false`를 유지한다. 임베딩 선삭제/전환 복구·전체outbox·SSRF·로그·운영 설정·모바일 저장소/실기기·공개 배포는 후속 범위다.

최종 자체 데이터 보존과 `CURRENT_MUTATION_SCOPE`는 PASS지만, 이번 새 전후 비교의 `CURRENT_EXTERNAL_ID_STABILITY`는 FAIL이다. ETCH 계열 외부6개 ID 교체와 별도2개 실행 상태 변화가 관측됐으며 원인 귀속은 UNVERIFIED다. strict isolation14 PASS/3 FAIL·종료1을 그대로 기록한다. 과거 실패를 소급 변경하거나 현재 전체 외부 보존을 PASS로 표시하지 않는다. 자세한 범위/증거는10문서를 따른다.

## 3-B 발행·색인 안정화 (2026-09-30)

과거 지적9와 당시 실패 기록을 보존한다. 새 전용 합성 인덱스에서 기존 경로의 정상1청크가 새 임베딩 실패 뒤0청크가 되는 문제를 실제 재현했다. 기존 자료의 정상 인덱스를 삭제해 재현한 것이 아니다. [11 설계](11-indexing-reliability-design.md)에 불변 입력·작업 원장·세대별 후보·검증 후 활성 전환·현재 권한과 조회 정책을, [12 결과](12-phase3b-results.md)에 최종 실제 검증·최초 실패·수정·미실행 범위를 기록한다.

색인 요청과 활성 포인터는 MySQL이 관리하며 발행과 작업 접수는 같은 짧은 트랜잭션에서 확정한다. 저장소 준비·해시 확인과 Redis 전송은 그 밖에서 수행한다. 큐에는 작업 UUID만 보내고 사용자 AT/RT·자료 원문·서명 URL을 넣지 않는다. 실제 Redis/Celery 워커와 Chroma 0.6.3 저장·query를 사용하되 임베딩/LLM/OCR/객체 저장/알림은 명시적 local 대역 또는 비활성이다. 기본 모델 다운로드나 저장소 오류의 파일 인덱스 우회는 허용하지 않는다.

검토에서 잠금 대기 후 SQLAlchemy identity map의 이전 값을 사용하는 문제와 Spring 재시도의 이전 권한 판정 사용 문제를 발견했다. 잠금 후 현재 원장·소유·삭제 상태를 다시 읽도록 수정하고 독립 연결 회귀를 추가했다. 같은 원본의 재색인 실패 때만 이전 활성 인덱스를 열람할 수 있으며, 새 원본과 일치하는 활성 버전이 없으면409, 저장소 장애는503이다. 현재 공유·담당·소유·삭제 검사를 우회하거나 초기 PDF를 학생에게 제공하지 않는다.

실제 Chroma pause 검사는 SDK 초기화가 제한을 설정한 연결을 새 무제한 연결로 교체하는 결함도 드러냈다. 고정한 0.6.3 SDK의 실제 HTTP transport와 Collection을 같은 연결로 묶어 수정했고, 실제 응답 정지에서5.02초 후503과 기존 pointer/digest 보존을 확인했다. 초기 실패 기록은 유지하며, 예외 주입 단위검사와 이 실제 저장소 장애 검사를 구분한다.

3-A의 채점 공급자 대기 중 독립 DB 조회6개는 이번 전체 grading 명령에 포함하며 중복 합산하지 않는다. 기존 인증·권한·채점 안전 기대값과 거부 전 무변경 검사를 유지한다. 실제 최종 상태와 횟수는12문서를 따른다. 보존 대상은 이번 시작 시 다시 수집한 원래 MySQL/SQLite 행과 객체 해시이며, 이전 단계 행 수를 복사하거나 기준선을 덮어쓰지 않는다.

과거 ETCH/3-A의 외부 ID 보존 FAIL과 원인 UNVERIFIED는 그대로 남는다. 이번 외부 ID/상태 전후 비교는 별도 판정이며 자체 변경 대상 gate와 혼동하지 않는다. 자동 후보 삭제/GC, 외부 모델 exactly-once, AI 품질·비용, HA/디스크 손실 복구, 전체 업로드/OCR/알림 원자성은 보장하지 않는다. `KNOWN_SECURITY_FINDINGS_OPEN=true`, `REAL_AI_INTEGRATION=NOT_RUN`, `PUBLIC_DEPLOYMENT_READY=false`를 유지한다.
