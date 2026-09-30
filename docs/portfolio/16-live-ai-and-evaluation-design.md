# 16. 실제 AI 연결 준비와 고정 평가 설계

팀 구현 기준은 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`, 개인 5단계 시작점은 `b26fc7dfd42a731307e13368a23c116790a9efcd`다. 이 단계는 기존 인증·권한·3-A 제출 snapshot·3-B 후보 검증/활성 전환·4단계 학생 화면을 유지한다. 실행 결과와 미실행 항목은 [17](17-phase5-results.md)에 따로 기록한다.

이번 요청에는 실제 외부 호출 승인·예산·요청 한도가 없고 제안된 전용 키 파일도 없다. **LIVE_API_AUTHORIZED=false, 실제 공급자 요청 0회**로 작업한다. 아래는 검증 가능한 준비 코드의 계약이며 실제 모델 연결·품질·비용 측정의 완료 선언이 아니다.

## 모델과 HTTP 계약

2026-09-30 공식 문서 확인 기준이다. 다른 모델로 자동 대체하지 않는다.

| 용도 | 고정 값 | 표준 동기 API 단가, USD / 100만 토큰 |
|---|---|---|
| 임베딩 | `text-embedding-3-small`, `dimensions=1536`, float | 입력 0.02 |
| 답변·검색 질문 재작성·채점 | `gpt-4.1-mini-2025-04-14` | 입력 0.40 / cached 입력 0.10 / 출력 1.60 |

[GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini)는 위 고정 snapshot과 Chat Completions·Structured Outputs 지원을 명시한다. [임베딩 모델](https://developers.openai.com/api/docs/models/text-embedding-3-small)은 별도 날짜 snapshot을 제공하지 않으므로 없는 버전을 만들지 않는다. [임베딩 형식](https://developers.openai.com/api/docs/guides/embeddings#how-to-get-embeddings)과 [공식 단가](https://developers.openai.com/api/docs/pricing)를 기준으로 한다. 모델 선택을 최신 권장 모델로 임의 변경하지 않았다.

기존에 고정된 `httpx==0.28.1`로 `https://api.openai.com/v1/embeddings`, `/v1/chat/completions` 두 POST만 보낸다. OpenAI SDK나 새 LangChain 공급자 패키지를 설치하지 않는다. TLS 검증, redirect 금지, 환경 proxy 미사용, HTTP 자동 재시도 0이다. 외부 클라이언트·Hugging Face 모델을 import 시 초기화하던 과거 경로를 제거했다. 서버 설정에 키가 있다는 이유만으로 실행 모드를 전환하지 않는다.

Chat 요청은 `n=1`, `store=false`, `service_tier=default`, `temperature=0`, `max_completion_tokens`와 `response_format.json_schema.strict=true`를 사용한다. 모든 객체는 `additionalProperties=false`, 모든 속성은 required다. 모델 refusal, finish_reason 중단, JSON/schema 오류, 잘못된 ID 집합을 성공한 오답으로 바꾸지 않는다. [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)에서 설명하는 형식 준수는 의미상 정답 보증과 별개다.

공급자 읽기 제한은 5초, 연결/쓰기/pool은 각각 2초, 한 호출 전체는 8초다. live RAG는 재작성→질문 임베딩→답변의 최대 세 호출을 위해 28초, 학생 화면은 32초로 명시적으로 제한한다. 로컬 RAG 15초/화면 20초와 기존 채점 10초 경계는 유지한다. 동기 Chroma 작업을 실행하는 thread는 바깥 coroutine 취소만으로 즉시 종료된다고 보장하지 않는다. 늦은 답변 저장은 권한·버전 재검사로 차단하고, 결과 불명 공급자 요청의 예약은 보존한다.

## 모드·자료·작업 격리

기본 Compose의 AI·worker·dispatcher는 `DODREAM_AI_MODE=LOCAL_FAKE`, `LIVE_API_AUTHORIZED=false`이며 키 마운트와 외부 gateway가 없다. 실제 Spring/FastAPI/MySQL/Redis/Chroma를 대역 서버로 바꾸지 않는다. 파일·OCR 경계는 `LOCAL_EXTERNAL_STUBS=true`를 유지한다.

`LIVE_OPENAI`는 승인된 manifest와 영속 예산 원장이 있는 별도 실행 설정이다. `compose.live.yml`은 같은 자체 프로젝트의 AI 서비스 하나만 순차적으로 바꾼다. launcher는 기존 local worker/dispatcher를 먼저 멈춘다. **live dispatcher와 live Celery consumer는 없다.** 수동 `app.indexing.live_worker JOB_UUID`가 정확히 한 작업만 처리한다. live 모드에서 공통 Celery worker와 dispatcher를 시작하려 하면 차단된다.

local dispatcher는 local specification만 조회한다. 실행 claim 앞에서도 모드/specification을 검사하므로 잘못된 큐 전달로 live 작업을 실행하지 않는다. live 수동 worker는 material ID, 실행 소유 교사, 원본 revision/hash, specification, 허용 목적을 승인 목록과 대조한 뒤에만 claim한다. API도 현재 학생 권한과 허용된 합성 사용자·자료를 공급자 호출 전에 다시 검사한다.

