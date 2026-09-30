# 4단계 학생 웹 체험 검증 결과

학생 웹과 로컬 체험 진입을 구현했다. 실제 Spring·FastAPI·MySQL·Redis·Celery·Chroma에 연결하며, 답변·8차원 임베딩·채점 공급자는 명시적인 로컬 대역이다. 최종 학생 웹 인수·관련 회귀·기존 데이터 보존·이번 외부 자원 비교를 완료했다. 실제 음성 청취·VoiceOver·외부 AI·공개 배포의 미실행 범위는 별도로 유지한다. 설계는 [13-student-web-design.md](13-student-web-design.md), 직접 실행은 [15-demo-walkthrough.md](15-demo-walkthrough.md)를 따른다.

## 1. 기준과 범위

| 항목 | 기록 |
|---|---|
| 저장소 | `/Users/yoonsu/Desktop/projects/DO-DREAM` |
| 팀 구현 기준 | `4c763af2316ebb00f523bc43b0c29e49ef7bf62e` |
| 시작 HEAD | `ed867e5f1bf1c1c5a9f926186150a6d161a8e000` |
| 시작/작업 브랜치 | `codex/dodream-phase3b-indexing` → `codex/dodream-phase4-student-web` |
| 실제 시작 상태 | 전달 HEAD와 일치, tracked 변경 없음. 제외 대상 `docs/.DS_Store`만 untracked |
| 로컬 커밋 | 이 문서를 포함하는 `feat(web): add isolated student learning demo` 커밋. 최종 SHA는 최종 응답과 ignored `review/git-final.json`에 기록한다. 자기 커밋 SHA를 문서에 미리 기입하지 않는다. |
| 증거 | ignored `.local/phase4/results/`, `browser-ui/`, `review/` |
| 사용자 파일 | `docs/.DS_Store`는 읽기·삭제·stage에서 제외 |

`/demo`, `/learn` 계열을 추가하고 교사용 `/student/:studentId`와 기존 로그인·자료 편집을 유지했다. 서버의 local 프로필과 명시적 opt-in을 모두 요구한다. 새 일반 자원 관리 체계 없이 기존 scope gate를 그대로 사용했다. 공개 서비스 인증, 실제 외부 AI, 모바일 전체 설치, 공개 배포는 범위 밖이다.

## 2. 실제 동작과 인수 실행

최종 단일 실행 명령은 `python3 scripts/local/manage.py student-web`이다. 전용 Chrome context에서 시작 버튼·교재·단원·질문·참고 자료·퀴즈·결과·새로고침을 실제 화면 조작으로 수행하고, 별도 교사 context의 실제 학생 결과 카드까지 확인한다. fixture 준비, 권한 경계와 저장 건수 확인에만 직접 API/DB 조회를 사용한다.

첫 완주 실행 `cd06df98-31ed-4b0c-b7e7-56ff61f7ae80`은 2026-09-30 07:35:04–07:36:26 UTC, exit0, 55 PASS였다. 이후 실제 캡처에서 참고 자료 dialog 정렬과 비활성 skip link의 표시를 다듬었다. 최종 실행은 별도 기록하며 두 실행의 PASS 수를 합하지 않는다.

**최종 PHASE4_ACCEPTANCE_RUN=PASS**: `2026-09-30 08:00:53–08:02:18 UTC`, Chrome154.0.8037.59, **exit0 · 55 PASS /0 FAIL /0 BLOCKED**, run `f4eb0e3f-5521-4b14-a094-d903d5edb725`. 실행 도중 앱 소스가 바뀌지 않았다. 전후 앱 SHA-256은 모두 `6bd66c26d3eb06dc6a131d7d6361702219a794dd46c84934a85845d26f115eeb`다.

55개는 실제 UI29, 실제 API 권한 경계6, 실제 완료 응답의 전송 유실5, 자체 서비스 장애7, 오류 응답 주입7, 브라우저 저장소 오류1로 나뉜다. 55개 모두를 정상 UI 동작 또는 실제 서버 실패 검사라고 표현하지 않는다. 증거는 `phase4-acceptance-f4eb0e3f-5521-4b14-a094-d903d5edb725.json`, `student-browser-f4eb0e3f-5521-4b14-a094-d903d5edb725.json`, `student-storage-f4eb0e3f-5521-4b14-a094-d903d5edb725-{0,1,4,7}.json`이다. 네 storage checkpoint 모두 PASS이며 논리 제출3개 각각 **attempt1 / result2 / log2 / 중복 문제0**을 확인했다. 각 source는 해당 시점의 실제 활성 pointer와 Chroma 청크1개에 일치한다.

