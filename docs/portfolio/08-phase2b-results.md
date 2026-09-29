# 08. 2-B 파일·자료·퀴즈·RAG 권한 결과

## 기준과 변경 구분

작업 경로: `/Users/yoonsu/Desktop/projects/DO-DREAM`. 시작 브랜치는 `codex/dodream-phase2a-auth`, 시작 HEAD는 `8414eec66d7acb5d37794b6f0fcb6f31d3acb48c`다. 팀 기준 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`의 기록은 보존하며 이 문서는 개인 개선이다.

- 2-A 검증 소스54개는 최종 SHA256/크기와 일치했다. 미검증 새 기능을 기존 PASS에 포함하지 않았다. `05-phase2a-results.md`에 후속 결정만 추가한 뒤 로컬 체크포인트 `ef91856cdc8a96c0e0d28a63e89f6efc8e85be3b`를 생성했다.
- 이후 `codex/dodream-phase2b-authorization`를 만들었다. 실행 범위 보강은 `25466b6e2034038235bbd319871662499ecee205`, 후속 안전 재기동 보완은 `9dd255b17f840d8897d7a3014e96987292d07ade`로 분리했다. 합성 범위검사33개와 실제 대상 metadata 검사 PASS를 확인했다.
- 2-B 최종 커밋/종료 상태는 아래 최종 기록에 적는다. 사용자 추가 파일 `docs/.DS_Store`는 읽거나 삭제하지 않고 stage/commit에서 제외한다.

2-A 원본 `.local/phase2a/results/`와 1차 `.local/results/`는 변경하지 않았다. 이번 증거는 `.local/phase2b/results/` 및 `.local/phase2b/review/`다. 토큰·cookie·비밀값·DB dump·원문 실행 로그·빌드 산출물은 커밋하지 않는다. 시도별 명령 로그는 시각별 파일에 남고 동일 이름 JSON/log는 최신 결과다.

## ETCH와 현재 범위

과거 ETCH6개의 ID 교체는 **HISTORICAL_EXTERNAL_ID_STABILITY=FAIL** 그대로다. 이름/상태 일치만으로 PASS를 주지 않는다. 최초 이번 조회는 Docker 연결 불가로 BLOCKED였고, 연결 복구 후 제한된 metadata와 종료 시각을 정한 lifecycle 이벤트를 읽었다. 지정 시간대 해당6개 이벤트는0개였으나 보존된 이벤트만으로 실행 주체를 확정할 수 없어 **EXTERNAL_CHANGE_ATTRIBUTION=UNVERIFIED**다. 상세 ID는 [06](06-resource-scope-review.md)를 따른다.

변경 전 snapshot은 자체9개 모두 exited, 외부33개, 전체 볼륨31개/네트워크12개였다. 현재 명령은 고정 project/file/directory와 정확한 라벨·서비스·기존 볼륨/네트워크·다른 프로젝트 공유 여부를 검증했다. 과거 원인 미확인과 현재 실행 범위를 분리했다. 한 차례 metadata 읽기 실패 시 해당 Redis TTL 읽기 전에 gate가 중단했고, 다시 현재 scope PASS를 확인한 후 인증 검사를 한 번 재실행했다. 실패 원인을 타 프로젝트 작업으로 귀속하지 않는다. 이후 진단은 실패한 Docker 하위 명령 종류/종료 코드만 기록하도록 좁게 보완했다.

## 구현

정책/상태코드/실제 FK 및 테스트 연결은 [07](07-authorization-policy.md)에 있다. JWT sub와 파일 업로더·자료 소유자·공유 학생은 User ID, 학급 배정 교사 FK는 TeacherProfile ID다. 양측 서버가 실제 관계를 따라 판정하며 클라이언트의 허용 플래그를 신뢰하지 않는다.

- Spring 공통 `AuthorizationPolicy`를 파일 URL/목록, PDF 원본·JSON·임시 저장·텍스트, 발행/라벨/삭제/공유, 문제 조회·저장·제출, 북마크·진도·성적·학생/학급 조회에 적용했다. 타인 객체는404, 부적격 역할403, 무인증401이다.
- 학생 문제 응답은 허용 필드 DTO다. 공유 JSON·북마크도 허용 구조로 다시 만들며 원본/교사 편집 파일 URL은 학생에게 발급하지 않는다. 제출 후에는 해당 문제의 서버 정답·피드백을 제공한다. quiz/material ID를 확인하며 위조한 studentId/score/정답은 채점·기록 소유자를 바꾸지 못한다.
- FastAPI는 실제 MySQL의 같은 관계로 문서/세션/학생 담당을 검사한다. 두 자료 모두 공유됐어도 기존 세션 자료를 바꾸면409다. `pdf_<UploadedFile ID>`와 양의 canonical Material ID만 허용한다. 작업 상태는 저장된 owner/document 연결을 확인하고 worker도 현재 권한을 재검증한다. 문서 직접 파서·개념 처리에도 파일 소유권을 적용했다.
- 학생 검색은 기존/신규 컬렉션 모두 content 유형만 사용하여 교사용 문제/정답 청크를 제외한다. 공유/담당 해제와 soft-delete는 다음 요청부터 반영한다. 일반 지식으로 답을 추론하는 것까지 방지했다는 의미가 아니다.
- Java의 기존 파일 컬럼 `s3key/jsons3key`를 실제 DB에서 확인해 Python mapping을 맞췄다. 기존 DB를 재생성/재소유하지 않았다. SQLite에는 작업 소유권 표만 additive하게 추가했다. local 저장 대역은 신규 합성 JSON만 쓰고 ai/worker는 기존 be-data를 read-only로 읽는다.
- 웹은 material/file ID 혼동을 제거하고 정상 소유자 편집을 유지한다. 모바일 계약은 학생 GET에서 정답을 제거하고 제출 응답의 서버 피드백만 결과 화면에 합친다. native helper 타입 검사만 수행했다.
- 같은 번호의 퀴즈 편집은 ID/FK를 보존한다. 풀이가 있는 문제 삭제는409로 중단한다. 신규 PDF 행이 commit되기 전 권한 조회되는 문제를 최소 조정하고 발행 후 임베딩 요청은 commit 뒤에 실행한다. 전체 비동기·멱등성·원자성 개편은 하지 않았다.

## 실제 명령과 증거

모든 manage 명령은 `python3 scripts/local/manage.py <명령>`이다. 웹 명령은 `fe-web`에서 실행했다.

| 명령 | 최종 종료 코드 | 실제 결과 | 증거 (results/ 아래) |
|---|---:|---|---|
| `scope-test` | 0 | 35 PASS (합성33 + 자체 임시 소켓2) | scope-unit.json/log |
| `config`, `scope`, `resources-before` | 0 | 설정·현재 범위 검증, 새 snapshot | compose-config.json, mutation-scope.jsonl, resources-before.json |
| `build`, `up` | 0 | 최종 소스 이미지/기동 성공 | compose-build.json, compose-up.json |
| `test` | 0 | Spring77 / AI48 / PDF6 PASS, skip0 | be-tests, ai-tests, pdf-tests JSON/log, unit-summary.json |
| `auth` | 0 | 131 PASS | auth-checks.json, auth-regression.json |
| `startup` | 0 | 잘못된 키 실제 기동6개 차단 PASS | startup-key-checks.json, startup-key-regression.json |
| `smoke` | 0 | 27 PASS | smoke-checks.json |
| `security` | 0 | 16 PASS (원래9+양성6+수명1) | security-checks.json |
| `authorization` | 0 | 188 PASS | authorization-checks.json |
| `npm run test:auth` | 0 | 웹/native helper25 PASS | web-auth-unit.json/log |
| `npm run test:authorization` | 0 | 계약9 PASS | web-authorization-unit.json/log |
| `npm run typecheck` | 0 | TypeScript 오류0 | web-typecheck.json/log |
| `npm run build -- --mode phase1` | 0 | 1,770 modules, 기존 chunk 경고 | web-build.json/log |
| native helper 제한 타입 검사 | 0 | 변경된 순수 계약/helper 범위 | native-authorization-helper-typecheck.json/log |
| `auth-test-up` | 0 | 전용 AT2초 서비스 기동 | auth-test-up.json |
| `npm run test:browser-auth` | 0 | 실제 Chrome17 PASS | browser-checks.json, browser-auth-command.json |
| `npm run test:browser-authorization` | 0 | 실제 Chrome18 PASS | browser-authorization-checks.json, browser-authorization-command.json |
| `persistence` | 0 | 8 PASS, 포트 반환 확인1개 추가 | persistence-checks.json |
| 추가 자료 보존 대조 | 0 | AUTHZ 자료 metadata·합성 JSON7개 hash 보존 | authz-data-preservation.json |
| `stop`, `status` | 0 | 자체9개 모두 원래 exited 복구 | compose-stop.json, compose-status.json |
| `isolation` | 0 | strict 기존16개 + 현재 scope1개 =17 PASS | resource-isolation-checks.json |

호스트 Spring 컴파일/단위60 PASS와 컨테이너 전체77 PASS를 중복 합산하지 않는다. AI 기존24개, Spring 기존53개, PDF 기존6개를 보존했다. 기존 보안9개의 이전/이후 표는 [security-evidence](security-evidence.md#2-b-객체권한-수정과-검증-2026-09-29)에 있다. 이전 인증3개 PASS 유지, 이전 객체6개 FAIL→PASS다. `security`의 비공유 세션 교체404와 `authorization`의 두 공유 자료 간 세션 교체409는 서로 다른 조건이다.

## 양성·우회·회수·무부작용과 최초 실패

실제 HTTP188개는 각 계정의 새 AT로 시작한다. 소유 교사, 같은 학교 비담당 교사, 다른 학교 교사, 직접 공유 학생, 같은 반 비공유 학생, CLASS 공유 학생, 다른 반/학교 학생을 사용했다. 교사와 학생의 User/Profile ID가 실제로 다름을 검사했다. 같은 합성 MySQL 관계를 Spring/FastAPI 모두 사용했고, 소유 파일 URL·원본 JSON·교사 정답·공유 학생 JSON/문제·직접/학급 RAG·초기본·정상 제출·자기/담당 이력은 성공했다.

부정 검사는 임의 파일/자료/quiz/session/task 대입, 잘못된 canonical ID, 다른 객체 URL, 비담당 학생, 모순된 공유 대상, 학생의 교사 API 접근을 포함한다. 공유 회수 뒤 JSON/문제/채팅/이력 상세는404, 목록에서는 제외됐다. 학생 현재 학급 연결을 해제해 담당 관계를 끊은 뒤 양쪽 서버와 교사 이력이 거부됐고 원래 연결을 복구했다. 별도 DB 테스트는 교사 배정 자체 해제도 검사했다. private 합성 자료를 일시 soft-delete한 뒤 초기본 접근/작업 예약이 거부되고 복구 후 정상화됨을 확인했다.

거부 요청 그룹 전후에 MySQL 대상 테이블 checksum/행 수, SQLite 세션/메시지/작업 행 digest, 신규 합성 JSON 파일 digest가 같았다. 실제 JPA/SQL 정책을 실행한 단위/통합 테스트에서는 서명·저장소·FCM·채점·작업예약·검색 경계의 호출0을 별도로 확인했다. HTTP 검사만으로 실제 AWS/LLM 호출을 관측했다고 주장하지 않는다. 권한 DB 예외의 안전한 실패는 오류 주입 단위검사이며 운영 DB 장애 시험은 아니다.

보존한 최초 시도:

- Docker 초기 metadata/event 조회 BLOCKED → 연결 복구 후 scope PASS. 반복 polling이나 Docker 전체 재시작을 수행하지 않았다.
- 첫 Java 컴파일은 소스 오류 후 수정했다. 호스트 최초 실패 원문은 파일 재사용으로 남지 않았고 tool 출력 기반 요약 한계를 `.local/be-phase2b-host-history.json`에 기록했다. 최종60/77 PASS 근거는 실제 로그다.
- 첫 객체 HTTP 검사154 PASS/3 FAIL: 학생 본인 이력 API의 teacher-only 누락2건을 구현 보완했다. 교사 목록에 본인 DRAFT가 포함되는 정상 계약을 잘못 제외한 새 테스트1건은 수정했다. 최종188개 모두 PASS.
- 첫 auth105 PASS/1 BLOCKED는 gate metadata 읽기 실패였다. 대상 확인 후131 PASS, 기능 기대값 변경 없음.
- 첫 security15 PASS/1 FAIL은 owner 목록 첫 자료를 공유 자료로 가정한 harness 문제였다. 실제 공유 자료를 명시적으로 선택하고 학생200/정답 없음 및 기존9개 식별자/안전 기대는 유지하여16 PASS.
- 첫 신규 Chrome 권한 검사13 PASS/1 FAIL은 editor 렌더링 완료 전 버튼 가시성을 확인한 harness 타이밍 문제였다. 렌더링 대기를 추가한 두 번째 검사는17 PASS와 복원 결과 출력의 status()/status 오타1 FAIL이었다. 서버 복원은 성공했고 다음 실행에서 원본 일치도 확인했다. 앱 소스 변경 없이 harness를 수정해 최종18 PASS/exit0이다. 두 실패의 시각별 결과를 보존했다.
- 첫 persistence는 stop1 PASS 뒤 포트 반환 전 scope gate에서 BLOCKED됐다. 후속 진단으로 포트가 반환됨을 확인하고, 실제 listener를 거부하면서 종료 연결 대기 상태를 허용하는 소켓 검사와 최대5초 반환 대기를 추가했다. 다른 프로세스를 종료하지 않았다. 최종 결과는 아래 기록에 따른다.

## 남은 범위와 한계

실제 인증/DB/Spring/FastAPI/Redis/Celery/SQLite를 사용했다. AWS/CloudFront/LLM/임베딩 모델/OCR/FCM은 표시된 local 경계 대역이거나 disabled다. Chrome 인증은 실제 브라우저지만 전체 앱 기능/E2E 전부를 뜻하지 않는다. 모바일 전체 설치·native 빌드·실기기는 NOT_RUN이다.

SSRF 전체 redirect/네트워크 정책, 전체 로그·운영 설정, HTTPS 배포, 실제 AI 품질, 모바일 보안 저장소, 이미 발급된 서명 URL의 즉시 철회는 남는다. 채점 중복/멱등성, 임베딩 버전/선삭제 복구, 업로드·발행·큐 실패의 원자성도 별도 후속 작업이다. 과거 StudentQuizLog는 정답 버전 snapshot이 없어 현재 Quiz 정답을 보여준다. 이번에 전체 처리 안정화나 공개 배포로 넘어가지 않았다.

## 최종 기록

최종 Chrome154.0.8037.58에서 인증17/권한18 PASS다. 인증 origin15174, 권한15173의 별도 테스트 프로필을 사용했다. 소유자 UI 편집·저장·재조회·Material ID 퀴즈 생성, 타교사의 실제 UI 읽기/생성/저장404 및 세션 유지, 공유 회수 후 학생 JSON/문제/채팅404를 확인했다. 원본 합성 JSON/문제/공유를 복구했고 Chrome을 종료했다. 외부 요청 관측0이며 스크린샷·trace·HAR·콘솔 수집은 하지 않았다.

재시작8개 PASS 이후 AUTHZ 자료 메타데이터와 새 합성 객체7개 digest도 일치했다. 기존 DB/Redis probe, SQLite 세션/대역 인덱스 보존을 확인했다. 최종 자체9개는 모두 시작 때와 같은 exited다. 외부33개의 기존 ID와 상태가 모두 유지됐고 기존 볼륨31개/네트워크12개가 보존됐으며 새 볼륨/네트워크는0개다. strict isolation17개 PASS, 관측한 runtime 로그에 JWT·생성 비밀값 패턴 없음도 확인했다. 관측 범위 밖의 영향 부재를 보장하지 않는다.

| 상태 | 최종 판정 |
|---|---|
| PHASE2A_CHECKPOINT | PASS — ef91856 체크포인트 |
| HISTORICAL_EXTERNAL_ID_STABILITY | FAIL — 과거 ETCH6개 ID 교체 유지 |
| EXTERNAL_CHANGE_ATTRIBUTION | UNVERIFIED — 과거 원인; 이번 window 변경0개에 대한 attribution은 NOT_APPLICABLE |
| CURRENT_MUTATION_SCOPE | PASS — 현재 metadata 및 실행 전 gate |
| CURRENT_EXTERNAL_ID_STABILITY | PASS — 이번 외부33개 ID/상태 유지 |
| OWN_DATA_PRESERVATION | PASS — 영속성8개 + 합성 객체7개 digest |
| AUTH_REGRESSION | PASS — 131 + 기존 Chrome17 |
| OBJECT_AUTHORIZATION | PASS — 실제 HTTP188 및 DB/단위/Chrome 범위 |
| STUDENT_QUIZ_RESPONSE | PASS — 허용 DTO/공유 JSON/북마크/검색/제출 피드백 |
| RAG_AUTHORIZATION | PASS — 실제 관계/세션/작업/회수/초기본 |
| SECURITY_REGRESSION_ALL | PASS — 실행한 회귀 검사 범위만 |
| KNOWN_SECURITY_FINDINGS_OPEN | true — 위 후속 범위 남음 |
| REAL_AI_INTEGRATION | NOT_RUN |
| PUBLIC_DEPLOYMENT_READY | false |

관련 최종 실패/미실행 때문에 숨긴 완료 항목은 없다. 모바일 전체/실제 외부 공급자/배포는 범위 밖 NOT_RUN으로 유지한다. 검토한 아래 경로만 stage하여 staged diff/비밀 후보/hash를 재확인한 뒤 `fix(authz): enforce resource ownership and scoped learning access` 로컬 커밋으로 기록한다. 정확한 최종 SHA는 사용자 최종 보고와 ignored `.local/phase2b/review/completion.json`에 남긴다. 사용자 `.DS_Store`는 미추적 상태로 보존한다. push/PR/merge/remote 변경/이력 재작성/공개 배포/터널은 수행하지 않았다.


## 2-B 커밋 대상 경로

- `ai/app/common/models.py`
- `ai/app/config.py`
- `ai/app/document_processor/router.py`
- `ai/app/local_providers.py`
- `ai/app/rag/models.py`
- `ai/app/rag/router.py`
- `ai/app/rag/service.py`
- `ai/app/rag/tasks.py`
- `ai/app/security/authorization.py`
- `ai/tests/runtime_fixture.py`
- `ai/tests/test_local_runtime.py`
- `ai/tests/test_object_authorization.py`
- `be/src/main/java/A704/DODREAM/authorization/AuthorizationFailure.java`
- `be/src/main/java/A704/DODREAM/authorization/AuthorizationFailureHandler.java`
- `be/src/main/java/A704/DODREAM/authorization/AuthorizationPolicy.java`
- `be/src/main/java/A704/DODREAM/authorization/StudentContent.java`
- `be/src/main/java/A704/DODREAM/bookmark/service/BookmarkService.java`
- `be/src/main/java/A704/DODREAM/config/SecurityConfig.java`
- `be/src/main/java/A704/DODREAM/file/controller/FileUploadController.java`
- `be/src/main/java/A704/DODREAM/file/controller/PdfController.java`
- `be/src/main/java/A704/DODREAM/file/service/PdfService.java`
- `be/src/main/java/A704/DODREAM/file/service/S3Service.java`
- `be/src/main/java/A704/DODREAM/file/service/TempPdfDataService.java`
- `be/src/main/java/A704/DODREAM/local/LocalAuthorizationFixtures.java`
- `be/src/main/java/A704/DODREAM/local/LocalDataSeeder.java`
- `be/src/main/java/A704/DODREAM/local/LocalExternalConfiguration.java`
- `be/src/main/java/A704/DODREAM/local/LocalObjectStore.java`
- `be/src/main/java/A704/DODREAM/local/LocalRuntimeFilter.java`
- `be/src/main/java/A704/DODREAM/material/controller/MaterialShareController.java`
- `be/src/main/java/A704/DODREAM/material/repository/MaterialRepository.java`
- `be/src/main/java/A704/DODREAM/material/service/MaterialShareService.java`
- `be/src/main/java/A704/DODREAM/material/service/PublishService.java`
- `be/src/main/java/A704/DODREAM/quiz/controller/QuizController.java`
- `be/src/main/java/A704/DODREAM/quiz/controller/StatsController.java`
- `be/src/main/java/A704/DODREAM/quiz/dto/GradingResultDto.java`
- `be/src/main/java/A704/DODREAM/quiz/dto/StudentQuizDto.java`
- `be/src/main/java/A704/DODREAM/quiz/entity/Quiz.java`
- `be/src/main/java/A704/DODREAM/quiz/repository/StudentQuizLogRepository.java`
- `be/src/main/java/A704/DODREAM/quiz/service/QuizService.java`
- `be/src/main/java/A704/DODREAM/report/controller/ProgressReportController.java`
- `be/src/main/java/A704/DODREAM/report/service/ProgressReportService.java`
- `be/src/main/java/A704/DODREAM/user/service/ClassroomService.java`
- `be/src/main/java/A704/DODREAM/user/service/StudentService.java`
- `be/src/test/java/A704/DODREAM/authorization/AuthorizationDatabaseTests.java`
- `be/src/test/java/A704/DODREAM/authorization/AuthorizationSideEffectTests.java`
- `be/src/test/java/A704/DODREAM/authorization/StudentProjectionTests.java`
- `be/src/test/java/A704/DODREAM/local/LocalExternalConfigurationTests.java`
- `be/src/test/java/A704/DODREAM/local/LocalObjectStoreTests.java`
- `compose.local.yml`
- `docs/portfolio/01-roadmap.md`
- `docs/portfolio/02-local-runbook.md`
- `docs/portfolio/07-authorization-policy.md`
- `docs/portfolio/08-phase2b-results.md`
- `docs/portfolio/security-evidence.md`
- `fe-web/package.json`
- `fe-web/src/pages/AdvancedEditor.tsx`
- `fe-web/src/utils/quizDocumentId.ts`
- `fe-web/tests/authorization-contract.test.ts`
- `fe-web/tests/browser-auth.mjs`
- `fe-web/tests/browser-authorization.mjs`
- `fe_app/src/api/quizApi.ts`
- `fe_app/src/api/submittedQuizResults.ts`
- `fe_app/src/screens/quiz/QuizScreen.tsx`
- `fe_app/src/types/api/materialApiTypes.ts`
- `fe_app/src/types/api/quizApiTypes.ts`
- `fe_app/src/types/quiz.ts`
- `scripts/local/manage.py`
- `scripts/local/verify.py`
- `scripts/local/verify_authorization.py`
