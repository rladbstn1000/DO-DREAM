# 3-B 발행·색인 신뢰성 검증 결과

**격리 로컬 구현·필수 검증 완료.** 실제 MySQL·Redis·Celery·Chroma에서 16개 색인 시나리오의 완료 근거를 확보했고 인증·권한·채점 회귀, 재시작 영속성, 기존 데이터와 이번 외부 자원 보존을 확인했다. 원본 전체 실행의 실패는 그대로 보존하고 후속 검증을 별도로 연결한다. `REAL_AI_INTEGRATION=NOT_RUN`, `PUBLIC_DEPLOYMENT_READY=false`다.

설계와 소스 근거는 [11-indexing-reliability-design.md](11-indexing-reliability-design.md)를 따른다. 성공한 단위검사만으로 실제 MySQL·Redis·Celery·Chroma 통합 성공을 대신하지 않는다.

## 1. 작업 기준·범위

| 항목 | 기록 |
|---|---|
| 저장소 | `/Users/yoonsu/Desktop/projects/DO-DREAM` |
| 팀 기준 | `4c763af2316ebb00f523bc43b0c29e49ef7bf62e` |
| 전달받은 시작 HEAD | `705c2a440e6e2d84fb26effc792e4ddd733f23d4` |
| 작업 브랜치 | `codex/dodream-phase3b-indexing` |
| 실제 시작 상태/전달값 차이 | 2026-09-30 04:16:18 UTC 확인: HEAD가 전달값과 같고 tracked 변경 없음. 유일한 untracked 항목은 제외 대상 `docs/.DS_Store`. `review/start-git.json` 보존 |
| 로컬 커밋 식별 | 이 보고서를 포함하는 `feat(indexing): add durable validated index activation` 커밋. 정확한 최종 SHA와 stage/commit 검증 결과는 최종 응답 및 ignored `review/git-final.json`에 기록한다. 문서가 자기 커밋 SHA를 미리 포함한다고 주장하지 않는다. |
| 사용자 파일 | `docs/.DS_Store` 읽기·삭제·stage 제외 |
| 증거 위치 | ignored `.local/phase3b/` |

허용 범위는 발행·색인 영속 원장, 후보 검증/활성 전환, 제한된 전달·실패 복구, 최소 교사 상태 UI와 관련 로컬 검증이다. 인증·권한·채점 재설계, 실제 외부 공급자 호출, 학생 웹 데모, 모바일 전체 설치/실행, 공개 배포는 포함하지 않는다.

이번 시작 데이터는 **MySQL 34개 테이블·477행, SQLite 189행, 기존 객체 파일 27개**다. 2026-09-30 04:23:31 UTC 수집한 `.local/phase3b/results/data-before.json`에서 원래 컬럼과 행/파일 digest를 보존했다. 3-A의 이전 행 수를 복사한 값이 아니다. 원래 자료를 시험용으로 변경하지 않고 새 `[AUTHZ 3B]`, `[GRADING LOCAL] phase3b`, `[INDEXING LOCAL]` 자료를 사용한다. 최종 비교에서도 원래 컬럼·행·객체가 모두 보존됐다(7절).

## 2. 변경 전 확인과 구현

