# 18. 포트폴리오 코드 최종 리뷰

> **현재 상태 안내 · 2026-10-08 확인:** 이 문서는 단계별 코드 검토·검증의 누적 기록이다. 현재 [공개 정적 데모](https://rladbstn1000.github.io/DO-DREAM/)는 [제출용 보완 공개 결과](21-original-ui-showcase-results.md#제출용-보완-공개-반영-2026-10-08)의 앱 SHA `888609661595d4cbef89de15097007453c871ca3`로 배포됐다. 이후 소스·문서의 원격 main은 `8767ec82b9818d96ea6b7a28a696475ab2122408`이며 앱 배포 SHA와 다르다. 이번 로컬 보완은 [근거·검사 후속 기록](#evidence-portability-2026-10-08)을 따른다. 아래 과거 미배포·NOT_RUN은 당시 상태를 보존한 것이며, 현재 공개 데모의 배포 완료를 취소하지 않는다.

2026-09-30, 팀 기준 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e` 이후의 개인 개선이다. 시작 브랜치 `codex/dodream-phase5-live-ai`, 시작 HEAD `e6410fda2df84c6e7fd0ab81d46c832e73f87318`를 실제 확인하고 새 `codex/dodream-portfolio-hardening` 브랜치에서 작업했다. 진행 중인 Git 작업은 없었으며, 기존 untracked `docs/.DS_Store`는 읽기·삭제·stage에서 제외했다. GitHub main을 로컬 코드의 대체 근거로 사용하지 않았다.

## 목표와 판정 경계

이번 목표는 실제 코드 리뷰 → 필요한 수정 → 키 없는 검증 → 문서화 → 검토한 변경의 로컬 커밋이다. 실제 공급자 호출·품질 평가·비용 측정은 현재 완료 조건에서 제외한다. 키가 없다는 이유로 코드 개선이나 정적 데모 준비를 막지 않는다. 공급자 adapter·오프라인 계약·고정 평가셋은 보존하며 `LOCAL_FAKE`가 기본이다. 키 존재에 따른 자동 활성화나 live 실패를 대역 성공으로 바꾸는 fallback은 허용하지 않는다.

| 판정 | 의미 |
|---|---|
| 프로젝트 코드 | 실제 Spring/FastAPI·DB·Redis·Chroma와 외부 경계 대역을 구분해 검증한 아래 범위 |
| 공개 정적 데모 | 분리 설계만 준비. 전체 구현·배포는 다음 작업이며 아직 실행하지 않음 |
| 전체 백엔드 운영 | 일반 PDF/OCR 운영 경로, 실제 외부 연결·HTTPS·운영 자격증명·백업 복구·관측을 포함한 운영 준비는 미완료 |
| 실제 AI | `REAL_AI_INTEGRATION=NOT_RUN` — 현재 범위 제외, 실제 요청 0 |
| 원격 CI | `REMOTE_CI_EXECUTION=NOT_RUN` — workflow 작성과 로컬 명령 검증을 원격 성공으로 표시하지 않음 |

[17 결과](17-phase5-results.md)의 NOT_RUN과 외부 자원 FAIL/UNVERIFIED는 소급 수정하지 않았다. 과거 외부 상태 변화의 원인 조사를 반복하지 않았다.

## 실제 검토 경로

문서 04~17의 계약을 소스·테스트와 대조했다. 테스트 개수만으로 안전을 판정하지 않고 입력이 저장·외부 요청·응답으로 이어지는 경로를 따라갔다.

| 영역 | 소스 경로와 확인점 |
|---|---|
| 인증·인가 | BE `auth/{util,service,controller,filter}`, `authorization/AuthorizationPolicy`; AI `security/{auth,authorization}`. JWT 종류·서명·현재 사용자, Redis 회전, CSRF·쿠키, 소유·담당·현재 공유, 학생 DTO를 확인 |
| 파일·자료 | BE `file`, `material`, local object store; AI `document_processor`, indexing source; PDF `main`, routers, analyzer/config. URL/식별자·파일 경로·제한·부분 성공·삭제/DB 경계를 확인 |
| 채점·색인 | BE `quiz/grading`, `indexing`; AI grading contract·provider·indexing store/worker/dispatcher/chroma. 고정 snapshot, 실행 세대, 외부 대기 전 연결 해제, 확정 전 권한·원본 재검사를 유지 |
| 웹·관련 앱 계약 | `fe-web/src/auth`, `student`, 교사 pages, `fe_app/src/api/{nativeTokenSession,interceptors,quizSubmission,submittedQuizResults}`. 인증 epoch·재시도·오류/저장소·HTML 경계 확인. 모바일 전체 설치·네이티브 기기는 제외 |
| 실행·재현성 | Compose·Dockerfiles·lockfiles·V003/V004·schema guards·scope gate·데이터 보존 스크립트·CI. 기존 볼륨과 새 스키마를 구분 |

## 발견·수정·보류

| 분류 / 항목 | 발생 조건과 변경 전 근거 | 선택·검사·결과 |
|---|---|---|
| 실제 결함: 공개 상태 정보 | [SecurityConfig](../../be/src/main/java/A704/DODREAM/config/SecurityConfig.java)의 `/actuator/**` permitAll + 일반 설정의 metrics/prometheus 노출, health detail always | 공개 GET health만 허용하고 상세/구성요소를 숨김. 다른 Actuator 차단, API 문서는 local/test만, 일반 CORS에서 localhost 제외. [SecurityExposureTests](../../be/src/test/java/A704/DODREAM/hardening/SecurityExposureTests.java)에서 실제 filter chain 검사. HTTPS·외부 방화벽 검증은 아님 |
| 실제 결함: 원시 PDF·JSON 무제한 읽기 | `PdfController`의 `@RequestBody byte[]`는 multipart 설정을 우회. S3 JSON `readAllBytes`와 미닫힌 stream도 존재 | [PdfInputPolicy](../../be/src/main/java/A704/DODREAM/file/service/PdfInputPolicy.java): teacher 확인 뒤 10MiB+1 bounded read, 파일명 255자·경로/제어문자·PDF signature 검사. [JsonRequestLimitFilter](../../be/src/main/java/A704/DODREAM/config/JsonRequestLimitFilter.java)와 [ObjectJsonReader](../../be/src/main/java/A704/DODREAM/file/service/ObjectJsonReader.java): 2MiB, 초과 413, object stream abort/close. [파일 회귀](../../be/src/test/java/A704/DODREAM/file/) |
| 실제 결함: 외부 PDF·파일 입력 | [PDF download_pdf](../../python-service/app/routers/pdf_structure.py)는 일반 모드에서 임의 URL·300초·전체 buffer를 허용, 업로드는 확장자만 검사. config는 dotenv/키 존재에 의존 | 현재 지원 경계를 명시적 local/test로 제한. 사용자 URL은 고정 fixture/소유 객체 경로만 처리하고 일반 외부 downloader는 연결 전 503. 자동 provider 활성화 제거. 10MiB 파일·100페이지·200만 추출문자, body 제한/15초 수신, MIME/path/signature 검사. [PDF 입력 회귀](../../python-service/tests/test_input_boundaries.py) 최초 6개 FAIL 재현 후 동일 안전 기대값으로 재검사 |
| 실제 결함: 오류·부분 성공 | PDF broad catch가 4xx를500으로 바꾸고 URL/서명 query·예외 원문을 응답/로그에 포함. analyzer가 페이지 실패를 건너뛰며 성공 반환 | HTTP 상태 보존, 정해진 오류 문구, close 보장, 부분 추출 실패 전파. 없는 table/OCR 기능 요청은 501. AI dormant PDF 경로도 503으로 닫음. BE signed URL/예외 원문 로그 제거 및 [ExceptionRedactionTests](../../be/src/test/java/A704/DODREAM/hardening/ExceptionRedactionTests.java) |
| 실제 결함: 교사 HTML 삽입 | `AdvancedEditor`의 병합 제목/입력 value, 생성 문제와 `ClassroomList`의 공유 자료·학생 이름 및 오류 원문을 HTML template에 직접 삽입 | [htmlText/htmlLines](../../fe-web/src/utils/htmlText.ts)로 일반 텍스트를 escape, API 오류 원문 대신 안내. 원본 template에 합성 제목을 넣었을 때 `<img>` 생성 FAIL을 기록. [실제 template 회귀](../../fe-web/tests/html-boundaries.test.ts)로 병합·문제·공유 표시와 로그 제한 검사. 에디터의 의도된 rich text 전체를 문자열 escape하지 않음 |
| 실제 결함: 자료/개인정보 진단 출력 | 교사 pages에서 parsed JSON·대화·학생 이름/성적·API body를 console에 출력 | 원문 출력 제거, 고정 오류 맥락은 유지. TXT를 HTML로 해석하지 않도록 변경하고 1MiB 제한. 지원하지 않는 파일에 더미 본문을 성공처럼 반환하던 `simulateExtract` 제거. 제품 API 오류에 showcase fallback을 추가하지 않음 |
| 실제 결함: 삭제 일관성 | `PublishService.deleteMaterial`이 S3 파일을 먼저 지운 뒤 DB soft delete를 확정. DB 실패 시 살아 있는 참조가 가리키는 파일 소실 | 권한 확인 후 논리 삭제만 수행. 저장 파일·불변 snapshot 보존, 물리 정리는 별도 정책. [ProgressAndDeletionTests](../../be/src/test/java/A704/DODREAM/hardening/ProgressAndDeletionTests.java)에서 DB 저장 실패도 외부 삭제 호출0 확인. 실제 기존 데이터 삭제는 실행하지 않음 |
| 실제 결함: 진도 입력 | null/음수/total0/초과 page 허용, 총페이지 변경 뒤 completedAt 유지 | 입력 범위 거부, 총페이지 변경에 맞춰 완료 상태 재계산. 과거 상한 초과 진도도 다음 정상 갱신에서 현재 총페이지 이내로 보정하며 기존 행을 일괄 수정하지 않음. 위 순수 회귀에서 잘못된 진도 무저장 확인. 클라이언트 보고 위치가 실제 이해도를 증명하지는 않음 |
| 측정된 병목 | 통계가 같은 material의 매 풀이에 `historyVisible`을 반복하고, AI 대화 이력이 매 메시지에 sources를 조회 | 아래 고정 데이터 측정 뒤 국소 개선. 요청 간 권한 캐시·새 큐·검색 엔진은 추가하지 않음 |
| 유지보수/방어 | 중복 PDF config·ambient provider key/SDK 로딩, 잠기지 않은 Gradle graph, CI 부재 | 공통 명시 config 사용, 현재 미지원 외부 PDF를 fail-closed, exact lock과 키 없는 CI. 기존 optional QA/채점 LIVE adapter는 비활성으로 보존 |

### 외부 요청 경계의 보장과 한계

현재 사용자/저장 URL이 임의 외부 네트워크로 연결되는 PDF 경로는 지원하지 않는다. BE/AI의 local 경로는 현재 권한으로 확인한 UploadedFile/Material 식별자 및 서버 소유 객체와 일치해야 한다. 독립 PDF 서비스의 고정 sample.pdf는 인증 없는 내부 합성 fixture이며 실제 자료의 권한 검증 경로와 구분한다. 현재 object store의 경로 탈출 거부와 별도로, 비활성 OCR 파일 도우미의 symlink 방어는 예방 개선이다. 스킴·포트·userinfo·query·fragment·IP 표현·IPv6·redirect/DNS 대역은 네트워크 호출 전 거부를 검사한다. 문자열 prefix나 DNS 한 번 확인으로 범용 SSRF를 해결했다고 주장하지 않는다. 비활성 일반 downloader에는 연결 시점 DNS 검증 구현이 없으므로 재활성화하려면 별도 설계·검증이 필요하다.

Chroma/MySQL/Redis 및 BE→AI는 사용자 URL 프록시와 구분되는 고정 내부 서비스 통신이다. 로컬 Compose는 내부망·nginx loopback 포트·scope gate를 유지한다. 선택 LIVE adapter는 고정 `api.openai.com`의 두 경로, TLS·redirect off·proxy off·기존 요청/예산 제한을 유지하지만 이번에 실행하지 않았다. 클라우드 metadata나 타 시스템으로 공격 요청을 보내지 않았다.

AWS SDK transport는 연결/획득 2초·read 5초, API 전체 15초/시도 10초·재시도0을 설정했다. [StorageTransportTimeoutTests](../../be/src/test/java/A704/DODREAM/hardening/StorageTransportTimeoutTests.java)는 실제 잠긴 SDK transport와 자체 loopback 정지 응답으로 read timeout 약 5초를 확인했다. AWS 연결·stream 전체 수신의 절대 15초 상한·write timeout의 실제 동작까지 입증한 검사는 아니다. 일반 WebClient 연결 2초/read 5초, CloudFront 호출 block 15초를 별도로 설정했다.

PDF 파일 signature/크기/페이지/텍스트 제한은 native parser 한 페이지 내부의 CPU·메모리 소비를 완전히 제한하지 못한다. Tomcat idle timeout도 slow-drip 요청의 절대 총시간 보장이 아니다. 공개 운영에는 worker 자원 격리·reverse proxy 요청 제한·속도 제한 검증이 추가로 필요하다.

### 의도적으로 남긴 항목

- 현재 controller 참조가 없는 팀 `OcrProcessService`의 긴 트랜잭션·부분 OCR 실패 처리: 팀 역사를 지우지 않았다. 재활성화 전 상태 전이·재시도·원자성 범위를 별도 설계해야 한다. 현재 local 제품 경로에서 호출하지 않는다.
- 통계의 전체 풀이 로딩, 자료/세션 목록의 다자료 권한 조회·pagination: 출력/커서/권한 계약에 영향이 있어 이번에는 확인한 반복 쿼리만 줄였다. 대량 데이터 운영 성능은 미검증이다.
- 일반 PDF/OCR 및 AWS/Firebase 실제 연결, 운영 secret·HTTPS·백업/복구·관측·기기 접근성은 미검증이다. 정적 showcase의 준비와 합산하지 않는다.
- 브라우저 localStorage/MMKV의 토큰 저장 위험은 잔존한다. 현재 서버 확인·권한 검사와 렌더링 결함 수정을 저장매체의 완전한 보호로 표현하지 않는다.

<a name="query-measurement-baseline"></a>

## 고정 합성 데이터 성능 검사

| 경로 / 조건 | 변경 전 | 변경 후 | 출력·권한 대조 |
|---|---:|---:|---|
| 실제 MySQL 통계, 자료1·문제2·풀이20, 1차 캐시 clear, fixture insert 제외. 자료별/전체 통계를 각각 측정 | 각각85 SELECT/statement | 각각9 | 총문제2·시도20·정답률50%, 현재 공유 회수 뒤 결과 없음. fixture 트랜잭션 rollback |
| 임시 SQLite 실제 JWT/DB policy 이력20·provenance10·legacy10 | history23 + authority7 SELECT | history3 + authority7 SELECT | 메시지 내용·순서·mode10·빈 sources 및 공유 회수404 대조 |

**비교 기준 보완 (2026-10-08):** 팀 기준 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`의 이 통계 경로에는 이후 추가한 현재 자료 권한 조회가 없었다. 개인 권한 강화 `eba04683a263b4a0fd327d428c1a4b3d693aee53`에서 풀이 로그마다 같은 자료의 권한을 조회하는 비용이 생겼고, `81ce22fcf60cd9a25513d096b6425216e0f46534`에서 같은 요청 안의 자료별 결과를 재사용하도록 개선했다. 다음 요청은 현재 공유·담당 관계를 다시 확인한다. 권한 강화 과정에서 생긴 반복 조회를 줄인 성과이며, 팀 기준 코드와의85→9 비교가 아니다.

이번에는 재측정하지 않고 당시 원시 로그·실행 metadata를 대조했다. `.local/portfolio-hardening/results/statistics-before-2026-09-30T104952789426+0000.log`는 `materials=85 overall=85`, `be-hardening-tests-2026-09-30T105333544480+0000.log`는 `materials=9 overall=9`이며 모두 자료1·문제2·풀이20이다. 해당 JSON의 실행 HEAD는 둘 다 `e6410fda2df84c6e7fd0ab81d46c832e73f87318`이고, **미커밋 작업 소스 digest**는 각각 `9a1ae0e6d2e5b4bfdf9268480d48aa388529112c3b7c1a8e0912ea72e4a20208` / `310cd30f37e2e7d05bfc5f8ee3f5f9008dc728bd62ad2bb85ba130dbdd4cb532`다. 권한 강화 커밋 자체나 깨끗한e6410fd checkout을 정확한85회 측정 소스로 표시하지 않는다. 당시 명령은 scoped `be-test`의 `gradle --no-daemon --offline test --tests '*StatisticsQueryDatabaseTests' --rerun-tasks --info`(변경 전)와 선택 hardening tests(변경 후), 각각 종료0이었다.

[현재 검사](https://github.com/rladbstn1000/DO-DREAM/blob/8767ec82b9818d96ea6b7a28a696475ab2122408/be/src/test/java/A704/DODREAM/hardening/StatisticsQueryDatabaseTests.java#L28-L70)의 관측값 출력과 회귀 상한 `≤12`는 별개다. 상한은10~12로 늘어나는 변화까지 잡지 않으며 이번에 수정하지 않는다. AI 이력은 **history23→3, 권한 포함 전체30→10**의 기존 보고 수치로 구분한다. 이번 통계 원시 로그 대조나 브라우저 검사로 AI 수치를 재측정했다고 주장하지 않는다.

통계는 [QuizService.visibleHistory](../../be/src/main/java/A704/DODREAM/quiz/service/QuizService.java)에서 호출 내 material별 권한 결정만 재사용한다. [StatisticsQueryDatabaseTests](../../be/src/test/java/A704/DODREAM/hardening/StatisticsQueryDatabaseTests.java)는 같은 데이터·권한·출력으로 비교한다. AI는 [get_student_chat_session_history](../../ai/app/rag/router.py)의 source LEFT JOIN과 [test_history_queries](../../ai/tests/test_history_queries.py)로 비교한다. 이는 로컬 쿼리 수이며 지연 시간·처리량·실사용자 성능 개선 수치가 아니다.

## 스키마와 새 환경 재현성

자동 migration platform을 새로 도입하지 않았다. `V003__grading_attempts.sql`, `V004__indexing_ledger.sql`을 선택한 새 schema에 먼저 적용하고, 팀 도메인은 현재 entity의 JPA `ddl-auto=update`로 만든다. `GradingSchemaGuard`/`IndexingSchemaGuard`는 필요한 열·unique가 없으면 startup을 거부한다. SQL의 재실행 안정성과 JPA 이후 실제 DB 제약을 확인한다. 이 절차는 전체 팀 스키마의 역사별 V001/V002 마이그레이션을 보유했다는 뜻이 아니다. 운영에서 자동 DDL을 검증된 전진 마이그레이션으로 교체하는 일은 별도 검토다.

이번에는 기존 `dodream_local`과 구별되는 새 `dodream_portfolio_hardening_fresh`를 생성했다. 이미 존재하면 reset하지 않고 거부한다. scope gate는 이 정확한 schema와 `dodream-phase3b-hardening-fresh`라는 disposable Spring 프로세스 조합만 허용한다. 새 schema도 삭제하지 않는다. 실제 첫 기동에서 JPA 이후39개 테이블과 건강 상태를 확인했다. 이후 검사대상8개 테이블에서 필수 unique10·FK4·활성 CHECK5(V004 소속)·non-null60개 및 ASCII binary 비교/긴 본문/legacy nullable 계약을 대조하고, V003/V004 재적용 전후 metadata가 동일함을 확인했다. 최초 기동 증거의 옛 `healthy_after_migration_before_jpa` 필드는 이름과 달리 JPA 완료 이후 관측값이며, 검증 코드의 필드명을 바로잡았다.

```bash
export DODREAM_RESULTS_DIR=.local/portfolio-hardening/results
python3 scripts/local/indexing_migration.py fresh-prepare-hardening
python3 scripts/local/verify_fresh_indexing_schema.py --hardening
python3 scripts/local/verify_fresh_indexing_schema.py --hardening-inspect
```

`--hardening-inspect`는 이 작업에서 만든 정확한 새 schema의 제약을 조회하고 V003/V004를 재적용해 metadata가 유지되는지 확인한다. 기존 `dodream_local`을 대상으로 실행할 수 없다. 위 prepare는 한 번만 실행한다. 실행한 DB를 매번 삭제·재생성하지 않는다. 일반 첫 기동에서도 `data-up`으로 MySQL/Redis/Chroma 시작 → V003/V004 적용 → Spring 시작 순서가 필요하다. 기존 볼륨에서 성공한 검사를 빈 환경 성공으로 대신 기록하지 않는다.

## 의존성과 CI

정확한 버전은 [웹 lock](../../fe-web/package-lock.json), [AI lock](../../ai/requirements.local.lock.txt), [PDF lock](../../python-service/requirements.local.lock.txt), [Gradle lock](../../be/gradle.lockfile)에 고정한다. 아래 버전은 manifest 범위가 아닌 실제 lock 기준이다. 무검토 major upgrade, `audit fix --force`, 전역 설치는 사용하지 않았다. 컨테이너 base image는 tag, Python runtime은 minor 버전이며 모든 image/wheel을 digest로 고정한 것은 아니다. exact 앱 의존성 graph를 전체 이미지의 비트 단위 재현성으로 표현하지 않는다.

| 대상 | 실제 변경 | 공식 근거와 도달 조건 |
|---|---|---|
| Vite | 7.1.11 → 7.3.5 | [dev server 경로 제한](https://github.com/vitejs/vite/security/advisories/GHSA-fx2h-pf6j-xcff). 로컬 dev server와 nginx static bundle을 구분 |
| React Router | 7.9.4 → 7.18.2 | [untrusted path](https://github.com/remix-run/react-router/security/advisories/GHSA-wrjc-x8rr-h8h6), [후속 RSC 수정](https://github.com/remix-run/react-router/security/advisories/GHSA-qwww-vcr4-c8h2). 현재 BrowserRouter에서 RSC는 사용하지 않음 |
| Tiptap | 3.7.2 → 3.30.5 | [DOM 속성 경계](https://github.com/ueberdosis/tiptap/security/advisories/GHSA-cp6q-959q-f8rh), [Markdown](https://github.com/ueberdosis/tiptap/security/advisories/GHSA-j95f-988m-3j2f). 편집기 속성 경계는 관련 가능, Markdown parser 직접 입력은 없음. 실제 exploit 재현으로 표시하지 않음 |
| PDF framework/parser | FastAPI0.104.1/Starlette0.27.0/multipart0.0.6/httpx0.25.2 → 0.116.1/0.47.3/0.0.30/0.28.1 | endpoint 이전 multipart parser 도달. [Starlette rollover](https://github.com/encode/starlette/security/advisories/GHSA-2c2j-9gv5-cj73), [multipart](https://github.com/Kludex/python-multipart/security/advisories/GHSA-5rvq-cxj2-64vf). 호환 FastAPI/TestClient 묶음과 exact lock 수정 |
| AI framework/core | FastAPI/Starlette → 0.116.1/0.47.3, LangChain core0.3.79 → 0.3.85 | [LC serialization](https://github.com/langchain-ai/langchain/security/advisories/GHSA-c67j-w6g6-q2cm). 현재 Document/messages 사용, 외부 serialized load/dump 경로는 없어 core 갱신은 예방 조치 |
| Spring Security/Tomcat | 6.5.6 → 6.5.9 / 10.1.48 → 10.1.60 | [HeaderWriterFilter](https://spring.io/security/cve-2026-22732/), [HTTP/1.0 reverse proxy](https://tomcat.apache.org/security-10.html#Fixed_in_Apache_Tomcat_10.1.60). servlet/filter·nginx 경로가 관련되어 Boot 전체 변경 대신 두 BOM property만 override |

`npm audit`는 초기 영향 패키지19개(high14/moderate4/low1) → 최종14개(high9/moderate3/low2)다. 고유 advisory 수가 아닌 **영향 패키지 노드 수**이며 잔여0을 주장하지 않는다. 남은 목록은 @babel/core, @humanfs/node, ajv, baseline-browser-mapping, brace-expansion, browserslist, esbuild, flatted, js-yaml, minimatch, nanoid, picomatch, postcss, rollup이다. nanoid는 docx 기본 길이21/PostCSS 상수6 호출로 현재 사용자 지정 길이가 없고, 나머지는 빌드/lint/dev 도구 경로로 현재 HTTP 본문이 전달되지 않는다. 개발 도구 자체가 안전하다는 뜻은 아니며 후속 lock 갱신 때 재점검한다.

Starlette의 [urlencoded form 제한](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq)은 1.3.1 수정이지만 무검토 major 전환 대신 현재 유일한 UploadFile endpoint에서 비-multipart를 parser 이전415로 거부하고 전체 body를 제한했다. 다른 form endpoint를 추가하면 재검토해야 한다. PyMuPDF1.23.8의 native parser 전수 검사는 미완료이며 확인한 [CLI embedded_get advisory](https://github.com/advisories/GHSA-cxqh-p2w9-fmr7)는 더 새로운 영향 버전·현재 미사용 경로다. [PDFBox](https://pdfbox.apache.org/security.html)의 확인한2026 traversal은 examples ExtractEmbeddedFiles 경로이며 현재 core Loader와 구분했다. Spring Framework6.2.12의 [versioned filesystem resource](https://spring.io/security/cve-2026-41843/)·[self-populating List binding](https://spring.io/security/cve-2026-59282/) 조건은 현재 설정/DTO에서 찾지 못했다. 공식 목록 조회와 입력 경로 검토는 전수 취약점 검사와 다르다. JVM/Python 전체 transitive scanner는 실행하지 않았고, wheel의 OpenSSL/native parser 전체 안전성·선택 AWS/Firebase 라이브러리 전체를 보증하지 않는다.

[필수 workflow](../../.github/workflows/keyless-ci.yml)는 Java17/Node22.22.0/Python3.11, lock 설치·단위/계약·타입·빌드를 사용한다. DB가 필요한 전체 검사는 [수동 workflow](../../.github/workflows/keyless-integration.yml)로 분리했다. [CI runner](../../scripts/ci/integration.py)는 GitHub-hosted Linux와 workspace/run identity를 확인한 뒤 고유 project를 만들고, 내부망·게시 포트 없음·tmpfs MySQL/Redis/Chroma를 사용한다. 로컬 fixed project/volume/env를 복사하지 않는다. V003/V004 initdb 선적용 뒤 실제 JPA 전체 테스트와 서비스 probe를 실행하도록 구성했다.

필수 BE 선택 명령은 초기 `A704...` 패턴이 Gradle의 대문자 simple-class 추론에 걸려 0개 검사 FAIL이었다. `*A704...`로 고쳐 실제 14개 클래스·92개 검사를 통과했다. 이후 추가된 진도 회귀는 최종 전체 BE 묶음으로 검증한다. 전체 테스트가 통과했다는 이유로 선택 명령까지 성공으로 가정하지 않았다.

권한은 `contents: read`, checkout credentials 보존 없음, 외부 actions는 공식 tag의 확인한 commit SHA로 고정한다. 배포/cloud login/secret 필요 step과 DB·원문 로그·사용자 artifact 업로드는 없다. 명령·YAML·scope guard 로컬 검증과 GitHub 실제 실행은 구분하며 원격은 NOT_RUN이다.

## 다음 정적 showcase의 최소 경계 (설계만)

| 현재 의존성 | 다음 구현 위치와 계약 |
|---|---|
| `main.tsx`→BrowserRouter→`App.tsx`→`StudentSessionProvider`가 실제 서버 identity에 의존 | 같은 프로젝트에 명시적 `vite build --mode showcase`, `dist-showcase/`, 상대 asset base `./`, `envDir: false`로 기존 dotenv 탐색 차단, API env 상수·개발 proxy 없음, showcase 전용 HashRouter entry를 둔다. `phase1`의 real auth tree를 import하지 않도록 build entry에서 선택한다. GitHub Pages subpath와 새로고침을 hash route로 처리한다. |
| `student/api.ts`·auth client의 실제 `/api`·`/ai` 요청 | 공통 화면에 필요한 자료함/본문/질문/제출 결과 port를 추출하고 real adapter와 sample adapter를 entry에서 명시 선택한다. catch에서 adapter를 바꾸지 않는다. 독립 프런트 프로젝트나 가짜 API 서버는 만들지 않는다. |
| 실제 JWT·`VerifiedRoute`·`session/me` | showcase는 `authRole/accessToken/isLoggedIn`을 쓰지 않고 시연 역할 선택만 제공한다. 역할을 실제 인증/권한이라고 표시하지 않는다. |
| 공유자료·질문·제출·진도 | 직접 작성한 공개 가능 sample module, `dodream.showcase.v1.*` browser 임시 state, 명시 초기화. 기존 DB dump·이력·raw 로그 export 금지. 추천 질문·준비 답변·예시 채점과 참고 발췌에 모의 동작 표시. |
| 제출 당시 실제 snapshot·정답 비노출 | showcase 예시 정답은 클라이언트에 포함될 수 있음을 명시한다. 이를 실제 학생 DTO 정책에 재사용하거나 실제 채점 검증으로 주장하지 않는다. |
| 외부 기능 | 외부/API 호출0 동작을 기본 기대값으로 하며 TTS는 가용 로컬 voice만 선택. 실제 AI key·운영 backend는 불필요. 빌드/라우팅/샘플 adapter·표시 경계만 이번에 설계했고 제품 코드의 대규모 분리는 수행하지 않음. |

후속 검증 조건은 서버 없이 직접 링크/새로고침·역할 전환·본문·질문·예시 채점·임시 상태 초기화가 동작하고, 네트워크 API/가짜 JWT 생성이 0인 것이다. 실제 API failure가 있으면 real mode에서 오류로 남아야 한다. 실제 정적 데모 구현·공개 배포에 자동 착수하지 않는다.

## 이력서·면접에서 설명할 세 사례

1. **인증과 현재 객체권한**: 토큰 유효성만으로 파일·자료·학생 이력 소유권을 보장하지 못했다. 공통 JWT 계약과 Redis 원자 회전 뒤 각 요청에서 현재 소유/담당/공유를 확인하도록 선택했다. 역할만 확인하거나 토큰에 권한을 오래 캐시하는 대안보다 DB 조회가 늘지만 권한 회수를 반영한다. [JWT/refresh](../../be/src/main/java/A704/DODREAM/auth/service/RefreshTokenService.java), [BE 정책](../../be/src/main/java/A704/DODREAM/authorization/AuthorizationPolicy.java), [AI 정책](../../ai/app/security/authorization.py), [DB 권한 회귀](../../be/src/test/java/A704/DODREAM/authorization/AuthorizationDatabaseTests.java)와 [AI 회귀](../../ai/tests/test_object_authorization.py)를 연결한다. 실제 HTTPS·기기 저장소 보안까지 검증한 것은 아니다.
2. **제출 멱등성과 당시 기준**: 재전송·동시 제출이 결과를 중복 반영하고 문제 변경이 과거 풀이 의미를 바꿀 수 있었다. 학생+key unique와 고정 문제/정답/답안 snapshot, 짧은 접수·확정 트랜잭션을 선택했다. 외부 대기를 DB 트랜잭션에 묶지 않는 대신 dispatch 이후 불명을 UNKNOWN으로 남겨 명시적 복구가 필요하다. [GradingAttemptService](../../be/src/main/java/A704/DODREAM/quiz/grading/GradingAttemptService.java), [GradingStore](../../be/src/main/java/A704/DODREAM/quiz/grading/GradingStore.java), [경쟁/DB 회귀](../../be/src/test/java/A704/DODREAM/quiz/grading/), [웹 제출](../../fe-web/src/student/submission.ts)을 연결한다. 외부 AI exactly-once/과금 중복 방지·모델 정확도를 보장하지 않는다.
3. **후보 검증과 활성 인덱스 전환**: 새 색인 실패가 기존 정상 검색을 훼손하거나 오래된 실행이 최신 원본을 덮을 수 있었다. 원본 revision·실행 generation별 후보를 만들고 검증 후 현재 DB 포인터만 바꿨다. 단일 컬렉션 in-place 교체보다 저장공간·상태 관리가 늘지만 실패 후보와 기존 활성본을 분리한다. [IndexingStore](../../be/src/main/java/A704/DODREAM/indexing/IndexingStore.java), [worker/store](../../ai/app/indexing/worker.py), [contract](../../ai/tests/test_indexing_contract.py), [실행 재현](../../scripts/local/verify_indexing.py)을 연결한다. 과거 16개 장애 시나리오는 [12 결과](12-phase3b-results.md), 이후 선택 회귀는 [17 결과](17-phase5-results.md)이며 이번에 전부 재실행했다고 주장하지 않는다.

## 실행 결과와 보존

원시 로그·DB 내용·개인 이력은 공개하지 않고 명령·종료 코드·범위·실패 원인 및 최종 결과만 기록한다. 로컬 증거는 `.local/portfolio-hardening/results`의 시간별 파일과 `commands.jsonl`로 기존 결과와 분리한다.

시작 기준선: 자체 컨테이너11개 모두 exited, 외부66개 모두 exited, 자체 영속 볼륨5개. 원본 MySQL40테이블/4260행·SQLite1050행·객체631개·Chroma434컬렉션/1406청크를 읽기 전용 hash로 기록했다. 기존 행·객체·컬렉션은 삭제하거나 초기화하지 않는다.


### 이번 실행 묶음

로컬 서비스·데이터 검증은 저장소 루트에서 `DODREAM_RESULTS_DIR=.local/portfolio-hardening/results`를 지정했다. 독립 도구 검사도 같은 증거 폴더에 출력을 보존했다. 호스트 Node22.14.0/Python3.9.6과 이미지의 Java17·Gradle8.14.3/Node22.22.0/Python3.11을 구분했다. 아래 PASS는 이번 실행이고, 이전 단계 숫자를 재실행 결과에 합산하지 않는다.

| 명령 / 층 | 종료 코드·결과 | 실제 범위 |
|---|---|---|
| `manage.py config`, `data-up`; scoped `compose build` | 각각0 PASS | 잠금 의존성으로 BE/test·AI/worker/dispatcher·PDF·웹 이미지 빌드. worker/dispatcher는 실행하지 않음 |
| `manage.py test`와 동일한 scoped `be-test`, AI/PDF unittest 명령 | 각0, BE177·AI183·PDF24 PASS | BE32개 suite에서 실패/오류/skip0, 실제 MySQL/Redis와 최종 진도 보완 포함. Python은 임시 SQLite/통제 transport, 양쪽 `pip check` 0 |
| `npm --prefix fe-web run test:auth`, `test:authorization`, `test:grading`, `test:indexing`, `test:student`, `test:hardening` | 각0, 합계115 PASS | 순서대로25/9/19/20/36/6. 기존 모바일 token·제출 계약 포함, 네이티브 빌드 아님 |
| 웹 `typecheck`, `build -- --mode phase1` | 각0 PASS | same-origin local bundle. 500kB 초과 chunk 경고는 남음 |
| `manage.py auth` | 0, 131 PASS | 실제 Spring/FastAPI JWT·Redis 회전/경쟁·CSRF·native, Redis 장애503 후 복구 |
| `node fe-web/tests/browser-hardening.mjs` | 최종0, 13 PASS | Chrome의 실제 학생 bootstrap→자료→질문→출처/이력→퀴즈→결과 재조회, 타 사용자/교사 API 거부. 교사 병합 modal에는 합성 browser state만 넣고 DB 저장 없음. 외부 요청0 |
| `python3 -m unittest discover -s scripts/local/tests -v` | 최종0, 101 PASS | 기존98개와 새 schema 계약3개. 명령·대상 범위 gate와 도구 계약, 실제 전체 장애 회귀와 구분 |
| `scripts/ci/tests`, `scripts/evaluation/tests` unittest | 각각0, 6/26 PASS | CI 격리·오프라인 평가 도구. YAML3개 parse0, 실제 공급자 품질평가 아님 |
| 필수 CI BE 선택 명령과 동등한 Gradle8.14.3 명령 | 최종0, 92 PASS | lock image에서 bootJar/testClasses/14개 순수 클래스 재실행. GitHub wrapper 다운로드와 원격 환경 실행 아님 |

빠른 재현은 웹 여섯 test script·typecheck·phase1 build 및 위 Python tooling unittest로 시작한다. 서버 검사는 [02 runbook](02-local-runbook.md)의 첫 기동/SQL 순서를 따르고 `manage.py test` → `auth`를 순차 실행한다. Browser hardening 검사는 `demo-up`/`demo-prepare`로 이미 준비한 현재 샘플, 기본 web15173, 기존 Chrome/Playwright가 필요하다. 실행당 새 합성 학생 하나만 추가하며 기존 자료를 편집하지 않는다. 이번 harness 보정 2회와 최종 1회를 합쳐 학생3명·각 새 대화/풀이를 보존했다. 신규 합성 기록과 테스트가 만든 객체도 정리 명목으로 삭제하지 않는다.

### 실패·미실행 기록

- 변경 전 PDF 안전 기대값 6개, AI history 쿼리 상한, 원본 웹 template escape 검사는 실제 FAIL(exit1)을 남긴 뒤 같은 기대값을 재검사했다. 통계 전후는 동일 합성 조건에서85→9를 측정했다.
- 구현 도중 final class를 상속하려던 Java 테스트 compile FAIL, 제거한 오류 원문 변수의 TypeScript 참조 FAIL은 각각 실제 stream mock 방식과 참조 정리로 수정했다. 잘못된 작업 디렉터리에서의 npm 실행254도 성공 기록으로 바꾸지 않았다.
- 로컬 도구 최초 98개 중2개는 sandbox의 loopback bind 거부로 환경 BLOCKED(exit1)였다. 허용된 자체 loopback 실행에서98개를 통과했고 원 실패 파일을 보존했다.
- Browser harness는 교사 로그인 화면 전환 누락과 실제 email 필드가 `type=text`인 선택자 차이로 두 번 timeout(exit1)했다. 매번 학생11개 흐름은 통과했으며 제품 안전 기대값을 완화하지 않고 UI 선택자를 수정해13개를 통과했다. 결과 파일은 wrapper 명령 메타데이터와 겹치지 않는 `browser-hardening-checks.json`에 둔다.
- CI 선택자0개 FAIL은 위와 같이 수정했다. 새 schema 상세 검사의 첫 precheck도 MySQL CHECK 표시에서 `OCTET_LENGTH`가 동의어 `LENGTH`로 보이고 quote가 escape되는 차이로 FAIL이었다. 의미가 같은 표시만 정규화했고 `CHAR_LENGTH`는 여전히 거부하며, 누락/비활성 제약을 허용하지 않았다.
- 원격 GitHub Actions, 전체 재시작 persistence, 16개 색인 장애 묶음, 실기기 접근성, 실제 외부 공급자·AI 품질·비용·HTTPS·운영 배포는 이번에 NOT_RUN이다. 변경하지 않은 무거운 장애 회귀를 전부 반복하지 않았으며 과거 검증은 각 원본 보고서에 남겼다.


### 종료 시 데이터 대조

`python3 scripts/local/student_demo_data.py after`는 exit1이었다. 엄격한 원본 모든 열 hash 비교49항목 중48개가 PASS이며, `local_demo_catalogs` 한 행의 hash만 달랐다. 이를 전체 PASS로 바꾸지 않았다. 기존 MySQL 행 중4259개는 그대로이고, 원본 SQLite1050행·객체631개·Chroma434컬렉션/1406청크는 모두 동일했다.

별도 SELECT 대조에서 신규 `local_demo_visitors`가 정확히3행 늘었고, 현재 phase5 카탈로그의 `visitor_count`만3을 뺀 값으로 원래 방식의 SHA256을 계산하면 카탈로그2행의 최초 hash와 모두 일치했다. [LocalDemoStore.start](../../be/src/main/java/A704/DODREAM/demo/LocalDemoStore.java)의 신규 체험 학생 생성 시 카운터 증가와 일치하며, 다른 카탈로그 열이 변경되지 않았음을 함께 확인했다. **엄격한 원본 hash 판정은 FAIL, 의도한 방문자 카운터 증가만 존재한다는 원인 대조는 PASS(exit0)**로 분리한다. 카운터·신규 학생·대화·풀이를 이전 값으로 되돌리거나 삭제하지 않았다. 이 대조는 새 DB 행을 계속 덮어쓰는 테스트를 허용한다는 뜻이 아니다.

hash 검사는 기존 데이터를 훼손하지 않았는지 대조하는 절차다. 재시작 내구성 전용 `persistence`를 이번에 재실행했다는 근거로 사용하지 않는다.


이번에 시작한 자체 서비스7개만 검증한 ID로 중지해 자체11개 모두 최초 `exited` 상태로 복구했다(exit0). `manage.py isolation`도 exit0으로 외부66개 컨테이너의 ID·이름·상태, 기존 볼륨/네트워크, 자체5개 영속 볼륨, loopback 게시 포트·내부망·로그 민감값 검사와 실행 범위를 통과했다. `CURRENT_MUTATION_SCOPE=PASS`, `CURRENT_EXTERNAL_ID_STABILITY=PASS`, `EXTERNAL_CHANGE_ATTRIBUTION=NOT_APPLICABLE`이다. 이 helper의 `OWN_DATA_PRESERVATION=NOT_RUN`은 재시작 persistence 영수증이 없기 때문이며 위 별도 hash/카운터 대조 결과로 덮어쓰지 않는다. 과거 외부 FAIL/UNVERIFIED는 그대로 보존했다.

검토한 소스·설정·테스트·문서84개 파일만 명시 경로로 stage해 이 보고서와 함께 로컬 커밋한다. 비밀 설정·DB·raw 로그는 ignored 영역에 유지하고 `docs/.DS_Store`는 읽기·삭제·stage에서 제외한다. 실제 AI/OCR/AWS/Firebase 기능 호출0, API 키 탐색·읽기·설정0, push·PR·merge·공개 배포·터널·클라우드 생성0이다. `REAL_AI_INTEGRATION=NOT_RUN`, `REMOTE_CI_EXECUTION=NOT_RUN`이며 다음 showcase 구현에 자동 착수하지 않는다.

## 채용 제출용 보완 (2026-10-08)

`codex/dodream-portfolio-polish`에서 기존 main `bce567b5afd8fdef45958dbb2edd16f90cc5b973`을 기준으로 로컬 보완했다. README는 서비스/샘플 → 팀 당시 역할과 개인 개선 → 채점·인증·색인 문제/결정/결과 → 화면·팀 당시 아키텍처 → 실행 → 검증 한계 → AI 활용/상세 근거 → 기존 팀 기록 순으로 재배치했다. 위 세 사례와 기존 측정값을 재사용했고 팀원 표·6명 역할·원본 이미지를 보존했다. ChatGPT의 문제/대안/계획 검토, Codex의 구현/테스트 실행/문서 초안, 사용자의 범위·원본 UI 방향 결정과 변경/보고/화면 검토를 구분했다. AGENTS는 유지보수 안내로 갱신하되 데이터·비밀·외부 호출·별도 원격 승인 규칙을 유지했다. 새 사례 문서·대규모 파일 이동·새 기능은 없다.

시작 화면 h1/비활성 복제 접근성, 작은 소개·GitHub 링크, 1024px 메모 라벨과 키보드 초점을 보완했다. 실제 원인·두 배경/경계 폭 검사·전후 캡처·과거 실패 보존은 [21번 후속 기록](21-original-ui-showcase-results.md#채용-제출용-제목메모-보완--로컬-검증-2026-10-08)에 있다. 이 수정은 과거 공개 검사 범위를 소급 변경하지 않으며 현재 공개 사이트에 배포하지 않았다.

**대표 코드 포맷은 별도 변경이다.** `GradingStore.java`는 들여쓰기·줄바꿈만 정리해 javac17 lexer의 2,577개 토큰(SQL·문자열 원문과 순서 포함), 전후 `javap -c -p` 명령 출력이 동일했다. 줄번호 debug metadata는 바뀌므로 class 파일 자체가 동일하다고 주장하지 않는다. `StudentExperience.tsx`는 기존 Prettier3.6.2 설정을 사용했고, JSX 끝 공백 3곳을 같은 문자열 표현식으로 보존했다. TypeScript5.9.3 transpile 결과의 중첩 AST6,883노드·문자열714개가 전후 동일했다. 메서드 추출·SQL text block/상수화·JPA 전환·상태/트랜잭션 순서 변경은 없다. [09번 JDBC 근거](09-grading-reliability-design.md#jdbc-선택-근거--제출용-사후-검토-2026-10-08)는 현재 SQL의 실행 순서·조건부 갱신, JPA 대안과 수동 매핑 부담을 사후 검토로 설명한다. OSIV 분리/복원은 JDBC 선택과 별개이며 성능 비교 실험을 주장하지 않는다.

| 이번 실행 명령·검사 | 종료 코드·결과 |
|---|---|
| `DODREAM_SHOWCASE_EVIDENCE=portfolio-polish npm --prefix fe-web run verify:showcase` | 0/PASS — 타입·두 모드 빌드, 계약66/서버40, 독립 Chrome244, 정적 요청153/금지 요청0 |
| `npm --prefix fe-web run test:auth`, `test:authorization`, `test:grading`, `test:indexing`, `test:student`, `test:hardening` | 각각0/PASS, 합계115; 실패·skip0 |
| `node --test fe-web/tests/pages-release.test.mjs` | 0/PASS, 기존 Pages 계약8 |
| 기존 Prettier의 StudentExperience 단일 파일 `--check`, TS 의미 AST/문자열 비교 | 각각0/PASS; 별도 학생/원본 상태49도 PASS(위 수에 합산하지 않음) |
| Java17·기존 Gradle8.14.3 `bootJar testClasses test` — `GradingContractTests`, `GradingAcceptanceRaceTests`, `GradingWiringTests` 선택 | 0/PASS, 컴파일·관련 단위/계약16, 실패·skip0 |
| 실제 DB 채점 장애/복구 회귀·Docker·실제 AI·음성 청취·VoiceOver·네이티브 앱 | NOT_RUN — 포맷만 변경해 DB/서비스 실행 불필요, 과거 PASS로 대체하지 않음 |

Java 최초 실행의 sandbox 소켓 차단/누락된 잠금 의존성은 BLOCKED, 기존 `*Tests 2.class` 중복 산출물의 로딩 실패와 임시 init-script 상대 경로 오류는 FAIL로 남겼다. 기존 산출물을 삭제하지 않고 필요한 잠금 버전 의존성만 받아, 새 ignored buildDirectory에서 같은 검사·기대값으로 최종 성공했다. 구조/의존성 lock/빌드 설정은 바꾸지 않았다. 실제 최종 전체 명령과 단계별 종료 코드·검사 XML은 `.local/portfolio-polish/java/verification.json`, `java/isolated-grading-checks-final.log`, `java/isolated-build/test-results/test/`에 있다. 그 밖의 명령은 `web-regressions.json`, `Student-format/commands.json`, `Student-format/equivalence.json`에 기록했다.

과거 문서/캡처는 보존하고 09·18·21에는 후속 구역만 추가했다. 검토한 경로만 UI·문서·포맷의 로컬 커밋으로 구분한다. push/PR/merge/재배포는 NOT_RUN이다. 미추적 `.DS_Store` 파일은 읽기·삭제·stage에서 제외했다. 이번 검증 서버·브라우저는 종료했으며 데이터·외부 자원은 건드리지 않았다. `REAL_AI_INTEGRATION=NOT_RUN`, `BACKEND_PRODUCTION_READY=false`, `BACKEND_DATA=NOT_TOUCHED`를 유지한다.


### 제출용 보완 공개 후속 (2026-10-08)

위 로컬 보완 `ac08ba1…`을 사용자가 승인해 [PR #6](https://github.com/rladbstn1000/DO-DREAM/pull/6)과 필수 CI·일반 merge를 거쳐 공개 반영했다. README의 팀 기여·AI 활용 설명과09번 JDBC 사후 근거를 포함한다. 실제 앱 배포 SHA는 `888609661595d4cbef89de15097007453c871ca3`이며, 공개177개와 이번 원격 manifest/공개13파일 대조를 통과했다. 최초 CI 실패·검사 교정·artifact 연결·한계는 [21번 공개 후속](21-original-ui-showcase-results.md#제출용-보완-공개-반영-2026-10-08)에 있다. 위 당시 PENDING·미배포/미실행 기록은 보존하고 후속 문서 SHA를 앱 배포 SHA로 표기하지 않는다.

<a name="evidence-portability-2026-10-08"></a>

## 근거 연결과 브라우저 검사 재현성 보완 (2026-10-08)

시작 checkout `31cb748cf59032c276f3923e34cfa5db1bd0066e`는 fetch한 main `8767ec82b9818d96ea6b7a28a696475ab2122408`의 조상이며 tree가 같았다. 진행 중 merge/rebase는 없었다. 후자의 SHA에서 `codex/dodream-evidence-portability`를 만들었다. 현재 배포 run `37722185194`의 성공과 앱 SHA `888609661595d4cbef89de15097007453c871ca3`를 원격에서 다시 조회했고 배포는 실행하지 않았다.

README의 세 사례는 공개 main 전체 SHA의 코드·검사 줄 범위와 기존 결과 구역을 연결한다. 채점의 [HTTP 경쟁·독립 DB 경쟁·mock 구분](09-grading-reliability-design.md#claim-evidence-grading), 인증의 [Lua 회전·객체 권한 구분](04-auth-security-design.md#claim-evidence-auth), 색인의 [Java 접수·Python 검증/활성 전환 구분](11-indexing-reliability-design.md#claim-evidence-indexing)을 기존 설계 문서에 뒀다. 코드 구간을 직접 읽어 의미와 범위를 대조하고 공개 SHA 내 경로·줄 범위 및 결과 anchor를 별도로 검사했다. 새 anchor는 [GitHub의 명시 anchor 규칙](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#custom-anchors)을 따른다. 과거 채점·색인·Redis 수치는 해당 단계 보고서의 근거이며 이번에 전체 재실행한 결과가 아니다. 통계는 위 [원시 로그 대조](#query-measurement-baseline)와 구분한다.

고정 코드 구간30개와 신규 상대 링크28개의 목적지·범위를 검사했고 별도 의미 검토도 통과했다. README 팀 기록은 본문·순서·제목 문구를 보존한 채 하위 제목 단계만 내렸으므로 기존 anchor는 바뀌지 않았다. 18·20·21의 앞부분에는 기준 날짜와 현재 앱/문서 버전을 구분했다.

7종 `fe-web/tests/browser-{auth,authorization,grading,indexing,student,demo-disabled,hardening}.mjs`의 로컬 수정안은 미선언 `playwright`·개인 캐시 fallback을 없애고 잠긴 `playwright-core`1.62.1을 명시 import한다. 작은 `chrome-launch.mjs`가 명시 Chrome 실행 파일 검증/미지정 installed Chrome channel을 담당하며 shell 실행·자동 다운로드·사용자 프로필 재사용은 없다. 잘못된 명시값은 다른 브라우저로 넘어가지 않는다. 기존 API·대기·쿠키·CSRF·timeout 기대값은 유지했다. `DODREAM_RESULTS_DIR`로 원본 결과와 plan을 새 실행 폴더에 분리하고 작은 정책·재유입 검사를 기존 `test:hardening`에 연결했다. 패키지 버전·lock·CI/workflow는 그대로다. **통합 검증과 데이터 보존이 완료되지 않아 검사 코드의 완료 커밋은 보류한다.**

개인 환경 없는 검증은 `/private/tmp/dodream-evidence-wf9f6_cz/after`의 현재 수정 파일 사본에서 실행했다. `.env`·DB·기존 `.local`은 복사하지 않고 `env -i`로 `PATH`, 임시 `HOME`·`TMPDIR`만 전달했다. `npm ci --ignore-scripts --no-audit --no-fund --cache <전용-임시-cache>` 종료0, `NODE_PATH`·`NODE_OPTIONS`·`DODREAM_PLAYWRIGHT_PATH` 없음, 실제 ESM resolve는 사본 안의 `node_modules/playwright-core/index.mjs`/1.62.1이었다. 상위/전역 모듈과 사용자 캐시를 삭제·이동·차용하지 않았다. Node22.14.0/npm10.9.2, 설치된 Chrome154.0.8037.98을 사용했다.

| 이번 실행 / 조건 | 결과와 경계 |
|---|---|
| 실제 Chrome launch smoke | 기본 channel과 명시 실행 파일 각각 새 context에서 자체 loopback 페이지 열기·버튼·닫기 PASS. 빈 값·상대경로·없는 파일·실행 불가 파일은 설정 오류로 거부, 외부 페이지 요청0 |
| `npm run test:hardening` | 종료0,12 PASS: 기존6 + 통제된 실행 파일 정책·재유입 계약6. Chrome 없는 환경의 오류 분류는 대역 검사이며 실제 Chrome 실행과 별개 |
| `node --test tests/pages-release.test.mjs` | 종료0,8 PASS. 기존 Pages 계약이며 원격 CI 실행이 아님 |
| `npm run verify:showcase` | 종료0,타입·계약66·두 빌드·정적 경계·브라우저244 PASS. API·외부 요청·마이크·WebSocket·CSP 위반0, 과거 통과 수와 합산하지 않음 |
| 같은 환경의 앱 산출물 비교 | 공개 main 사본과 현재 수정 사본의 별도 `build:showcase`:13파일/6,721,625bytes, 모든 상대경로·bytes·SHA-256 동일. 기존 dist의 사용자 복제 파일을 삭제·덮어쓰지 않음 |
| 실제 `npm --prefix fe-web run test:browser-auth` | 종료0,17 PASS/외부 요청0. 기존 AT2초 서버와 현재 수정 harness,05:04:58–05:06:03 UTC. 실제 API 검사이며 패키지 smoke와 구분 |
| 나머지 실제 통합 브라우저6종 | 아래 데이터 보존 실패로 중단. authorization·grading·hardening은 NOT_RUN. student는 기존 샘플의 문제/발행 revision 변경, demo-disabled는 현재 활성화된 short 서버 교체, indexing은 기존 launcher의 이미지 재조정이 보존 조건과 충돌해 BLOCKED. 검사 삭제·skip·기대값 완화 없음 |

**데이터 보존 실패와 실행 중단:** 기존 scope 단위 검사101 PASS와 실제 scope gate를 통과하고, 시작 시 자체11개·타 프로젝트67개 컨테이너가 모두 중지임을 확인했다. 원래 데이터는 MySQL40테이블/4,659행·SQLite1,068행·객체640개·Chroma434컬렉션/1,406청크였다. 하지만 검증 준비 중 worker·dispatcher를 기동한 것은 기존 대기 작업을 먼저 차단하지 못한 **이번 실행의 오류**다. 05:04:22 기동 직후 기존 작업30행·자료 상태27행이 바뀌었고, 새 ACTIVE execution27개와 컬렉션27개/청크51개가 생겼다. 기존 자료27개의 활성 포인터가 이번 새 실행을 참조함을 확인했다. 신규 fixture 준비나 발행 API는 실행하지 않았으며 이 변화는 허용된 테스트 방문자 카운터 변화가 아니다.

기존 실행457개의 행 hash, 원본 SQLite·객체·Chroma434컬렉션/1,406청크는 일치했지만 **엄격한 보존49항목 중47 PASS/2 FAIL**(index_jobs30행, index_resources27행)을 그대로 남긴다. 현재 실행484개·컬렉션461개이며 새 결과는 삭제하지 않았다. baseline이 행 hash만 담았으므로 각 행의 이전 상태·이전 활성 포인터 값은 복원해 주장할 수 없다. 변경된 작업의 현재 상태는 SUCCEEDED27/REVOKED3이다. worker·dispatcher를05:06:10–05:06:20에 중지하고 추가 데이터 검사를 중단했다. DB를 추측으로 복구하거나 baseline을 바꿔 PASS로 만들지 않았다. `BACKEND_DATA=CHANGED_BY_VALIDATION`, `DATA_PRESERVATION=FAIL`이다.

브라우저 수정은 패키지·Chrome smoke와 인증 경로까지만 실제 확인했다. 전체 통합 완료가 아니므로 코드10파일(7종 검사·helper·정책 검사·package script)은 미커밋으로 남기며, 독립 검토한 README·기존 문서만 로컬 커밋한다. runbook의 새 실행 정책도 로컬 수정안임을 명시한다. 공개 entry/UI/CSS/샘플/이미지·폰트, 제품 Java/Python·DB 스키마, lock·Pages workflow의 Git diff는 없다. 이는 **제품 소스 불변** 판정이며 위 런타임 데이터 보존 FAIL과 구분한다.

05:12:03 UTC 종료 대조에서는 컨테이너78개의 ID·이름·상태·라벨·이미지 태그가 최초와 같았다. 자체11개 모두 중지, 타 프로젝트67개 불변, 볼륨61개·네트워크23개도 일치했다. 기존 컨테이너를 교체하지 않았으며 브라우저·임시 HTTP 서버는 각 실행의 finally에서 닫았다. 인증은 기존 컨테이너 이미지와 현재 수정 harness의 실행으로, 백엔드 이미지를 이번 소스에서 새로 빌드했다고 주장하지 않는다. 이 자원 복구 PASS는 DB 변경을 되돌렸다는 뜻이 아니다. 상세 대조는 `integration/results/integration-outcome.json`, `data-preservation.json`, `background-impact-summary.json`, `resources-restored-exact.json`에 있다. scope 단위 검사의 최초 sandbox loopback 차단과 읽기 전용 진단 실패도 원본에 보존했다.

| 상태 | 판정 |
|---|---|
| CLAIM_EVIDENCE_MAPPING | PASS — 코드 의미와 경로·줄/anchor 별도 대조 |
| BROWSER_DEPENDENCY_PORTABILITY / BROWSER_LAUNCH_SMOKE | PASS_ISOLATED / PASS — 로컬 수정안, 통합 완료 커밋 보류 |
| AFFECTED_INTEGRATION_CHECKS | PARTIAL_BLOCKED — 인증17 PASS, 나머지6종 미완료; 데이터 보존 FAIL |
| CURRENT_STATUS_CLARITY / METRIC_BASELINE_CLARITY | PASS / PASS — 과거 수치·원시 대조·현재 참조 버전 구분 |
| PRODUCT_AND_SHOWCASE_UNCHANGED | PASS — 제품 소스·동일 환경 앱13파일 불변, 런타임 데이터와 별도 |
| REMOTE_CI_EXECUTION_THIS_CHANGE / push·PR·merge | NOT_RUN / NOT_RUN |
| PAGES_REDEPLOYMENT | NOT_REQUIRED_UNCHANGED_APP |

상세 증거는 ignored `.local/evidence-portability/`와 그 `integration/results/`에 분리한다. 요약은 원시 실행 증거를 대신하는 새 독립 검사로 취급하지 않는다. 원격 CI 실행·push·PR·merge는 NOT_RUN, `PAGES_REDEPLOYMENT=NOT_REQUIRED_UNCHANGED_APP`이다. 기존 공개 데모 승인·배포 완료는 유지한다. 실제 AI·음성 청취·VoiceOver·네이티브 앱은 이번에도 NOT_RUN이다.

<a name="evidence-portability-safe-resume"></a>

### 안전 정리와 통합 재개 조건 (2026-10-08)

문서 커밋 `dde553e2d15f678bae1986dc94914e955a3fc8ee`와 미커밋 검사10파일을 확인했다. 이번 정리는 저장된 파일·소스와 필요한 Docker 상태 메타데이터만 읽었다. 기존 서비스 start/up/restart, worker·dispatcher, DB·Redis·Chroma 접속, 통합 검사·복구·삭제·큐 정리·dump·볼륨 복제는 실행하지 않았다. 현재 판정은 **BACKEND_DATA=CHANGED_UNEXPECTEDLY, DATA_PRESERVATION=FAIL, RECOVERY_EXECUTED=false**다. 위 당시 `CHANGED_BY_VALIDATION` 표기와 실패 원본은 보존하며, 원인 미확인 외부 변화로 재분류하지 않는다.

**실제 실행 경로:** `integration/results/commands.jsonl`의5행은05:04:22.185390–05:04:22.533453 UTC에 기존 web·web-auth-test·index-dispatcher·worker의 **4개 ID를 직접 지정한 `docker start`**다. 접두부는 순서대로 `2ee13f903f6d`, `747f49a71245`, `b5dc18999787`, `fe52c08ab649`이며 전체64자리 argv는 해당 행과 `integration-browser-services-start.json`에 있다. 데이터3서비스 → AI → before hash → BE/PDF/short-BE → 이 직접 start → auth 순서였다. `manage.py`의 `run→record` 형식으로 실제 argv·종료값이 저장됐지만 최상위 일회성 호출 스크립트 원문은 이 증거 목록에 없어 추정하지 않는다. **이번 사건에 전체 Compose up이나 의존성 자동 기동을 사용했다는 기록은 없다.** 별도로 공개 기준 `manage.py:268–275`의 `up/demo-up`은 서비스 목록 없는 Compose up이며 worker·dispatcher가 기본 목록에 있다는 정적 위험은 남는다.

직전 `mutation-scope.jsonl:89`는05:04:21.824674 UTC의 **operation=config PASS**이고 해당 직접 시작을 operation=start로 검증한 기록은 없다. [scope gate](../../scripts/local/scope_guard.py)의 `_gate()`는 대상 소유권·구성·마운트·네트워크를 확인하고 결과에도 metadata-only 한계를 명시한다. 기존 작업 처리·데이터 변경 허가를 검사하지 않는다. 이를 데이터 보존 승인으로 취급한 실행 판단 오류였다. [dispatcher](../../ai/app/indexing/dispatcher.py)가 호출하는 `store.claim_deliveries()` → `indexing-v3` 전송 → worker의 후보 생성·검증 → `activate()`가 현재 코드 경로다. DB 전체의 QUEUED/PROCESSING 후보를 읽으므로 사후 Redis 큐 길이0은 DB outbox가 비었다는 증거가 아니다.

**저장된 영향 대조:** jobs545→545·resources400→400이지만 원래 행 hash가 각각30개·27개 불일치한다. 현재 필드 진단에는 SUCCEEDED27/REVOKED3과05:04:23.625389–05:04:27.395818 갱신 시각이 있다. 실행457→484 중 새 ACTIVE27개를 기존 자료27개가 참조하고, 컬렉션434→461·새 청크51개다. 원래 실행457행·SQLite1,068행·객체640개와 기존434컬렉션/1,406청크의 내용 보존은 **활성 포인터 보존과 다르다**. `data-preservation.json`, `index-preservation-diagnosis.json`, `background-impact-summary.json`, `physical-additions-summary.json`, `chroma-preservation.json`을 대조했으며47 PASS/2 FAIL 판정을 유지한다. 개별 작업의 상세 이벤트 로그와 변경 전 필드값은 확보되지 않아 작업별 전이 과정을 추가로 만들어 쓰지 않는다.

**복구 원값: 현재 확보하지 못함.** 위 증거 목록의 `data-before.json`은 컬럼 이름과 SHA256별 개수, `chroma-before.json`은 이름·UUID·청크 수·hash를 담지만 자료→이전 active_execution_id 대응이 없다. 진단파일은 변경 후 값이다. 해시·현재값·generation-1·가까운 옛 컬렉션으로 이전 값을 역산하지 않는다. 이후 복구 검토에는 영향 job30/resource27의 정확한 이전 상태·포인터·카운터/lease/시각과 원래 execution/collection 대응, 소비자 정지·재처리 방지 조건이 먼저 필요하다. 근거 확보와 실제 복구는 별도이며 이번에는 복구하지 않았다.

| 문서/코드 정합성 | 이번 확인·보완 |
|---|---|
| A: 커밋 코드만으로 유효 | README의 근거·통계·제목,04/09/11의 의미 대응,05/08/10/12의 결과 anchor,18의 역사적 측정,20/21의 앱/문서 버전 구분은 유효 |
| B: 미커밋 코드가 필요한 안내 | 02의 import/helper·오류 분류·결과 경로·추가 정책 검사는 **10파일 반영·통합 검증 대기**로 명시. `dde553e`의 `test:hardening`은 HTML 경계6개뿐이다. README와02의 기존 서비스 기동 안내에 현재 통합 중단을 표시 |
| C: 사건·미완료 | 독립 의존성/Chrome 확인과 실제 auth17 PASS를 구분. authorization·grading·hardening NOT_RUN, indexing·student·disabled BLOCKED를 그대로 유지. 검사 코드10파일은 이전 검증 hash와 같고 이번 문서 커밋에 포함하지 않음 |

**최소 재개안은 현재 실행 불가(BLOCKED)이며 이번에는 기동하지 않는다.** 기존 `.local/env`·자격증명·DB·Redis·Chroma·객체 경로·볼륨을 전혀 재사용하지 않는 새 합성 시험 범위를 먼저 검토해야 한다. 새 자원명·마운트/endpoint·loopback 포트·내부망·의존 서비스의 완전한 목록을 한정된 명세로 검증하며, 프로젝트명 변경이나 결과 폴더 변경만으로 격리를 판정하지 않는다. 기존 데이터를 복제하지 않고 추적된 합성 seed로 빈 시험 저장소를 준비한다. auth·disabled 및 새 fixture의 grading 등 배경 처리가 불필요한 단계는 worker·dispatcher를 제외한다. 게시·색인·학생 검사는 새 DB와 새 Redis에 시험 작업만 존재하고 새 Chroma·객체 저장 경로임을 확인한 후에만 두 서비스를 명시 허용해야 한다. auth-short의2초와 일반900초, 데모 비활성/활성 서버도 새 시험 범위에서 구분한다.

| 현재 재개 차단 파일·조건 | 필요한 최소 보완·예방 가드 제안(미구현) |
|---|---|
| `scripts/local/manage.py:22–23,53–55`; `scope_guard.py:10–16,218–237`의 기존 project/env/볼륨 강제 | 기존 gate를 우회·무제한 확장하지 않고 **하나의 한정된 새 시험 범위**를 별도로 검토. 소유권 PASS와 데이터 변경 허용을 분리하고 직접 Docker 실행도 실제 서비스 계획 검증을 거치게 함 |
| `manage.py:268–275`, `scope_guard.py:111–114`의 서비스 생략; `verify_indexing.py:68–73`의 의존 기동 | 보존 작업에서 서비스 없는 up/start/restart와 배경 소비자 포함 계획을 거부. `validate_plan()`이 의존 서비스까지 계산하고 기존 저장소와 새 저장소의 혼합을 차단 |
| `compose.local.yml:100,119`, `ai/app/celery_config.py:7–8`, `dispatcher.py:15–16`의 큐 고정; `store.py:222–245`의 DB 전체 outbox | 큐명만 바꿔 격리됐다고 가정하지 않음. 새 DB·Redis·Chroma·객체 저장소 조합과 새 시험 작업 소유를 검사하고 기존 endpoint·마운트를 거부 |
| 7종 browser harness의 기존 origin/`.local/env`; `indexing_fixtures.py:10–16`; `verify_student_web.py:28–31,65–97` | 새 시험 endpoint·자격증명 경로와 합성 seed 순서를 명시하고 기존 fixture/plan을 복사하지 않음. authorization의 게시·재게시, student의 revision/공유 변경, indexing의 finally 기동까지 새 시험 자원만 대상으로 검증 |

이 제안은 새 플랫폼이나 Compose 전체 개편의 구현 완료가 아니다. 향후 순수 명령 계획·합성 metadata 검사로 기존 저장소 혼입, 암묵적 소비자 기동, 잘못된 plan을 먼저 거부해야 한다. 이번에는 저장 파일 대조와 통제된 브라우저 정책6개만 실행해 PASS였으며 실제 Chrome·통합 재실행으로 세지 않는다. Docker context/inspect의 제한된 ID·상태·소유 라벨 조회에서 자체11개가 여전히 exited임을 확인했다. 최초 sandbox 메타데이터 조회 차단과 후속 읽기 성공은 새 ignored `.local/evidence-portability-safety-review/20261008T052844Z/`에 분리했다. 기존 기준선·증거94파일·미커밋10파일은 변경하지 않으며 데이터 보존 FAIL을 새 PASS로 대체하지 않는다. 이번 문서 보완만 별도 로컬 커밋하고 push·PR·merge·Pages 재배포는 하지 않는다.

<a name="isolated-preflight-2026-10-14"></a>

### 독립 합성 시험의 오프라인 준비 (2026-10-14)

시작 HEAD `91ebc824a36d12848b607dc7bb560778c1795a31`, 브랜치 `codex/dodream-evidence-portability`를 확인했다. **준비됨, 실제 기동·통합 검증 전**이다. 아래 설정·실행기·검사 코드는 모두 미커밋 작업트리 안이며 이 문서만 checkout해 실행할 수 없다. 제품 Java/Python·DB 스키마·기존 Compose/scope gate·showcase는 바꾸지 않았다. 사고 원인은 위 기록대로 **기존 ID를 직접 지정한 docker start에 worker/dispatcher 포함, operation=config 소유권 확인을 데이터 변경 허가로 사용**한 것이다. 재조사하거나 외부 변화로 재분류하지 않는다.

**구현:** `scripts/local/isolated-trial.json` 한 파일에서 시험 ID·project·root·자격증명 위치·두 origin을 지정한다. `isolated_trial.py`는 suite별 Compose 후보와 정확한 argv를 **출력만** 한다. `.local/env`를 읽거나 `manage.py`를 import하지 않는다. `validate_invocation()`은 실제 argv의 operation·서비스·root·config와 전체 서비스 환경·볼륨·네트워크를 대조한다. 직접 ID start, config→up 허가 재사용, external/name 기존 볼륨, 기존 DB/Redis/Chroma endpoint, 객체/SQLite bind, 홈/socket, 불필요한 소비자, 누락·알 수 없는 입력을 거부한다. 상속 환경변수도 거부하고 `execute_invocation()`은 유효한 계획이어도 항상 중단한다. `validate_fresh_inventory()`는 전달된 최소 메타데이터의 이름 충돌을 검사할 뿐 실제 Docker 조회나 기동 허가가 아니다. 일반 셸의 모든 직접 명령 오용까지 차단한다고 주장하지 않는다.

`fe-web/tests/isolated-runtime.mjs`는7종 실제 서버 harness에 명시 manifest·새 합성 fixture receipt를 연결한다. origin·결과·plan·자격증명 기본 경로와 자료명/계정/device/학생 ID 가정을 제거했고, `browser-student-boundaries.mjs`의 short origin도 전달받는다. 새 `fixtures/<suite>.json`은 trial/project/suite/origin/runId와 합성 seed에서 얻은 식별자를 담아야 한다. indexing/student plan도 같은 실행에 속해야 한다. 자격증명 읽기는 별도 함수이며 이번에는 메모리의 `SYNTHETIC_NOT_A_SECRET`만 사용했다. receipt 표식 자체가 실제 저장소의 새 생성 증거를 대신하지 않는다.

| 자원 | 동결된 기존 환경 | 새 시험 계획 |
|---|---|---|
| project·root | `dodream-phase1`, `.local/`의 기존 결과·데이터 | `dodream-evidence-20261014`, `.local/isolated/evidence-portability-20261014/` |
| 주소 | 15173/15174 및 기존 직접 API 포트 | loopback 25173/25174만; 브라우저는 same-origin API 사용 |
| 설정·자격증명 | `.local/env` | 명시 manifest + 시험 root의 `credentials.env`; 아직 생성하지 않음, 이후 새 `ISOLATED_*` 값과 실행 ID만 |
| MySQL·Redis | 기존 `dodream-phase1_*` 볼륨과 outbox/queue | 새 project의 `mysql-data`, `redis-data`; DB `dodream_evidence_20261014`; 내부망의 mysql:3306·redis:6379/1 |
| Chroma·SQLite·객체 | 기존 chroma-data·ai-data·be-data | 새 project의 동명 **논리 키**에 해당하는 별개 볼륨; 내부 경로만 유지. 두 BE는 새 be-data 공유 |
| 네트워크·bind | 기존 default/gateway·데이터 bind | 새 project default(internal)/gateway. 데이터 bind 없음; short nginx의 검토된 설정 복사본 하나만 새 root에서 read-only mount |
| fixture·결과 | 과거 자료/작업 ID·browser plan·결과 | 새 합성 seed에서 조회한 ID, `fixtures/`, `browser-ui/`, `results/`; 기존 파일/큐 복사 금지 |

queue명 `indexing-v3`는 제품 코드에 고정되어 유지한다. **새 MySQL outbox·Redis·Chroma·객체 저장소의 조합**으로 격리하며 queue명이나 project명만으로 격리를 판정하지 않는다.

| 검사 | 명시할 서비스(브라우저 단계) | 소비자·준비 조건 |
|---|---|---|
| auth / demo-disabled | mysql, redis, be, ai, be-auth-short, web-auth-test | 소비자 없음; short BE 2초·demo=false |
| grading | mysql, redis, be, ai, python-service, web | 소비자·Chroma 없음; 새 Spring grading seed |
| authorization / indexing | grading의6개 + chroma, worker, index-dispatcher | 게시·복원·새 색인에 필요; 새 시험 작업만 |
| hardening | grading의6개 + chroma | 새 catalog 준비 때 소비자 필요, 검사 단계에서는 제외; 준비 실행기는 아직 차단 |
| student | authorization의9개 + be-auth-short, web-auth-test | short BE도 demo=true; 새 demo/색인과 장애 복구 실행기 필요 |
| 공개 showcase | Docker 서비스 없음 | 기존 정상 공개본·검사 경로 유지, 이번에는 실행하지 않음 |

기존 nginx main 설정은 사용하지 않는 PDF 경로도 시작 시 `python-service` 이름을 해석하므로 main 웹 검사에 포함한다. auth nginx에는 이 upstream이 없어 제외한다. 일반 BE의 demo는 student/hardening에서만 켜고 phase5 API는 모두 끈다. 데이터 준비 단계는 각 행에서 mysql·redis 및 필요한 chroma만 선택하며 worker/dispatcher를 공통 시작하지 않는다.

**실행 없는 재현 명령(현재 미커밋 안 필요):**

```bash
python3 scripts/local/test_isolated_trial.py
node --test fe-web/tests/isolated-runtime.test.mjs fe-web/tests/browser-runtime.test.mjs
python3 scripts/local/isolated_trial.py \
  --manifest "$PWD/scripts/local/isolated-trial.json" --suite auth --phase data \
  --operation up --services mysql redis
python3 scripts/local/isolated_trial.py \
  --manifest "$PWD/scripts/local/isolated-trial.json" --suite auth --phase browser \
  --operation up --services mysql redis be ai be-auth-short web-auth-test
```

`--operation up`도 실행하지 않고 JSON을 출력한다. 실제 기동 단계의 최소 명령 후보는 출력 `argv`의 `docker compose --project-directory <새 root> --env-file <새 credentials> -p <새 project> -f <새 compose.json> up -d --no-deps --wait --wait-timeout 180 <명시 서비스>`다. 현재 해당 파일들을 materialize하거나 이 명령을 실행하지 않았다. 이후 아래 차단 조건을 먼저 해결하고 기동을 별도로 승인받아야 한다. 준비 완료 후 실제 auth 브라우저 후보는 `DODREAM_ISOLATED_MANIFEST="$PWD/scripts/local/isolated-trial.json" node fe-web/tests/browser-auth.mjs`이며 현재는 새 receipt·자격증명이 없어 실행할 수 없다.

**실제 기동 전 차단:** `manage.py`, `verify.py`의 import-time 기존 env/RESULTS, `scope_guard.py`의 기존 project, `indexing_browser_checks.py`의 origin override 제거와 서비스 제어, `verify_indexing.py`·`verify_student_web.py`의 기존 fixture/plan 및 finally 기동을 아직 전환하지 않았다. 새 설정을 전달해도 이들 실행기를 호출하면 안 된다. 새 시험에 한정된 V003/V004 적용 → 일반 BE 합성 seed 완료 → short BE 순서, 새 fixture/receipt/handshake 생성, 소비자 장애 복구 동작을 별도로 연결해야 한다. 첫 생성 메타데이터 검사 후의 단계 전환에는 새 자원 생성 증표와 정확한 현재 상태 검사가 더 필요하며 처음의 config PASS를 재사용하지 않는다. 이미지 재사용은 immutable digest·소스/Dockerfile/lock 대응과 비밀·데이터 미포함을 확인한 뒤에만 가능하다(현재 미확인). 새 자격증명은 이후 생성하고 MySQL URL에 안전한 문자를 사용한다. 실제 Compose 해석·포트 가용성·자원 부재도 이번에는 검사하지 않았다.

**최종 순수 검사:** Python 정책28개 PASS(exit0), Node의 새 파일 격리10개 + 기존 Chrome 대역 정책6개 PASS(exit0),8개 브라우저 파일 문법 검사 exit0. 모든 신규 정책 검사에서 프로세스·네트워크 실행 진입점을 실패 처리했다.7종×2단계의 CLI 계획14개도 exit0이며 `executionAuthorized=false`다. 이 수치는 실제 Chrome·서버 통합 통과 수가 아니다. 개발 중 합성 검사 fixture 공유와 루트 경로 처리의 실패를 고친 뒤 최종 실행을 새로 수행했으며 기대값을 낮추지 않았다.

새 증거는 ignored `.local/evidence-portability-isolated-preflight/20261014/`의 `before.json`, `after.json`, `working-tree.patch`, `final-pure-commands.json`, `plan-commands.json`, `plan-*.json`으로 구분한다. 시작 시 기존10파일 hash와 원본94개 증거 hash가 직전 기록과 같았다. 이번에는 그중7개 harness를 수정하고 package.json·chrome-launch·browser-runtime.test의3개 hash는 유지했다. 학생 boundary1개와 신규 설정/helper/순수 검사5개를 포함해 코드16파일을 미커밋으로 보존한다. 과거 해시 불변 기록은 당시 상태로 남기고 원본94개·기존 사용자 파일을 보존한다. 문서3개만 별도 로컬 커밋 대상이다.

`PREEXISTING_ENVIRONMENT=FROZEN`, `ISOLATED_EXECUTION_PLAN=PREPARED_OFFLINE_ONLY`, `ISOLATION_POLICY_TESTS=PASS`, `NEW_ENVIRONMENT_STARTED=false`, `INTEGRATION_VALIDATION=NOT_RUN`, `RECOVERY_EXECUTED=false`. **BACKEND_DATA=CHANGED_UNEXPECTEDLY, DATA_PRESERVATION=FAIL**을 유지한다. 이번에는 Docker 명령·DB/Redis/Chroma 연결·실제 브라우저·실제 비밀 파일 읽기/생성·복구·원격 Git/Pages 변경을 하지 않았다. 시험 root 자체도 생성하지 않았고 공개 데모는 그대로다. 과거 auth17 PASS 및 나머지 BLOCKED/NOT_RUN은 새 검증으로 바꾸지 않는다.