동일 앱 소스의 앞선 `d064d285-84b2-49d2-8904-0f2a7f305125`(07:57:17–07:58:40)도55 PASS였다. 최종 캡처 방식과 합성 학생 exact 선택자를 반영한 위 실행을 최종 근거로 사용한다. 앞선 성공/실패의 수를 합산하지 않는다.

실제 정상/경계 검증과 오류 응답 주입을 구분한다.

| 방식 | 검사 범위 |
|---|---|
| 실제 UI + 실제 서버 | 독립 학생 두 명의 완주, 교사 결과 카드, 실제 답변 청크와 Chroma 활성 버전 대응, 동일 key의 attempt/result/log 수 |
| 실제 서버 권한 | 타인 attempt/session/source 404, 공유 없는 자료 URL 거부, 학생의 교사 API 403 및 route guard, 공유 회수 후 본문/source 404와 화면 캐시 정리 |
| 실제 데이터 변경 | 문제 수정 후 version409와 명시적 새 풀이; 새 원본 발행 접수 중 학습 제한, 활성화 뒤 기존 RAG409, 사용자 선택으로 새 대화와 새 버전 본문/source 조회, 옛 대화 보존 |
| 실제 저장소 장애 | 자체 Chroma pause로 검색 실패를 확인하고 가짜 답변 없음; unpause 뒤 같은 권한 있는 세션에서 회복 |
| 실제 제출 후 전송 유실 | 서버가 완료한 응답만 브라우저에서 유실. 탭 pending 복구 후 같은 key/동결 body/attempt로 재확인하고 DB 중복 없음 |
| 실제 인증 | 2초 AT 만료 후 학생 HttpOnly cookie refresh, 같은 사용자 유지. 로그아웃 시 pending과 늦은 응답 차단 |
| ERROR_RESPONSE_INJECTION | UNKNOWN·provider 오류·악성 HTML·비활성 config의 화면 처리. 서버의 실제 UNKNOWN/모델 장애 발생 증거로 합산하지 않음 |
| 브라우저 저장소 오류 주입 | sessionStorage 실패 시 복구 불가능한 새 제출 자체를 차단하고 안내; API 제출 0건 |

local chain이 실제 입력으로 사용한 첫 검색 청크만 sources에 연결한다. 발췌·revision·hash·chunk position은 실제 서버 값이며 `/sources/{index}`도 소유자·공유·현재 버전을 다시 확인한다. 이것은 검색 품질이나 답변 정확성 평가가 아니다. 실제 local mode를 화면과 캡처에 유지한다.

## 3. 체험 계정과 합성 자료

별도 HttpOnly 방문자 cookie의 서버 hash에 합성 학생을 연결한다. 독립 context는 다른 학생이 되고 같은 방문자의 재시작은 같은 계정을 사용한다. 실제 JWT·Redis refresh·CSRF를 유지하며 요청의 userId/role/schoolId를 받지 않는다. 기존 세션에서는 409로 명시적인 로그아웃을 요구한다. 기본 방문자 상한100, 생성 잠금·lease·cooldown을 둔다. 공개 게스트 인증으로 평가하지 않는다.

`student-web-v1`의 직접 작성 자료 **물의 여행**, **생활 속 분리배출**을 각각 3단원·2문제로 준비했다. 출처는 “DO:DREAM 로컬 체험용 직접 작성 · v1”이다. 새 교사·학급·학생 관계를 사용하며 기존 사용자를 체험 계정으로 배정하지 않는다. 실제 발행·작업 원장·Celery·Chroma 검증을 거치며 SQL로 ACTIVE 포인터를 만들지 않는다. 같은 버전 재준비는 교재·문제·논리 작업을 추가하지 않는다. 시연용 데이터는 종료 후에도 보존한다.

## 4. 현재 회귀 실행

아래 표는 이번 4단계에서 실행한 결과만 기록한다. 테스트·HTTP 체크·브라우저 체크를 서로 합산하지 않는다. 모든 시간은 UTC다. 표의 `manage.py`는 저장소 루트에서 `python3 scripts/local/manage.py`의 약칭이고, `npm run`은 `npm --prefix fe-web run`의 약칭이다. 실제 전체 argv·시각·종료 코드는 각 JSON과 `commands.jsonl`에 남는다.

