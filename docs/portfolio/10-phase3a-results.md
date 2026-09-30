# 3-A 퀴즈 제출·채점 안정화 실행 결과

## 기준과 작업 범위

작업 경로 `/Users/yoonsu/Desktop/projects/DO-DREAM`. 실제 시작 브랜치 `codex/dodream-phase2b-authorization`, HEAD `eba04683a263b4a0fd327d428c1a4b3d693aee53`가 전달값과 일치했다. merge/rebase/cherry-pick 진행 상태는 없었고 사용자 미추적 `docs/.DS_Store` 한 파일만 있었다. 이 파일은 읽기·삭제·stage에서 제외했다. 신규 브랜치는 `codex/dodream-phase3a-grading`이다. 검증은 KST 2026-09-29~30에 수행했다.

팀 구현 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`, 이전 인증/범위/객체권한 커밋 및 과거 증거는 그대로 유지한다. 3-A의 승인된 로컬 구현·검증·문서화·로컬 커밋만 수행한다. push/PR/merge/이력 재작성/공개 배포/외부 공급자 호출은 하지 않는다.

증거 루트는 ignored `.local/phase3a/`다. 과거 ETCH 보존 실패는 **FAIL**, 원인은 **UNVERIFIED**로 그대로 남긴다. 이번 실행 범위와 현재 외부 ID 안정성은 아래에서 별도로 판정한다.

## 변경 전 확인

기준 2-B 이미지를 실제 MySQL·Spring·FastAPI에서 실행하고 **새** `[GRADING LOCAL] baseline` 자료/문제에서 재현했다. 기존 자료·로그에는 수정하지 않았다.

| 사례 | 구분 | 변경 전 결과 |
|---|---|---|
| 같은 2문항 답안을 두 번 제출 | 실제 HTTP/DB | 두 응답200, 로그0→2→4. 중복 제출 방지 FAIL |
| 제출 후 교사 정답 수정과 과거 이력 조회 | 실제 HTTP/DB | 과거 풀이에도 수정된 현재 정답이 표시됨. 당시 기준 보존 FAIL |
| 외부 채점 대기 중 DB 트랜잭션 | 정적 분석만 | `@Transactional gradeAndLog` 안의 `WebClient.block` 확인. 당시 실행 계측으로 재현했다고 주장하지 않음 |
| 잘못된 AI 결과 | 정적 분석만 | 기존 개수/ID 검사는 있으나 primitive boolean 변환·문항 예외→false fallback 존재 |
| 종료 후 불명 결과 복구 | 정적 분석만 | 영속 attempt/dispatch/generation/deadline 기록 부재 |

실제 증거: `results/grading-before.json`. 초기 준비 중 범위 메타데이터 조회가 한 번 실패해 해당 변경을 차단했고, 현재 scope 재확인 성공 뒤 미완료 합성 사례 준비를 계속했다. 원인이 같은 무한 재시도나 gate 우회는 하지 않았다.

## 구현과 검토

계약·상태·스냅샷·보장 한계는 [09 설계](09-grading-reliability-design.md)를 따른다. MySQL 필수 binary UUID key unique, 요청 자체의 고정 fingerprint, 불변 문제/정답 snapshot, 공개 문제 version, 별도 상태/복구 API, 짧은 `TransactionTemplate`, 세대·기한 fencing, 현재 권한 재확인, strict 전체 응답 검증과 원자적 결과/로그 확정을 구현했다. 통계는 제출 순서와 attempt ID로 최신 결과를 정하고 제출 수와 문항 로그 수를 구분한다.

검토 중 JVM 재시작마다 순서가 바뀔 수 있는 `Map.of` 직렬화를 고정 필드 순서로 바꾸고 golden fingerprint 검사를 추가했다. 같은 키의 동시 접수 loser가 교사 편집 뒤 버전 충돌로 잘못 분류되지 않도록 unique INSERT를 스냅샷과 같은 트랜잭션의 앞에 배치했다. Reactor Netty 연결 재설정의 자동 재시도를 명시적으로 껐다.

최초 새 이미지 기동은 WebClient 두 bean 중 주입 대상을 선택하지 않아 실패했다. `@Qualifier("webClient")`로 기존 local 허용 경계를 유지하고 실제 복수 bean 문맥 검사를 추가했다. 실패한 명령·첫 설치 스키마를 보존하고 수정 후 새 스키마 `dodream_phase3a_fresh_v2`에서 최초 설치를 재검증해 PASS였다. 순수 컴파일/테스트 시도 중 변수명 충돌, 잘못 지정한 검사 task 등의 실패 로그도 지우지 않았다. 최종 통과 수에 실패/호스트 재실행을 중복 합산하지 않는다. Spring 테스트 이미지가 아직 빌드되는 동안 시작된 한 회귀 실행은 이전98검사 이미지의 공통 DI 실패23개를 관측했다. 이를 새 소스의 독립23개 결함으로 계산하지 않고, 이미지 완료 후 최종 소스 전체 회귀104개 PASS로 확인했다.

첫 채점 통합 실행은 `GRADING_TRANSACTION_BOUNDARY`에서 차단되어 대역 공급자 호출0이었다. `NOT_SUPPORTED`의 빈 synchronization scope에서 로컬 관측용 JDBC 조회가 연결을 남기는 문제와 요청 OSIV EntityManager가 물리 연결을 보유하는 문제를 수정했다. 경계 검사를 완화하지 않고 해당 조회도 짧은 트랜잭션에서 종료하게 했다. 첫 실행의82 PASS/74 FAIL/1 BLOCKED를 보존했으며, 이를74개의 독립 결함으로 해석하지 않는다. 중단 신호 전 프로세스가 이미 종료해 실제 신호는 보내지 않았다. 첫 정상 제출을 통과하지 못하면 fail-fast하도록 검사 도구를 보완했다. 공급자 경계는 실제 transaction/DataSource 자원뿐 아니라 Hibernate의 물리 연결 보유 여부도 관측하며, 전역 OSIV 설정을 바꾸지 않고 채점 저장 작업의 EntityManager 수명을 국소적으로 분리했다.

추가 검토에서 권한 정책의 예외를 확정 트랜잭션 안에서 처리하면 REVOKED 기록까지 rollback되는 문제를 찾았다. 권한 거부 트랜잭션이 종료된 뒤 별도 짧은 트랜잭션에서 현재 세대를 확인하고 REVOKED를 기록하도록 고쳤다. 공급자 경계 검사에 막혀 실제 호출이 시작되지 않은 실패는 UNKNOWN 대신 FAILED로 분류한다. 공유 회수·자료 삭제의 실제 DB 검사를 추가하여 상태와 결과/로그0을 함께 확인한다.

첫 fresh 기동의 실시간 로그 최신 사본은 검사 도구의 시각별 복사 누락으로 한 번 덮어써졌다. 실패 결과 JSON·명령 로그·같은 DI 원인의 기존 이미지 테스트 로그는 보존했고, 당시 확인한 진단 문구는 `fresh-initial-diagnostic-excerpt.json`에 **발췌**로 표시했다. 이후 fresh 기동 로그는 시각별 사본을 저장하도록 수정했다. 전체 원본 로그가 남았다고 주장하지 않는다.

첫 Chrome 인증 실행6개는 공통 로그인 준비 단계에서 실패했다. 영속성 검사는 main7 서비스를 재기동했지만 별도 auth-short 프로세스는 계속 실행 중이었다. 같은 합성 로그인은 일반15173에서200, auth-short15174에서503이었고, short BE 로그에서 Redis 명령 타임아웃을 확인했다. 범위 gate를 통과해 `be-auth-short`만 재기동했다. DNS/IP 변화가 원인이라고 단정하지 않았고 앱 소스나 기대값은 바꾸지 않았다. 실패 사본 `results/browser-checks-1790696122980.json`, 상태 비교 `browser-login-http-diagnostic-1790696289.json`, `auth-short-after-persistence-diagnostic.log`와 재기동 `auth-short-reconnect.json`을 보존했다. 응답하지 않은 별도 Chrome 진단 프로세스 하나만 중단한 exit130도 별도로 기록했으며 원인 증거로 삼지 않았다.

## 최종 실제 검증

아래 증거 경로는 `.local/phase3a/` 기준이다. 기본 명령 접두사는 `python3 scripts/local/manage.py`이며 `compose` 호출도 기존 고정 project/file/directory·대상 라벨 gate를 통과했다. 명령 전체 인자·UTC 시작/종료 시각·종료 코드는 `results/commands.jsonl`, 시각별 로그와 각 명령 JSON에 있다. 기존 식별자·안전 기대값·양성 대조군을 삭제하거나 skip하지 않았다.

| 실제 명령/검사 | 종료 코드 | 최종 결과 | 주요 증거 |
|---|---:|---|---|
| `manage.py check`, `config` | 0 | 실행 도구/프로젝트 포트 및 Compose 유효성 PASS | `results/check-*.json`, `compose-config.json` |
| `manage.py scope-test` | 0 | 39 PASS: 기존35 + 좁은 새 스키마 허용/거부4 | `results/scope-unit.log` |
| `manage.py grading-migrate`; `grading_migration.py fresh-prepare`; `verify_fresh_grading_schema.py` | 0 | 기존 DB 전진 적용/재실행 및 새 스키마 최초 기동 PASS | `results/migration-forward.json`, `migration-fresh.json` |
| `manage.compose(... build be be-test ai worker)`; 최종 `build be be-test`, `up ... be` | 0 | 최종 이미지 빌드/기동 PASS | `results/grading-final-build.json`, `grading-dispatch-build.json`, `grading-final-up.json` |
| `manage.py test` | 0 | Spring104 / AI67 / PDF6 PASS, 실패·skip0 | `results/be-tests.log`, `ai-tests.log`, `pdf-tests.log` |
| `manage.py grading` | 0 | 278 PASS, FAIL/BLOCKED/NOT_RUN0 | `results/grading-checks-20260929T152354-3fe23025.json` |
| 추가 `Runner.independent_query_during_provider()` 실행 | 0 | 신규 보조6 PASS. 로그인/fixture 사전조건9는 중복 합산 안 함 | `results/grading-provider-wait.json`, `grading-provider-wait-checks.json` |
| `manage.py auth-test-up`, `auth` | 0 | 인증131 PASS | `results/auth-checks.json` |
| `manage.py startup` | 0 | 잘못된 키의 실제 기동 차단6 PASS | `results/startup-key-checks.json` |
| `manage.py smoke`, `security`, `authorization` | 0 | 27 / 16 / 188 PASS | `results/smoke-checks.json`, `security-checks.json`, `authorization-checks.json` |
| `manage.py persistence` | 0 | 서비스 실제 재기동·영속성8 PASS | `results/persistence-checks.json` |
| `npm run test:auth`, `test:authorization`, `test:grading` (`fe-web`) | 0 | 25 / 9 / 19 PASS | `results/web-*-unit.json` |
| `npm run typecheck`, `npm run build -- --mode phase1` (`fe-web`) | 0 | 타입 검사/빌드 PASS | `results/web-typecheck.json`, `web-build.json` |
| `npm run test:browser-auth`, `test:browser-authorization`, `test:browser-grading` | 0 | 실제 Chrome 17 / 18 / 11 PASS | `results/browser-checks.json`, `browser-authorization-checks.json`, `browser-grading-checks.json` |
| native 순수 helper `tsc --noEmit`; 호출부 syntax 검사 | 0 | helper 타입 검사 PASS, TS/TSX 호출부5개 문법 오류0 | `results/native-grading-helper-typecheck.json`, `native-callers-syntax.json` |
| `python3 scripts/local/grading_data.py after` | 0 | MySQL 원래86행/RAG 원래83행의 전체 원래 컬럼 보존 PASS | `results/grading-data-final.json`, `data-preservation.json` |
| `manage.py stop`, `status` | 0 | 자체9개 서비스의 시작 전 exited 상태 복구 | `results/compose-stop.json`, `compose-status.json` |
| `manage.py isolation` | 1 | strict14 PASS / 3 FAIL. 외부 ID·상태 변화 관측 | `results/resource-isolation-checks.json`, `isolation.json` |

최종 서버 회귀는 UTC 2026-09-29 15:22:31~15:22:54에 수행했다. Spring104는 기존77과 신규27(순수19/실제DB8)이며, 별도 호스트 순수79는 이104에 포함하므로 더하지 않는다. 전체 채점 실행은15:23:54~15:27:52다. 그 뒤 검사 도구에 공급자 대기 중 독립DB 조회를 추가하고 해당 새 시나리오만15:30:19~15:30:28에 별도 실행했다. 이전278개 전체를 수정된 검사 도구로 다시 실행했다고 표현하지 않는다. 서비스 소스는 변경되지 않았다.

Chrome154.0.8037.58에서 최종 인증은15:41:02~15:42:09, 교사 UI 권한은15:42:32~15:42:52, 채점 API 계약은15:43:14~15:43:15에 통과했다. 각 실행의 외부 요청 차단 카운터는0이고 별도 테스트 브라우저만 사용했다. 채점11개는 학생 UI 전체 테스트가 아닌 **BROWSER_API_CONTRACT_ONLY**다.

### 실제 동시성·장애·재시작의 횟수

- 12개 독립 HTTP 클라이언트 ×3라운드. 매 라운드 같은 학생/key의 **attempt1, snapshot2, result2, log2, 공급자 시작1/반환1**이었다. 동일 key 재전송과 DB 확정 후 응답 유실에도 추가 저장/채점은0이다.
- 실제 MySQL 독립 연결12개(`CONNECTION_ID` 확인)의 unique INSERT 경쟁에서 성공1/중복 오류1062가11이었다. student/key의 NULL 우회는1048로 거부했다. 순수 mock 경쟁 테스트와 이 실제 연결 증거를 구분한다.
- 제출 전 편집은409, 접수/완료 후 편집은 최초 snapshot 유지, 같은 key replay도 유지했다. 공백은 보존하고 답안 순서만 정규화했다. 부분 제출은 허용하되 제출 집합의 결과 누락·중복·다른 ID·틀린 타입·변경된 답안·긴 피드백은 실패했다.
- HTTP 실패·timeout·결과 저장 중 실패·최대3세대·과거 세대의 늦은 확정·공유 회수·삭제·최신 제출 순서/동률·legacy 이력을 검증했다. 권한 회수 시 REVOKED, 결과/로그0이며 상태·replay·retry 접근도 거부했다.
- 실제 외부 호출 직전 `transactionActive=false`, `connectionBound=false`, `hibernateConnectionHeld=false`였다. 추가 보조 검사에서는 로컬 공급자 `started=1, finished=0`인 동안 독립 MySQL 요청이 완료됐고, gate 해제 후200·결과2·로그2였다. 앱 전체 연결 수를 해당 제출의 사용량으로 해석하지 않았다.

| 실제 자체 Spring 중지·재기동 구간 | 복구 전 대역 호출/로그 | 명시 복구 또는 replay 후 | 상태 의미 |
|---|---|---|---|
| 외부 호출 전 | 0 / 0 | 총1 / 2, attempt1 유지 | 기한 후 FAILED, 같은 attempt 명시 재실행 |
| 공급자 호출 진행 중 | 1 / 0 | 총2 / 2, attempt1 유지 | UNKNOWN 확인 후 다음 세대 |
| 응답 수신 후 DB 확정 전 | 1 / 0 | 총2 / 2, attempt1 유지 | UNKNOWN, 이전 결과 확정 차단 |
| DB 확정 후 사용자 응답 전 | 1 / 2 | 총1 / 2, 추가 호출0 | SUCCEEDED 그대로 replay |

이 네 사례는 gate로 구간을 관측한 뒤 실제 자체 Spring 프로세스를 중지·재기동했다. 별도의 저장 예외·응답 유실 오류 주입 검사와 구분한다. 상세 횟수는 `results/grading-attempt-evidence-20260929T152354-3fe23025.json`, 보조 공급자 대기 증거는 `results/grading-provider-wait-evidence.json`이다. 대역 호출2인 복구 사례가 있으므로 외부 exactly-once라고 주장하지 않는다.

## 데이터와 자원 보존

변경 전 기존 MySQL 30개 도메인 테이블 86행과 RAG SQLite 83행(세션17/메시지50/embedding task16)의 **모든 기존 컬럼** 해시를 저장했다. 원문/인증값/DB dump는 출력·내보내지 않았다. 신규 컬럼은 과거 값 비교에서 제외하되 원래 컬럼/행은 모두 비교했다. 준비 후 첫 보존 검사와 모든 Chrome 검사까지 마친 최종33개 테이블 비교가 모두 PASS였고 변경/유실된 원래 행은0이었다. 최초 기준선 `data-before.json`, 준비 후 사본 `data-preservation-after-setup.json`, 최종 `data-preservation.json`을 구분했다.

기존 2-B 회귀는 `[AUTHZ 3A]`로 새 자료·문제·공유와 새 로컬 합성 객체를 복제하여 실행한다. 기존 객체·행을 수정한 뒤 기준선을 덮어쓰지 않는다. Spring 자체 합성 채점 fixture와 이번 테스트 로그는 원래 행과 별도 ID다. 신규 legacy 사례도 새 행으로 만든다.

`V003__grading_attempts.sql`의 기존 DB 전진 적용·재실행 동일성·실제 unique/NOT NULL/ascii_bin은 PASS였다. 같은 최종 SQL과 JPA 컬럼 정의로 새 `dodream_phase3a_fresh_v2`에 migration→최초 기동→migration 재실행을 확인했고33개 테이블·실제 unique 유지도 PASS였다. 증거는 `migration-forward.json`, `migration-fresh.json`이다. 실패한 첫 스키마와 통과한 새 시험 스키마를 모두 보존했다. 기존 네 볼륨을 삭제하거나 초기화하지 않았다.

자체9개 서비스는 모두 시작 전 `exited`로 복구했다. 원래 볼륨/네트워크 이름, 내부망, loopback 포트, DB 포트 비공개, 로그의 JWT/생성 비밀 비노출은 PASS다. 기록된 범위 gate720개 중717개 PASS이며 모두 `dodream-phase1`과 허용된 서비스였다. 나머지3개는 Docker metadata inspect 실패로 변경을 차단한 기록이다. 우회 명령으로 실행하지 않았다. 최종 범위 검토는 `results/final-scope-audit.json`에 있다.

**이번 전후 비교에서도 외부 보존은 FAIL이다.** 원래 외부 컨테이너60개 중 `etch-phase7-migration` 계열6개는 ID가 달라졌으며 같은 이름은 남아 있었다. 해당 계열의 원래 mysql/redis 두 컨테이너는 running→exited로 바뀌었다. 외부 볼륨4개·네트워크2개가 추가로 관측됐다. 그래서 기존 ID 보존·원래 상태 보존·이름 기준 상태 보존3개가 FAIL이고 strict isolation 종료 코드는1이다. 원본 before/after와 기대값은 바꾸지 않았다. 이전 ETCH 사건의 FAIL과 이번 새 관측을 구분하며, 양쪽 원인 귀속은 **UNVERIFIED**다. 외부 자원을 조작하거나 과거 상태로 복원하지 않았다. 자체 변경 대상 검증 PASS가 모든 직접·간접 환경 영향의 부재를 증명한다고 주장하지 않는다.

## 최종 상태

| 상태 | 판정 |
|---|---|
| SUBMISSION_IDEMPOTENCY | PASS |
| GRADING_TRANSACTION_BOUNDARY | PASS |
| GRADING_SNAPSHOT | PASS |
| GRADING_RESPONSE_VALIDATION | PASS |
| GRADING_FAILURE_RECOVERY | PASS |
| AUTH_AND_AUTHORIZATION_REGRESSION | PASS |
| DATA_PRESERVATION | PASS — 자체 기존 MySQL/RAG 행과 볼륨 |
| CURRENT_MUTATION_SCOPE | PASS — 확인한 실행 명령/허용 대상 범위 |
| CURRENT_EXTERNAL_ID_STABILITY | FAIL — 이번 외부6개 ID 교체 관측 |
| EXTERNAL_CHANGE_ATTRIBUTION | UNVERIFIED |
| REAL_AI_INTEGRATION | NOT_RUN |
| PUBLIC_DEPLOYMENT_READY | false |

## 파일 검토와 로컬 커밋 범위

변경66개 파일의 구현·검사·문서를 검토했다. 생성된 로컬 비밀값과 JWT/개인 키 후보 검사에서 후보0이었고, 파일별 SHA-256을 ignored 검토 기록에 남겼다. 원문 로그·DB·캐시·빌드 결과·`.local/env`·사용자 `docs/.DS_Store`는 대상에서 제외했다. Git diff의 공백 오류와 stage된 파일/내용을 다시 확인하고 명시한66개 경로만 로컬 커밋 대상으로 삼는다. 커밋 메시지는 `fix(quiz): make grading attempts idempotent and preserve snapshots`다.

검증한 기능·자체 데이터·실행 범위와 미귀속 외부 환경 변화를 구분해 허용된 로컬 커밋을 진행하는 판단이다. 이번 외부 FAIL을 과거 사건의 예외로 바꾸거나 전체 보존 완료를 선언하지 않는다. 이 문서를 포함하는 로컬 커밋의 실제 SHA는 Git HEAD와 최종 보고에 기록한다. push/PR/merge/remote 변경/이력 재작성/공개 배포는 수행하지 않는다.

## 검증 범위와 후속 작업

학생 앱에는 논리 제출별 key·버전·답안 동결, 동시 클릭 단일 요청, 응답 유실/AT 갱신 시 같은 key, 인증 epoch fence, 제한 polling·명시 복구를 연결했다. key는 현재 퀴즈 화면 메모리에서 유지한다. 앱 프로세스 종료 후 자동 복원은 구현하지 않았으며 서버 재시작 뒤 영속 replay와 구분한다. 요청당20초 제한, 1초 간격 상태GET 최대3회, 자동 공급자 재채점0회, 수동복구 최대2회(서버 총3세대)다.

실제 React Native 설치·네이티브 빌드·실기기는 **NOT_RUN**이다. 순수 helper 타입/실행 검사와 실제 UI 테스트를 혼동하지 않는다. Chrome 새 채점 검사는 **BROWSER_API_CONTRACT_ONLY**이며 학생 웹 화면을 새로 만들지 않는다.

로컬 공급자 호출 횟수는 실제 외부 모델 호출/요금이 아니다. 장애 복구 후 외부 실행 중복 가능성은 남으며 공급자 exactly-once·HTTP 취소에 따른 실제 작업 취소를 보장하지 않는다. **REAL_AI_INTEGRATION=NOT_RUN**, **PUBLIC_DEPLOYMENT_READY=false**. 3-B는 별도 범위에서 임베딩 전환/이전 인덱스 보존과 발행·큐 경계 복구를 검토한다. 전체 outbox·비동기화, 공개 데모, RAG 평가, 전체 SSRF/로그/배포 설정 보완에는 자동 착수하지 않는다.
