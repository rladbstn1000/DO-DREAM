# 19. 서버 없는 정적 showcase 구현·인수 결과

## 기준과 범위

팀 구현 기준 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e` 이후의 개인 개선이다. 작업 경로는 `/Users/yoonsu/Desktop/projects/DO-DREAM`, 전달·실제 시작 브랜치는 `codex/dodream-portfolio-hardening`, 시작 HEAD는 `81ce22fcf60cd9a25513d096b6425216e0f46534`로 일치했다. 시작 상태는 `?? docs/.DS_Store`만 있었으며 해당 파일을 읽거나 삭제하거나 stage하지 않았다. 진행 중 merge/rebase가 없는 상태에서 `codex/dodream-static-showcase`를 만들었다. 이 문서와 구현을 포함하는 로컬 커밋의 SHA는 해당 브랜치에서 `git rev-parse HEAD`로 확인한다. 원격 main으로 소스를 대체하지 않았다.

이번 변경은 `fe-web`의 별도 진입점·공개 샘플·임시 상태·화면·정적 빌드/검사, 순수 공통 표시 컴포넌트, 기존 키 없는 CI와 문서다. Docker·DB·기존 서비스·볼륨·외부 공급자·실제 `.env`·사용자 브라우저 프로필에 접근하지 않았다. 실제 인증/API/채점/색인 계약을 바꾸지 않아 서버 통합 회귀를 재실행하지 않았다. 기존 [18 리뷰](18-portfolio-code-review.md)의 방문자 카운터 strict FAIL과 원인 분리 대조 PASS를 그대로 보존한다. 새 데이터 해시 PASS를 주장하지 않는다.

## 화면과 데이터 경계

| 화면 | 구현한 동작 | 경계 |
|---|---|---|
| 시작 | 서비스 목적·학생 시작·교사 보기·샘플 안내 | 가입·비밀번호·API 설정 없음 |
| 자료함/본문 | 두 교재, 단원 이동/위치, 18/22/26px 글자, 로컬 한국어 음성 | 자체 공개 텍스트만 사용 |
| 질문/참고 | 추천 질문과 앞뒤/연속 공백을 정리한 뒤 정확히 일치하는 입력에 준비된 답변, 같은 교재의 연결 문장 대화상자 | 미지원 입력은 안내만 제공. 의미 추론·RAG·가짜 지연 없음 |
| 퀴즈/결과 | 교재당 객관식 2문제, 정답 일치당 1점, 중복 제출 한 결과, 명시적 새 풀이, 새로고침 복원 | 자유서술 채점/AI 평가/서버 저장 없음 |
| 교사 샘플 | 자료와 처리 흐름 설명, 같은 탭에서 살펴본 질문·풀이 | 실제 학생/학급/담당관계·업로드·변환·공유·동기화 아님 |
| 초기화/오류 | 소유 키만 제거, 알 수 없는 교재/단원/결과 안내, 손상 상태 복구, 저장소 실패 시 메모리 체험 | 삭제 실패 시 이전 저장 상태가 남을 수 있음을 명시 |

모든 화면에 “포트폴리오 체험용 데모입니다. 샘플 교재와 준비된 답변·채점 규칙을 사용합니다. 질문과 답안은 이 페이지에서만 처리합니다.”를 표시한다. 이 문구는 앱의 입력 전송 경계를 뜻한다. 정적 파일 HTTP 요청은 발생하며 향후 호스팅 제공자의 접속 로그가 없다는 주장이 아니다.

`src/showcase/samples.ts`는 고정 버전 `2026-09-v1`, 읽기 쉬운 `water-journey`/`recycling-day` ID를 쓴다. 기존 직접 작성 `DemoManifest.java` 원문 fixture를 소스에서 검토해 짧은 공개 교재·질문·선택지를 수작업으로 정리했다. DB dump, Chroma/object store 추출, 실제 프로필·대화·로그·숫자 식별자·자격증명을 사용하지 않았다. 이 샘플의 정답과 설명은 공개 JavaScript에 포함된다. 실제 학생 API의 정답 비노출 DTO나 제품용 채점 정책을 대체하지 않는다.

`src/showcase/store.ts`는 메모리와 `sessionStorage`의 `dodream.showcase.v1.state`만 사용한다. 전체 키 삭제·localStorage 쓰기·가짜 JWT/인증 쿠키를 만들지 않는다. 정확한 JSON 구조·버전·UTF-8 64KiB 상한·알려진 교재/단원/질문/선택지 ID·풀이 순서를 검증한다. 저장된 점수는 신뢰하지 않고 선택 ID로 다시 계산한다. 교재별 최근 10개 제출을 보관하며 자유 입력 질문 원문은 저장하지 않는다. 저장소 접근/쓰기 오류에서는 메모리 체험을 유지하고 새로고침 제한을 표시한다. 초기화는 쓰기 실패 이후에도 최초 저장소 핸들로 소유 키 삭제를 시도한다. 클라이언트 저장소는 인증·보안 경계가 아니다.

## 진입점·빌드·재사용

| 항목 | 실제 서버 연결 phase1 | 정적 showcase |
|---|---|---|
| 진입 | 기존 `index.html` → `src/main.tsx` → 실제 App/auth/session/API | `showcase/index.html` → `src/showcase/main.tsx` → 명시적 sample port/store |
| 라우터 | 기존 BrowserRouter | HashRouter |
| 출력 | `fe-web/dist/` | `fe-web/dist-showcase/index.html`과 assets |
| 데이터 | 실제 자체 서버 + 선택 공급자 adapter(기본 비활성) | 직접 작성한 공개 모듈·탭 상태 |
| 전환 | 기존 명시적 실행 구성 | URL/role/storage/env로 real 모드 전환 불가 |

같은 프로젝트·package-lock을 사용한다. 기존 설정은 선택적인 배포 환경 로딩과 개발 proxy가 있어, 작은 전용 `vite.showcase.config.ts`가 경계를 더 명확하게 만든다. `mode=showcase`, `base='./'`, `envDir=false`, `envPrefix=[]`, `publicDir=false`, source map 없음, 고정 outDir를 강제한다. `import.meta.env`에는 Vite 내장 필드만 남고 상속된 `VITE_*`나 `process.env` 전체를 직렬화하지 않는다. 실제 env 파일 없이 합성 `VITE_API_BASE`/`VITE_PROVIDER_KEY`/일반 process sentinel로 검사했다. 상속된 `NODE_ENV=development`도 공개 빌드 wrapper가 Vite 로딩 전에 production으로 고정하며 전용 config는 개발/SSR 빌드를 거부한다.

출력 경로는 절대 경로·고정 이름·조상 및 자손 symlink 부재를 검사한다. CLI의 mode/base/outDir/Rollup output 우회도 Vite가 출력 폴더를 비우기 전에 거부한다. 생성물 정리는 전용 `dist-showcase` 안에서만 허용한다. Rollup이 파일을 쓰기 전에도 모든 출력 key/fileName을 `index.html`과 허용 assets 이름으로 검사한다. 기존 public/문서/저장소 복사는 없다.

기존 학생 화면 전체를 복제하지 않았다. `src/learning/Presentation.tsx`의 Notice·PageHeading·ReaderSpeechView, 기존 `student.css`·`speech.ts`만 재사용한다. 실제 Layout은 기존 auth epoch를 주입하며 인증 wrapper와 계약을 보존한다. showcase는 자체 reset epoch를 주입한다. 원격 음성은 고르지 않고, 초기 열거 오류에도 텍스트 화면을 유지하며, 화면 이동/초기화 시 동기 정리로 늦은 이벤트를 차단한다. 교사 편집기와 Tiptap은 불러오지 않는다.

HTML meta CSP는 실제 적용되는 `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'`이다. 외부 폰트·이미지·analytics·HMR·서비스워커는 없다. meta에서 지원하지 않는 frame-ancestors나 HTTP 헤더 정책을 적용했다고 주장하지 않는다.