| 검사 | 실제 명령/동등 호출 | 시작–종료 UTC | exit·PASS 수 | 증거(JSON/log) |
|---|---|---|---|---|
| 실제 Spring 단위 | `manage.py test` | 07:32:13–07:32:31 | 0 · 145 | `be-tests-2026-09-30T073213055642+0000` |
| 실제 AI 단위 | `manage.py test` | 07:32:32–07:32:46 | 0 · 110 | `ai-tests-2026-09-30T073232528136+0000` |
| 실제 PDF 단위 | `manage.py test` | 07:32:47–07:32:49 | 0 · 6 | `pdf-tests-2026-09-30T073247611771+0000` |
| scope gate 단위 | `manage.py scope-test` | 07:26:37–07:26:37 | 0 · 58 | `scope-unit-2026-09-30T072637807692+0000` |
| 웹 인증 단위 | `npm run test:auth` | 07:31:56–07:31:56 | 0 · 25 | `phase4-web-test-auth-2026-09-30T073156444541+0000` |
| 웹 객체권한 단위 | `npm run test:authorization` | 07:31:56–07:31:57 | 0 · 9 | `phase4-web-test-authorization-2026-09-30T073156931422+0000` |
| 웹 채점 단위 | `npm run test:grading` | 07:31:57–07:31:57 | 0 · 19 | `phase4-web-test-grading-2026-09-30T073157266776+0000` |
| 웹 색인 단위 | `npm run test:indexing` | 07:31:57–07:31:57 | 0 · 20 | `phase4-web-test-indexing-2026-09-30T073157614954+0000` |
| 학생 웹 단위 | `npm run test:student` | 07:31:57–07:31:58 | 0 · 35 | `phase4-web-test-student-2026-09-30T073157947057+0000` |
| 웹 typecheck | `npm run typecheck` | 07:31:58–07:31:58 | 0 · — | `phase4-web-typecheck-2026-09-30T073158297465+0000` |
| 최종 CSS 포함 웹 빌드 | `npm run build -- --mode phase1` | 07:43:35–07:43:38 | 0 · — | `phase4-final-web-build-2026-09-30T074335976218+0000` |
| 실제 인증 | `manage.py auth` | 07:36:54–07:37:14 | 0 · 131 | `phase4-auth-regression-2026-09-30T073654765245+0000` |
| 실제 객체권한 | `manage.py authorization` | 07:37:14–07:37:32 | 0 · 188 | `phase4-object-authorization-2026-09-30T073714327685+0000` |
| 실제 smoke | `manage.py smoke` | 07:38:32–07:38:34 | 0 · 27 | `phase4-smoke-2026-09-30T073832929125+0000` |
| 실제 보안 | `manage.py security` | 07:38:34–07:38:35 | 0 · 16 | `phase4-security-2026-09-30T073834476379+0000` |
| 실제 채점 전체 | `manage.py grading` | 07:38:36–07:42:56 | 0 · 284 | `phase4-grading-regression-2026-09-30T073836073178+0000` |
| 색인 선택6개 시나리오 | `manage.py indexing happy publication source_versions storage_failure transport_timeout browser` | 07:42:56–07:48:08 | 0 · 111 | `phase4-indexing-regression-2026-09-30T074256301368+0000` |
| 최종 Chrome 교사 권한 | `npm run test:browser-authorization` | 07:49:15–07:49:38 | 0 · 18 | `phase4-final-browser-authorization-2026-09-30T074915813972+0000` |
| 최종 Chrome 채점 API 계약 | `npm run test:browser-grading` | 07:49:38–07:49:39 | 0 · 11 | `phase4-final-browser-grading-2026-09-30T074938238183+0000` |
| 최종 Chrome 교사 색인 | `manage.py indexing browser` | 07:49:39–07:51:14 | 0 · orchestrator29 · 별도 Chrome14(합산하지 않음) | `phase4-final-browser-indexing-2026-09-30T074939711446+0000` |

