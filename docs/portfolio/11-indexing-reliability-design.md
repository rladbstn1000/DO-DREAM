# 3-B 발행·색인 신뢰성 설계

팀 구현 기준은 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`, 이번 개인 개선의 출발점은 3-A `705c2a440e6e2d84fb26effc792e4ddd733f23d4`다. 이 문서는 현재 코드가 구현한 저장·전달·활성 전환·조회 계약을 설명한다. 실제 장애 재현과 최종 이미지의 실행 결과는 [12-phase3b-results.md](12-phase3b-results.md)에 따로 기록한다.

**ACTUAL_RUNTIME_FINAL=PASS (격리 로컬 범위).** 실제 Chroma/Celery, 독립 워커 경쟁, 네 구간의 실제 프로세스 중단, 기존 데이터와 재시작 영속성 검사를 완료했다. 명령별 실패 이력·후속 검증·16개 시나리오 근거는 [최종 결과](12-phase3b-results.md)에 구분해 기록했다. 아래 장애 표는 설계 설명이며 모든 환경에 대한 보장은 아니다. `REAL_AI_INTEGRATION=NOT_RUN`, `PUBLIC_DEPLOYMENT_READY=false`를 유지한다.

## 기준 저장소와 서로 다른 식별자

발행 기록, 색인 요청, 활성 포인터의 기준 저장소는 MySQL이다. Redis는 메시지 전달 수단이고 Celery 결과 상태는 준비 완료의 기준이 아니다. 기존 SQLite 대화·작업 기록을 MySQL로 일괄 이전하거나 과거 파일 인덱스를 새 활성 인덱스로 자동 승격하지 않는다.

| 개념 | 현재 구현과 구분 |
|---|---|
| 자료 | `resource_kind`의 `PDF` 또는 `MATERIAL`과 실제 자료 ID. 초기 PDF는 `UploadedFile.id`, 발행 자료는 `Material.id`이며 학생에게 PDF 권한을 확대하지 않는다. |
| 원본 개정 | 자료별 `source_revision`과 정규화 학습 본문의 SHA-256. 같은 현재 본문이면 유지하고 본문이 바뀌면 증가한다. 퀴즈의 JPA `version`과 다른 의미다. |
| 색인 설정 | `index_spec`. 현재 허용 값은 `local-hash8-content-v1`, `local-hash8-content-v2`이며 둘 다 명시적인 로컬 시험 설정이다. 설정 버전 구분 자체를 모델 품질 개선으로 주장하지 않는다. |
| 논리 작업 | 공개 UUID `job_id`. `(resource_pk, source_revision, index_spec)` UNIQUE로 같은 자료·현재 원본·설정의 중복을 합친다. 전역 본문 해시로 타인 자료를 합치지 않는다. |
| 요청 순서 | 자료 행 잠금 안에서 증가하는 `request_seq`, `latest_job_id`. 이전 작업을 다시 조회·접수해도 최신 포인터를 되돌리지 않는다. |
| 실행 세대 | 작업별 `execution_generation`. 명시적 복구로 새 실행권을 얻을 때 증가한다. |
| 물리 후보 | `idx_<job UUID without hyphens>_g<generation>` 컬렉션. 세대마다 별도 공간이며 DB UNIQUE도 적용한다. |

새 테이블은 세 개다. `index_resources`는 현재 원본·최신 요청·활성 실행과 활성 전환 횟수, `index_jobs`는 불변 입력과 전달 원장, `index_executions`는 세대·기한·candidate·검증 결과·임베딩 호출 수를 보존한다. `index_jobs` 자체가 발행용 outbox 역할을 하므로 같은 요청을 별도 outbox 테이블에 복제하지 않는다. [V004 SQL:3](../../be/src/main/resources/db/migration/V004__indexing_ledger.sql#L3), [작업 접수:127](../../be/src/main/java/A704/DODREAM/indexing/IndexingStore.java#L127), [실행 매핑:51](../../ai/app/indexing/models.py#L51).

V004는 기존 테이블/행을 지우지 않는 `CREATE TABLE IF NOT EXISTS` 방식이다. 필요한 키·스냅샷 크기·세대 상한에 제약을 두고 시작 시 필수 컬럼과 UNIQUE를 확인한다. 기존에 같은 이름의 잘못된 테이블이 있어도 자동으로 고쳤다고 가정하지 않는다. 기존 DB 전진 적용·재실행, 별도 새 스키마 최초 설치, 원래 컬럼 보존은 실행 결과의 별도 항목이다. [스키마 시작 검사:12](../../be/src/main/java/A704/DODREAM/indexing/IndexingSchemaGuard.java#L12).

## 불변 입력과 발행 트랜잭션

발행 요청은 소유 교사와 파일을 확인한 뒤 학습용 `content` 블록만 정규화한다. 교사용 quiz 블록·정답은 색인 스냅샷에 포함하지 않는다. 초기 PDF 형식도 학습 본문을 추출하며 개념 Check 영역을 제외한다. 스냅샷은 문자열 전용 canonical JSON, UTF-8 바이트 수, SHA-256으로 저장한다. 최대 2MiB, 최대 500개 원본 블록이며 잘못된 Unicode·잘못된 타입을 거부한다. 저장 JSON을 읽는 `IndexingSource.parse`와 워커의 canonical snapshot 검증은 중복 JSON 필드를 거부한다. 이를 모든 HTTP 요청 본문의 중복 키를 거부하는 전역 정책으로 확대하지 않는다. 워커는 MySQL에 저장된 이 입력을 검증하고 사용한다. 실행 시 같은 URL의 최신 파일을 다시 읽어 옛 버전으로 색인하지 않는다. [Spring 정규화:43](../../be/src/main/java/A704/DODREAM/indexing/IndexingSource.java#L43), [Python canonical 정규화:74](../../ai/app/indexing/source.py#L74), [snapshot 해시·중복 필드 검증:91](../../ai/app/indexing/source.py#L91).

처리는 다음 순서로 나뉜다.

1. 짧은 DB 조회로 교사 소유·파일 상태·퀴즈 편집 가능 여부를 확인한다.
2. 새 UUID 저장 객체를 준비한다. 기존 JSON을 덮어쓰지 않고 저장 후 읽은 바이트가 준비한 바이트와 같은지 확인한다.
3. 짧은 DB 트랜잭션에서 파일/연결 자료를 잠그고 현재 소유를 다시 확인한다. 자료·퀴즈·객체 참조와 색인 원본/작업을 함께 확정한다.
4. HTTP 200은 저장·색인 접수를 뜻한다. 별도 전달기가 commit된 작업을 찾아 전달한다.

초기 PDF도 파싱 결과 객체 준비 후 `completeInitial`에서 객체 참조·파싱 정보와 PDF 색인 요청을 함께 확정한다. 전체 업로드 파일 저장·OCR까지 하나의 트랜잭션으로 묶은 것은 아니다. 객체 준비 후 DB 실패가 나면 미참조 객체가 남을 수 있다. 기존 객체 참조는 DB rollback으로 유지되며 미참조 객체를 자동 삭제하지 않는다. [객체 준비:21](../../be/src/main/java/A704/DODREAM/indexing/IndexingService.java#L21), [불변 키:62](../../be/src/main/java/A704/DODREAM/indexing/IndexingService.java#L62), [저장 후 읽기 검증:67](../../be/src/main/java/A704/DODREAM/indexing/IndexingService.java#L67), [발행 원자 저장:90](../../be/src/main/java/A704/DODREAM/indexing/IndexingStore.java#L90), [초기 PDF 저장:110](../../be/src/main/java/A704/DODREAM/indexing/IndexingStore.java#L110).

Spring은 8초 제한의 `REQUIRES_NEW`/`READ_COMMITTED` 짧은 트랜잭션을 사용한다. 비활성 요청 OSIV holder를 트랜잭션 동안 분리하여 해당 트랜잭션의 EntityManager가 종료되도록 하고 원래 holder를 복원한다. 객체 호출 직전에 실제 트랜잭션, DataSource 연결 바인딩, Hibernate의 물리 연결 보유를 확인한다. 외부 저장소 호출이나 broker 전송을 DB 트랜잭션 안에 넣지 않는다. Python도 작업 claim/진행/활성화를 각각 `SessionLocal.begin()`으로 끝내고 Chroma I/O를 수행한다. [Spring 트랜잭션 경계:39](../../be/src/main/java/A704/DODREAM/indexing/IndexingStore.java#L39), [외부 호출 검사:29](../../be/src/main/java/A704/DODREAM/indexing/IndexingLocalHooks.java#L29), [워커 단계:8](../../ai/app/indexing/worker.py#L8).

## 영속 전달과 제한된 복구

전달기는 매 반복에 최대 10개 미완료 작업을 읽는다. 자료·작업 행 잠금 안에서 현재 소유와 최신 원본을 확인하고 전달 token과 30초 기한을 기록한 다음 트랜잭션 밖에서 Redis/Celery에 전송한다. 메시지는 `job_id`만 포함한다. 사용자 AT/RT, 원문, URL, 클라이언트의 owner/allowed/collection 값을 큐에 보관하지 않는다. 전송 결과는 별도 짧은 트랜잭션에서 자기 전달 token이 여전히 유효할 때만 기록한다. [전달 claim:221](../../ai/app/indexing/store.py#L221), [전달 결과:247](../../ai/app/indexing/store.py#L247), [전달기:6](../../ai/app/indexing/dispatcher.py#L6), [task 계약:5](../../ai/app/rag/tasks.py#L5).

전송 성공 후 결과 기록 전에 종료되면 같은 메시지가 재전달될 수 있다. `QUEUED` 작업의 전달 기한 만료는 다시 전달 가능한 상태로 돌아간다. `PROCESSING` 실행의 30초 lease가 만료되면 자동으로 새 외부 실행을 시작하지 않고 `FAILED`로 판정한다. 소유 교사가 현재 세대를 지정해 명시적으로 재시도해야 한다. 한 논리 작업의 전달은 최대 5회, 실행은 최대 3세대다. 상한을 넘긴 작업의 횟수를 API로 초기화하지 않는다. 중복 메시지가 같은 Celery task_id를 갖는지에 의존하지 않는다. [lease 만료 복구:205](../../ai/app/indexing/store.py#L205), [제한 상수:21](../../ai/app/indexing/store.py#L21), [Spring 명시 재시도:163](../../be/src/main/java/A704/DODREAM/indexing/IndexingStore.java#L163).

Celery 5.5.3은 실제 Redis broker의 `indexing-v3` 큐를 사용한다. `acks_late`, `reject_on_worker_lost`, prefetch 1, visibility timeout 60초, publish retry 비활성, task 자동 retry 0을 설정한다. 워커의 현재 실행 방식은 concurrency 1 / solo이며, 설정한 soft 50초·hard 55초만으로 실제 프로세스 중단을 보장했다고 주장하지 않는다. 실행권의 최종 기준은 MySQL lease/세대이고, crash 검증은 gate 관측 후 실제 대상 프로세스 종료 증거로 구분한다. Celery result backend의 SUCCESS를 활성 성공으로 읽지 않으며 신규 task 결과는 저장하지 않는다. [Celery 설정:4](../../ai/app/celery_config.py#L4), [Compose 워커:109](../../compose.local.yml#L109). ACK·재전달 의미는 [Celery 5.5.3 설정](https://docs.celeryq.dev/en/v5.5.3/userguide/configuration.html#task-acks-late), visibility timeout은 [Redis broker 공식 문서](https://docs.celeryq.dev/en/v5.5.3/getting-started/backends-and-brokers/redis.html#visibility-timeout)를 기준으로 확인한다.

## 실제 Chroma 후보와 검증 후 활성 전환

Chroma 서버와 HTTP thin client는 모두 **0.6.3**이다. 서버만 전용 `chroma-data` 볼륨을 쓴다. AI·워커·전달기에 같은 Chroma 저장 디렉터리를 쓰기 마운트하지 않는다. 서버 포트를 호스트에 공개하지 않고 내부 네트워크로 HTTP 연결한다. `ALLOW_RESET=false`, telemetry 비활성이다. 실제 이미지 digest와 실행 버전은 최종 결과 문서에 기록하며 이미지 태그만으로 실행 사실을 대신하지 않는다. [Compose:122](../../compose.local.yml#L122), [서버 이미지](../../scripts/local/chroma/Dockerfile.local), [클라이언트 잠금:65](../../ai/requirements.local.lock.txt#L65).

컬렉션 생성/조회에 `embedding_function=None`을 지정하고 벡터를 직접 넘긴다. local 임베딩은 UTF-8 문자열의 SHA-256 앞 8바이트를 각 255로 나눈 8차원 결정적 벡터이며 거리 함수는 cosine이다. HTML을 학습 텍스트로 변환한 뒤 최대 1,000자, 겹침 100자(이동 900자)로 나눈다. 최종 청크는 최대 500개, 배치는 최대 32개다. 청크 ID에는 자료 종류/ID·원본 버전·설정·위치·content 타입·내용 해시를 포함한다. 같은 배치의 재전송은 결정적 ID로 upsert된다. [청킹:109](../../ai/app/indexing/source.py#L109), [임베딩·컬렉션:79](../../ai/app/indexing/chroma.py#L79).

`BoundedHTTPClient`는 첫 네트워크 호출 전에 실제 0.6.3 `ServerAPI`의 HTTP transport에 connect 2초, read/write/pool 5초 제한을 설정한다. 컬렉션 생성·조회는 실제 SDK `Collection`에 그 transport를 그대로 전달한다. 상태 확인의 heartbeat/version과 보존 목록의 collection 조회도 같은 연결을 사용한다. 이 값은 연결·읽기·쓰기·pool 대기 각각의 제한이며 전체 색인 작업이나 전체 요청의 5초 상한을 뜻하지 않는다. 버전이 다르면 내부 API 호환성을 가정하지 않고 거부한다. Chroma 장애를 파일/메모리 인덱스로 우회하지 않는다. [동일 transport 연결:15](../../ai/app/indexing/chroma.py#L15), [시간 제한 설정:55](../../ai/app/indexing/chroma.py#L55).

0.6.3의 `Client.from_system()`은 HTTP System 식별자를 매번 새 UUID로 만들기 때문에 전달한 System의 transport를 재사용하지 않는다. 이 경로를 사용하면 설정한 제한과 별개인 기본 `timeout=None` 연결이 생길 수 있다. 현재 adapter는 이 factory를 거치지 않는다. 따라서 첫 구현의 factory 모킹 테스트만으로 시간 제한을 검증했다고 주장하지 않으며, 실제 SDK Collection이 동일 transport를 사용하는지와 timeout이 503으로 전달되는지를 검사한다. 실제 Chroma 정지·일시 중단 시간 측정은 결과 문서에서 따로 확인한다. 이 제약은 [0.6.3 System 식별자 생성](https://github.com/chroma-core/chroma/blob/0.6.3/chromadb/api/shared_system_client.py#L53-L74), [Client.from_system 생성 경로](https://github.com/chroma-core/chroma/blob/0.6.3/chromadb/api/client.py#L78-L86), [기본 HTTP timeout](https://github.com/chroma-core/chroma/blob/0.6.3/chromadb/api/fastapi.py#L59-L81)을 기준으로 확인한다. `upsert`, `get`, `query(query_embeddings, where)`는 [실제 SDK Collection](https://github.com/chroma-core/chroma/blob/0.6.3/chromadb/api/models/Collection.py) 구현을 그대로 사용한다.

실행권 획득 시 `(job_pk,generation)`과 candidate 이름의 DB UNIQUE가 경쟁을 중재한다. 각 쓰기 전 현재 원본·최신 요청·권한·실행 세대·token·lease를 확인한다. 그 확인 후 멈췄던 옛 워커가 늦게 쓰더라도 자기 세대의 candidate에만 쓴다. 다른 세대의 컬렉션이나 기존 활성 컬렉션을 수정할 이름을 받지 않는다. [실행 claim:263](../../ai/app/indexing/store.py#L263), [실행 검사:289](../../ai/app/indexing/store.py#L289), [쓰기 직전 검사:53](../../ai/app/indexing/worker.py#L53).

활성화 전에 예상 ID 집합과 실제 ID 집합·개수, 각 문서·메타데이터, 벡터 수·8차원·유한 수치와 저장된 값, 실제 content query 성공을 확인한다. 검증 digest를 저장하고 짧은 MySQL 트랜잭션에서 현재 소유·최신 원본/hash·세대·lease·VALIDATED 상태를 다시 검사한 뒤 활성 포인터와 성공 상태를 확정한다. 활성화된 candidate는 이후 신규 실행의 쓰기 대상이 되지 않는다. 늦은 실패는 이미 ACTIVE인 실행을 실패로 바꾸지 않는다. [물리 검증:120](../../ai/app/indexing/chroma.py#L120), [활성 확정:315](../../ai/app/indexing/store.py#L315), [늦은 실패 방어:334](../../ai/app/indexing/store.py#L334).

## 장애 구간과 보존 정책

| 관측할 중단 구간 | 남는 상태와 설계상 복구 | 실제 검증에서 구분할 것 |
|---|---|---|
| 발행 DB commit 후 전달 전 | 자료와 QUEUED 작업이 함께 남는다. 전달기 재시작 후 MySQL에서 다시 발견한다. | DB rollback 오류 주입과 commit 뒤 실제 Spring/전달기 종료는 서로 다른 검사다. |
| candidate 일부 쓰기 후 | 이전 활성 포인터는 그대로다. PROCESSING lease 만료 후 FAILED, 명시 재시도는 새 generation/candidate를 쓴다. | 실제 워커 중단, 부분 청크 수, 이전 pointer/digest, 새 실행 수를 각각 기록한다. |
| candidate 검증 후 활성 commit 전 | 검증 후보는 남지만 아직 검색되지 않는다. DB 오류/종료로 포인터 확정이 안 되면 이전 활성은 유지한다. | 예외 주입과 `before_activation` gate에서 실제 종료를 구분한다. |
| 활성 commit 후 응답/ACK 전 | MySQL 성공과 포인터는 남는다. 재전달은 terminal 작업을 재활성화하지 않는다. | broker 재전달 수와 실제 활성 전환 수를 혼동하지 않는다. |

이전 정상 컬렉션과 실패 후보, 미참조 저장 객체는 이번 단계에서 모두 보존한다. Chroma와 MySQL은 분산 트랜잭션이 아니다. 후보 완성 후 마지막에 포인터만 확정하므로 원장이 참조하지 않는 물리 후보가 남을 수 있다.

읽기 전용 목록은 `python3 scripts/local/indexing_retention.py`로 수집한다. 이 명령은 기존 실행 범위 gate를 거쳐 MySQL 작업/실행/포인터와 실제 Chroma collection 이름·ID를 대조하고 `active`, `previous-verified`, `failed-unreferenced`, 미확인 후보를 나눈다. 정리 후보 이름은 검토용일 뿐 모든 `action`은 `retain`이다. 삭제 모드와 자동 GC는 없다. [보존 목록 도구](../../scripts/local/indexing_retention.py).

객체 파일은 AI의 읽기 전용 마운트에서 해시 파일명만 관측한다. 현재 UploadedFile의 객체 참조를 DB 안에서 같은 해시 파일명으로 바꾸어 비교하며 원문 키·서명 URL·파일 내용을 출력하지 않는다. 현재 참조가 없는 오래된 파일도 `retained_unreferenced`로 남긴다. 해시 이름만으로 원래 키나 모든 과거 참조를 복원할 수 없으므로 안전한 삭제 가능성을 주장하지 않는다. MySQL과 Chroma/파일 목록은 별도 시점의 관측이며 동시 변경 중 전역 스냅샷이 아니다. 결과는 `.local/phase3b/results/index-retention-dry-run-<timestamp>-<id>.json`과 `index-retention-dry-run-latest.json`에 저장된다.

## 현재 권한·원본 버전으로 조회

잠금 획득 전 읽은 객체를 그대로 권한·원본 판단에 쓰지 않는다. Python은 자료·원장·작업을 `FOR UPDATE`로 다시 읽을 때 `populate_existing()`으로 세션의 기존 객체도 갱신한다. Spring 재시도는 파일→자료→원장→작업 순서로 잠근 뒤 `em.clear()`와 현재 소유·파일 연결 검사를 다시 수행한다. 처음 권한 확인 이후 잠금을 기다리는 동안 소유나 연결이 바뀌었으면 이전 판단만으로 작업을 재접수하지 않는다. [Python 잠금 재조회:44](../../ai/app/indexing/store.py#L44), [Spring 재시도 권한 재검사:177](../../be/src/main/java/A704/DODREAM/indexing/IndexingStore.java#L177).

조회는 JWT 검증과 기존 2-B 현재 자료 권한을 먼저 확인한다. 학생은 현재 담당 관계·공유·PUBLISHED·미삭제 조건을 모두 만족해야 하며, 초기 PDF는 소유 교사 전용이다. 상태·재색인·재시도 API도 현재 소유 교사만 접근한다. 임의 collection·owner·URL을 신규 Spring API 입력으로 받지 않는다. AI의 URL 호환 API는 현재 DB 객체 키와 허용 host/path를 먼저 대조하고 읽은 뒤 접수 시 키가 그대로인지 재확인한다. [자료 권한 정책:121](../../ai/app/security/authorization.py#L121), [PDF 권한 정책:88](../../ai/app/security/authorization.py#L88), [URL 바인딩:183](../../ai/app/security/authorization.py#L183), [AI 접수 경계:79](../../ai/app/rag/router.py#L79), [Spring 입력:13](../../be/src/main/java/A704/DODREAM/indexing/IndexingController.java#L13).

한 RAG 요청은 현재 권한으로 확정한 활성 pointer 하나를 메모리에 복사한 뒤 DB 연결을 놓고 Chroma를 조회한다. 자료 ID만으로 캐시한 이전 체인이나 임의 초기본/타 자료 컬렉션으로 fallback하지 않는다. 조회는 `get_collection`을 사용하며 `get_or_create`로 빈 컬렉션을 만들지 않는다. 검색 조건은 `type=content`와 정확한 자료 종류/ID·원본 revision/hash·설정이다. [활성 조회:346](../../ai/app/indexing/store.py#L346), [검색 필터:150](../../ai/app/indexing/chroma.py#L150), [요청별 체인:279](../../ai/app/rag/service.py#L279).

| 상황 | 조회와 상태 계약 |
|---|---|
| 새 원본과 일치하는 활성 인덱스 없음 | 409 `INDEX_NOT_READY`. 준비 중 후보나 예전 원본을 최신처럼 제공하지 않는다. |
| 같은 원본의 새 설정 재색인 실패 | 기존 정상 활성 원본이 일치하면 `readable=true`, 최신 작업은 FAILED, `activeCurrent=false`. 기존 자료 조회는 가능하다. |
| 원본이 바뀐 뒤 새 색인 실패 | 이전 물리 컬렉션은 보존하되 `readable=false`. 새 원본에 옛 내용을 섞지 않는다. |
| Chroma 연결/조회 오류 | 503 `INDEX_STORAGE_UNAVAILABLE`. 빈 성공 또는 합성 정상 답으로 숨기지 않는다. |
| 공유·담당 회수, 자료 삭제, 소유 불일치 | 기존 권한 정책에 따른 거부. 물리 보존은 열람 허용을 뜻하지 않는다. |
| 대화 중 원본 변경 | 세션의 저장 revision/hash와 현재 pointer가 다르면 409 `RAG_SOURCE_CHANGED`. 이전 대화 기록은 보존하고 새 원본에 옛 문맥을 자동 재사용하지 않는다. |

새 세션의 인덱스 연결은 기존 SQLite에 추가한 `ChatSessionIndex`로 보존한다. 과거 세션에 근거 없는 버전을 역채움하지 않으며 연결이 없는 과거 세션의 계속 대화도 명시적으로 거부한다. 같은 원본에서 설정만 바뀌면 세션의 원본 버전은 일치한다. 채팅의 자료 일치 검사도 유지한다. [세션 원본 검사·저장:141](../../ai/app/rag/router.py#L141).

## 교사 화면의 최소 계약

발행 HTTP 200 응답과 자료 목록의 `indexing`은 `jobId`, `state`, `sourceRevision`, `readable`, `activeCurrent`, `retryable`, `executionGeneration`을 포함한다. 작업이 없으면 `NONE`/`jobId=null`이며 준비 완료로 해석하지 않는다. task_id 존재나 Celery SUCCESS만으로 사용 가능을 표시하지 않는다. 화면은 접수·준비 중·사용 가능·실패를 구분하고 같은 원본의 재색인 실패는 **사용 가능 · 재색인 실패**로 표시한다. [표시 해석:20](../../fe-web/src/indexing/status.ts#L20), [목록 통합:1766](../../fe-web/src/pages/ClassroomList.tsx#L1766), [발행 접수 안내:1091](../../fe-web/src/pages/AdvancedEditor.tsx#L1091).

자동 상태 조회는 최초 GET 후 최대 10회, 간격 2초, 요청당 8초 제한이다. 이것을 전체 20초 제한으로 주장하지 않는다. 기한/횟수를 다 쓰면 자동 재접수하지 않고 사용자가 상태를 다시 확인하도록 안내한다. 명시 재시도는 관측한 job UUID와 generation을 고정하고 인증 갱신 재전송에서도 유지한다. 응답 유실 뒤에는 read-only 상태 확인 없이 새 재시도를 보내지 않는다. 403/404는 상태 접근 거부로 표시하며 인증 세션을 지우지 않는다. 로그아웃·계정 전환 epoch 뒤 도착한 응답은 이전 summary를 반영하지 않고 로그인 확인이 필요한 session 오류로 전환한다. unmount 뒤에는 화면 갱신을 하지 않는다. [제한 조회·재시도:77](../../fe-web/src/indexing/status.ts#L77), [화면 lifecycle](../../fe-web/src/component/IndexingStatus.tsx).

실제 교사 UI 검사는 새 합성 자료에서 편집/접수→QUEUED→PROCESSING→검증 활성, 최초 실패, 기존 사용 가능 상태의 재색인 실패와 명시 재시도를 구분한다. 파일 checkpoint로 관측한 UI와 실제 워커 gate를 연결하며 브라우저가 Docker를 직접 변경하지 않는다. 학생 웹 화면을 새로 만들지 않는다. 모바일 전체 설치·기기 실행은 NOT_RUN이다. [실제 UI 하네스](../../fe-web/tests/browser-indexing.mjs).

## 로컬 경계와 미보장 범위

이번 실행 경로는 실제 Spring/FastAPI, MySQL, Redis/Celery, Chroma HTTP 저장/query를 대상으로 한다. 임베딩·LLM 답변·OCR·외부 객체 저장소·알림은 명시적인 local 대역이거나 비활성이다. hash 임베딩은 `LOCAL_EXTERNAL_STUBS` 없이는 선택되지 않으며 잘못된 운영 키 설정을 이유로 자동 대역으로 전환하지 않는다. 모델 자동 다운로드와 기본 embedding function을 사용하지 않는다. 과거 local 인덱스 파일·SQLite 기록을 검증 없이 활성 데이터로 재분류하지 않는다. [local 벡터 경계:79](../../ai/app/indexing/chroma.py#L79), [legacy 직접 쓰기 거부:270](../../ai/app/rag/service.py#L270).

AI 오류 주입은 local/test 및 명시적 local 대역 설정, `[INDEX LOCAL]` 스냅샷, 작업 UUID별 제어 파일 조건에서 켜진다. Spring 오류 주입은 local profile, 파일명/객체 키에 따른 전용 합성 파일 분류, `file-<fileId>.json` 제어 파일 조건을 사용한다. 공개 fault API는 없다. 합성 관측 로그는 작업/세대/후보·프로세스 식별자, 시각, 상태·횟수 등 메타데이터를 남기며 원문과 사용자 토큰을 출력하지 않는다. [AI gate:19](../../ai/app/indexing/hooks.py#L19), [Spring 합성 gate:23](../../be/src/main/java/A704/DODREAM/indexing/IndexingLocalHooks.java#L23).

설계 목표는 실패·중복·역순 완료에서 정상 인덱스와 활성 포인터를 보호하고, commit된 미완료 작업을 발견해 제한적으로 복구하는 것이다. 외부 모델 exactly-once, 실제 모델 품질·요금·가용성, 전체 업로드/OCR/알림 원자성은 보장하지 않는다. 같은 로컬 볼륨을 보존한 재시작은 HA·복제 failover·디스크 손실 복구 검증이 아니다. 원인 미확인 과거 외부 자원 변화의 FAIL/UNVERIFIED는 새 기능의 설계 설명으로 덮지 않는다. 실제 공급자 호출·공개 배포·학생 웹 데모·모바일 전체 실행은 이번 설계의 완료 범위에 포함하지 않는다.
