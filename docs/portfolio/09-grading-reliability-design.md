# 3-A 퀴즈 제출·채점 신뢰성 설계

개인 개선 기준: 팀 구현 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`, 2-B 출발점 `eba04683a263b4a0fd327d428c1a4b3d693aee53`. 이번 범위는 퀴즈 접수·채점·복구뿐이다. 실제 실행 증거와 최종 판정은 [10-phase3a-results.md](10-phase3a-results.md)에 기록한다.

## 제출 계약

학생 문제 조회 `GET /api/materials/{materialId}/quizzes`는 정답 대신 서버 관리 `version`(비음수 정수)을 추가한다. 버전은 정답 해시가 아닌 JPA 낙관적 잠금 버전이다. 제출은 `POST /api/materials/{materialId}/quizzes/submit`, 필수 `Idempotency-Key: <소문자 canonical UUID>`, 본문 `{"answers":[{"quizId":1,"version":0,"answer":"얼음"}]}`이다. 키 누락을 서버 임의 생성으로 우회하지 않는다. 본인 식별은 검증한 JWT에서 얻으며 클라이언트 소유자·점수·정답을 채점 근거로 사용하지 않는다.

최대 50문항, 답안 2,000자, 피드백 2,000자. 중복 quizId, 빈 집합, 잘못된 타입·버전·키를 거부한다. 부분 제출은 유지하되 제출한 모든 문제에 대한 결과가 있어야 성공한다. fingerprint는 자료 ID와 quizId 오름차순의 `(quizId, version, answer)`로 만든다. 답안 앞뒤/내부 공백은 그대로 보존한다. 현재 정답이나 시각을 fingerprint에 섞지 않는다. 올바른 Unicode 문자열만 허용하고 단독 surrogate를 거부하여 UTF-8 변환에서 서로 다른 답안이 같은 값으로 바뀌지 않게 한다.

MySQL `grading_attempts`의 `(student_id,idempotency_key)`는 **NOT NULL + UNIQUE**, 키는 ASCII `ascii_bin` 비교이다. DB 유일성 제약이 다중 요청을 중재한다. 중복 INSERT 실패는 해당 짧은 트랜잭션을 끝낸 뒤 기존 레코드를 별도 트랜잭션에서 조회한다. 같은 사용자·키와 같은 fingerprint는 상태/결과를 replay하고 다른 자료·답안·버전은 409 충돌이다. 새 키는 의도적인 별도 풀이이다.

정상 완료 응답은 기존 결과 배열을 유지하고 `X-Grading-Attempt-Id`, `X-Grading-State` 헤더로 제출을 식별한다. 상태 조회는 `GET /api/materials/{materialId}/quiz-attempts/{attemptId}`, 복구는 같은 경로의 `POST /retry`다. 복구 본문은 `expectedGeneration`과 `confirmUnknown`이며 상태와 실행 세대가 맞아야 실행권을 얻는다.

## 고정 스냅샷과 과거 이력

최초 접수의 짧은 트랜잭션에서 DB unique INSERT로 키를 먼저 확보한 뒤 문제 행을 정해진 순서로 잠그고 모든 조회 버전을 확인한다. 스냅샷 실패·버전 충돌이면 시도 생성도 함께 rollback된다. 동일 키의 동시 요청은 INSERT 충돌을 처리한 뒤 이미 접수된 스냅샷을 replay하므로 중간 교사 편집 때문에 기존 제출이 새 버전 충돌로 바뀌지 않는다. 새 제출의 버전 불일치는 409로 갱신을 요구한다. 이미 접수된 같은 키는 현재 버전을 검사하지 않고 기존 fingerprint·스냅샷을 사용한다.

`grading_attempt_items`에는 문제 ID·버전·번호·유형·제목·본문·서버 정답·학생 답안·채점 정책 버전을 저장한다. 채점 공급자 입력과 완료 결과는 이 불변 기록에서 만들어진다. 교사 편집은 원래 기능을 유지하고, 편집 후 과거 제출 replay와 이력은 최초 기준을 유지한다. 모델이 보내는 정답을 서버 정답에 덮어쓰지 않는다.

기존 `student_quiz_logs` 행, FK와 결과는 유지한다. 새 nullable attempt/snapshot 필드는 과거 행에 NULL로 남겨 두며 현재 정답을 역채움하지 않는다. 과거 기준을 알 수 없는 이력은 `snapshotAvailable=false`로 구분한다.

## 트랜잭션과 외부 호출

오케스트레이션 전체에는 장시간 트랜잭션을 두지 않는다. `TransactionTemplate`로 접수·실행권 확보, dispatch 기록, 확정 단계를 각각 나눈다. 채점 저장 작업은 비활성 요청 OSIV EntityManager holder를 짧은 트랜잭션 기간에만 분리하고 자체 EntityManager를 생성·종료한 뒤 원래 holder를 복원한다. 전역 OSIV 설정은 유지한다. FastAPI HTTP 호출은 실제 트랜잭션 및 연결이 종료된 이후 실행한다. 경계에서 `transactionActive=false`, `connectionBound=false`, `hibernateConnectionHeld=false` 세 조건을 검사한다. 마지막 값은 새 연결을 얻지 않고 Hibernate logical connection의 물리 연결 보유 상태를 관측한다. AI도 현재 소유·권한·실행 세대·기한·execution capability를 DB에서 확인하고 스냅샷을 메모리에 복사한 뒤 SQLAlchemy 세션을 rollback/close하고 공급자를 기다린다.

BE→AI 내부 본문은 `attempt_id`, `execution_generation`, `execution_token`이다. 임의 문제·정답을 보내는 이전 직접 호출 계약은 거부한다. 실행 토큰은 무작위 capability이고 DB에는 SHA-256 해시만 저장한다. 학생용 응답에는 토큰·fingerprint·처리 중 정답을 노출하지 않는다.

BE connect 2초/read 12초/HTTP 전체 15초, AI 전체 10초/공급자 8초, 공급자 자동 재시도 0회. 실행 기한은 MySQL 시각 기준 30초다. 타임아웃으로 실제 외부 작업까지 취소됐다고 보장하지 않는다.

BE 응답 수신과 파싱은 최대 2MiB로 제한한다. 문자 수 제한과 별도로 적용되는 전송 크기 제한이며, FastAPI의 UTF-8 JSON 응답을 사용한다. AI의 문항별 모델 JSON 파싱 한도는 32,768자이며 디코딩한 피드백은 여전히2,000자 이하만 허용한다. 결과 ID 집합·개수·중복·타입·학생 답안 일치·피드백 길이를 확인한다. 잘못된 결과나 공급자 예외를 임의 오답으로 변환하지 않는다. 결과 레코드, 학생 로그, 성공 상태는 한 짧은 트랜잭션에서 확정한다. 세대번호·상태·기한이 일치하는 실행만 쓸 수 있고, 성공 상태를 뒤늦은 실패로 덮지 않는다.

## 상태와 복구

| 상태 | 의미 | 허용되는 다음 처리 |
|---|---|---|
| READY | 접수·스냅샷 저장, 외부 실행 미확보 | 한 요청만 실행권 확보 |
| PROCESSING | 실행 세대·기한을 가진 실행 중 | 상태 조회, 완료 확정, 기한 만료 판정 |
| SUCCEEDED | 결과·로그·상태가 원자적으로 확정됨 | 현재 권한 확인 후 replay |
| FAILED | 미호출 실패 또는 유효한 결과를 얻지 못한 확인된 실패 | 횟수·현재 세대·권한 조건을 만족하는 명시적 재시도 |
| UNKNOWN | dispatch 이후 결과 미확인 또는 확정 전 장애 | 중복 외부 실행 가능성을 확인한 명시적 재시도 |
| REVOKED | 확정 시점에 자료 접근권한이 회수됨 | 성적 반영·결과 노출 거부 |

최대 실행 세대는 3이다. 무한 자동 재호출이나 새 큐는 도입하지 않는다. 처리 기한이 지난 시도는 상태 조회/재시도에서 dispatch 여부에 따라 FAILED 또는 UNKNOWN으로 전환한다. HTTP 취소는 공급자 취소의 증거가 아니다.

| 장애 구간 | 저장 상태와 복구 |
|---|---|
| 접수 후 외부 호출 전 종료 | 스냅샷 유지. 기한 만료 후 미호출로 구분하고 명시적으로 같은 attempt 재실행 |
| 외부 호출 중 종료/timeout | dispatch 기록 유지. UNKNOWN; 결과 불명 안내와 확인 후 제한 재시도 |
| 응답 수신 후 확정 전 실패 | 부분 결과/로그 rollback. UNKNOWN; 이전 세대의 늦은 확정 차단 |
| DB 확정 후 응답 유실 | SUCCEEDED 유지. 같은 키로 재전송하면 추가 채점 없이 결과 반환 |

## 권한·통계·클라이언트

제출·상태·결과·retry·성공 replay·확정 시점 모두 기존 2-B 현재 권한 정책을 적용한다. 본인 attempt만 접근하며 같은 키를 다른 학생이 쓸 수 있어도 다른 학생의 attemptId를 조회할 수 없다. 채점 중 공유 회수·삭제·현재 학급 관계 변경 시 신규 성적 반영과 결과 노출을 거부한다. 권한 정책의 예외로 확정 트랜잭션이 rollback되면, 그 트랜잭션이 종료된 뒤 현재 실행 세대를 다시 확인하는 별도 짧은 트랜잭션으로 REVOKED를 기록한다. 실패한 트랜잭션 안에서 예외만 삼켜 종료 상태까지 rollback되는 일을 막는다. 이미 dispatch한 외부 요청을 철회했다고 주장하지 않는다.

풀이 횟수는 제출과 문항 로그를 구분한다. `submissionCount`는 성공 확정된 신규 attempt 수, `legacyLogCount`는 제출 묶음을 복원할 수 없는 과거 문항 로그 수다. 기존 `tryCount`는 전체 문항 로그 수라는 호환 의미를 유지하며 제출 횟수로 표시하지 않는다. 최신 풀이 선택은 완료 시각이 아닌 제출 시각 및 단조 증가 attempt 내부 ID로 정한다. 늦게 완료된 옛 풀이가 새 풀이 결과를 덮지 않는다. 기존 legacy 기록은 알려진 풀이 시각을 사용하고 당시 제출 묶음을 추측해 생성하지 않는다.

학생 앱 helper는 퀴즈 화면에서 생성될 때 문제·버전 사본과 인증 epoch를 고정하고, 첫 제출 시 key와 답안을 고정한다. 동시 클릭, 네트워크 유실, access token 갱신은 같은 키를 유지한다. 현재 퀴즈 화면 메모리에서 키를 유지하며 앱 프로세스 종료 뒤 클라이언트 자동 복원은 구현하지 않았다. 서버의 제출·결과 영속성과 이 클라이언트 범위는 구분한다. 상태 polling은 제한하고 FAILED와 UNKNOWN을 구분하며, 명시적인 새 풀이에서만 새 키를 만든다. 로그아웃/계정 전환 이후 옛 제출을 재전송하지 않는다. 웹에는 학생 전체 화면을 새로 만들지 않고 브라우저 API 계약과 실제 교사 UI 검증을 구분한다. 모바일 전체 설치·기기 검증은 NOT_RUN이다.

## 마이그레이션과 보장 범위

`be/src/main/resources/db/migration/V003__grading_attempts.sql`은 기존 DB를 지우지 않는 additive·재실행 가능한 SQL이다. 신규 JDBC 테이블은 JPA 엔티티 자동 DDL 대상이 아니다. 기존 테이블이 있으면 컬럼·인덱스가 없는 경우에만 추가하며, 새 DB에서는 SQL 이후 JPA가 legacy 테이블의 최신 구조를 생성한다. 전체 migration framework 전환은 하지 않는다. 자체 local/test DB에만 적용하고 실제 제약, 신규 설치, 전진 적용, 재실행 및 데이터 해시 보존을 검증한다.

보장하는 것은 동일 논리 제출의 결과·로그 중복 반영 방지와 정상 조건의 추가 채점 호출 방지다. 장애 복구로 외부 실행이 중복될 수 있다. 실제 공급자의 exactly-once, 요금 중복 방지, AI 품질은 보장하거나 검증했다고 주장하지 않는다. **REAL_AI_INTEGRATION=NOT_RUN**, **PUBLIC_DEPLOYMENT_READY=false**다.

로컬 오류 주입은 `[GRADING LOCAL]` 전용 자료 및 파일 기반 제어에서만 허용한다. 공개 오류 주입 API는 없다. 호출 경계 카운터와 DB 확정 수를 별도로 기록하며 원문·답안·토큰을 실행 증거에 출력하지 않는다. 실제 Spring 종료·재기동 사례와 오류 주입은 결과 문서에서 구분한다.