## 실행과 단일 인수

```bash
cd /Users/yoonsu/Desktop/projects/DO-DREAM/fe-web
# 의존성이 없는 환경에서만: npm ci --ignore-scripts --no-audit --no-fund
npm run build:showcase
npm run preview:showcase
npm run test:showcase
npm run test:showcase-browser
npm run verify:showcase
```

호스트 실제 Node `22.14.0`/npm `10.9.2`, 기존 CI Node `22.22.0`을 사용한다. 같은 lock에 `playwright-core=1.62.1` 개발 의존성만 추가했다. 브라우저는 기본 설치 Chrome의 독립 headless context이며 사용자의 프로필·탭을 열지 않는다. 별도 브라우저/전역 도구/모델 설치는 없다.

`preview:showcase`는 `127.0.0.1`의 사용 가능한 포트에만 바인딩한다. 공개 산출물 bytes만 읽어 `/`와 `/DO-DREAM/`에서 제공한다. API proxy·SPA rewrite·디렉터리 목록은 없고 소스·비밀·기타 경로는 404다. 로컬 확인용이며 공개 운영 서버가 아니다.

`verify:showcase`는 타입·상태/빌드 계약·합성 환경값 showcase 빌드·phase1 빌드·양쪽 모듈 그래프·공개 파일/URL·서버 경계·실제 브라우저를 한 실행으로 검사한다. 시작/종료 앱·검사 소스 digest와 산출물 digest를 비교한다. 원시 실행 기록과 출력은 ignored `.local/static-showcase/results/`, 빌드 결과는 ignored `fe-web/dist-showcase/`다. `.local/static-showcase/` 증거는 배포하지 않고 검토한 `fe-web/dist-showcase/` 내용만 배포 대상으로 삼는다.