| 추가 검사 | 실제 명령/동등 호출 | 시작–종료 UTC | exit·PASS 수 | 증거(JSON/log) |
|---|---|---|---|---|
| 체험 API 활성 | `manage.py demo-api` | 07:33:49–07:34:09 | 0 · 150 | `phase4-demo-api-2026-09-30T073349468960+0000` |
| 체험 API 비활성 | `manage.py demo-api --disabled` | 07:24:37–07:24:41 | 0 · 7 | `phase4-demo-disabled-api-2026-09-30T072437471540+0000` |
| 실제 비활성 Chrome | `node fe-web/tests/browser-demo-disabled.mjs` | 07:34:28–07:34:29 | 0 · 1 | `phase4-disabled-browser-2026-09-30T073428501321+0000` |
| 최종 Chrome 인증 | `npm run test:browser-auth` | 07:54:32–07:55:36 | 0 · 17 | `phase4-final-browser-auth-2026-09-30T075432484837+0000` |
| 실제 재시작 영속성 | `manage.py persistence` | 07:53:10–07:54:03 | 0 · 19 | `phase4-final-persistence-2026-09-30T075310819007+0000` |
| 샘플 재준비/반복 안정성 | `manage.py demo-prepare` | 07:54:03–07:54:04 | 0 · 두 자료, 추가 중복0 | `phase4-final-demo-prepare-2026-09-30T075403982265+0000` |
| 최종 학생 전체 인수 | `manage.py student-web` | 08:00:53–08:02:18 | 0 · 55 | `student-web-2026-09-30T080053852168+0000` |

최종 이미지 식별자는 다음과 같다. CSS만 바뀐 뒤 웹을 다시 빌드했고, 최종 Chrome 회귀·학생 인수는 이 웹 이미지를 사용했다. 서버 소스/이미지는 마지막 단위·HTTP·장애 회귀 후 변경하지 않았다. 단위검사 이후 문서와 검사 동기화 코드는 별도로 정리했다.

| 최종 실제 이미지 | image ID |
|---|---|
| ai | `sha256:e8990acd9f708874bd4bcf489da10b40b2ba817a2022b063ba7a4b8567673189` |
| be | `sha256:24cf91d1e7cae69be44cf1bbda18d31030190abe5c9c4e66177144f8cb223e1f` |
| be-auth-short | `sha256:24cf91d1e7cae69be44cf1bbda18d31030190abe5c9c4e66177144f8cb223e1f` |
| chroma | `sha256:6871ba69fa65ce7f8fa779583d2266207c29c05009961c851c3331c7bd46734d` |
| index-dispatcher | `sha256:0017b2fd75495f3cd6da8daf5bacea13bb1b851d1658c3c57e44f89371c7e602` |
| mysql | `sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb` |
| python-service | `sha256:1910e86576f8f9945c64fcc90279d5a3573be14ca8ba86c31c38a9e9966e8e94` |
| redis | `sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499` |
| web | `sha256:b3b70d3b2b1ec07aa35470d123a45fed87eb542102cb566a6dc7ba18367cfc45` |
| web-auth-test | `sha256:b3b70d3b2b1ec07aa35470d123a45fed87eb542102cb566a6dc7ba18367cfc45` |
| worker | `sha256:c87d81686d60b12dfd9d1575dd5f531647f2d9d38dbeb966e67298d8bf7183fa` |

앱의 원장·dispatcher·worker·Chroma transport 구현은 변경하지 않았다. 다만 누적된 옛 컬렉션을 모두 읽을 때 실제 Chroma의 메모리 종료가 발생하여 local Compose에 LRU segment cache 한도를 추가했다. 따라서 정상 발행·버전·저장 실패·실제 transport timeout/회복 및 재시작/물리 컬렉션 보존을 이번에 다시 검사한다. 3-B 전체 crash suite는 이번에 재실행하지 않는다.

기존 Chrome 인증 검사에서 full reload는 새 `/api/session/me` gate를 먼저 통과하므로 병렬 만료 요청을 더 이상 만들지 않는다. 해당 세 시나리오만 실제 학급 진입 → AT 만료 → **목록으로** 버튼의 SPA 이동으로 바꿨다. 기존 병렬401 개수·refresh1회·로그아웃 후 서버401 판정을 유지하며, 늦은 응답이 실제401이고 새 AT의 클래스 재요청이200인 조건도 추가했다. 테스트를 삭제하거나 기대값을 낮추지 않았다.

**과거 기록은 유지한다.** [3-B 결과](12-phase3b-results.md)의 전체 색인 명령 원본 FAIL, 후속 실행을 연결한 16개 시나리오 coverage PASS, 기존 회귀 묶음 원본 FAIL, 영속성 후속19개 PASS는 이번 결과와 별개다. 과거 ETCH 및 3-A 외부 변화 FAIL / 원인 귀속 UNVERIFIED도 바꾸지 않는다.

## 5. 실패 원본과 해결 근거

실패·BLOCKED 원본은 timestamp 파일에 남긴다. 준비가 되기 전의 실패를 성공으로 덮거나 중단 실행의 PASS를 합산하지 않는다.

