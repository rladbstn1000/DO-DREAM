# 13. 학생 웹 체험 설계

이 문서는 팀 구현 기준 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e` 이후의 **개인 개선 4단계**를 설명한다. 시작 소스는 `ed867e5f1bf1c1c5a9f926186150a6d161a8e000`이며, 2-A 인증·2-B 객체권한·3-A 채점·3-B 색인 계약을 학생 웹에 연결한다. 이 설계 설명 자체가 실행 PASS를 의미하지 않는다. 최종 명령·종료 코드·실행별 증거와 미실행 범위는 [14 결과](14-phase4-results.md), 사용 순서는 [15 시연](15-demo-walkthrough.md)을 따른다.

## 1. 화면과 기존 API 연결

기존 `fe-web`의 React 라우터와 인증 클라이언트를 사용한다. 새 BFF·Next.js·UI 프레임워크와 React Native 전체 변환은 도입하지 않는다. 기존 `/student/:studentId`는 교사가 담당 학생의 결과를 보는 화면으로 유지한다.

| 화면 | URL | 실제 서버 계약 |
|---|---|---|
| 학생 체험 시작 | `/demo` | `GET /api/auth/demo/config`, CSRF 획득 뒤 `POST /api/auth/demo/bootstrap`, `POST /api/auth/demo/start` |
| 현재 사용자 확인 | 보호 화면 공통 | `GET /api/session/me`의 `userId`, `name`, `role`, `demo` |
| 학생 자료함 | `/learn` | `GET /api/materials/shared`; 현재 공유된 `materials`와 학생용 `indexing` |
| 단원·본문·학습 완료 | `/learn/:materialId?chapter=1` | `GET /api/materials/shared/{id}/json`, `GET /api/progress/materials/{id}`, 명시적 완료 시 `POST /api/progress/update` |
| 질문·이력 | 학습 화면 안 | `GET /rag/mode`, `POST /rag/chat`, `GET /rag/chat/sessions?student_id=...`, `GET /rag/chat/sessions/{id}/messages?student_id=...` |
| 답변 참고 자료 | 학습 화면의 발췌 대화상자 | `GET /rag/chat/sessions/{sessionId}/messages/{messageId}/sources/{index}?student_id=...` |
| 학생 문제·제출 | `/learn/:materialId/quiz` | `GET /api/materials/{id}/quizzes`, `POST /api/materials/{id}/quizzes/submit` |
| 제출 상태·명시적 재시도 | 퀴즈 화면 안 | `GET /api/materials/{id}/quiz-attempts/{attemptId}`, `POST .../{attemptId}/retry` |
| 저장된 결과 | `/learn/:materialId/results/:attemptId` | 같은 attempt 조회; 현재 권한과 제출 당시 snapshot 재확인 |
| 담당 교사의 학생 결과 | 기존 `/classrooms` → `/classroom/:id` → `/student/:studentId` | 기존 담당 관계·학생별 자료/결과 조회 유지 |

표의 `/rag`는 FastAPI 경로다. 웹에서는 기존 nginx의 `/ai/rag` 프록시를 사용하고 Spring은 `/api`로 접근한다. 학생용 본문은 서버 `StudentContent`의 허용 구조를 거친다. 문제 조회에는 정답 대신 서버 관리 `version`이 포함된다. 교사 편집본·정답 포함 JSON을 내려받고 화면에서 숨기는 방식은 사용하지 않는다.

자료함의 로딩·빈 목록·실패를 구분한다. `StudentIndexingSummary`는 `state`, `readable`, `activeCurrent`, `sourceRevision`만 공개하며 작업 ID·물리 컬렉션·retry capability를 학생에게 주지 않는다. `QUEUED`는 발행 접수, `PROCESSING`은 준비 중이고, 학습 시작은 `readable`을 기준으로 제한한다. 같은 원본 재색인 실패에서 이전 정상 색인이 유효하면 사용 가능 여부는 기존 서버 판정을 따른다.

단원 선택은 URL query에 반영하며 직접 접근·새로고침·뒤로 가기로 다시 조회한다. 스크롤은 완료로 처리하지 않는다. 마지막 단원의 **학습 완료** 버튼이 기존 진도 API의 전체 단원 위치를 명시적으로 저장한다. 이 동작은 실제 이해도나 읽기 시간을 측정하지 않는다.

## 2. 로컬 체험 진입과 사용자 격리

`LocalDemoService`, `LocalDemoStore`, 준비 controller는 Spring `local` 프로필 **및** `LOCAL_DEMO_ENABLED=true`에서만 생성된다. Compose 기본값은 false이며 `manage.py demo-up`이 명시적으로 opt-in한다. 브라우저 VITE 설정, 요청의 Host/loopback 문자열, 임의 userId·role·schoolId로 서버 기능을 켤 수 없다. 비활성 설정은 config의 `enabled=false`, 준비·진입 차단으로 나타난다.

`bootstrap`과 `start`는 빈 JSON 객체만 허용한다. 두 POST 모두 기존 `/api/auth/csrf` 토큰과 CSRF 쿠키 정책을 적용한다. `bootstrap`은 서버 난수 32바이트를 64자리 hex visitor cookie에 넣고, 이미 존재하는 정상 visitor cookie를 재사용한다. cookie는 HttpOnly·SameSite=Lax·Path=`/api/auth/demo`이고 서버에는 SHA-256 식별값만 저장한다. JS body·번들·localStorage에 visitor 비밀, refresh token, deviceSecret 또는 준비용 자격증명을 반환하지 않는다.

서버는 전용 catalog 행 잠금 아래 새 합성 학생·학급 관계·두 자료의 개별 공유를 만든다. 서로 다른 독립 브라우저 context는 다른 visitor와 학생을 받는다. visitor 해시 PK와 학생 UNIQUE 제약, 진행 lease로 같은 visitor의 동시 클릭을 제한하고, catalog의 생성 수로 기본 **100명** 상한을 적용한다. 설정 허용 범위는 1–1,000명이다. 기존 사용자·회귀 계정은 재사용하지 않는다. 샘플 자료는 공유하지만 진도·대화·attempt 소유자는 각 학생이다.

같은 visitor의 재시작은 같은 학생을 사용하고 현재 학생 역할과 공유 권한을 다시 검사한다. 회수된 공유를 진입 API가 자동 복원하지 않는다. 로그아웃 뒤 visitor cookie는 남으므로 이후 명시적인 체험 시작으로 같은 합성 학생에 돌아갈 수 있다. 새로고침은 새 학생·교재·색인을 만들지 않는다. 유효한 기존 AT 또는 RT가 있으면 `SESSION_ALREADY_PRESENT` 409로 계정 교체를 거부한다. UI도 현재 세션을 유지하고, 역할 전환은 명시적 로그아웃으로 한다.

발급은 기존 `AuthSessionService`의 실제 JWT와 Redis refresh 저장을 사용한다. 학생 웹 refresh/logout은 `/api/auth/student/refresh`, `/api/auth/student/logout`의 쿠키 계약을 이용한다. 기존 AT 저장 방식은 유지하되 RT를 JS 저장소에 추가하지 않는다. `/api/session/me`의 현재 DB 사용자 확인이 학생 화면과 pending 복구의 기준이며 localStorage의 역할 표시는 라우팅 힌트일 뿐이다. 교사·학생 동시 시연은 별도 context를 사용한다. 이 구조는 로컬 합성 체험용이며 공개 게스트 인증·실제 학생 등록·생체인증 검증을 의미하지 않는다.

## 3. 샘플과 재현 가능한 준비

서버 `DemoManifest`의 버전은 `student-web-v1`, 표시 출처는 **DO:DREAM 로컬 체험용 직접 작성 · v1**이다.

| 자료 | 단원 | 퀴즈 |
|---|---|---|
| 물의 여행 | 얼음과 물 / 하늘로 올라가는 물 / 다시 땅으로 돌아오는 물 | 물이 차가워졌을 때의 모습, 액체→기체 변화 이름 |
| 생활 속 분리배출 | 먼저 비우고 헹구기 / 종이와 용기 살펴보기 / 안내를 확인하기 | 내용물을 먼저 처리하는 방법, 혼동될 때 확인할 안내 |

각 자료는 짧은 본문 3단원과 단답형 문제 2개다. 실제 학생 정보·비공개 교재·상용 교재는 사용하지 않는다. 정답은 서버 fixture와 quiz 저장소에만 있고 제출 전 학생 DTO에는 포함되지 않는다. 제출 후의 설명은 기존 채점 snapshot의 정답과 공급자 피드백을 사용한다. 이번 local 채점 피드백은 결정적 대역이며 별도의 교육용 해설 생성·평가를 추가하지 않았다.

전용 합성 교사 `demo-phase4-v1@local.dodream.invalid`와 합성 학급은 local 초기화 시 새로 만든다. 준비 API `POST /api/demo/prepare`는 이 교사 본인만 사용할 수 있다. `student_demo_prepare.py`는 생성된 로컬 비밀번호를 메모리에서 사용해 실제 로그인하고 준비 API를 호출한다. 인증 body·토큰·비밀번호는 출력하지 않는다.

최초 실제 준비 요청에서는 fixture 예약 트랜잭션이 request OSIV EntityManager에 DB 연결을 남겨 기존 색인 경계가 `503 INDEXING_TRANSACTION_BOUNDARY`로 차단했다. 이 실패 원본을 보존하며 안전 검사를 완화하지 않았다. `LocalDemoService.prepare`가 비활성 request EntityManager holder를 잠시 분리하여 예약·확정·lease 해제 트랜잭션이 각각 자신의 EntityManager와 연결을 종료하도록 하고, 성공·실패 모두 finally에서 원래 holder를 복원한다. 이미 활성화된 호출자 트랜잭션은 동일한 503으로 거부하므로 연결을 보유한 채 숨겨서 저장소 호출을 진행하지 않는다. 실제 JPA/MySQL·로컬 객체 저장소의 두 자료 준비, 공급자 실패 후 lease/holder 복원, 활성 트랜잭션 거부를 별도 회귀 검사로 둔다. 실행 결과는 14 문서를 따른다.

자료 준비는 `IndexingService.completeInitial` → `IndexingService.publish`를 거친다. MySQL 작업 원장 → dispatcher → Redis/Celery worker → 실제 Chroma 후보 검증 → 활성 포인터 전환이라는 3-B 흐름을 유지한다. SQL로 ACTIVE를 조작하지 않는다. 최초 두 자료는 PDF 초기본과 발행본을 합쳐 논리 작업 4개를 만든다. 같은 fixture 버전은 저장된 sample/file/material 식별자를 재사용하고, 준비 재실행 전후의 교재·문제·작업 수가 같아야 한다. 이후 합법적 편집으로 생긴 불변 버전 이력은 삭제하거나 최초 4개로 되돌리지 않는다. 준비 스크립트가 교사 편집 내용을 원문으로 덮어쓰지도 않는다.

자료 ID는 응답과 목록에서 얻으며 웹에 하드코딩하지 않는다. 준비 결과의 민감값 없는 plan은 `.local/phase4/results/student-demo-plan.json`에 저장된다. 시연 자료와 새 개인 기록은 검사 후에도 영속 볼륨에 보존한다.

## 4. 답변과 실제 참고 자료

질문은 현재 공유 권한과 활성 원본을 검사한 뒤 실제 Chroma 검색을 수행한다. `answer`와 함께 `session_id`, `message_id`, `document_id`, `source_revision`, `source_hash`, `sources`, `mode`를 반환한다. 각 source는 실제 답변 입력의 `chunk_position`, `content_hash`, 저장된 `material_title`, 최대 300자 `excerpt`와 같은 원본 revision/hash를 포함한다. 없는 페이지·단원 번호를 만들지 않으며 물리 컬렉션 이름·저장 경로·교사 정답은 공개하지 않는다.

local 공급자는 검색 결과 첫 청크의 앞 300자를 사용하고 그 청크 하나만 sources에 넣는다. 외부 모델 설정 경로는 실제 전달한 최대 5개 청크를 사용하지만 이번 실행에서 호출·평가하지 않는다. 청크 metadata의 자료·원본 revision/hash·position·내용 해시가 선택한 pointer와 일치해야 답변을 저장한다. 답변과 sources/mode는 같은 SQLite 트랜잭션에서 저장된다. 과거 sources가 없는 메시지는 빈 sources로 유지하며 추측해 역채우지 않는다.

공급자 대기 후 새 DB session에서 사용자·현재 공유 권한·활성 원본을 다시 확인한다. 권한 회수·삭제는 거부하고 원본이 바뀌면 `RAG_SOURCE_CHANGED` 409로 답변 확정을 막는다. 같은 원본의 candidate/spec 교체는 답변에 이미 사용한 원본을 유지하며 검색을 다시 섞지 않는다. 이미 저장된 사용자 질문은 실패 후에도 이력으로 남을 수 있다.

**참고 자료 보기**는 저장된 문자열만 믿고 열지 않는다. source 전용 GET이 현재 소유·공유·대화·원본 버전을 다시 검사한 뒤 같은 답변의 발췌를 반환한다. UI는 예상 revision/hash와도 대조한 뒤 본문 발췌 대화상자를 연다. 이는 전체 단원이나 페이지 이동을 꾸민 링크가 아닌, 같은 버전의 실제 본문 구간 조회다. 공유 회수 뒤 403/404가 오면 본문·답변·sources 표시를 비우고 우회 fallback을 사용하지 않는다.

기존 대화가 구버전이면 의미를 설명하고 **새 자료로 대화 시작**을 눌렀을 때만 session을 비우고 현재 본문·원본 revision·준비 상태를 다시 조회한 뒤 다음 요청으로 새 대화를 만든다. 과거 서버 기록은 삭제하지 않는다. UI는 중복 전송을 막고 요청 대기를 제한한다. 서버 공급자 await의 15초 제한은 동기 검색을 포함한 전체 HTTP 요청의 엄격한 15초 보장을 뜻하지 않는다. 채팅에 새 범용 멱등 시스템은 추가하지 않았으므로 응답 유실 시 자동 POST 반복 없이 **대화 기록 확인**과 사용자의 명시적 재전송으로 처리한다. 재전송하면 질문이 중복 저장될 수 있다는 한계를 표시한다.

자료·사용자 이동, 로그아웃, 요청 세대 변경 뒤의 늦은 응답은 화면에 붙이지 않는다. 본문·답변·발췌는 텍스트로 렌더링하며 `dangerouslySetInnerHTML`, 모델 생성 URL, 외부 이미지·폰트·스크립트 자동 로드를 학습 렌더러에 추가하지 않는다.

## 5. 제출 고정·복구·결과

3-A의 `Idempotency-Key`와 문제 `version` 계약을 그대로 사용한다. 논리 제출을 시작할 때 UUID key를 한 번 만들고 문제 ID·버전·학생 답안을 고정한다. 같은 제출의 연속 클릭·AT refresh·응답 유실 재확인은 같은 key와 body를 사용한다. 문제 변경 충돌을 새 key로 몰래 우회하지 않는다. 사용자가 최신 문제로 새 풀이를 선택하거나 완료 뒤 새 풀이를 시작할 때만 새로운 논리 제출을 만든다.

전송 전에 `sessionStorage`에 schema, 검증된 사용자 ID, material ID, key, 고정 answers와 반환받은 attempt ID를 보존한다. 명시적 retry가 시작되면 해당 세대·UNKNOWN 확인 값도 같은 탭에 저장한다. 정답·RT·전체 결과 이력은 저장하지 않는다. 저장소 값은 신뢰된 서버 상태가 아니므로 형식·상한·사용자·자료를 검사하고 실제 서버 권한·버전·attempt 응답으로 재확인한다.

새로고침 뒤 현재 사용자를 먼저 확인한 다음 **같은 제출 확인**을 선택한다. attempt ID가 있으면 GET, 접수 응답을 잃어 ID가 없으면 같은 key/body로 POST replay한다. 복구 과정에서 임의 새 attempt를 만들지 않는다. 상태 조회는 제한된 횟수로 관측하고 FAILED/UNKNOWN의 재실행은 명시적 retry API와 최대 3세대 제한을 따른다. UNKNOWN은 사용자의 결과 불명 확인을 요구한다.

전송 전 저장·재읽기에 실패하면 제출을 중단하고 복구 보장 불가를 안내한다. 복구 시 저장소 읽기 자체가 실패하면 잘못된 JSON과 구분하여 기존 record를 삭제하지 않고 `STORAGE_UNAVAILABLE`로 새 제출·초기화를 차단한다. 일시적인 읽기 오류를 pending 없음으로 오해해 새 key를 만드는 것을 막는다. 완료·로그아웃·계정 전환 시 pending을 정리하며 완료 후 삭제 실패도 안내한다. 탭 닫기·브라우저 전체 종료·다른 기기로의 복구는 보장하지 않는다. 성공 결과 URL은 pending 없이도 서버에서 다시 조회할 수 있다.

제출 중, READY/PROCESSING, SUCCEEDED, FAILED, UNKNOWN, 권한 회수, 버전 충돌, 재시도 한도를 구분한다. 실패·불명 상태를 0점 또는 오답으로 바꾸지 않는다. 성공은 서버의 제출 당시 문제·정답·답안·피드백 snapshot을 표시한다. legacy snapshot이 없으면 당시 기준을 알 수 없다는 사실을 유지하고 현재 정답을 섞지 않는다.

## 6. 접근성·읽어주기·검증 경계

학습 화면은 landmark·heading·실제 button/link·연결된 입력 label, 본문 건너뛰기, 보이는 focus, 상태/오류 안내를 제공한다. 단원 이동과 화면 이동에서 제목으로 focus를 옮기며 참고 자료 대화상자를 닫으면 시작 버튼으로 돌아간다. 글자 크기 조절과 좁은 화면 재배치를 제공한다. 320 CSS px 검사와 실제 브라우저 확대 검사는 별개이며 CSS 크기 변경을 실제 확대 검증으로 기록하지 않는다.

읽어주기는 사용자가 **본문 듣기**를 선택할 때만 현재 단원을 읽는다. `speechSynthesis`의 `localService=true`인 한국어 voice만 선택하고, 없으면 기능 제한을 표시한다. 원격 voice fallback·자동 음성 모델 설치·자동 재생은 하지 않는다. 시작·일시정지·재개·중지, 현재 구간 표시를 제공하고 단원/자료 이동·로그아웃·dispose 시 음성과 늦은 callback을 정리한다. 긴 본문은 최대 10,000자를 220자 구간으로 나누어 하나씩 등록하며 구간별 대기 한도를 둔다. 음성 실패와 관계없이 텍스트·질문·퀴즈는 계속 사용할 수 있다.

| 검증 분류 | 무엇을 확인하는가 | 확대 해석하지 않는 범위 |
|---|---|---|
| 합성 speech 단위검사 | local 한국어 선택, 순차 구간, pause/resume/stop, callback 정리 | 실제 소리 출력·음성 품질 |
| 실제 Chrome API | 실제 voice 목록·지원 상태·발생한 API 이벤트 | 사람이 들었다는 사실 |
| 키보드·반응형 UI | 실제 Tab/Enter 입력, label/focus/상태, 320px·데스크톱 화면 | 전체 WCAG 또는 모바일 접근성 인증 |
| 음성 청취·스크린리더 | 직접 수행한 수동 점검만 별도 기록 | headless/mock을 VoiceOver 결과로 대체하지 않음 |

최종 항목별 PASS/FAIL/NOT_RUN/BLOCKED는 14 결과를 따른다. 실제 음성 청취와 VoiceOver가 미실행이면 그대로 NOT_RUN이며 시스템 접근성 설정을 바꾸지 않는다.

## 7. 로컬 한계와 보존

AI 실행 표시는 인증된 `/rag/mode`의 실제 서버 설정과 연결한다. mode를 받지 못하면 확인 필요로 표시한다. 이번 공급자 경계는 로컬 답변·8차원 hash 임베딩·결정적 채점 대역이고, 실제 Spring/FastAPI·MySQL·Redis·Celery·Chroma·SQLite를 사용한다. 검색된 청크가 있다는 사실은 답변 정확성·교육 효과·실제 모델 검색 성능의 근거가 아니다. 오류를 성공한 대역 응답으로 몰래 바꾸지 않는다.

데이터 기준선은 이번 시작 상태에서 새로 수집하며 기존 행·컬럼·객체·활성 포인터와 Chroma 내용을 보존한다. 기존 3-B 전체 색인 명령 FAIL과 후속 16시나리오 coverage PASS, 기존 회귀 묶음 FAIL과 영속성 후속 19 PASS를 이번 성공 수로 합산하지 않는다. 과거 외부 자원 FAIL/UNVERIFIED도 유지한다. 학생 인수 실행 중 앱 소스를 바꾸면 실패 원본을 보존한 뒤 새 실행으로 시작한다.

**REAL_AI_INTEGRATION=NOT_RUN**, **PUBLIC_DEPLOYMENT_READY=false**. 모바일 전체 실행·실제 외부 AI/OCR/AWS/Firebase·공개 배포·운영 게스트 인증은 이번 범위 밖이다.