## 최종 단일 인수 결과 (2026-09-30)

| 상태 | 판정 | 근거 |
|---|---|---|
| `SHOWCASE_BUILD` | **PASS** | 전용 production 정적 빌드 |
| `BACKEND_FREE_JOURNEY` | **PASS** | root/subpath 실제 학생→교사 UI 완주 |
| `BUILD_MODE_ISOLATION` | **PASS** | 실제/샘플 import graph 분리·합성 환경/auth/mode 조작 |
| `SHOWCASE_STATE_AND_RESET` | **PASS** | 복원·오류·독립 context·소유 키 초기화 |
| `SHOWCASE_BROWSER_ACCEPTANCE` | **PASS** | 고정 소스의 단일 브라우저 인수 92개 |
| `STATIC_ARTIFACT_REVIEW` | **PASS** | 3개 정적 파일·공개 경로/URL/파일명/CSP 검토 |
| `EXISTING_WEB_REGRESSION` | **PASS** | 기존 웹 115개·타입·phase1 build |
| `STATIC_DEMO_DEPLOY_READY` | **PASS** | 검토한 웹 산출물 기준. 원격 CI/계정/공개 접속 완료 아님 |

최종 실행 ID는 `2026-09-30T14-14-44-202Z`, 종료코드 0이다. 실행 증거는 `verify-showcase-2026-09-30T14-14-53-063Z.json`, 브라우저 증거는 `showcase-browser-2026-09-30T141447135Z.json`이다. 타입과 두 빌드 모두 PASS, showcase 계약 **50개(상태 42 + 빌드 경계 8)** PASS, 별도 정적 서버 경계 요청 **14개** 기대값 일치, 실제 브라우저 assertion **92개** PASS다. 기존 학생 UI 최종 보완 후 student 36개를 다시 확인했고 이전 auth25/authorization9/grading19/indexing20/hardening6과 합쳐 기존 웹 **115개 PASS**다. 과거 서버 검사를 이 수에 더하지 않는다.

브라우저는 Chrome `154.0.8037.59`다. 실제 인수 주소는 `http://127.0.0.1:49349/`와 `http://127.0.0.1:49349/DO-DREAM/`였으며 실행이 끝난 뒤 종료했다. 경계 전용 서버 주소는 `http://127.0.0.1:49334`였고 역시 종료했다. 다음 preview 실행은 새 빈 포트를 쓰므로 위 주소가 계속 열려 있다고 안내하지 않는다.