| 최초 관찰 | 처리·후속 근거 |
|---|---|
| 기본 sandbox에서 Docker 접근 불가 | BLOCKED 기록 후 승인된 자체 Docker 범위로 실행. 자동 승인 거절이 발생한 것은 아님 |
| 첫 기존 컬렉션 전체 읽기에서 Chroma exit137/OOMKilled | 첫 before 수집은 실패해 baseline을 쓰지 않음. 기존 이미지·볼륨을 유지하고 local LRU 한도8MiB를 설정한 뒤 295개/987청크의 새 baseline 수집 완료. 이 값은 segment cache 설정이며 프로세스 RSS 전체의8MiB 제한이 아님 |
| host Spring 테스트 discovery “No tests found” | host 결과를 단위검사 PASS로 쓰지 않음. 실제 Docker 테스트에서 최종145개 통과 |
| 첫 비활성 API 검사에서 gateway 연결 불가 | 자체 gateway의 미기동 dependency DNS가 원인. 자체 서비스 준비 후 같은 API7개와 실제 비활성 Chrome 검사 통과 |
| 첫 샘플 준비503 `INDEXING_TRANSACTION_BOUNDARY` | OSIV가 비활성 EntityManager의 physical connection을 보유한 채 외부 객체 호출 경계에 도달. local 준비에서 비활성 holder를 잠시 분리하고 finally 복원. 실제 활성 transaction은 계속 거부. 경계 단위3개와 실제 준비/반복 준비 통과 |
| BE/BE-test 동시 build의 test image export “parent snapshot not found” | compile 통과와 image export 실패를 구분. cache/이미지 삭제 없이 be-test를 순차 no-cache build하여 성공 |
| scope 단위검사2개 local bind 권한 오류 | 환경 BLOCKED 원본 유지. 허용된 local port 실행에서 기존58개 통과, 기대값 수정 없음 |
| security 최초15 PASS /1 BLOCKED | 이전 smoke session 증거가 없어 중단. 실제 smoke27개를 실행한 뒤 security16개 재검사 통과. 보안 결함 FAIL로 오인하지 않음 |
| 최종 이미지 첫 Chrome 인증15 PASS /2 FAIL (같은 원인의 중복 진단) | SPA 이동 뒤 `networkidle`이 이전 문서 상태로 즉시 반환해 React의 병렬 요청 전 refresh0/401개수0에서 판정. 실제 두 API 성공 응답을 미리 등록하고 기다리도록 검사 동기화만 수정. 동시401·refresh1회 기대값 유지. 원본 `phase4-final-browser-auth-2026-09-30T075130310197+0000.json/.log` 보존; 재검사 결과는4절 |
| 최종 학생 인수 두 실행8 PASS /1 FAIL | `0f63c625-1a5e-43a3-bce0-94144ec71ffb`(07:55:36–43)와 진단 실행 `a4cfb1e4-4cdb-4fd9-bb1b-42ad639ee855`(07:56:35–41), 각각 exit1. 단원 URL 변경만 기다린 검사와 앱의 다음 frame 제목 focus 이동이 겹쳐 질문 입력으로 Tab 이동하는 outline 판정에서 실패. 비밀 없는 line/numeric 진단으로 위치 확인 후 실제 새 단원 제목 focus 도착을 기다리게 수정. 앱·기존 outline/키보드 기대값은 유지. 두 원본의 PASS를 최종 실행에 합산하지 않음 |
| 좁은 화면 재촬영 실행6 PASS /1 FAIL | `82399307-12b7-4862-9c22-d43ff3f2ae79`(07:59:35–41), exit1. 교사 학생 카드의 부분 문자열 선택이 누적된 `체험 학생 13`과 `체험 학생 1` 뒤의 `3학년` 텍스트를 함께 일치시킬 수 있어 strict locator가 거부. 실제 학생 이름 heading의 exact 일치로 선택 범위를 바로잡고 같은 교사 결과 검사를 유지. 앱 변경 없음 |
| 첫 학생 UI55 PASS 뒤 캡처 정렬 개선 | dialog 중앙 정렬·비활성 skip link clipping만 수정. 최종 웹 image를 다시 만들고 새 단일 인수 실행으로 검증 |

실패 원본 식별자: `phase4-data-before-2026-09-30T065933730715+0000`, `phase4-demo-disabled-api-2026-09-30T072232197934+0000`, `phase4-demo-prepare-2026-09-30T072503359406+0000`, `scope-unit-2026-09-30T072627792813+0000`, `phase4-be-boundary-build-2026-09-30T072843737085+0000`, `phase4-security-2026-09-30T073732679153+0000`의 JSON/log. 최초 Docker 환경 차단은 `initial-docker-sandbox-blocked.json`이다.

