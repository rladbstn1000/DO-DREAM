# 17. 5단계 실제 AI 연결 준비 결과

작업일은 2026-09-30, 저장소는 `/Users/yoonsu/Desktop/projects/DO-DREAM`, 작업 브랜치는 `codex/dodream-phase5-live-ai`다. 전달된 4단계 HEAD `b26fc7dfd42a731307e13368a23c116790a9efcd`와 실제 시작점이 일치했다. 팀 기준 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e` 이후 이번 변경은 개인 포트폴리오 개선이다. 시작 시 진행 중 Git 작업은 없었고 사용자 파일 `docs/.DS_Store`는 읽거나 변경·stage하지 않았다.

**실제 공급자 호출은 0회다.** 이번 요청에 유료 외부 호출 승인·예산·요청 한도·승인 데이터 범위가 없었다. 제안한 `~/.config/dodream/provider-live.env` 경로의 존재 여부만 확인했으며 파일이 없었다. 다른 키를 탐색하거나 비밀값을 읽지 않았다. `LIVE_API_AUTHORIZED=false`를 유지했고 live 세션·예산 원장을 열지 않았다. 실제 연결 성공·품질 개선·운영 준비 완료를 주장하지 않는다.

## 상태

| 항목 | 판정 | 범위 |
|---|---|---|
| PROVIDER_ADAPTER_CONTRACT | PASS | 고정 모델/URL, strict 응답, 오류·timeout, 예산·권한 경계의 오프라인 검사 |
| LIVE_RUN_AUTHORIZATION | NOT_RUN | 사용자 호출 승인 및 전용 키 없음; 기본 false |
| LIVE_EMBEDDING_STORAGE | NOT_RUN | 1536차원 실제 벡터 생성·저장 미실행 |
| LIVE_RAG_INTEGRATION | NOT_RUN | 실제 임베딩 검색·답변 미실행 |
| LIVE_GRADING_INTEGRATION | NOT_RUN | 실제 모델 채점 미실행 |
| LIVE_STUDENT_JOURNEY | NOT_RUN | 실제 모델을 사용한 브라우저 체험 미실행 |
| EVALUATION_EXECUTION | NOT_RUN | 고정 평가 자료/runner/검토표 준비; 유료 A/B 실행 없음 |
| ANSWER_QUALITY_REVIEW | NOT_RUN | 모델 출력·사람 의미 검토 없음 |
| USAGE_AND_COST_ACCOUNTING | PASS (오프라인 계약) / NOT_RUN (실측) | 공유 영속 예약·요청 한도·unknown 보존 검증; 실제 usage 없음 |
| LOCAL_REGRESSION | PASS | 변경된 단위/계약 및 실제 로컬 API·브라우저·색인·영속성 회귀 |
| DATA_PRESERVATION | PASS | 원래49개 행/파일 비교 항목 및361개 물리 컬렉션 보존 |
| CURRENT_MUTATION_SCOPE | PASS | 자체 프로젝트 범위 gate; 자체11개 시작 상태 복구 |
| CURRENT_EXTERNAL_ID_STABILITY | FAIL | 외부66개 ID 집합은 같지만5개 실행 상태가 변경됨; 원인 UNVERIFIED |
| REAL_AI_INTEGRATION | NOT_RUN | 실제 호출 미실행 |
| PUBLIC_DEPLOYMENT_READY | false | 공개 운영 설정·배포는 별도 |

## 구현과 한계

임베딩은 `text-embedding-3-small`, 1536차원, L2 정규화이며 spec은 `openai-text-embedding-3-small-1536-l2-content-v1`이다. 답변·검색 질문 재작성·채점은 공식 문서에 있는 snapshot `gpt-4.1-mini-2025-04-14`로 고정했다. 기존 `httpx==0.28.1`의 Embeddings/Chat Completions HTTP 경계를 사용하며 새 SDK를 설치하지 않았다. API 인자·표준 단가와 상세 설계는 [16](16-live-ai-and-evaluation-design.md)에 있다.

LOCAL_FAKE와 LIVE_OPENAI를 명시적으로 나누고 import 시 외부 클라이언트/모델 초기화를 제거했다. live 설정은 같은 자체 프로젝트의 AI 서비스에만 두 read-only 파일과 외부 연결을 허용한다. launcher가 local worker/dispatcher를 멈춘 뒤 승인된 신규 자료 작업 하나씩 수동 실행한다. live 공통 큐 소비자는 없다. local dispatcher/claim은 live spec을 처리하지 않는다. 회귀 진입점은 live 키 마운트/외부망이 있는 AI를 거부한다.

예산은 API·수동 worker·CLI가 같은 SQLite 원장으로 공유한다. 입력 상한과 최대 출력 비용을 예약하고 한 호출씩 처리한다. 자동 재시도는 없고 timeout/결과 불명 예약은 되돌리지 않으며 run을 중지한다. 공급자 오류를 local 답변 또는 0점 성공으로 바꾸지 않는다. HTTP 호출은 고정 host와 두 endpoint만 사용하지만 OS 방화벽 또는 전체 SSRF 방어 완료를 뜻하지 않는다.

RAG는 생성에 넣은 모든 청크와 실제 인용 ID 부분집합을 구분한다. 현재 권한·원본 버전·spec을 재확인하며 정답/문제 gold를 검색 문맥에 넣지 않는다. 채점은 기존 서버 snapshot과 짧은 트랜잭션 경계를 유지한다. 학생 화면 변경은 독립적인 답변/임베딩/채점 모드 안내와 live 대기 시간에 한정했다. 설정 표시는 실제 품질 검증을 뜻하지 않는다.

## 고정 평가와 비용

내부 합성 평가셋 hash는 `952e8d97eb5dee5b1f226bd1836de106d712bf41b6bdaac8316c3e935de27fa7`이다. RAG 24개는 직접 근거/대화 의존/자료에 답 없음 각 8개이고 개발·최종 각각 12개다. 채점 16개는 개발·최종 각각 8개다. 평가 교재 두 개는 각각 8개 의미 구간이며 top-3로 전체 본문을 가져오지 않는다. 기존 짧은 교재의 신규 스모크 복사본 두 개는 검색 품질 분모와 분리한다.

A는 현재 질문 검색, B는 동일 조건에서 이전 대화가 있을 때 검색용 재작성만 추가한다. gold는 evaluator에만 남기고 실제 입력 projection에서 제외한다. 모델 출력이 없으므로 Hit@3·보류율·채점 일치율·지연·의미 충실성은 **NOT_RUN**이다. B 채택은 보류한다. 오프라인 대역 통과를 실제 품질 개선율로 쓰지 않는다.

이번 실행의 실제 공급자 요청은 **0**, 이 작업이 발생시킨 호출의 계산 비용은 **USD 0**이다. 공급자 usage와 실제 청구서는 관측하지 않았으며 비용 성능을 측정한 결과가 아니다. 별도 유료 심판 모델도 호출하지 않았다. 오프라인 비용 계약은 cached 입력을 입력의 부분집합, reasoning을 출력의 부분집합으로 처리하고 예약·관측 usage·계산 금액·청구 확인 여부를 구분한다.

작은 로컬 HTML 검토표는 `.local/phase5/evaluation/20260930T091338062757Z-review.html`에 남겼다. 실제 답변·참고 구간·기대 핵심 내용·검토 필요 사유를 나란히 표시하고 현재 모든 자연어 검토는 미실행이다. 구조/ID 자동 검사와 사람이 확인하는 의미·근거 충실성은 별도 항목이다.

## 실제 로컬 검증

| 실행 | 이번 결과 |
|---|---|
| Spring 단위/계약 | 154 PASS, 25 suites |
| AI 단위/계약 | 176 PASS; 공급자 40개·AI 평가 6개 포함 |
| 문서 처리 단위/계약 | 6 PASS |
| 호스트 실행 범위/launcher/평가/자료 준비 | 97 PASS; 호스트 평가 18개·신규 자료 준비 6개 포함 |
| 고정 평가 도구 | 26 PASS, 동결 hash 일치 |
| 웹 단위 및 타입 검사 | 인증25 / 권한9 / 채점19 / 색인20 / 학생36 PASS; 타입 검사 PASS |
| 실제 인증 API | 131 PASS |
| 실제 객체 권한 API | 188 PASS |
| 기본 동작 / 보안 | 27 / 16 PASS |
| 실제 채점 API | 284 PASS |
| 실제 학생 API | 150 PASS |
| 실제 Chrome 학생 흐름 | 55 PASS, 외부 리소스 요청0 |
| 실제 색인 회귀 | 6개 시나리오, 225 PASS |
| 실제 재시작 영속성 | 19 PASS |
| 신규 평가 자료 발행 및 재실행 | 4개 자료 PASS, 재실행 추가 생성0, 실제 AI 호출0 |

브라우저는 Chrome154.0.8037.59, 실행 ID `40a658ef-3866-4de7-acc0-412c1b29d360`다. 55개 중 실제 UI29, API 경계6, 전달 장애5, 자체 서비스 장애7, 브라우저 저장 장애1, 응답 주입7로 구분한다. 자연어 모델 품질 검사가 아니며 55개 전체를 live로 실행하지 않았다. 실행 전후 application hash는 `8cc8403d318adff9d6a55730c7660d3e3a4da0443b85d762c992b4449d19d1a2`로 일치했다. 320px 화면을 직접 확인했고 sources·퀴즈 결과 캡처도 보존했다.

신규 live 준비 자료 ID는405–408, 전용 합성 학생은844다. 공개 발행은 완료됐지만 live spec 작업은 승인 대기이며 실제1536차원 벡터 저장은 미실행이다. 재호출에서 동일한 자료·문제·작업·학생 ID를 확인했다.

증거는 ignored `.local/phase5/`에만 있으며 원시 로그·합성 인증 cookie·생성된 로컬 비밀은 커밋하지 않는다. 실행별 source hash, 이미지 ID, 시각, 첫 실패와 후속 결과를 보존한다.

최초 AI 계약 실행의 한 실패는 새 spec 경계가 추가된 뒤 이전 Chroma timeout fixture에 spec이 빠져 HTTP 호출 전에 거부된 사례였다. fixture에 기존 local spec을 명시하고 요청 1회/503 assertion은 유지했다. 후속 전체 AI 계약 176개가 통과했다. 컨테이너 교체와 겹친 회귀 fixture 준비는 Docker metadata gate가 중단했고, 교체 종료 후 같은 idempotent 준비가 통과했다. 초기 제한된 호스트 실행의 loopback socket 검사 2개는 환경 권한 차단이었고, 허용된 로컬 실행에서 통과했다. 각 첫 기록을 삭제하거나 성공 결과로 덮지 않았다. 미승인 preflight는 예상대로 `LIVE_NOT_AUTHORIZED`와 exit2로 차단됐다. 공통 명령 기록기의 nonzero 표시는 FAIL이지만 이 미승인 차단 검사의 판정은 차단 성공이며 공급자 요청0이다.

이번 색인 재실행은 `happy`, `failure_preservation`, `corruption`, `source_versions`, `authorization`, `transport_timeout`이다. 변경하지 않은 3-B 강제 종료 전체 suite는 이번에 다시 실행하지 않았으며 [12의 과거 증거](12-phase3b-results.md)와 구분한다. 새1536차원 spec·정규화·다른 공간·잘못된 차원 거부는 오프라인 계약 검사이며 실제1536차원 Chroma 저장 성공으로 해석하지 않는다. 유료 호출을 이용한 강제 종료·장애 실험은 하지 않았다.

## 데이터와 자원 보존

이번 시작 시 실제 수집한 baseline은 MySQL **40개 테이블/3,485행**, SQLite **817행**, 파일 **540개**, Chroma **361개 컬렉션/1,165청크**였다. 이전 보고서 숫자를 재사용하지 않았다. 행/파일 hash와 Chroma ID·문서·metadata·벡터 hash를 비교하며 기존 분할 읽기와 메모리 제한을 유지한다. 삭제·초기화·retention 실행은 없고 retention은 dry-run이다.

원래 행/파일 보존 **49개 항목 PASS**, 원래 Chroma361개 컬렉션/1,165청크의 ID·내용·metadata·벡터 hash도 **PASS**이며 변경/누락0이다. 현재 총량은 다음과 같다.

| 대상 | 시작 | 종료 전 실측 | 증가 |
|---|---:|---:|---:|
| MySQL 테이블 | 40 | 40 | 0 |
| MySQL 행 | 3,485 | 4,260 | 775 |
| SQLite 행 | 817 | 1,050 | 233 |
| 객체 파일 | 540 | 631 | 91 |
| Chroma 컬렉션 | 361 | 434 | 73 |
| Chroma 청크 | 1,165 | 1,406 | 241 |

추가분은 이번 합성 회귀·학생 체험·자료 준비 기록이며 삭제하지 않았다. retention dry-run은 원장 실행454개/물리 컬렉션434개/파일631개를 관측했고 active pointer 문제0, 모든 action은 retain이다. 신규 live 작업4개의 상태는 QUEUED/PENDING, delivery_attempts·execution_generation·executions는 모두0이었다. 실제 AI 환경은 LOCAL_FAKE/미승인이고 전용 키 변수·키 마운트·live manifest·live 예산 원장은 모두 없었다.

 시작 시 자체 컨테이너 11개는 모두 종료 상태였고 자체 볼륨은 5개였다. 외부 컨테이너는 66개, 그중 실행 중 5개였다. 종료 시 자체11개가 모두 exited로 복구됐고 자체5개 볼륨을 보존했다. 새 볼륨/네트워크는0이다. loopback 포트·내부망·키 없는 구성·JWT/생성 비밀값 로그 비노출도 PASS다.

**외부 자원 상태 보존은 FAIL이다.** 외부 컨테이너66개 ID와 이름·볼륨·네트워크는 모두 보존됐지만 `etch-phase7-fresh-v4`의 web/backend/elasticsearch/mysql/redis 5개가 running→exited로 바뀌었다. 외부 실행 중 수는5→0이다. 종료 검사에서 관측한 사실이며 변경 원인은 **UNVERIFIED**다. 이 작업의 실행 범위 gate는 자체 프로젝트만 허용했으며 외부 상태 변경을 이번 작업의 정상 복구로 해석하거나 임의로 재시작하지 않았다. `isolation`의 exit1과 두 snapshot을 보존했다. 따라서 전체 자원 검사를 PASS로 합치지 않는다. 자체 데이터 보존·대상 범위 PASS와 외부 상태 보존 FAIL을 분리한다.

## 재개와 커밋

키 없는 양식은 `.local/phase5/live/manifest.template.json`, `.local/phase5/live/provider-live.env.example`이다. 명시적인 사람 승인과 모델·예산·요청 한도·합성 사용자/자료 범위가 준비된 뒤 [로컬 runbook](02-local-runbook.md)의 순서로만 재개한다. 파일에 키가 생겼다는 사실을 승인으로 취급하지 않는다. 승인 상태나 승인 문구를 대신 작성하지 않았다.

로컬 커밋은 검증된 준비 코드·검사·문서87개만 포함한다. 커밋 제목은 `feat(ai): prepare opt-in providers and frozen evaluation`이며 실제 연동 완료 커밋이 아니다. 최종 SHA는 작업 응답과 로컬 Git 기록에 남긴다. 원시 로그와 사용자 파일은 제외하고 generated secret/JWT 검사 및 staged diff를 확인한다. push·PR·merge·배포·터널·클라우드 생성·결제·자동 충전은 수행하지 않았다. 다음 운영/배포 단계에 자동 착수하지 않는다.