| 브라우저 관측 | 최종 값 |
|---|---:|
| 허용된 정적 document/JS/CSS 요청 | **63** |
| 허용 목록 밖 요청 시도(거절도 실패로 집계) | **0** |
| fetch/XHR/WebSocket/EventSource/beacon/service worker 호출 시도(CSP 이전 계측) | **0** |
| WebSocket 연결 시도 | **0** |
| CSP 위반 | **0** |
| 브라우저 앱 오류 | **0** |

이는 전체 네트워크 0이라는 뜻이 아니다. 위 63건은 브라우저 요청이며, Node harness가 정적 서버의 404/405를 확인한 14건은 별도다. `/api/session/me` 경계 probe도 이 정적 서버에만 보내 404를 확인했으며 실제 백엔드 서비스에 보내지 않았다. API 가짜 응답을 route interception으로 채워 넣지 않았고, 금지 요청을 abort해도 시도 수로 실패시키는 검사다.

`/`와 `/DO-DREAM/` 모두 첫 진입·교재·단원·준비 질문/참고·퀴즈·결과 새로고침·교사 확인·초기화를 UI로 완료했다. 중첩 해시 직접 접근/뒤로 가기, 다른 교재와 없는 결과, 손상/구버전/과대/알 수 없는 상태, 접근 거부·quota 뒤 초기화, 독립 context, 실제 서비스용 합성 auth key 무시, outer query와 hash query의 live/role 조작, 악성 HTML/URL 입력, 중복 제출/명시 재풀이, 키보드/320px를 검사했다.

실제 브라우저에서 로컬 한국어 voice 9개와 음성 API 존재를 관측했다. 별도 합성 엔진으로 로컬/원격만 존재/음성 열거 오류, pause/resume, 단원 이동/초기화와 늦은 end/error의 비간섭을 확인했다. 실제 음성을 재생해 듣거나 VoiceOver로 읽은 검사는 아니다.

앱·검사·설정 소스 묶음 SHA-256은 `cc10738397eb120d610a2aea36b37570428043c0f86b608f0bfa477afee7824c`이며 전후 일치했다. 최종 산출물 manifest digest는 `646dfe49c131d283223381db6b71f764d307cdb8c5ecc41bad936a4f58609760`이며 인수 중 변경이 없었다. 브라우저 자체 digest는 경로+파일 bytes를 연결하는 별도 방식이므로 manifest digest와 값이 다르며 각 방식의 전후 동일성을 확인한다.

| 공개 파일 | bytes | SHA-256 |
|---|---:|---|
| `assets/index-BnkY1AWG.css` | 10,227 | `78660cfaac5c006e58655202aeba2679f53acca171c4d726e28c94afd4c5dff9` |
| `assets/index-SNe9wLPP.js` | 261,491 | `64ecd40ebb0c1ffb0fd0217608d3858339a8bcfe11107e1badb28a582b8039d9` |
| `index.html` | 891 | `e666a84ec9ff4da9053d2086878bd442bb94fc2f4e5b43bb5c1aea61a578de0a` |

합계 **3개 / 272,609 bytes**다. `.env`·`.git`·DB·로그·증거·raw manifest·source map·개인 파일은 없다. showcase 전체 import graph 45개, phase1 1,786개를 대조했다. showcase에는 허용한 순수 UI 외 실제 auth/session/API entry가 없고, phase1에는 showcase 샘플/정답/state가 없다. 실제 emitted runtime의 패키지는 React·React DOM·React Router·scheduler다. graph의 cookie/set-cookie-parser는 Router의 미출력 부분이며 가짜 인증 초기화가 아니다.

bundle URL 문자열은 XML namespace와 React/Router 오류 안내 URL, URL parser의 정확한 `http://localhost` 기본값으로 분류했다. Router 소스의 parser fallback을 실제 API 주소로 오인하지 않되 임의 localhost port/path를 허용하지 않는다. 이 분류는 문자열 검색만이 아니라 module graph·원본 dependency 코드·실제 자동 요청 0을 함께 확인한 결과다. 기존 phase1의 500kB chunk 경고는 남아 있으며 261,491-byte showcase JS와 구분한다.

### 이전 실패와 수정 이력