일부 Spring 진단 로그의 사용하지 않는 기본 생성 비밀번호 줄은 `[REDACTED]`로 치환했다. 실패/검사 행은 보존하며 redaction 파일 목록만 `review/log-redaction.json`에 기록한다. JWT·cookie·실제 생성 비밀은 문서·스크린샷·커밋에 포함하지 않는다.

## 6. 접근성·음성·화면 증거

실제 Chrome에서 포인터와 키보드 각각 핵심 흐름을 완료하고, 보이는 focus·label·상태 안내와 320 CSS px의 가로 넘침/버튼 잘림을 검사한다. 320px reflow를 실제 브라우저 확대 검사라고 표현하지 않는다. 실제 OS 확대와 VoiceOver 점검은 남은 수동 항목이다.

speechSynthesis의 로컬 한국어 voice를 명시적으로 선택한다. 단위검사는 시작·일시정지·재개·중지·단원/사용자 변경 cleanup·늦은 callback·긴 본문/timeout 계약을 확인한다. 실제 Chrome에서는 local Korean voice와 `start` 이벤트를 관찰했다. **음성 청취 NOT_RUN, VoiceOver NOT_RUN**이며 headless 이벤트를 소리가 들렸다는 증거로 쓰지 않는다. 접근성 인증이나 전체 WCAG 준수를 주장하지 않는다.

최종 단일 실행의 실제 캡처5개를 모두 열어 검토한 뒤 원본 PNG 그대로 복사했다. digest·크기·원본 runId는 `review/screenshots.json`에 있다. 전체 약498KiB이며 합성 학생과 직접 작성 자료만 표시한다.

| 화면 | 문서 자산 |
|---|---|
| 자료함 | [library-desktop.png](assets/phase4/library-desktop.png) |
| 본문·질문·실제 local 답변 | [learning-page.png](assets/phase4/learning-page.png) |
| 현재 권한/동일 버전 참고 발췌 | [source-reference.png](assets/phase4/source-reference.png) |
| 저장된 제출 snapshot 결과 | [quiz-result.png](assets/phase4/quiz-result.png) |
| 320 CSS px 본문 viewport | [learning-320.png](assets/phase4/learning-320.png) |

처음의320px full-page 캡처는 Chrome compositor tile이 반복되는 문제가 보여 문서에 넣지 않았다. 최종320px 자산은 실제 본문을 스크롤하여 보이는 viewport를 촬영했다. 이미지 생성·크롭 편집으로 화면을 만들지 않았다. 질문/AI 모드 영역은 이 좁은 viewport 아래에 있으며 desktop 학습 캡처에서 로컬 대역 표시를 확인할 수 있다.

캡처는 실제 구현과 합성 데이터만 표시한다. DevTools·토큰·cookie·인증 요청·기존 개인정보는 포함하지 않는다. trace/HAR와 영상은 생성하지 않았다. [시연 문서](15-demo-walkthrough.md)에 수동 음성/보조기술 점검표를 남긴다.

## 7. 데이터·실행 범위·종료

이번 새 baseline은 2026-09-30 07:03:09–07:04:08 UTC에 수집했다. MySQL **37개 테이블·2,587행**, SQLite **540행**, 객체 파일 **461개**, 물리 Chroma **295개 컬렉션·987청크**다. 원본은 `data-before.json`, `chroma-before.json`, 외부 자원은 `resources-before.json`이며 갱신하지 않았다.

회귀용 자료는 새 `[AUTHZ 4]`, `[GRADING LOCAL] phase4`, `[INDEXING LOCAL]` 행/객체를 사용한다. 기존 합성 authz 학생의 classroom 관계는 기존 회귀 중 잠시 변경한 뒤 finally 복원한다. 새 체험 자료의 공유·문제·원본 변경 검사는 복원된 내용과 누적 version/history를 보존한다. 기존 행에 일시적 쓰기도 전혀 없었다고 주장하지 않는다.

**DATA_PRESERVATION=PASS.** 원래 MySQL2,587행/SQLite540행의 원래 컬럼, 객체461개, 활성 포인터를 모두 보존했다. 물리 Chroma295개/987청크의 collection ID와 document·metadata·embedding digest도 모두 일치하며 변경/누락0이다. 증거는 `data-preservation.json`, `chroma-preservation.json`이다. 삭제 없는 retention dry-run도 PASS, `activePointerProblems=[]`, `action=retain_all`이다. 신규 자료/실행/학생 기록을 포함한 관측은361개 physical collections와540개 객체 파일이며 자동 GC는 추가하지 않았다.