`scope_guard.py`는 기존 프로젝트·서비스·볼륨·네트워크·loopback 제한을 유지하며 AI의 정확한 두 read-only 파일만 추가 허용한다. 하나는 `.local/phase5/live/manifest.json`, 다른 하나는 `~/.config/dodream/provider-live.env`다. 다른 서비스·경로·쓰기 마운트·임의 base URL을 허용하지 않는다. 키 내용은 환경변수·명령 인자·브라우저로 전달하지 않는다. local 회귀 진입은 AI에 live 키 마운트/egress가 있으면 거부한다. 전체 SSRF 방어 또는 OS 차원의 API host 방화벽을 완성했다는 의미는 아니다.

실행을 열기 전 현재 소스/계약 hash와 검증한 AI·Spring·웹 이미지 ID를 대조한다. AI 태그가 다른 빌드를 가리키면 시작을 거부한다. 실행 중 작업/평가도 AI 컨테이너 ID와 local 소비자 중지 상태를 다시 검사한다.

종료는 승인 만료·키 삭제와 무관하게 가능해야 한다. 먼저 자체 AI를 중지하고, 소비자 ID를 확인한 다음 키 없는 local 설정을 복원한다. 예상하지 못한 소비자 교체는 자동 복원을 막는다. 영속 볼륨과 후보 컬렉션은 삭제하지 않는다.

## 색인 specification과 신규 자료

live specification은 `openai-text-embedding-3-small-1536-l2-content-v1`이다. provider/model/dimensions/L2 정규화/content-v1 청킹(최대 1,000자, 이동 900자)을 식별한다. 기존 `local-hash8-content-v1/v2` 및 8차원 컬렉션을 그대로 보존한다. 같은 차원이라도 다른 spec을 호환 처리하지 않는다.

색인·저장·조회 모두 동일한 spec을 확인한다. 후보 컬렉션 metadata, 원본 hash, 작업/세대, 문서/청크 metadata, 벡터 차원·유한값·정규화·저장값·실제 검색을 검증한 뒤 기존 짧은 활성 전환 트랜잭션을 사용한다. SQL로 ACTIVE를 직접 만들지 않는다. live 임베딩 배치는 최대 3청크이며 기존 30초 실행 lease를 늘리지 않았다. 제한 안에 끝나지 않으면 새 후보가 실패하고 기존 정상 인덱스는 보존된다. 이 경계의 실제 공급자 지연은 아직 측정하지 않았다.

새 준비 API는 local 프로필과 `LOCAL_DEMO_ENABLED=true`, `LOCAL_PHASE5_ENABLED=true`가 모두 필요하고 현재 체험 전용 교사만 호출할 수 있다. 기존 샘플의 새로운 스모크 복사본 2개와 자체 평가 교재 2개를 최대 4개의 `phase5eval-*` 레코드로 예약한다. 실제 `completeInitial`→`publish`→live spec 요청을 거친다. 재실행은 저장 객체·논리 작업을 다시 만들지 않으며 편집된 원본·문제·정답을 원래 fixture로 덮지 않는다. 선택한 학생도 현재 체험 cohort·학급에 속해야 한다. 4단계 자료와 과거 학생은 재사용하지 않는다.

## 좁은 영속 비용 제한

`app/providers/budget.py`의 SQLite 원장을 API·수동 worker·평가 CLI가 공유한다. 초기화는 명시적인 작업이며 파일/동일 run을 재설정하지 않는다. 런타임은 기존 파일을 `mode=rw`로 열고 manifest hash와 run ID를 확인한다. 파일이 사라졌다고 빈 예산을 만들지 않는다.

`BEGIN IMMEDIATE` 안에서 요청 수·누적 금액·미완료 호출을 검사하고 예약한다. 동시에 한 호출만 허용한다. UTF-8 요청 바이트 수와 제한된 schema/message framing 여유 4,096토큰을 입력 토큰 상한으로 잡고, 최대 출력 토큰까지 표준 단가로 예약한다. 이것은 실제 tokenizer 측정값이 아닌 보수적인 상한이다. 전체 입력은 최대 16,384바이트, 임베딩 문자열 하나는 최대 4,096바이트, 답변 512/재작성 256/채점 배치 1,024 출력 토큰이다. 긴 입력은 잘라 의미를 바꾸지 않고 거부한다.

실제 usage가 있으면 입력·cached·출력·reasoning 및 계산 비용을 따로 기록한다. cached는 입력의 부분집합, reasoning은 출력의 부분집합으로 처리해 두 번 더하지 않는다. usage가 없는 오류는 예약을 유지한다. timeout/취소/전송 결과 불명은 UNKNOWN이며 run을 중지한다. 재시작 후에도 RESERVED/DISPATCHED가 남으면 다음 호출을 막는다. 실패·명시 재시도·브라우저·스모크 모두 같은 요청 한도를 소비한다. 숨은 자동 재시도나 무료 timeout 가정은 없다.