최종 PASS 이전 기록은 삭제하거나 통과 항목만 합산하지 않았다. `showcase-browser-2026-09-30T140421140Z.json`의 음성 단원 이동 시점 실패, `...T140751464Z.json`의 native dialog Tab이 Chrome 도구 영역으로 나가는 실패, `...T141201400Z.json`의 분리된 focus/style 관측 사이 race를 보존했다. 음성 초기화/정리·제목 focus는 화면 반영 전에 동기 처리하고 대화상자 Tab/ShiftTab 순환을 추가했다. harness는 같은 DOM 관측에서 focus와 시각 표시를 함께 판단하도록 바꿨으며 임의 sleep이나 기대값 완화로 통과시키지 않았다.

초기 빌드 검사는 Vite env 객체의 SSR 필드 시점 오판, Router URL parser 문자열 분류 누락, React plugin에 지원되지 않는 Babel 설정 옵션, resolveConfig 단위 검사와 build API의 기본 NODE_ENV 차이를 수정했다. 출력 경계와 금지 요청 기대값은 유지했으며 관련 실패 로그를 ignored 증거에 보존했다. 첫 UI TypeScript 검사에서 ES2020에 없는 배열 `.at` 사용도 호환 인덱싱으로 수정했다.



## 의존성 경고의 도달 범위

이번 실제 `npm audit --json`은 **exit 1**, 영향 패키지 14개(high 9 / moderate 3 / low 2 / critical 0)다. 경고를 0으로 만들기 위한 force/major 갱신은 하지 않았다. 원시 결과 `npm-audit.json`과 패키지별 advisory/조건을 대조한 `dependency-review.json`은 ignored 증거에 남긴다. 이 경고들이 공개 showcase 모듈 그래프와 출력 runtime에는 포함되지 않는지 확인했다. 그것만으로 빌드 경로까지 안전하다고 판단하지 않고 다음 조건을 별도로 확인했다.