**CURRENT_MUTATION_SCOPE=PASS, CURRENT_EXTERNAL_ID_STABILITY=PASS.** 외부66개 컨테이너의 ID 집합과 상태가 일치하고, 원래 실행 중5개도 유지했다. 기존 모든 볼륨/네트워크 이름을 보존했다. 자체11개는 모두 원래의 exited 상태이며 영속 볼륨5개와 시연 샘플은 남겼다. 외부 자원은 변경하거나 복원하지 않았다. 원인 귀속이 필요한 이번 외부 변화는 없다(`NOT_APPLICABLE`). 증거는 `resource-isolation-checks.json`과 before/after inventory다.

| 마지막 확인 | 실제 명령 | 시작–종료 UTC | 결과 | 증거(JSON/log) |
|---|---|---|---|---|
| 기존 데이터/Chroma | `python3 scripts/local/student_demo_data.py after` | 08:03:02–08:03:38 | exit0 · PASS, 원본 변경0 | `phase4-final-data-preservation-2026-09-30T080302508787+0000` |
| 삭제 없는 보존 검토 | `python3 scripts/local/indexing_retention.py` | 08:03:38–08:03:42 | exit0 · PASS, retain_all, pointer 문제0 | `phase4-final-retention-2026-09-30T080338895219+0000` |
| 도구/포트 | `python3 scripts/local/manage.py check` | 08:03:42–08:03:44 | exit0 · PASS | `phase4-final-check-2026-09-30T080342826843+0000` |
| Compose 설정 | `python3 scripts/local/manage.py config` | 08:03:44–08:03:44 | exit0 · PASS | `phase4-final-config-2026-09-30T080344172738+0000` |
| 자체 중지 | `python3 scripts/local/manage.py stop` | 08:04:29–08:04:45 | exit0 · PASS, 자체11개 exited | `phase4-final-stop-2026-09-30T080429814734+0000` |
| 외부/자체 범위 | `python3 scripts/local/manage.py isolation` | 08:04:45–08:04:47 | exit0 · PASS, 18 checks true | `phase4-final-isolation-2026-09-30T080445377038+0000` |
| 최종 상태 | `python3 scripts/local/manage.py status` | 08:04:47–08:04:48 | exit0 · PASS | `phase4-final-status-2026-09-30T080447847139+0000` |

## 8. 최종 상태와 남은 범위

| 상태 | 판정 | 범위 |
|---|---|---|
| `STUDENT_WEB_JOURNEY` | **PASS** | 포인터/키보드 완주와 담당 교사 실제 결과 |
| `DEMO_USER_ISOLATION` | **PASS** | 별도 학생·개인 기록·권한 거부와 실제 API150 |
| `RAG_SOURCE_PROVENANCE` | **PASS** | 답변 입력 청크, live pointer, 동일 버전 source GET |
| `GRADING_UI_REPLAY` | **PASS** | 동결 key/body 복구, attempt/result/log 중복0 |
| `KEYBOARD_AND_REFLOW` | **PASS** | 실제 키보드·focus·320 CSS px/desktop 범위 |
| `TTS_CONTROL_CONTRACT` | **PASS** | 합성 API 제어/cleanup 단위 + 실제 start 이벤트 |
| `TTS_AUDIBLE_CHECK` | **NOT_RUN** | 실제 소리 청취하지 않음 |
| `SCREEN_READER_MANUAL` | **NOT_RUN** | VoiceOver·시스템 설정 변경 없음 |
| `PHASE4_ACCEPTANCE_RUN` | **PASS** | 최종 한 실행55PASS/exit0, 이전 실패 별도 보존 |
| `EXISTING_REGRESSION` | **PASS** | 이번 필요한 회귀만; 과거 전체 suite FAIL은 유지 |
| `DATA_PRESERVATION` | **PASS** | 이번 새 baseline 행·컬럼·객체·pointer·Chroma 비교 |
| `CURRENT_MUTATION_SCOPE` | **PASS** | 기존 자체 scope gate 유지 |
| `CURRENT_EXTERNAL_ID_STABILITY` | **PASS** | 외부66개 ID·상태 유지 |
| `REAL_AI_INTEGRATION` | **NOT_RUN** | local 공급자만 사용 |
| `PUBLIC_DEPLOYMENT_READY` | **false** | 운영/공개 인증·보안·배포 미검증 |