원장은 provider request ID, 모델, 시각, 상태, latency, usage, 안전한 trace ID와 합성 자료/사용자 식별만 남긴다. 인증정보·질문/답안 원문을 원장에 저장하지 않는다. 실제 청구 확인은 항상 계산 비용과 별도이며 이번에는 미확인이다.

## RAG와 채점

RAG는 현재 권한/승인 범위→현재 활성 pointer→top-3 검색→근거 문맥→답변→현재 권한/원본 재확인 순서다. 생성 입력에 제공한 모든 청크를 sources로 남긴다. 모델의 source ID는 그 실제 집합의 부분집합인지 확인하며, 발췌는 저장된 본문에서만 만든다. 모델이 만든 페이지·URL을 쓰지 않는다. 유효한 ID는 답변을 의미상 뒷받침한다는 증거가 아니다.

본문만 canonical snapshot에 포함하며 quiz/교사 정답을 검색 입력에 넣지 않는다. 자료·대화·질문은 신뢰되지 않는 데이터다. 근거가 없으면 보류하고, 전체 교재 fallback이나 예제 답변 하드코딩은 없다. A는 현재 질문 검색, B는 이전 대화가 있을 때만 검색용 재작성 한 번을 추가한다. top-k·자료·임베딩·답변 프롬프트/모델/출력 한도는 동일하다.

채점은 기존 3-A DB execution capability와 불변 문제/서버 정답/학생 답안 snapshot만 사용한다. 최대 8문항을 하나의 strict 요청으로 보내 기존 10초 경계를 유지한다. 응답의 문제 ID 집합·중복·타입·길이를 다시 검사한다. 공급자 대기는 기존 트랜잭션 밖에서 수행한다. confirmed 오류는 FAILED, 결과 불명은 UNKNOWN 계약으로 전달하며 false/0점 성공 저장으로 바꾸지 않는다. 이미 성공한 같은 제출 재조회는 새 채점 요청을 만들지 않는다.

학생 화면은 서버의 embedding/answer/grading 설정을 독립적으로 표시한다. `real_ai_verified=false`는 설정만으로 실제 검증을 주장하지 않는다는 뜻이다. OCR·파일 저장소·기기 로컬 TTS는 별도 범위다.

## 동결 평가와 판정

평가 파일은 `scripts/evaluation/phase5_data/`에 있다. 실제 모델 출력을 보기 전에 고정한 dataset hash는 `952e8d97eb5dee5b1f226bd1836de106d712bf41b6bdaac8316c3e935de27fa7`이다. 내부 합성 자료이며 전문가 검증이나 실제 학생 데이터가 아니다.

- RAG 24개: 직접 근거 8 / 고정 이전 대화 의존 8 / 자료에 답 없음 8. 개발 12, 최종 12로 각각 4/4/4다.
- 채점 답안 16개: 개발 8, 최종 8. 정답·바꿔 쓴 정답·부분 정답·오답·부정 표현을 포함한다.
- 평가 교재 2개는 각각 다른 의미의 8구간이다. top-3가 전체 자료를 가져오지 않는다. 기존 3구간 스모크 복사본의 쉬운 Hit@3를 검색 품질 지표에 넣지 않는다.

gold와 rubric은 evaluator 전용이다. 공급자에 보내는 projection은 질문·동일한 고정 대화·공개 자료만 허용한다. 실제 채점 정답은 서버 snapshot에서 얻는다. 비교군은 고정된 동일 대화를 사용하고 앞선 생성 결과로 다음 비교군의 대화를 채우지 않는다. 최종 결과를 본 뒤 프롬프트를 바꾸면 탐색 실행으로 남긴다.

Hit@3 분모는 비교군별 실행한 근거 있는 질문(예정 16개)이며 오류/timeout은 miss다. 미실행은 분모에서 제외하되 전체 완료 여부를 별도 표시한다. 답 없는 질문의 보류율, 고정 채점 기대값 일치율, 구조/ID 검사, 자연어 의미/근거 충실성은 별개다. 사람 검토는 확인한 행만 기록하며 개발 도구의 판단은 자동 예비 검토다. 유료 심판 모델을 호출하지 않는다.

한 번의 paired A/B 실행과 실패를 보존한다. RAG 평가 CLI는 사례마다 새 프로세스를 사용하므로 cold로 기록한다. 장기 실행 앱 API의 채점·스모크는 프로세스 최초 호출 여부를 확인하지 못하면 cold/warm 미확인으로 남긴다. 별도 유료 warmup은 없다. 앱 답변/질문 임베딩 캐시는 없으며 공급자 cached input은 실제 usage로 관측한다. 재작성 시간·토큰·비용은 B에 포함한다. 표본 수·단계별/전체 지연·오류를 함께 기록하며 작은 표본의 p95를 운영 SLA로 표현하지 않는다.

작은 로컬 HTML 검토표는 실제 답변/참고 구간/고정 기준/검토 필요 사유를 나란히 보이며 관측이 없으면 NOT_RUN이다. 평가 실행 완료와 B 채택은 별개다. local hash 벡터 대비 개선율을 실제 서비스 품질 개선으로 주장하지 않는다.

공개 운영 설정·클라우드·배포는 별도 단계이며 **PUBLIC_DEPLOYMENT_READY=false**다.