| 범위/패키지 | 현재 노출·대응 |
|---|---|
| Rollup(high) | 빌드 도구로 실행된다. [출력 경로 쓰기 취약점](https://github.com/rollup/rollup/security/advisories/GHSA-mw96-cpmx-2vgc)의 입력·출력 이름 조건에 대해 고정 entry/outDir·override 거부·쓰기 전 모든 파일명 allowlist를 적용했다. |
| PostCSS(high) | 검토한 자체 CSS만 빌드한다. 인라인 `map:false, plugins:[]`로 이전 map·주변 config 탐색을 차단한다. 외부 CSS 파일로 내보내므로 [inline style 문자열 문제](https://github.com/postcss/postcss/security/advisories/GHSA-qx2v-qp2m-jg93)의 경로가 없고, [이전 source map 읽기 문제](https://github.com/postcss/postcss/security/advisories/GHSA-fxqj-rqcc-2cmp)에 해당하는 방문자 CSS/주석을 받지 않는다. |
| Babel(low)·Browserslist(high)·baseline mapping(moderate) | 실제 production React plugin의 Babel transform이 비활성임을 구성 검사로 확인했다. babelrc/configFile을 끄며 임의 source map·custom stats·mapping query를 받지 않는다. |
| esbuild(low) | 검토한 소스의 compiler/minifier로 사용한다. 경고의 Windows 개발 서버 조건과 달리 macOS 로컬/Linux CI 구성에서 Node 정적 서버로 인수한다. Vite/esbuild 개발 서버를 공개하지 않는다. |
| brace-expansion/minimatch/picomatch(high) | 유지보수한 빌드/검사 패턴을 사용한다. 방문자의 glob·업로드 소스·아카이브를 받는 기능이 없다. |
| flatted/js-yaml(high)·ajv/@humanfs/node(moderate) | lint/config/cache 계열. 이번 검증 경로는 방문자 YAML/schema/직렬화 데이터/재귀 복사 API를 제공하지 않는다. 파일 복사·출력 경로의 symlink도 별도 거부한다. |
| nanoid(high) | 기존 docx와 빌드 도구 경로에 남는다. 공개 샘플은 고정 ID를 쓰며 방문자가 생성 길이를 지정할 경로가 없다. docx는 showcase import graph에서 제외된다. |

검토한 입력 경로와 산출물에서 공개 실행 경로에 도달하는 중요한 미해결 advisory는 식별하지 못했다. 전체 저장소·임의로 변조된 빌드 소스·미래 의존성까지 안전하다는 선언은 아니다. 남은 패키지 patch 유지보수와 실제 서버 모드의 별도 위험 검토는 후속 범위이며 경고 자체는 그대로 남는다.

## 캡처와 접근성 범위

다음 다섯 장은 최종 빌드 산출물의 실제 브라우저 화면이다. 샘플 표시를 유지하고 직접 열어 본문·배너·버튼·레이아웃을 검토했다. 토큰·DevTools·개인정보·생성 이미지·mockup이 없다. 원본 실행 증거에서 아래 작은 PNG만 문서 자산으로 복사한다.

| 화면 | 캡처 |
|---|---|
| 시작 화면 | [01-start.png](assets/showcase/01-start.png) |
| 학생 본문·준비 답변·참고 구간 | [02-student-answer-reference.png](assets/showcase/02-student-answer-reference.png) |
| 퀴즈 결과 | [03-quiz-result.png](assets/showcase/03-quiz-result.png) |
| 교사 샘플 결과 | [04-teacher-result.png](assets/showcase/04-teacher-result.png) |
| 320 CSS px 본문 | [05-narrow-reader.png](assets/showcase/05-narrow-reader.png) |

실제 Tab/Enter/Space/방향키/Escape 완주와 보이는 focus, 모달 순환/닫기/복귀, 320px overflow를 검사했다. 실제 청취 `TTS_AUDIBLE_CHECK=NOT_RUN`, VoiceOver `SCREEN_READER_MANUAL=NOT_RUN`, 실제 브라우저 확대 검사는 NOT_RUN이다. 합성 speech API 이벤트 검사를 실제 음질·낭독 정확도·접근성 인증으로 설명하지 않는다.

## 기존 모드와 다음 공개 반영

기존 웹 auth 25 / authorization 9 / grading 19 / indexing 20 / student 36 / hardening 6 = **115개**를 별도로 실행한다. showcase 검사 수와 과거 백엔드 검사 수에 합산하지 않는다. 타입과 phase1 빌드는 단일 인수에도 포함된다. 이번에는 서버 계약 변경이 없고, Docker·BE/AI·DB 전체 통합/crash suite는 재실행하지 않았다.

기존 `.github/workflows/keyless-ci.yml` web job에 기존 여섯 회귀와 `verify:showcase`를 연결했다. 기존 action SHA와 Node 고정값을 유지한다. 원격 workflow는 실행하지 않았으며 새 배포 trigger나 배포 workflow를 추가하지 않았다.

다음 별도 승인 작업에서 Pages 배포 대상은 **`fe-web/dist-showcase/`만**이다. 소스 entry가 아니라 이 폴더 루트의 `index.html`과 `assets/`를 업로드한다. 저장소 Pages의 GitHub Actions source 설정, `pages:write`/`id-token:write`, Pages environment와 검토한 actions SHA를 사용하는 `.github/workflows/showcase-pages.yml`을 후속으로 마련할 수 있다. 처음에는 명시적인 수동 실행 정책을 검토하고, 원격 CI 및 실제 `/DO-DREAM/#/...` 공개 접속·새로고침·CSP를 다시 확인해야 한다. 이번에는 해당 파일·계정 설정·도메인을 만들거나 변경하지 않았다.

정적 웹 배포 준비는 계정 설정·원격 CI·공개 접속 완료와 다르다. 실제 AI 품질·비용·백엔드 운영 보안/복구·모바일/스크린리더 검증은 별도 범위다. `REAL_AI_INTEGRATION=NOT_RUN`, `REMOTE_CI_EXECUTION=NOT_RUN`, `PUBLIC_DEMO_DEPLOYED=false`, `BACKEND_PRODUCTION_READY=false`, `BACKEND_DATA=NOT_TOUCHED`를 유지한다. push·PR·merge·공개 배포·터널·클라우드 생성은 수행하지 않는다.