실제 AI/음성 모델 설치, 모바일 전체 실행·생체인증, 운영 HTTPS/SSRF/log/CI/CD 개편, 기기 간 제출 복원, 클라우드·공개 도메인은 이번에 수행하지 않는다. push·PR·merge·공개 배포·터널은 수행하지 않았다.

## 변경 파일

검토 대상77개 파일이다. 실제 stage는 아래 명시 경로만 사용하고 `.local/`, `.env`, `docs/.DS_Store`, 원시 trace/HAR를 포함하지 않는다. 파일 hash·비밀 후보 검사·staged diff 식별자는 ignored `review/`에 보존한다.

```text
README.md
ai/app/rag/models.py
ai/app/rag/provenance.py
ai/app/rag/router.py
ai/app/rag/service.py
ai/tests/test_object_authorization.py
ai/tests/test_rag_provenance.py
be/src/main/java/A704/DODREAM/auth/controller/SessionController.java
be/src/main/java/A704/DODREAM/config/SecurityConfig.java
be/src/main/java/A704/DODREAM/demo/DemoAuthController.java
be/src/main/java/A704/DODREAM/demo/DemoCatalog.java
be/src/main/java/A704/DODREAM/demo/DemoManifest.java
be/src/main/java/A704/DODREAM/demo/DemoPreparationController.java
be/src/main/java/A704/DODREAM/demo/DemoSample.java
be/src/main/java/A704/DODREAM/demo/DemoVisitor.java
be/src/main/java/A704/DODREAM/demo/LocalDemoService.java
be/src/main/java/A704/DODREAM/demo/LocalDemoStore.java
be/src/main/java/A704/DODREAM/indexing/IndexingStore.java
be/src/main/java/A704/DODREAM/indexing/StudentIndexingSummary.java
be/src/main/java/A704/DODREAM/material/dto/MaterialShareListResponse.java
be/src/main/java/A704/DODREAM/material/service/MaterialShareService.java
be/src/test/java/A704/DODREAM/authorization/AuthorizationDatabaseTests.java
be/src/test/java/A704/DODREAM/demo/DemoAuthTests.java
be/src/test/java/A704/DODREAM/demo/DemoManifestTests.java
be/src/test/java/A704/DODREAM/demo/DemoPreparationBoundaryTests.java
be/src/test/java/A704/DODREAM/demo/DemoStoreTests.java
compose.local.yml
docs/portfolio/01-roadmap.md
docs/portfolio/02-local-runbook.md
docs/portfolio/13-student-web-design.md
docs/portfolio/14-phase4-results.md
docs/portfolio/15-demo-walkthrough.md
docs/portfolio/assets/phase4/learning-320.png
docs/portfolio/assets/phase4/learning-page.png
docs/portfolio/assets/phase4/library-desktop.png
docs/portfolio/assets/phase4/quiz-result.png
docs/portfolio/assets/phase4/source-reference.png
fe-web/package.json
fe-web/src/App.tsx
fe-web/src/auth/session.ts
fe-web/src/index.css
fe-web/src/pages/ClassroomList.css
fe-web/src/pages/Join.css
fe-web/src/student/DemoLibrary.tsx
fe-web/src/student/Layout.tsx
fe-web/src/student/Quiz.tsx
fe-web/src/student/Reader.tsx
fe-web/src/student/Session.tsx
fe-web/src/student/api.ts
fe-web/src/student/model.ts
fe-web/src/student/speech.ts
fe-web/src/student/student.css
fe-web/src/student/submission.ts
fe-web/tests/browser-auth.mjs
fe-web/tests/browser-authorization.mjs
fe-web/tests/browser-demo-disabled.mjs
fe-web/tests/browser-grading.mjs
fe-web/tests/browser-indexing.mjs
fe-web/tests/browser-student-boundaries.mjs
fe-web/tests/browser-student.mjs
fe-web/tests/student-auth.test.ts
fe-web/tests/student-model.test.ts
fe-web/tests/student-speech.test.ts
fe-web/tests/student-submission.test.ts
fe-web/tsconfig.app.json
scripts/local/grading_fixtures.py
scripts/local/indexing_browser_checks.py
scripts/local/indexing_fixtures.py
scripts/local/indexing_retention.py
scripts/local/manage.py
scripts/local/student_demo_data.py
scripts/local/student_demo_prepare.py
scripts/local/verify.py
scripts/local/verify_authorization.py
scripts/local/verify_grading.py
scripts/local/verify_student_demo.py
scripts/local/verify_student_web.py
```