| 문제/경계 | 변경 전 확인 방식·소스 줄 | 수정과 현재 소스 | 새 합성 객체에서의 실제 재현 증거 |
|---|---|---|---|
| 기존 인덱스 선삭제 후 생성 실패 | 시작 HEAD의 `ai/app/rag/service.py:306`이 기존 collection을 삭제한 뒤 `from_documents` 호출. 소스 확인과 아래 local 재현을 구분 | [세대별 candidate](../../ai/app/indexing/store.py#L263), [검증 후 활성화](../../ai/app/indexing/store.py#L315) | 새 전용 legacy SQLite 대역 디렉터리에서 정상 청크 **1→임베딩 실패 후 0**, 기존 인덱스 보존 FAIL. 실제 Chroma 재현은 아님 |
| 발행 commit 후 전달 유실 | 시작 HEAD의 `PublishService.java:202`는 `afterCommit` HTTP 전송에 의존 | [발행과 작업 같은 DB 저장](../../be/src/main/java/A704/DODREAM/indexing/IndexingStore.java#L90), [원장 전달기](../../ai/app/indexing/dispatcher.py#L6) | 변경 전 실제 crash 재현 NOT_RUN. 새 경로의 실제 Spring/worker/dispatcher crash·복구 PASS, 6절 |
| 중복·역순·옛 세대 완료 | 시작 HEAD는 자료별 같은 컬렉션을 교체. 실행 세대별 물리 후보와 활성 포인터 원장 없음 — 정적 확인 | [3개 원장 테이블](../../be/src/main/resources/db/migration/V004__indexing_ledger.sql#L3), [현재 원본·권한 재검사](../../ai/app/indexing/store.py#L300), [세대·lease 검사](../../ai/app/indexing/store.py#L289) | 변경 전 실제 경쟁 재현 NOT_RUN. 새 경로의 독립 워커 claim·늦은 쓰기·역순 완료 PASS, 6절 |
| mutable URL 입력 | 시작 HEAD `ai/app/rag/tasks.py:53`은 실행 때 전달된 URL을 읽음 — 정적 확인 | [DB canonical snapshot 검증](../../ai/app/indexing/source.py#L91), [불변 객체 준비](../../be/src/main/java/A704/DODREAM/indexing/IndexingService.java#L62) | 변경 전 내용 교체 경쟁 재현 NOT_RUN. 새 경로의 snapshot/digest·잘못된 원본 거부 PASS, 5·6절 |
| Celery 결과와 준비 상태 혼동 | 시작 HEAD `ai/app/rag/router.py:132`는 AsyncResult 상태로 응답 — 정적 확인 | [현재 활성 버전 조회](../../ai/app/indexing/store.py#L346), [교사 상태 표시](../../fe-web/src/indexing/status.ts#L37) | 변경 전 화면 재현 NOT_RUN. 새 실제 Chrome 교사 상태 UI 14 PASS, 5절 |

선삭제 재현의 증거는 `results/before-reproduction.json`과 `baseline-repro-2026-09-30T042732196553+0000.json`이다. 재현 명령은 04:27:32 UTC exit0으로 종료했지만, 확인한 **이전 구현의 보존 성질은 FAIL**이다. 시험을 위해 새 전용 디렉터리를 만들었고 기존 정상 인덱스를 삭제한 증거로 해석하지 않는다.

검토한 변경 파일은 부록의80개이며 파일별 hash와 staged diff 식별자는 ignored `review/`에 보존한다. 현재 구현은 MySQL `index_resources/index_jobs/index_executions`를 원장으로 삼고 Chroma candidate를 검증한 후 활성 포인터만 전환한다. 기존 SQLite/파일 인덱스는 자동 승격하지 않는다. 상세 소스 근거는 [설계 문서](11-indexing-reliability-design.md)에 정리했다.

V004의 기존 자체 DB 전진 적용·재실행은 04:32:54–04:32:59 UTC exit0, `rerun_unchanged=true`, 필수 컬럼/UNIQUE 확인 PASS였다. 별도 새 스키마 `dodream_phase3b_fresh`에 migration을 JPA 시작 전에 적용한 최초 설치 검사는 04:40:59–04:41:17 UTC exit0, 기동·제약·재실행 안정성 PASS였다. 해당 스키마를 지우지 않고 보존했다. 증거: `index-migration-forward-2026-09-30T043254477481+0000.json/.log`, `index-fresh-schema-2026-09-30T044059310371+0000.json/.log`, `index-migration-fresh.json`. 이 결과와 기존 모든 행/객체의 최종 보존 판정은 별개다.

시험 자료 본문은 새 합성 fixture를 사용한다. 다만 보존한 기존 권한 회귀 검사는 기존 합성 authz 학생의 `classroom_id`를 잠시 해제한 뒤 `finally`에서 원래 값으로 복구하는 경로를 포함한다([관계 해제·복구](../../scripts/local/verify_authorization.py#L206)). 따라서 기존 행에 일시적 쓰기도 전혀 없었다고 표현하지 않는다. 관계 복구를 포함한 원래 모든 행·객체 digest의 최종 일치는 **PASS**다(7절).

## 3. 초기 실패와 최종 재검증의 연결

과거 사건을 이번 결과로 덮지 않는다. 이전 ETCH ID 보존은 **FAIL**, 원인 귀속은 **UNVERIFIED**이며 [06-resource-scope-review.md](06-resource-scope-review.md)에 남아 있다. 3-A의 별도 외부 ID·상태 변화도 **FAIL / UNVERIFIED**로 [10-phase3a-results.md](10-phase3a-results.md)에 보존한다. 이번 3-B before/after 결과는 별도로 수집한다.

다음은 수정 과정의 개별 실행이다. 로그는 timestamp가 있는 원본을 보존했으며 같은 원인의 실패를 여러 독립 결함으로 세지 않는다. **57개 또는 112개 PASS가 있는 중단 보고서도 실행 종료가 -2이므로 전체 PASS가 아니다.** 아래 시간은 UTC이고 증거 파일은 `.local/phase3b/results/` 기준이다. 실패 뒤 분리 실행한 Part A/B/C의 성공 항목을 합쳐 전체 suite PASS로 계산하지 않는다.

| 실행 | 최초 증상/중단 지점 | 종료 코드·원본 증거 | 확인한 원인/수정 | 같은 검사 최종 재실행 |
|---|---|---|---|---|
| 첫 BE 단위검사, 04:41:37 | 기존 권한 fixture의 미commit 자료가 새 메타데이터 읽기의 별도 트랜잭션에서 보이지 않음 | exit1, 124개 중 1 실패. `be-index-unit-first-2026-09-30T044137825552+0000.json/.log` | 외부 호출이 없는 `materialSummaries` 읽기는 호출자의 실제 트랜잭션이 있으면 같은 트랜잭션에 참여. 외부 저장 호출 경계는 유지 | 04:47:32 재검사 124 PASS/exit0. `be-index-unit-fixed-2026-09-30T044732323622+0000.json/.log` |
| 첫 AI 단위검사, 04:41:32 | 중복 배치 시험 fixture의 실제 임베딩 2회와 3회 호출 기대가 불일치 | exit1, 87개 중 1 실패. `ai-index-unit-first-2026-09-30T044132198928+0000.json/.log` | fixture를 명확한 3개 학습 블록으로 구성하고 upsert 6회/임베딩 3회/정확한 청크 수를 함께 검사 | 첫 수정 재검사 88 PASS/exit0, 이후 추가 회귀 포함 90 PASS. `ai-index-unit-fixed-2026-09-30T044720836611+0000.json/.log`, `ai-tests-2026-09-30T045544224104+0000.json/.log` |
| 첫 정상 색인 경로, 04:48:30–04:49:00 | 실제 접수→broker→worker→Chroma→활성→조회 | exit0, 해당 실행 19 PASS. `index-first-happy-2026-09-30T044830925606+0000.json`, `indexing-checks-20260930T044830-6b7c8824.json` | 정상 제어 경로 확보 | 전체 장애 suite 완료를 뜻하지 않음 |
| 전체 suite 첫 시도, 04:56:05–04:56:53 | 정상 시나리오 뒤 publication helper `ValueError` | exit1, 21 PASS/1 FAIL. `index-final-suite-2026-09-30T045605703337+0000.json`, `indexing-checks-20260930T045605-6238c451.json` | 검증용 SQL identifier 검사에서 숫자를 포함한 실제 `s3key` 계열 컬럼명을 거부하던 오류 수정. 식별자 allowlist는 유지 | 최종 이미지에서 publication 포함16개 시나리오 완료 확인(5절) |
| 후속 suite 의도적 중단, 05:01:50–05:04:29 | happy/publication/failure_preservation까지 진행 후 소스 수정 반영을 위해 중단 | **exit-2 / 명령 FAIL**, 완료된 체크 57 PASS/0 FAIL. `indexing-2026-09-30T050150355441+0000.json`, `indexing-checks-20260930T050150-21f0ec65.json` | 이 부분 결과를 전체 통과로 사용하지 않고 새 이미지 검증으로 분리 | 최종 이미지의 원본 실패와 후속 시나리오 검증은5절 |
| AI identity-map 수정, 05:05:33–05:05:44 | FOR UPDATE만으로 기존 SQLAlchemy identity-map 객체가 새 DB 값으로 갱신되지 않는 정적 검토 문제 | 관련 회귀 2개 추가 후 AI 92 PASS/exit0. `ai-tests-2026-09-30T050533399936+0000.json/.log` | resource와 현재 소유 객체의 잠금 조회에 `populate_existing()` 적용, 다른 연결 commit 후 최신 원본/소유 재조회 검사 | 최종 이미지의 독립 연결/워커 통합 PASS(5·6절) |
| 두 번째 suite 의도적 중단, 05:05:49–05:11:15 | happy/publication/failure_preservation 완료 후 진행 중 BE 재시도 권한 경합 수정을 반영하려고 중단 | **exit-2 / 명령 FAIL**, 완료된 체크 112 PASS/0 FAIL. `index-final-suite-2026-09-30T050549523215+0000.json`, `indexing-checks-20260930T050549-57ef7903.json` | 첫 권한 검사 후 잠금 대기 중 소유·연결 변경을 놓치지 않도록 현재 소유와 연결을 잠금 후 다시 검사하고 JPA 캐시를 비움 | 해당 수정의 BE 회귀 추가 후 아래 126개 단위검사 통과. 전체 suite 결과는 별도 |
| 재시도 권한 수정 후 단위검사, 05:12:18–05:12:49 | 당시 BE/AI/PDF 이미지의 단위검사 | BE126/AI92/PDF6 PASS, exit0. `final-unit-suite-2026-09-30T051218029734+0000.json/.log`; `be-tests-2026-09-30T051218624188+0000.json`, `ai-tests-2026-09-30T051236823161+0000.json` | BE 재시도 경합 회귀 2개를 추가. 이 실행의 AI92는 아래 실제 HTTP timeout 결함 수정 전 이미지 | 이후 transport 수정 이미지의 최종 단위/시나리오 검증은5절 |
| Part A, 05:12:52–05:25:52 | broker 장애 시험의 `broker_down_job_remains_durable` 실패 후 suite 중단 | **exit1 / FAIL**, 254 PASS/2 FAIL. `index-final-suite-2026-09-30T051252762233+0000.json`, `indexing-checks-20260930T051252-0684d000.json` | 검사 보조 코드가 Compose `start`로 의존 서비스까지 시작하여 의도한 broker 중단 상태를 해제함. 선택한 기존 서비스만 `up -d --no-deps`로 시작하도록 보조 코드 수정. 두 FAIL 중 하나는 같은 실패의 실행 래퍼 기록 | Part B에서 delivery 완료. Part A 원본 실패는 유지하며 최종 이미지의 결과는5절 |
| Part B, 05:27:14–05:32:42 | delivery/late_worker 완료 후 클라이언트 owner 필드 거부 상태 코드 기대 불일치 | **exit1 / FAIL**, 109 PASS/2 FAIL/7 NOT_RUN. `indexing-2026-09-30T052714681059+0000.json`, `indexing-checks-20260930T052714-4834394c.json` | Spring은 잘못된 owner 입력을 HTTP400으로 거부했으나 검사가 422를 기대함. Spring 계약에 맞게 400을 요구하고 거부 전후 색인 원장 불변 검사를 추가. 입력 허용으로 기대값을 완화한 변경은 아님 | Part C에서 authorization 및 원장 불변 검사 완료. 최종 이미지 결과는5절 |
| Part C, 05:33:41–05:37:16 | authorization/storage_failure 완료 후 실제 Chroma 일시 정지에서 HTTP transport 대기가 끝나지 않음 | **exit1 / FAIL**, 67 PASS/1 FAIL/5 NOT_RUN. `indexing-2026-09-30T053341992830+0000.json`, `indexing-checks-20260930T053342-6dd285f5.json` | 실제 구현 결함: Chroma 0.6.3 `Client.from_system` 경로가 미리 제한을 설정한 transport를 다른 transport로 교체하여 기한이 적용되지 않음. 전용 설정 transport를 실제 SDK 호출에 유지하도록 수정 | 수정 이미지의 실제 pause가5.02초/503으로 종료. 이후 검증은5절. 예외 주입 결과로 대체하지 않음 |

04:55:25–04:55:57 UTC의 중간 통합 단위 실행은 BE124/AI90/PDF6, exit0이었다(`final-unit-suite-2026-09-30T045525990497+0000.json`). identity-map 수정 후 05:05:15–05:05:46 UTC 단위 실행도 exit0이며 AI는 92개로 늘었다(`final-unit-suite-2026-09-30T050515081788+0000.json`). 서로 다른 소스/이미지의 결과를 최종 전체 통합 수치로 합산하지 않는다. 최종 회귀 결과는5절에서 별도로 기록한다.

나머지 schema/초기 PDF/제한 복구/브라우저를 살펴본 탐색 실행은 **05:39:09–05:43:41 UTC exit0, 107 PASS**였다(`indexing-checks-20260930T053909-227b6564.json`, `indexing-2026-09-30T053909065143+0000.json`). 실제 Chrome 14개 검사를 포함하지만 transport 수정 전 실행 이미지이므로 최종 전체 PASS 수에 더하지 않는다. 원본 실패 기록을 보존한 채 수정 이미지로 정상 경로부터 순차 재검증했다(5절).

transport 수정 후 **05:44:18–05:44:50 UTC** BE126/AI93/PDF6 단위검사는 exit0이었다(`final-unit-suite-2026-09-30T054418932592+0000.json`). 뒤이은 실제 pause 검사에서 조회가 **5.02초 후 503**으로 끝나고 이전 pointer/digest와 복구 후 조회가 유지됨을 확인했다. 최종 검토에서 DB 단위검사의 전달기 중지 전제도 명령에 자동화하여, 마지막 단위검사는 그 전제를 적용한 별도 실행으로 5절에 기록한다.

최종 앱 이미지의 전체 시도 **05:45:12–06:07:10 UTC**는 15개 시나리오를 완료했지만 마지막 browser 준비 로그인에서 중단됐다. 원본은 **exit1, 472 PASS/2 FAIL/1 NOT_RUN**이다(`final-index-all-2026-09-30T054512001129+0000.json`, `indexing-checks-20260930T054512-27c118d3.json`). 두 FAIL은 로그인 assertion과 같은 예외의 래퍼이며 별개 결함 두 개가 아니다. 당시 첫 HTTP 코드는 기록되지 않았으므로 이를 특정 상태 코드였다고 단정하지 않는다. 같은 구간 자체 Spring 로그에서 Redis command timeout을 확인했고, 후속 실제 합성 로그인/BE health/Redis PING은 정상 복구됐다(`post-broker-login-diagnostic.json`).

검증 보조 코드가 실제 broker 장애 뒤에는 health만으로 준비 완료라고 간주하지 않도록 보완했다. 합성 로그인은 최종 HTTP200/AT를 요구하며, 401/403/400 또는 잘못된200은 즉시 실패한다. 502/503/504만 재시도 예산25초·각 HTTP 요청5초로 준비를 기다린다. CSRF와 로그인 두 요청을 쓰므로 전체25초 상한이라는 뜻은 아니며, CSRF 오류는 즉시 실패로 전파된다. 복구 한도와 browser를 동일한 서비스 이미지에서 다시 검사하고, 15개 완료 원본의 FAIL을 지우거나 부분 PASS 수를 합산하지 않는다.


영속성 검사 최초 실행 **06:18:46–06:19:31 UTC**의7 PASS/1 FAIL은 변경된 자료에 과거 smoke 세션을 사용해 발생한 `409 RAG_SOURCE_CHANGED`였다. 기존 SQLite 세션은 실제로 남아 있었고 데이터를 잃은 오류가 아니다(`persistence-old-session-diagnostic.json`). 보조 검사는 기존 로그를 보존하며 현재 활성 원본에 연결된 새 합성 세션을 만든다. 재색인 없이 같은 컨테이너 ID/이미지, 자료 pointer·source, 세션 연결·메시지, 실제 Chroma 내용 digest를 재시작 전후 비교하도록 강화했다.

이 보조 코드 첫 실행 **06:27:13–06:27:19 UTC**는5 PASS/0 FAIL/1 BLOCKED였다(`final-persistence-2026-09-30T062713908850+0000.json`). Health 필드가 없는 worker의 Docker 메타데이터 조회 오류였고 stop 전에 끝났다. 필드 유무를 검사한 뒤 읽도록 수정했다. 최종 **06:29:02–06:29:53 UTC exit0,19 PASS**에서 동일 컨테이너 재시작·실제 조회를 완료했다. 두 실패/차단 원본은 timestamp 파일로 보존한다.

## 4. 실제 의존성과 실행 식별자

| 대상 | 설정/대역 경계 | 실제 버전·이미지 ID/digest·관측 시각 | 최종 증거 |
|---|---|---|---|
| Spring/FastAPI/MySQL | 실제 서비스·실제 원장 | 실제 HTTP/DB 확인. 아래 최종 이미지 및 구성요소 소스 식별자 기록 | `runtime-manifest-2026-09-30T054510333213+0000.json` |
| Redis/Celery | 실제 broker→worker, eager 아님 | Celery **5.5.3**, `eager=false`, 큐 `indexing-v3`, 실제 broker send/worker receipt 관측 | 명령별 이미지 식별자와 6절 작업/전달 집계 |
| Chroma | 전용 서버/볼륨, HTTP thin client | 실제 서버/클라이언트 **0.6.3**, heartbeat·저장·query 확인. SDK의 실제 transport와 Collection을 연결해 connect 2초/read 5초 유지 | 실제 pause 조회 **5.02초/503**, 기존 digest 보존 및 재시도 성공. 최종 전체 실행은 5절 |
| 임베딩/LLM/OCR/파일 저장/알림 | 명시적 local 대역 또는 비활성 | 8차원 deterministic hash 벡터를 실제 Chroma에 저장. 실제 외부 공급자 호출 NOT_RUN | 소스 계약은 [11절 설계](11-indexing-reliability-design.md), 호출 횟수는6절 |

기존 의존성 버전은 일괄 갱신하지 않고 Chroma thin client 0.6.3과 필요한 추가 패키지를 잠갔다. `dependency-resolution.json`에는 `existing_versions_unchanged=true`와 wheel hash가 있다. 서버는 전용 Chroma 이미지/영속 볼륨을 쓰고 AI/워커가 서버 저장 디렉터리를 공유 쓰기하지 않는다.

최종 AI/worker/dispatcher build는 **05:43:57–05:43:59 UTC exit0**, 재기동은 **05:44:00–05:44:18 UTC exit0**이다. `index-transport-fix-build-2026-09-30T054357005883+0000.json/.log`, `index-transport-fix-up-2026-09-30T054400350291+0000.json/.log`에 보존했다. build 명령의 관측 컨테이너는 재기동 전 이미지일 수 있으므로 build 직후 성공만을 새 이미지 실행으로 해석하지 않는다. 아래는 최종 **06:30:22 UTC** 실제 서비스 관측값이다(`runtime-manifest-2026-09-30T063022571774+0000.json`). 05:45:10 manifest도 원본으로 보존했다. 인증 전용 BE/web alias는06:16:58–06:17:11 `auth-test-up` 이후 각각 본 서비스와 같은 이미지임을 확인했다.

| 서비스 | 최종 실행 image ID (`sha256:`) |
|---|---|
| be | `95c3dd12b2afe76c7cc87ea3ce86bde4c22df887ad7351b1458da5805247259c` |
| ai | `fc33a754a4be3762c793699e0f550be0bc74991fd7d0d0a73b658cd1b4940633` |
| worker | `48a3425fdbd726c66a0714fa569b012a94d7e700570644511e2f4925edf0e944` |
| index-dispatcher | `006ca6b3adc4495b2ef894dc337e7ba8fe6685c9cbf36309aacbef31751d7781` |
| chroma | `6871ba69fa65ce7f8fa779583d2266207c29c05009961c851c3331c7bd46734d` |
| web | `2eee1f57c6ea599a0eb9a2bb0ec5d37fcf0657ff29e03e52ef229f8512f42d28` |
| python-service | `1910e86576f8f9945c64fcc90279d5a3573be14ca8ba86c31c38a9e9966e8e94` (아래 platform payload 동등성 근거) |
| mysql | `b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb` |
| redis | `858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499` |

Chroma base는 BuildKit이 실제로 해석한 `chromadb/chroma:0.6.3@sha256:e0e78dc7609a599b63c99753442c7d01b1d3d369ce0e3bf3e0540536fec4fa7a`다(`compose-build.log`). 별도로 tag된 base runtime image가 있다는 주장은 하지 않는다. 자체 wrapper image와 base digest를 구분한다.

서비스 소스 SHA256은 위 manifest에서 `ai/app=c801ba8641ccf9428730c4ecef4ad38848c761b4a54bb4ea6a09fd3c0548f0ac`, `be/src/main=f62e63cd5ecf356ac3e3a5724535ce88cde0ff47441f96cf01057c6c8ac3e371`, `fe-web/src=32ddf2c5172cae07d2d95aa43de8dfc59d6312b1fb2b49fc4ac7a19d6e8841f2`로 기록했다. 정렬한 상대 경로·NUL·파일 바이트·NUL을 연결하며 pycache를 제외한다. 문서/검증 하네스 수정에 따라 저장소 전체 working-source hash가 바뀌는 것과 앱 이미지 변경을 구분한다. 이전 이미지의 부분 결과를 최종 전체 PASS 수에 합치지 않는다.

첫 영속성 검사의 Compose `up`은 빌드 태그를 다시 적용해 PDF 서비스의 image index를 `bbd57…`에서 `1910e86576f8f9945c64fcc90279d5a3573be14ca8ba86c31c38a9e9966e8e94`로 바꿨다. 이 차이를 숨기지 않는다. 이전/이번 immutable build 로그를 대조한 결과 **실행 platform manifest `7e688bb4f609124dc873cf7b982e2f811f4f2f527a95b672a9a4bb3ac66d087f`와 config/rootfs `8ceb033432a6c6dc6107b9588aa90335091d97c53a2802ffdcd7a0695da6384c`는 동일**했고 attestation/index만 달랐다. `pdf-image-equivalence.json`에 두 원본 로그 해시를 기록했다. 새 index의 현재 PDF에서도 06:23:39–06:23:40 UTC 단위6개/exit0을 확인했다(`final-pdf-unit-equivalent-image-2026-09-30T062339091870+0000.json`). 이후 영속성 검사는 같은 컨테이너 ID/이미지를 직접 시작하고 전후 일치를 요구한다. 변경된 실행 코드의 결과를 예전 이미지로 대신한 것으로 취급하지 않는다.

## 5. 실제 명령·종료 코드·회귀

아래 시각은 **2026-09-30 UTC**, 증거 경로는 `.local/phase3b/results/` 기준이다. 각 명령의 timestamp JSON에 종료 코드와 소스·관측 이미지 식별자를 보존했다. 앱 핵심 소스·이미지의 연결과 PDF 이미지 attestation 차이는 4절을 따른다. PASS인 개별 검사는 해당 명령에서 FAIL/BLOCKED가 없었다는 뜻이며, 전체 묶음 실행의 결과와 구분한다. 단위검사·실제 HTTP·실제 프로세스 중단·실제 Chrome의 개수를 합산하지 않는다.

**기존 회귀 묶음의 원본 실행은 FAIL이다.** `final-legacy-all-2026-09-30T061045536242+0000.json/.log`의 06:10:45–06:19:31 실행은 exit1이었다. 06:18:46–06:19:31 영속성 검사에서 옛 대화 세션을 재사용하여 `409 RAG_SOURCE_CHANGED`를 받았고 원본은 **7 PASS/1 FAIL**이다(`final-persistence-2026-09-30T061846319819+0000.json`, `persistence-2026-09-30T061846359297+0000.json/.log`). 아래 개별 회귀의 PASS를 이 묶음 전체의 PASS로 바꾸지 않는다. 이후 영속성 보조 코드의 계약을 고치고 최종19개 검사, after/retention을 별도 재검증했다. 원본 실패를 지우지 않는다.

| 명령/검사 | 상태 | 시작–종료 UTC | 종료 코드·개수 | 원본 증거 |
|---|---|---|---|---|
| `manage.py scope-test` | PASS | 06:11:38–06:11:38 | exit0, 58 PASS | `scope-unit-2026-09-30T061138209074+0000.json/.log`; `final-scope-test-2026-09-30T061138171887+0000.json` |
| `manage.py test` — BE/AI/PDF | PASS | 06:10:46–06:11:34 | exit0, BE126 / AI93 / PDF6 PASS | `final-unit-suite-2026-09-30T061046263105+0000.json/.log`; `be-tests-2026-09-30T061059743425+0000.json/.log`, `ai-tests-2026-09-30T061118562375+0000.json/.log`, `pdf-tests-2026-09-30T061130890865+0000.json/.log` |
| `manage.py startup` | PASS | 06:11:39–06:11:54 | exit0, 6 PASS | `startup-key-regression-2026-09-30T061139242246+0000.json/.log` |
| `manage.py auth` | PASS | 06:11:55–06:12:14 | exit0, 131 PASS | `auth-regression-2026-09-30T061155598793+0000.json/.log`; `auth-checks.json` |
| `manage.py smoke` | PASS | 06:12:15–06:12:20 | exit0, 27 PASS | `smoke-2026-09-30T061215550427+0000.json/.log`; `smoke-checks.json` |
| `manage.py security` | PASS | 06:12:21–06:12:24 | exit0, 16 PASS | `security-2026-09-30T061221495080+0000.json/.log`; `security-checks.json` |
| `manage.py authorization` | PASS | 06:12:25–06:12:41 | exit0, 188 PASS | `authorization-2026-09-30T061225418173+0000.json/.log`; `authorization-checks.json` |
| `manage.py grading` | PASS | 06:12:42–06:16:58 | exit0, 284 PASS — 실제 공급자 대기 경계 회귀 6개 포함 | `grading-2026-09-30T061242445813+0000.json/.log`; `grading-checks-20260930T061242-4ddb2e26.json` |
| 색인 전체 시도 원본 | **FAIL 유지** | 05:45:12–06:07:10 | exit1, 472 PASS / 2 FAIL / 1 NOT_RUN | `final-index-all-2026-09-30T054512001129+0000.json/.log`; `indexing-checks-20260930T054512-27c118d3.json` |
| 색인 제한 복구·브라우저 후속 실행 | PASS | 06:07:22–06:10:45 | exit0, 78 PASS / 0 FAIL / 0 NOT_RUN | `final-index-remaining-2026-09-30T060722558458+0000.json/.log`; `indexing-checks-20260930T060722-eaed0b91.json` |
| 색인 시나리오 coverage 판정 | PASS — 16개 시나리오 | 위 두 실행의 증거 매핑 | 별도 명령 exit 없음. 같은 앱 이미지·컴포넌트 소스에서 16개 완료 확인 | `indexing-final-coverage.json` — 두 원본 보고서 SHA-256과 시나리오별 근거 포함 |
| 웹 `test:auth` | PASS | 04:37:53–04:37:54 | exit0, 25 PASS | `web-auth-unit-metadata-20260930T043830108718Z.json`; `web-auth-unit-20260930T043753995490Z.log` |
| 웹 `test:authorization` | PASS | 04:37:53–04:37:54 | exit0, 9 PASS | `web-authorization-unit-metadata-20260930T043830110149Z.json`; `web-authorization-unit-20260930T043753995458Z.log` |
| 웹 `test:grading` | PASS | 04:37:53–04:37:54 | exit0, 19 PASS | `web-grading-unit-metadata-20260930T043830111129Z.json`; `web-grading-unit-20260930T043753995570Z.log` |
| 웹 `test:indexing` | PASS | 04:37:53–04:37:54 | exit0, 20 PASS | `web-indexing-unit-metadata-20260930T043830112719Z.json`; `web-indexing-unit-20260930T043753995452Z.log` |
| 웹 `typecheck` | PASS | 04:37:53–04:37:54 | exit0, 테스트 개수 해당 없음 | `web-typecheck-metadata-20260930T043830113855Z.json`; `web-typecheck-20260930T043753995520Z.log` |
| 웹 `build -- --mode phase1` | PASS | 04:38:30–04:38:32 | exit0, 테스트 개수 해당 없음 | `web-build-20260930T043830107531Z.json/.log` |
| Chrome 인증 UI | PASS | 06:17:12–06:18:19 | exit0, 17 PASS | `final-browser-auth-2026-09-30T061712751028+0000.json/.log`; `browser-checks-1790749099755.json` |
| Chrome 권한 UI | PASS | 06:18:20–06:18:43 | exit0, 18 PASS | `final-browser-authorization-2026-09-30T061820688994+0000.json/.log`; `browser-authorization-checks-1790749123015.json` |
| Chrome 채점 API 계약 | PASS | 06:18:44–06:18:45 | exit0, 11 PASS — 학생 웹 UI 검사가 아님 | `final-browser-grading-2026-09-30T061844037388+0000.json/.log`; `browser-grading-checks-1790749125521.json` |
| Chrome 교사 색인 UI | PASS | 06:09:47–06:10:20 | exit0, 14 PASS — 위 후속 색인 실행에 포함 | `browser-indexing-orchestration-2026-09-30T060947862170+0000.json/.log`; `browser-indexing-checks-1790748616629.json` |
| `manage.py persistence` 최종 재검증 | PASS — 원본 FAIL 보존 | 06:29:02–06:29:53 | exit0, 19 PASS | `final-persistence-2026-09-30T062902362405+0000.json/.log`; `persistence-session-20260930T062907Z-261fe99b.json` |
| `manage.py isolation` | PASS | 06:31:19–06:31:21 | exit0, 18 checks true | `final-isolation-2026-09-30T063119389682+0000.json/.log`; `resource-isolation-checks.json` |
| `indexing_data.py after` | PASS | 06:29:53–06:30:18 | exit0, 원래 MySQL477/SQLite189행·27파일 보존 | `final-data-preservation-2026-09-30T062953753160+0000.json/.log`; `data-preservation.json` |
| `indexing_retention.py` dry-run | PASS | 06:30:19–06:30:22 | exit0, 활성 pointer 문제0, 모두 보존 | `final-retention-2026-09-30T063019095435+0000.json/.log`; `index-retention-dry-run-20260930T063019138618Z-6a802c50.json` |
| `manage.py stop` | PASS | 06:31:06–06:31:19 | exit0, 자체11개 모두 exited | `final-stop-2026-09-30T063106910972+0000.json/.log` |

색인 coverage는 원본 실패를 덮는 합산 통계가 아니다. 첫 실행은 15개 시나리오를 완료한 뒤 Redis 장애 이후 로그인 준비에서 실패했고, 후속 실행은 실제 합성 로그인 준비를 확인한 다음 제한 복구·브라우저를 다시 수행했다. coverage 파일은 `bounded_recovery`를 후속 실행에 연결하고 나머지 시나리오도 명시적으로 한 원본에 연결한다. **472와 78을 더한 PASS 총계를 만들지 않으며**, Chrome 색인 UI14와 채점의 공급자 대기6도 상위 실행에 중복 가산하지 않는다. 원본 실행의 FAIL은 유지하며 영속성 최종 재검증은 별도19 PASS다.

## 6. 작업·호출·활성 전환과 실제 중단

원본: `indexing-checks-20260930T054512-27c118d3.json`
SHA-256: `28d76a5ea8074d60149825e14d6f59ffafa406f92472d06a04158dd65e787adb`

원문 **472 PASS / 2 FAIL / 1 NOT_RUN** 보존. 완료 15그룹이며 browser 완료는 이 보고서에서 주장하지 않는다. FAIL은 `index_login_owner` 및 전파된 `indexing_execution/AssertionError`다.

아래는 MATERIAL별 누계이며 기준용 이전 작업도 포함한다. 초기 PDF 33개는 제외했다. 전달/반환/수신 = DB 전달 시도 / broker 반환 / worker 수신. 실행/후보의 후보는 할당된 이름 수이며 실제 생성 성공과 같지 않다. 현재 청크는 활성 pointer가 가리키는 실행의 검증된 수다.

| 시나리오 (자료 ID) | 논리 작업 | 전달/반환/수신 | 실행/후보 | 임베딩 시도 | 현재 활성 청크 | 활성화 |
|---|---:|---:|---:|---:|---:|---:|
| 정상 (239) | 1 | 1/1/1 | 1/1 | 3 | 3 | 1 |
| 실제 HTTP 읽기 timeout·복구 (240) | 2 | 3/3/3 | 3/3 | 6 | 3 | 2 |
| 발행 객체·DB 원자성 (241) | 1 | 1/1/1 | 1/1 | 3 | 3 | 1 |
| 부분 저장 실패·재시도 (242) | 2 | 3/3/3 | 3/3 | 7 | 3 | 2 |
| 검증 거부: hash_mismatch (243) | 2 | 2/2/2 | 2/2 | 3 | 3 | 1 |
| 검증 거부: bad_dimension (244) | 2 | 2/2/2 | 2/2 | 4 | 3 | 1 |
| 검증 거부: bad_vector (245) | 2 | 2/2/2 | 2/2 | 4 | 3 | 1 |
| 검증 거부: missing_chunk (246) | 2 | 2/2/2 | 2/2 | 6 | 3 | 1 |
| 검증 거부: foreign_metadata (247) | 2 | 2/2/2 | 2/2 | 6 | 3 | 1 |
| 검증 거부: extra_chunk (248) | 2 | 2/2/2 | 2/2 | 6 | 3 | 1 |
| 검증 거부: bad_stored_vector (249) | 2 | 2/2/2 | 2/2 | 6 | 3 | 1 |
| 검증 거부: bad_document (250) | 2 | 2/2/2 | 2/2 | 6 | 3 | 1 |
| 검증 거부: activation_rollback (251) | 2 | 2/2/2 | 2/2 | 6 | 3 | 1 |
| 검증 거부: storage_timeout (252) | 2 | 2/2/2 | 2/2 | 4 | 3 | 1 |
| 본문·세션 개정 (253) | 2 | 3/3/3 | 3/3 | 7 | 3 | 2 |
| 중복 메시지 (254) | 1 | 1/1/4 | 1/1 | 3 | 3 | 1 |
| 발행 commit 직후 Spring crash (255) | 1 | 1/1/1 | 1/1 | 3 | 3 | 1 |
| 부분 저장 직후 worker crash (256) | 2 | 3/3/4 | 3/3 | 7 | 3 | 2 |
| 활성화 직전 worker crash (257) | 2 | 3/3/4 | 3/3 | 9 | 3 | 2 |
| 활성화 직후 worker crash (258) | 2 | 2/2/5 | 2/2 | 6 | 3 | 2 |
| broker 장애·복구 (259) | 1 | 2/1/1 | 1/1 | 3 | 3 | 1 |
| 전송 직후 dispatcher crash (260) | 1 | 2/2/2 | 1/1 | 3 | 3 | 1 |
| 잠금 후 실제 DB 갱신 조회 (261) | 2 | 1/1/1 | 1/1 | 3 | 3 | 1 |
| 만료된 worker의 늦은 쓰기 (262) | 1 | 2/2/4 | 2/2 | 4 | 3 | 1 |
| 본문 역순 완료 (263) | 2 | 2/2/2 | 2/2 | 6 | 3 | 1 |
| 중복 batch upsert (264) | 1 | 1/1/1 | 1/1 | 3 | 3 | 1 |
| 삭제·공유 해제 권한 (265) | 2 | 2/2/2 | 2/2 | 6 | 3 | 1 |
| 소유권 변경 (266) | 2 | 2/2/2 | 2/2 | 6 | 3 | 1 |
| Chroma 중단·재시작 (267) | 2 | 3/3/3 | 3/3 | 6 | 3 | 2 |
| DB 제약·활성화 조건 (268) | 1 | 1/1/1 | 1/1 | 3 | 3 | 1 |
| 실행 한도 3회 (269) | 1 | 3/3/3 | 3/3 | 3 | 없음 | 0 |
| 전달 한도 5회 (270) | 1 | 5/0/0 | 0/0 | 0 | 없음 | 0 |

합계(자료 32개): 논리 작업 53, 실행/후보 60/60, 전달/반환/수신 67/61/71, 로컬 임베딩 시도 151, 활성화 37.

`null` 청크는 0이 아니다. 늦은 worker 사례는 실제 이전 후보가 0→1청크로 바뀌었지만 현재 활성 3청크는 보존됐다. 실행 한도 사례는 1개 작업·3개 세대·3개 후보·활성화 0이며 4번째 retry는 409다. 전달 한도 사례는 5회에서 FAILED, worker 수신/실행/활성화 모두 0이며 broker 복원 후에도 예산이 초기화되지 않았다.

이전/현재 digest 비교(전체 값; 이전 = 별도 표시가 없는 한 이전 작업의 검증된 digest):

| 시나리오 | 이전 digest | 현재 활성 digest |
|---|---|---|
| 실제 HTTP 읽기 timeout·복구 (보존된 실제 이전 index) | `dcdd4ef7d776b32789e0663cd8ac36b9a9b759c24cc9daffc909a97681d391e8` | `42f3882373414a618137c1826626b5d62c40c5d21cf33cd21e98a24b945f8880` |
| 부분 저장 실패·재시도 (before=after 실제 보존 확인) | `13b4b474d35b3600cb390c5cb7e25ab7a108807c09e8ce7405799fddfe69c872` | `6efd067b3b0b43c4225705b07f9fd03c3222cff5a5ebc26cc0a5f5c761ea1d32` |
| 부분 저장 직후 worker crash (보존된 실제 이전 index) | `a357c43d7d8fb4dcb3aed6ff88cf501ab4b9c0504e8e16bca89532762dc133db` | `9ede32ddbda9308fd352300bc72e4b67e4e52dd2ac0354f1503a3259a17f3c09` |
| 활성화 직전 worker crash (보존된 실제 이전 index) | `dfde5010e07415eb18558ef2246181afbc93b48c28eb98d3adf0ddb3cff6d0a9` | `98148de7f424efd172267dc7c66b098fa535c83456bcba1b492e7272a7a9f238` |
| 활성화 직후 worker crash (보존된 실제 이전 index) | `225d3d9cfac94fdde088dce2c7cea51a9c5e508bbd934bce3d454114c65a0d2a` | `d4babdf84a47ddf0682bbf3d00f7ef68ad8d639654c54f22b5fdc35c1522ad41` |
| 만료된 worker의 늦은 쓰기 (늦은 후보 실제 1청크) | `ec5314f99cda722489a946c286cc0d685b934cd88e0134c230bc77d825dc81da` | `12c1b24a6d84a662a87005f77bf6c4960640c9d4b8b7aa28cc88488b718d459a` |
| 본문 역순 완료 (늦게 완료된 이전 source) | `30bfe3660696a1679def42c2606710c738d9cd21315c45c0699ce5f5a4164acc` | `1302cb3b3c0c52fd8ed274547c2c129db46283e56cb59ad0a39156a59dded36e` |
| Chroma 중단·재시작 (보존된 실제 이전 index) | `100c0e6a461d9757a8bf8f78a36ea7f10c8bc8706e5bf4ac0b1309821f9e5bc3` | `6a9a647c3cd779f3ad1c7f010119f1e4cc8a30e549b7c2d2db9b2464a6b25e6b` |

이전 물리 digest와 비교 PASS만 있고 after 원문값이 없는 사례는 두 값을 새로 관측했다고 주장하지 않는다. 전체 job UUID, 세대별 상태·후보·청크·digest 및 원본 중간 증거는 같은 이름의 JSON에 있다. 실제 외부 임베딩/LLM 호출 수나 품질을 뜻하지 않는다.

위 digest 표는 이전 버전과 복구 후 새 활성 버전을 나란히 적은 것이다. 서로 다른 설정/원본의 digest가 같아야 한다는 뜻이 아니다. **보존 판정은 이전 물리 컬렉션의 장애 전후 비교**를 사용한다. 이전 candidate 자체를 다시 쓴 것이 아니라 별도 세대 candidate를 활성화했다. 네 중단 구간은 private gate 관측 뒤 검증한 자체 Spring/worker의 실제 `SIGKILL`과 재기동으로 수행했다. broker 전송 직후 전달기 종료도 별도 실제 중단이며, 오류 주입/DB rollback probe와 구분한다. `review/final-index-statistics.json`에 세대별 실행과 전체 digest를 보존했다.

## 7. 스키마·기존 데이터·물리 인덱스 보존

| 대상 | 이번 시작 baseline | 최종 비교 | 증거 |
|---|---|---|---|
| MySQL 원래 테이블·행·원래 컬럼 digest | 34개 테이블477행 | PASS, 모든 원래 컬럼의 행 hash 다중집합에서 누락/변경0 | `data-before.json`, `data-preservation.json` |
| 기존 채점 attempt/snapshot/result/log | attempts68 / items130 / results68 / quiz logs75행 | PASS, 각각 원래 행·컬럼 보존 | 위 보고서의 네 테이블 항목 |
| SQLite 원래 행·대화/작업 기록 | 189행: grading calls50 / vectors22 / chat messages68 / sessions24 / embedding tasks25 | PASS, 누락/변경0. 과거 대역 인덱스를 새 활성으로 재분류하지 않음 | 위 보고서의 다섯 SQLite 항목 |
| 기존 파일 객체 | 27개 | PASS, changed_files=[] | `original_objects` 항목 |
| V004 전진 적용·재실행·실제 제약 | 기존 자체 DB | PASS, 같은 migration 재실행 무변경·필수/UNIQUE/조건 검사 | 2절 migration 증거 및 최종 schema 시나리오 |
| 별도 새 자체 시험 스키마 최초 설치 | 새 `dodream_phase3b_fresh` | PASS, JPA 시작 전 V003/V004 적용·최초 기동·제약. 스키마 보존 | 2절 fresh 증거 |
| 이전 정상 Chroma pointer/청크 | 각 새 합성 자료의 정상 candidate | PASS, 실패 중 이전 pointer/digest·조회 보존. 상세6절 | 최종 색인 원본의 시나리오별 보존 체크 |
| 동일 컨테이너 재시작 영속성 | 현재 원본rev3/활성 execution310, 새 세션의 메시지2개, 실제 Chroma1청크 | PASS, 전후 ID/이미지·pointer·source·binding·messages·physical digest 동일, 재색인 없이 HTTP200 | `persistence-session-20260930T062907Z-261fe99b.json`, 최종19 PASS |
| retention dry-run | 원장 실행308 / 물리 collection295 / 객체 파일461 / 현재 참조 파일명374 | PASS, 활성 pointer 문제0. 이전 정상/실패/미참조/미분류 모두 retain | `index-retention-dry-run-20260930T063019138618Z-6a802c50.json` |

재시작 전후 물리 digest는 모두 `1f99ca912047cedd610ab4924245ddd6f1a85e8af981ae3234b74a193363b205`다. 이는 같은 컬렉션의 문서·메타데이터·벡터 내용을 비교한 값이다. MySQL/SQLite baseline은04:23:31 원본을 그대로 사용했다. 기존 authz 합성 관계의 일시 변경/복원은2절에서 구분했고 baseline을 갱신하지 않았다.

원장 실행 수와 물리 collection 수의 차이는 실패/미생성 후보와 단위검사 fixture를 포함한다. DB 단위검사는 전달기를 원래 상태에 맞춰 잠시 중지·복구하며 실제 candidate가 없는 test ACTIVE 행을 통합 활성화 성공으로 세지 않는다. 최종 현재 활성 pointer의 물리 존재 검사에서 문제는0이었다. Chroma와 객체 목록은 서로 다른 관측이며 분산 snapshot이나 삭제 안전성 증명이 아니다. 미참조 후보/객체의 자동 삭제·GC를 하지 않았고 이번에 추가한 Chroma 볼륨을 포함해 자체 영속 볼륨5개를 보존했다.

## 8. 권한·조회·브라우저 범위

현재 공유·담당·소유·미삭제 확인, 타인 작업 ID/임의 collection/URL 거부, 같은 원본 실패의 이전 정상 조회, 새 원본과 구버전 불일치409, 채팅 세션의 원본 버전 검사를 실제 API로 통과했다. 작업 실행/활성화 때 현재 권한을 재확인하고, 조회는 한 요청에서 선택한 활성 버전 하나만 사용한다. 준비 중 후보·다른 자료·초기 PDF로 fallback하지 않는다. 변경된 원본에 연결된 이전 대화는409로 거부하고 로그는 보존한다.

교사 Chrome UI의 접수·준비·사용 가능·실패·명시 재시도14개가 PASS다. bounded polling, 세션 epoch/로그아웃 뒤 늦은 응답 차단도 웹 단위20개에 포함한다. 별도 로컬 시험 프로필과 loopback 서비스에서 실제 인증17/권한18/채점 API 계약11개도 PASS였다. 네트워크·화면 증거는 합성 데이터만 사용하고 원문 토큰/자격증명을 결과 문서에 저장하지 않았다. 기존 인증·권한 거부 기대값을 완화하거나 검사 삭제/skip으로 통과시키지 않았다.

채점 Chrome 검사는 API 계약이며 학생 웹 전체 UI를 뜻하지 않는다. 학생 웹 데모 전체 구현, 모바일 전체 설치·네이티브/기기 실행, 실제 임베딩·LLM·OCR·AWS·Firebase/FCM은 NOT_RUN이다. 실제 서버·DB·broker·worker·Chroma와 명시적 local 공급자 경계는4절과 설계 문서에 구분했다.

## 9. 자체 변경 범위·외부 자원 비교·종료 상태

| 항목 | 최종 판정·증거 |
|---|---|
| 정확한 project/file/directory·서비스/라벨 gate | PASS, 거부 회귀 포함58개. Chroma/dispatcher만 좁게 추가 |
| 이번 외부 컨테이너 ID 집합 | PASS, 새 외부 ID도 없는 엄격한 집합 일치. external_identity_changes=[], external_added_containers=[] |
| 이번 외부 상태·이름 기준 상태 | PASS, 원래 외부 ID별 이름/실행 상태 및 이름 기준 상태 유지 |
| 외부 볼륨·네트워크 | PASS, 원래 이름 모두 유지. 이름 snapshot의 한계상 외부 볼륨 내용 또는 내부 ID의 증명으로 확대하지 않음 |
| 이번 외부 변화의 원인 귀속 | NOT_APPLICABLE, 이번 구간에서 외부 변화 관측 없음 |
| 시작한 자체 서비스 원래 상태 복구 | PASS, 시작 자체9개는 모두 exited였고 최종 동일 서비스 모두 exited |
| 신규 서비스·볼륨 | Chroma와 dispatcher2개 모두 exited. 추가 볼륨 `dodream-phase1_chroma-data` 포함 자체5개 볼륨 유지. 새 네트워크 없음 |
| 포트·네트워크·로그 | 내부 앱 네트워크, gateway의 nginx만 허용, 공개 포트 loopback, DB/Redis/Chroma 호스트 포트 없음, 실제 로그 읽기·JWT/생성 비밀 비노출 PASS |

시작 snapshot은 전체75개 컨테이너(자체9/외부66), 실행 중5개였다. 최종 전체77개 중 외부66개와 실행 중5개는 그대로다. 최종 자체 서비스는11개이며 모두 중지했다. 증거는 `resources-before.json`, `resources-after.json`, `resource-isolation-checks.json`과5절의 stop/isolation 명령이다. 자체 이미지 업데이트로 자체 컨테이너 ID가 바뀐 것과 외부 ID 안정성을 혼동하지 않는다. 최종 영속성 검사에서는 별도로 같은9개 주 서비스 컨테이너 ID/이미지의 재시작을 확인했다.

자체 명령 대상 검증 PASS와 외부 비교 PASS를 각각 기록했다. 과거 ETCH 및3-A 외부 변화의 **FAIL / UNVERIFIED는 그대로 유지**한다. 이번 PASS로 과거 원인을 해소하거나 타 프로젝트를 복원했다고 주장하지 않는다. 타 프로젝트 변경·재시작·삭제 명령, 공유 쓰기 경로, prune, DB/Chroma reset 또는 볼륨 삭제는 수행하지 않았다.

## 10. 최종 상태

아래 PASS는 이번 격리 로컬 검증 범위다. 모든 실패/차단 원본과 후속 검증 연결은3·5절에 남겨 두었다.

| 상태 | 판정 |
|---|---|
| INDEX_SOURCE_SNAPSHOT | PASS |
| PUBLISH_JOB_ATOMICITY | PASS |
| INDEX_JOB_DELIVERY_RECOVERY | PASS |
| CELERY_DELIVERY_INTEGRATION | PASS |
| CHROMA_STORAGE_INTEGRATION | PASS |
| INDEX_ACTIVATION_FENCING | PASS |
| PREVIOUS_INDEX_PRESERVATION | PASS |
| INDEX_FAILURE_RECOVERY | PASS |
| RAG_VERSION_AND_AUTHORIZATION | PASS |
| AUTH_AUTHZ_GRADING_REGRESSION | PASS |
| DATA_PRESERVATION | PASS |
| CURRENT_MUTATION_SCOPE | PASS |
| CURRENT_EXTERNAL_ID_STABILITY | PASS |
| EXTERNAL_CHANGE_ATTRIBUTION | NOT_APPLICABLE (이번 구간); 과거 두 사건 UNVERIFIED 유지 |
| REAL_AI_INTEGRATION | NOT_RUN |
| PUBLIC_DEPLOYMENT_READY | false |

## 11. Git·한계·남은 작업

부록80개 경로만 검토·stage 대상이다. `docs/.DS_Store`, 기존 `.env`, ignored `.local/` 증거는 제외했다. 코드별 독립 검토, 최종 민감 후보·Python 구문·diff 검사를 수행하고 명시 경로 stage 이후 staged 경로/내용을 다시 대조한다. 해당 결과와 정확한 로컬 커밋 SHA는 ignored `review/final-sensitive-candidate-scan.json`, `review/review-paths.json`, `review/staged-review.json`, `review/git-final.json` 및 최종 응답에 남긴다. 자기 커밋 SHA를 문서에 넣기 위한 amend나 추가 이력 수정은 하지 않는다.

필수 실제 Chroma/Celery·회귀·데이터 보존 검증의 미해결 실패는 없다. 기존 묶음 명령의 실패 로그는 유효한 과거 증거로 보존하고 별도 재검증과 구분한다. 남은 항목은 실제 AI 품질/비용/공급자 가용성, 외부 모델 exactly-once, HA·복제 failover·디스크 손실 복구, 전체 업로드/OCR/알림 원자성, 운영 SSRF·전체 로그·HTTPS 점검이다. 이번 재시작 검증은 같은 로컬 저장소의 프로세스 재시작 범위다.

push·PR·merge·remote 변경·amend·이력 재작성·공개 배포는 수행하지 않았다. 다음 학생 웹 데모·RAG 평가·공개 배포에 자동 착수하지 않는다.

## 검토한 변경·신규 파일 경로 (80개)

시작 HEAD 대비 tracked diff와 nonignored 신규 경로의 합집합이다. 최종 파일별 hash 목록과 stage 목록을 대조한다. `docs/.DS_Store`는 파일을 열기 전에 제외했다. 아래는 파일 경로만 기록하며 파일 내용·비밀값은 포함하지 않는다.

### ai (22개)

- `ai/app/celery_config.py`
- `ai/app/config.py`
- `ai/app/indexing/__init__.py`
- `ai/app/indexing/chroma.py`
- `ai/app/indexing/dispatcher.py`
- `ai/app/indexing/hooks.py`
- `ai/app/indexing/models.py`
- `ai/app/indexing/source.py`
- `ai/app/indexing/store.py`
- `ai/app/indexing/worker.py`
- `ai/app/local_providers.py`
- `ai/app/rag/models.py`
- `ai/app/rag/quiz_service.py`
- `ai/app/rag/router.py`
- `ai/app/rag/service.py`
- `ai/app/rag/tasks.py`
- `ai/requirements.local.lock.txt`
- `ai/requirements.local.txt`
- `ai/tests/indexing_fixture.py`
- `ai/tests/test_indexing_contract.py`
- `ai/tests/test_local_runtime.py`
- `ai/tests/test_object_authorization.py`

### be (20개)

- `be/src/main/java/A704/DODREAM/file/controller/PdfController.java`
- `be/src/main/java/A704/DODREAM/file/service/PdfService.java`
- `be/src/main/java/A704/DODREAM/indexing/IndexingController.java`
- `be/src/main/java/A704/DODREAM/indexing/IndexingFailure.java`
- `be/src/main/java/A704/DODREAM/indexing/IndexingFailureHandler.java`
- `be/src/main/java/A704/DODREAM/indexing/IndexingLocalHooks.java`
- `be/src/main/java/A704/DODREAM/indexing/IndexingSchemaGuard.java`
- `be/src/main/java/A704/DODREAM/indexing/IndexingService.java`
- `be/src/main/java/A704/DODREAM/indexing/IndexingSource.java`
- `be/src/main/java/A704/DODREAM/indexing/IndexingStore.java`
- `be/src/main/java/A704/DODREAM/indexing/IndexingSummary.java`
- `be/src/main/java/A704/DODREAM/local/LocalExternalConfiguration.java`
- `be/src/main/java/A704/DODREAM/local/LocalObjectStore.java`
- `be/src/main/java/A704/DODREAM/material/dto/PublishResponseDto.java`
- `be/src/main/java/A704/DODREAM/material/dto/PublishedMaterialListResponse.java`
- `be/src/main/java/A704/DODREAM/material/service/PublishService.java`
- `be/src/main/resources/db/migration/V004__indexing_ledger.sql`
- `be/src/test/java/A704/DODREAM/indexing/IndexingBoundaryTests.java`
- `be/src/test/java/A704/DODREAM/indexing/IndexingDatabaseTests.java`
- `be/src/test/java/A704/DODREAM/indexing/IndexingSourceTests.java`

### fe-web (12개)

- `fe-web/package.json`
- `fe-web/src/auth/session.ts`
- `fe-web/src/component/IndexingStatus.css`
- `fe-web/src/component/IndexingStatus.tsx`
- `fe-web/src/indexing/status.ts`
- `fe-web/src/pages/AdvancedEditor.tsx`
- `fe-web/src/pages/ClassroomList.tsx`
- `fe-web/tests/browser-auth.mjs`
- `fe-web/tests/browser-authorization.mjs`
- `fe-web/tests/browser-grading.mjs`
- `fe-web/tests/browser-indexing.mjs`
- `fe-web/tests/indexing-status.test.ts`

### scripts (20개)

- `scripts/local/check_resources.py`
- `scripts/local/chroma/Dockerfile.local`
- `scripts/local/grading_fixtures.py`
- `scripts/local/indexing_browser_checks.py`
- `scripts/local/indexing_concurrency.py`
- `scripts/local/indexing_contract_checks.py`
- `scripts/local/indexing_data.py`
- `scripts/local/indexing_fixtures.py`
- `scripts/local/indexing_migration.py`
- `scripts/local/indexing_retention.py`
- `scripts/local/manage.py`
- `scripts/local/scope_guard.py`
- `scripts/local/tests/test_manage_unit_guard.py`
- `scripts/local/tests/test_scope_guard.py`
- `scripts/local/verify.py`
- `scripts/local/verify_authorization.py`
- `scripts/local/verify_fresh_indexing_schema.py`
- `scripts/local/verify_grading.py`
- `scripts/local/verify_indexing.py`
- `scripts/local/verify_startup.py`

### compose (1개)

- `compose.local.yml`

### docs (5개)

- `docs/portfolio/01-roadmap.md`
- `docs/portfolio/02-local-runbook.md`
- `docs/portfolio/11-indexing-reliability-design.md`
- `docs/portfolio/12-phase3b-results.md`
- `docs/portfolio/security-evidence.md`
