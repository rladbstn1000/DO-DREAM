# 20. 소스 공개와 GitHub Pages 배포 근거

2026-10-01(KST). 팀 구현과 이후 개인 개선을 기존 `rladbstn1000/DO-DREAM` 공개 저장소에 이력을 보존해 반영하고, 검증한 정적 showcase만 공개하는 작업이다. 실제 AI·백엔드 운영 준비·새 기능 개발은 범위에 넣지 않는다. [18 코드 리뷰](18-portfolio-code-review.md)는 실제 서버 검증, [19 정적 인수](19-static-showcase-results.md)는 이전 로컬 showcase 검증의 당시 기록이다.

## 기준과 승인 범위

- 실제 시작 브랜치 `codex/dodream-static-showcase`, HEAD `d0f156eb002ed3fd61ec1314336b49d948a5a188`가 전달값과 일치했다. 새 `codex/dodream-pages-release`에서 진행한다.
- 다시 조회·fetch한 원격 main은 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`이며 로컬 HEAD의 조상이다. main에 없는 개인 개선은 11개 커밋이고 원격만의 변경은 0개다. 진행 중 merge/rebase는 없다.
- 연결 GitHub와 로컬 gh 계정은 `rladbstn1000`이다. 연결 도구의 저장소 metadata와 실제 gh API 모두 push/admin을 보고했다. 연결 도구의 collaborator endpoint는 integration scope 403이지만 gh의 대상 저장소 조회·인증 계정 확인은 성공했다. 토큰을 출력·복사·새로 생성하지 않았다.
- 저장소는 public/default main/일반 merge commit 허용이다. 시작 시 Pages는 404/`has_pages=false`, custom domain·homepage·배포 환경·ruleset·main 보호 규칙은 없었다. 기존 보호를 약화하거나 `--admin`으로 우회하지 않는다.
- 사용자가 승인한 대상 저장소의 단일 branch push·PR·일반 merge·Actions/Pages·About homepage만 변경한다. force/mirror/all/tags push, 이력 재작성, 임의 domain/CNAME, 다른 저장소 설정 변경은 하지 않는다.
- `docs/.DS_Store`는 시작부터 미추적이며 읽기·삭제·stage에서 제외한다. 로컬 Docker·DB·Chroma·타 프로젝트와 실제 AI/OCR/AWS/Firebase는 사용하지 않는다.

## 공개 검토 A: 소스와 커밋 이력

기준 `d0f156e`의 최종 추적 **676파일**, 원격 main 이후 **11개 커밋·632개 신규 blob**, 최종본과 과거 버전의 합집합 **914blob(880 text/34 binary, 46,647,021 bytes)**을 검사했다. 최신본으로 대체된 과거 blob 244개를 포함한다. 신규 추가 후 최종 삭제된 경로는 0개다. `.gitignore`나 최신본만으로 이력이 안전하다고 판단하지 않았다. Git LFS pointer·submodule·symlink는 해당 범위에 없으며 자동 추가 전송 대상도 없다.

기존 전용 scanner가 없어 Git 객체만 읽는 다중 패턴/할당/경로/커밋 메타데이터 검사를 만들고 의심 문맥을 읽었다. 작업트리 `.env`·로컬 키·DB·raw 로그·사용자 파일은 읽지 않았다. 525개 후보(자격 관련 할당 382, 이메일 125, URL 표현식 6, PEM 표기 11, 공급자 형식 1)를 분류했다. 코드/타입 표현식·환경 변수 template·합성 테스트·기존 문서의 불완전 placeholder로 확인했으며 **실제 비밀값 또는 신규 비공개 자료 발견 0**이다. 후보의 원문은 보고하지 않는다. 추적된 frontend env blob은 원격과 동일한 공개 endpoint 설정이고 자격정보 할당은 없었다.

신규 캡처 PNG 10개와 기존 이미지 20개를 직접 열어 확인했다. 신규 PNG는 Git blob과 일치하고 text/EXIF metadata가 없으며 직접 작성 교재·합성 학생·샘플 표시만 담았다. 기존 원격과 같은 영상 3개(`fe_app/assets/splash_*.mp4`)와 Gradle wrapper JAR 1개는 전수 재생/역컴파일하지 않았다. 이 네 바이너리는 이미 검증한 원격 main에 있으며 새 공개 blob이 아니다. 기존 팀 저작자·출처·기여 기록을 유지하고 새 라이선스를 임의 부여하지 않았다.

판정은 **PASS_WITH_DOCUMENTED_LIMITATIONS**다. 정규식·문맥·이미지 검토가 모든 비밀이나 저작권 문제의 부재를 보장하는 것은 아니다. release workflow/공개 검사/문서 8개 text 파일(86,974 bytes)도 최종 staged diff에서 검토했다. 새 binary는 없고 실제 비밀·신규 개인정보는 없었다. README/결과 문서의 상대 링크 42개가 유효했다. 이후 테스트 시각 한 줄과 실패 기록, 공개 결과를 담는 문서 변경도 별도 diff로 검토한다. 검토 범위·오탐 유형·미검증 바이너리는 ignored `source-publication-classification.json`에 보존한다. 신규 실제 비밀이 발견되면 최신본만 지워 과거 커밋과 push하는 우회를 하지 않는다.

## 공개 검토 B: 정적 산출물

배포 대상은 **`fe-web/dist-showcase/` 안의 `index.html`과 검토한 assets만**이다. 같은 lock과 `verify:showcase`를 재사용한다. 전용 envDir/publicDir/base/production·outDir/symlink·파일명·모듈 graph·CSP·합성 환경값 경계를 검사하며 소스·docs·.local·DB·로그·trace·source map은 배포하지 않는다.

의존성 `npm audit --json`은 이번에도 exit 1이며 영향 패키지 14개(high 9/moderate 3/low 2/critical 0)다. 이전 19 검토의 advisory 기록과 완전히 같고 lock 변경이 없어 기존 공개 runtime/빌드 경로 영향 분석을 재사용한다. 새 Pages 계약 검사에서 js-yaml은 체크인된 workflow만 읽으며 공개 방문자의 YAML·파일 업로드를 처리하지 않는다. 경고를 삭제하거나 force/major update하지 않는다. 실제 서버 모드 전체 의존성 안전성을 선언하지 않는다.

## 실행과 확인 상태

소스는 PR #1, 초 경계 테스트 최소 수정은 PR #2로 일반 병합했다. 최초 main 실패는 보존했고 수정한 main의 5개 CI 작업이 모두 성공했다. **[공개 showcase](https://rladbstn1000.github.io/DO-DREAM/)** 배포와 공개 인수도 통과했다. README/About에 실제 확인한 URL을 사용하며 아래에서 배포된 앱 SHA와 이후 문서 변경을 구분한다.

| 상태 | 현재 판정 |
|---|---|
| SOURCE_PUBLICATION_REVIEW | PASS_WITH_DOCUMENTED_LIMITATIONS — 기준 소스·이력 및 release delta |
| REMOTE_SOURCE_SYNC | PASS — PR #1·#2 일반 병합 |
| REMOTE_REQUIRED_CI | PASS — PR #2와 수정 main의 기대 5개 job 전부 성공; 최초 실패 보존 |
| REMOTE_OPTIONAL_INTEGRATION | NOT_RUN — 정적 배포의 필수 조건이 아닌 별도 서버 통합 범위 |
| PAGES_WORKFLOW | PASS — 수동/main/최소 권한/산출물 계약 및 원격 실행 |
| PAGES_DEPLOYMENT | PASS — 실행 36741020484의 build·deploy success |
| PUBLIC_SITE_ACCEPTANCE | PASS — 독립 공개 브라우저 24개 검사 |
| RELEASE_ARTIFACT_PROVENANCE | PASS — 원격 manifest·다운로드 artifact·공개 HTTP/브라우저 bytes 일치 |
| PORTFOLIO_LINKS | PASS — 실제 데모 URL·About·README/문서 연결 검토 |
| PUBLIC_DEMO_DEPLOYED | true |

로컬 최종 `verify:showcase`는 2026-09-30 15:38:41 UTC에 PASS했다. 기존 웹 회귀 115개, showcase 계약 50개, 브라우저 92개, Pages 계약 7개, CI 경계 6개를 각각 통과했다. 브라우저 정적 요청 63건, 금지 요청/API 시도/CSP 위반 0건이다. root·저장소 하위 경로의 정적 서버 검사 14개도 통과했다. 검증 전후 소스와 산출물은 같으며 공개 파일 3개/272,609 bytes, 로컬 manifest digest는 `646dfe49c131d283223381db6b71f764d307cdb8c5ecc41bad936a4f58609760`이다. 일반 서버용 빌드의 500 kB chunk 경고는 유지된다. 이 문단은 로컬 결과이며 아래 원격 Linux/공개 사이트 결과와 구분한다.

## 원격 소스·CI 기록

- 공개 release 커밋 `4ad7b356f35573389e4ebe5ef03d3640326dbbfd`는 기준 개인 개선 11개 커밋을 그대로 잇는다. 첫 push는 `codex/dodream-pages-release` 하나였으며 태그·다른 로컬 브랜치를 보내지 않았다.
- [PR #1 CI 36738964317](https://github.com/rladbstn1000/DO-DREAM/actions/runs/36738964317): event=`pull_request`, head=`4ad7b356f35573389e4ebe5ef03d3640326dbbfd`, 실제 5개 job checkout test merge SHA=`1bf93c8e48cff3eb216cae2fe27f5bec60eb40a7`. `web`, `python (ai)`, `python (python-service)`, `backend`, `offline-tools` 모두 success. [동일 branch push CI](https://github.com/rladbstn1000/DO-DREAM/actions/runs/36738944271)도 성공했다.
- 실제 PR #1 merge SHA는 `2902335a10b32f17c856ed7deee5c3804c3382c8`이며 2026-09-30 15:46:41 UTC에 일반 merge commit으로 병합했다. PR 검사 SHA와 구분한다. 기존 required checks·review 보호는 없었지만 기대한 다섯 job과 병합 상태를 직접 확인했다. `--admin`/squash/rebase는 사용하지 않았다.
- 병합 후 자동 push run이 조회되지 않아 승인된 keyless CI를 main에서 한 번 수동 실행했다. [main CI 36739526438](https://github.com/rladbstn1000/DO-DREAM/actions/runs/36739526438), source=`2902335a10b32f17c856ed7deee5c3804c3382c8`, event=`workflow_dispatch`는 **FAIL**이다. 4개 job은 성공했고 `python (ai)`의 `test_five_second_skew_and_maximum_access_lifetime` 한 건에서 기대 401/실제 200을 기록했다. 실패 로그·실행을 보존했으며 이 SHA를 배포하지 않았다.

원인은 만료값 `exp=now+901`만 테스트 시작 시각으로 고정하고 helper의 `iat/nbf`는 새 시각으로 생성한 것이었다. 다음 초로 넘어가면 실제 `exp-iat`가 900초가 되어 정상 토큰을 거부하라는 잘못된 기대를 만든다. 인증 구현의 900초 최대 수명 검사는 유지하고 테스트의 발급·시작·만료 시각만 같은 기준으로 묶는다. 실패 검사를 삭제·skip하거나 허용 수명을 늘리지 않는다. 새 공개 변경은 테스트 한 줄과 이 실패 기록뿐이며 실제 자격정보·비공개 데이터가 없다. 로컬 Python에는 FastAPI/jose/SQLAlchemy 의존성이 없어 실제 HTTP targeted 실행은 BLOCKED로 구분했다. 새 원격 CI에서는 기존 전체 테스트가 통과했다.

- [PR #2](https://github.com/rladbstn1000/DO-DREAM/pull/2): 수정 head=`7b40c086e971b67e9bb775ce10d58de7ab2f766d`, 실제 5개 job checkout test merge=`3fa307fe933b555a1c6060982394cafdc8c01f4f`, [CI 36740266759](https://github.com/rladbstn1000/DO-DREAM/actions/runs/36740266759) 전부 success. 실제 일반 merge는 `c3d9617768392903085a246a1520229b22eeb674`다.
- [수정 main CI 36740621696](https://github.com/rladbstn1000/DO-DREAM/actions/runs/36740621696): event=`push`, source=`c3d9617768392903085a246a1520229b22eeb674`, 기대한 `web`·두 `python`·`backend`·`offline-tools`가 모두 success이며 생략된 job은 없다. 바로 이 SHA를 배포 후보로 선택하고 dispatch 직전 main과 다시 대조했다.
- 추가 로컬 재현은 실제 fixture 함수/호출 AST/수명 비교식을 사용해 시각을 0·1·2·5·30초 진행시켰다. 기존 수명 901·900·899·896·871초가 수정 후 모두 901초로 유지됐고 900초 허용 경계도 유지됐다. 이는 실제 HTTP 검사의 대체가 아니며 HTTP/서명/auth 전체 검증은 위 원격 AI 183개 성공으로 확인했다.

PR #1의 실제 범위는 웹 단위·계약 172개(기존115+Pages7+showcase50), 브라우저 92개, AI 183개, python-service 24개, 오프라인 CI6/평가26/local101개다. backend는 `bootJar`, `testClasses`, 선택된 인증·권한·채점·색인·hardening/file 검사이며 실제 DB crash suite 전체를 실행한 것으로 쓰지 않는다. 로그의 Gradle 6 tasks를 테스트 6개로 해석하지 않는다. Actions가 기존 Node20 기반 checkout/setup action을 Node24로 실행한다는 경고, 일반 phase1 build chunk 경고와 JS module type 경고를 보존한다. 앱 검증 Node 버전은 22.22.0이다.

## 실제 Pages 배포·공개 인수

[Pages 실행 36741020484](https://github.com/rladbstn1000/DO-DREAM/actions/runs/36741020484)는 `workflow_dispatch`/main/attempt 1, source **`c3d9617768392903085a246a1520229b22eeb674`**로 build·deploy 모두 success다. 기존 사이트·환경이 없음을 재확인한 뒤 source=`workflow`로 설정하고 `cname=null`·HTTPS 강제 상태를 확인했으며 `github-pages`에는 정확한 main branch 규칙 하나만 둔다. 기존 저장소/브랜치 보호 규칙은 변경하지 않았다. 공개 사이트를 추측한 주소로 표시하지 않고 deployment `6764043313`의 성공 상태(2026-09-30 16:01:52 UTC)와 Pages API가 반환한 `https://rladbstn1000.github.io/DO-DREAM/`를 대조했다.

원격 도구는 Ubuntu24.04 GitHub-hosted runner, Node22.22.0/npm10.9.4/Playwright1.62.1, `/opt/google/chrome/chrome`의 Google Chrome153.0.8010.52였다. 기존 웹115+Pages7+showcase50, typecheck·두 build·artifact graph 검사·브라우저92개가 성공했고 정적 요청63/금지 요청0이다. 검증 후 재빌드 없이 같은 파일을 업로드했다.

| 같은 실행의 artifact | ID / 보관 | 근거 |
|---|---|---|
| [github-pages](https://github.com/rladbstn1000/DO-DREAM/actions/runs/36741020484/artifacts/11109444549) | 11109444549 / 1일 | 공개 디렉토리 3파일만 든 tar; 배포 입력 |
| [showcase-provenance](https://github.com/rladbstn1000/DO-DREAM/actions/runs/36741020484/artifacts/11109154763) | 11109154763 / 7일 | 선택된 커밋·도구·검증 상태·파일별 해시를 담는 manifest 1개 |

다운로드한 tar의 경로·파일 종류·크기·해시를 확인하고 승인된 3파일만 새 ignored 폴더에 추출했다. manifest source SHA/run ID가 배포와 같고 file count=3, total=272,609 bytes, **manifest digest=`646dfe49c131d283223381db6b71f764d307cdb8c5ecc41bad936a4f58609760`**다. Mac과 Linux 결과가 이번에 실제로 같았지만 과거 Mac 산출물로 대신 판정하지 않았다. Actions 압축 artifact의 digest와 아래 개별 공개 파일 digest는 서로 다른 대상이다.

| 공개 파일 | bytes | SHA-256 |
|---|---:|---|
| `index.html` | 891 | `e666a84ec9ff4da9053d2086878bd442bb94fc2f4e5b43bb5c1aea61a578de0a` |
| `assets/index-BnkY1AWG.css` | 10,227 | `78660cfaac5c006e58655202aeba2679f53acca171c4d726e28c94afd4c5dff9` |
| `assets/index-SNe9wLPP.js` | 261,491 | `64ecd40ebb0c1ffb0fd0217608d3858339a8bcfe11107e1badb28a582b8039d9` |

공개 인수는 **2026-09-30 16:02:45.692–16:02:48.689 UTC**(KST 10월1일 01:02)에 [별도 공개 harness](../../fe-web/tests/showcase-public-browser.mjs)로 실행했다. 사용자 프로필·로그인 세션 없이 새 Chrome154.0.8037.59 context 두 개, macOS/Node22.14.0에서 **24개 PASS**다. 공개 HTML/JS/CSS 3개를 HTTPS로 직접 내려받아 content type·bytes·SHA-256을 원격 manifest와 비교했고, 브라우저 정적 응답 12건도 같은 파일로 확인했다. 첫 확인에서 일치해 CDN 재시도는 없었다.

- 학생 시작 → 교재 → 단원 → 추천 질문 → 준비된 답변과 정확한 참고 문장 → 퀴즈 → 결과 → 교사 샘플 성공.
- 해시 경로 직접 접근·새로고침·뒤로 가기·같은 탭 풀이 복구·독립 context 분리·초기화 성공.
- 320 CSS px의 본문/질문 조작부가 잘리지 않았고, 키보드 이동·보이는 초점·참고 창 Escape/초점 복귀 성공. 결과·좁은 화면 캡처도 직접 열어 확인했다.
- console/page error 0, CSP 위반 0, 관측한 금지 요청·API·WebSocket 시도 0. provenance HTTP 3건과 브라우저 정적 요청 12건을 따로 센다. 브라우저에서 관측할 수 없는 모든 인터넷 통신이 0이라고 주장하지 않는다.

이 공개24개와 기존 로컬/원격 loopback92개를 더해 하나의 인수 개수로 보고하지 않는다. 정적 데모의 샘플 정답은 공개 JS에 포함되며 실제 로그인·서버 데이터 보호 성과가 아니다. 실제 음성 청취·VoiceOver·모바일 실기기는 **NOT_RUN**이다. 기존 [화면 캡처와 로컬 한계](19-static-showcase-results.md)는 당시 기록으로 보존한다.

## 공개 링크와 후속 문서

About homepage는 위 실제 URL로 갱신했다. README의 첫 링크와 짧은 학생/교사 사용 순서, roadmap·runbook·walkthrough는 최신 배포 근거로 연결하며 이전 단계 기록은 보존한다. 배포 이후 문서만 바꾸는 후속 PR의 commit은 **배포 SHA가 아니다**. 후속 PR/merge/최종 main CI는 해당 PR과 Actions 및 최종 작업 보고에서 확인하며, 이 문서가 자기 commit SHA를 담도록 amend하지 않는다. 문서 변경만으로 Pages를 다시 배포하지 않는다.

## 재현 명령과 배포 계약

저장소를 받은 위치에서 실행한다. Node 22 계열과 기존 Chrome이 필요하다.

```bash
cd fe-web
npm ci --ignore-scripts --no-audit --no-fund
npm run build:showcase
npm run preview:showcase
npm run verify:showcase
```

기존 웹 회귀는 `npm run test:auth`, `test:authorization`, `test:grading`, `test:indexing`, `test:student`, `test:hardening`이다. 핵심 구현·회귀는 [인증](../../be/src/main/java/A704/DODREAM/auth/), [객체 정책](../../be/src/main/java/A704/DODREAM/authorization/AuthorizationPolicy.java), [채점](../../be/src/main/java/A704/DODREAM/quiz/grading/), [색인](../../be/src/main/java/A704/DODREAM/indexing/), [인증 실패/쿠키 검사](../../be/src/test/java/A704/DODREAM/auth/AuthFailureAndCookieTests.java), [채점 경쟁 검사](../../be/src/test/java/A704/DODREAM/quiz/grading/GradingAcceptanceRaceTests.java), [색인 경계 검사](../../be/src/test/java/A704/DODREAM/indexing/IndexingBoundaryTests.java), [showcase 상태 검사](../../fe-web/tests/showcase-state.test.ts), [브라우저 인수](../../fe-web/tests/showcase-browser.mjs)로 연결한다. 실제 서버 로컬 실행은 별도로 [runbook](02-local-runbook.md), 학생/교사 시연은 [walkthrough](15-demo-walkthrough.md)를 따른다. 정적 데모에는 실제 인증/서버 저장/AI 호출이 없고 공개 JS에 예시 정답이 포함된다.

Pages workflow는 수동 `workflow_dispatch`만 허용하고 해당 저장소 main에서만 실행한다. PR 검증과 일반 merge 이후 main의 필수 CI를 다시 확인하고 수동 실행한다. build/verify 성공 후 그 산출물을 그대로 업로드하며 별도 deploy job은 성공한 build에 의존한다. 기본 읽기 권한, deploy job만 pages/id-token 쓰기, github-pages 환경의 main 제한을 사용한다. 다른 branch나 PR/fork에서 배포하지 않고 push 자동 배포를 추가하지 않는다.

원격 Linux에서 새로 검증한 artifact manifest/digest를 공개 HTTP 파일 bytes와 대조한다. 과거 Mac digest와 같다고 가정하지 않는다. 배포 source SHA, 이후 문서 PR SHA, PR 검사 merge SHA는 따로 기록한다.

## 공식 action 고정과 배포 권한

[GitHub 공식 Pages workflow 안내](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)와 각 공식 저장소의 release/tag commit 및 action.yml을 대조했다. 아래 SHA는 추측한 tag가 아니라 실제 조회한 전체 commit이다. 기존 checkout v4.3.1과 setup-node v4.4.0의 검토된 SHA도 유지한다. Pages action 자체는 Node24 런타임을 쓰며 앱 빌드·검사는 Node22.22.0이다.

| action | 검증한 버전 | 고정 SHA·명세 |
|---|---|---|
| actions/configure-pages | v6.0.0 | [`45bfe0192ca1faeb007ade9deae92b16b8254a0d`](https://github.com/actions/configure-pages/blob/45bfe0192ca1faeb007ade9deae92b16b8254a0d/action.yml) |
| actions/upload-pages-artifact | v5.0.0 | [`fc324d3547104276b827a68afc52ff2a11cc49c9`](https://github.com/actions/upload-pages-artifact/blob/fc324d3547104276b827a68afc52ff2a11cc49c9/action.yml) |
| actions/deploy-pages | v5.0.1 | [`368f82528645a54fb793d4d04e342629a3f51346`](https://github.com/actions/deploy-pages/blob/368f82528645a54fb793d4d04e342629a3f51346/action.yml) |
| actions/upload-artifact | v7.0.1 | [`043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`](https://github.com/actions/upload-artifact/blob/043fb46d1a93c77aae656e7c1c64a875d1fc6a0a/action.yml) |

`configure-pages`는 enablement=false와 pages:read로 이미 설정한 metadata만 읽는다. `upload-pages-artifact`는 `fe-web/dist-showcase`만 1일 보관하며, 별도 `showcase-provenance` artifact는 공개 경로·파일 크기·SHA-256·도구/커밋 정보만 든 `release-manifest.json` 한 개를 7일 보관한다. 원시 네트워크·질문·로그·스크린샷을 artifact로 올리지 않는다. 기존 키 없는 CI의 artifact 금지는 유지하며 Pages의 이 두 경로만 계약 검사로 허용한다.

검토한 main SHA를 `expected_sha` 입력으로 전달한다. ref가 main이어도 dispatch 시점의 commit이 입력과 다르면 첫 단계에서 실패한다. 선택 SHA가 필수 CI를 통과했는지는 배포 직전 실제 run 목록과 함께 확인한다. 사용자 Mac은 runner로 등록하지 않으며 Ubuntu24.04 표준 GitHub-hosted runner의 Chrome 경로/버전을 실제 job에서 확인한다.

수동 재배포는 먼저 대상 main SHA의 다섯 keyless job 성공을 확인하고 아래처럼 **실제로 확인한 40자리 SHA**를 전달한다.

```bash
gh workflow run showcase-pages.yml --repo rladbstn1000/DO-DREAM --ref main -f expected_sha=VERIFIED_MAIN_SHA
```

해당 실행의 두 artifact를 내려받아 안전하게 추출한 후 공개 인수는 다음 형태로 실행한다. 이 작업의 원시 입력과 결과는 ignored 위치에만 두며, artifact는 보관 기간 이후 만료되므로 위 파일 해시·source SHA·run 링크도 함께 남긴다.

```bash
node fe-web/tests/showcase-public-browser.mjs --url https://rladbstn1000.github.io/DO-DREAM/ --manifest .local/publication-pages/downloads/RUN/showcase-provenance/release-manifest.json --artifact-dir .local/publication-pages/downloads/RUN/verified-pages
```

## 실패·재배포·되돌리기

검증 실패 시 deploy를 실행하지 않고 run/실패 로그를 보존한다. 원인을 최소 수정한 새 커밋으로 PR 검사→일반 merge→main 검사→수동 배포를 반복한다. 테스트 skip/삭제/continue-on-error나 main 직접 push를 쓰지 않는다. 보호 규칙이나 권한 때문에 막히면 해당 상태를 별도로 보고한다.

첫 공개에서는 이전 정상 배포가 없으므로 rollback 검증 완료라고 쓰지 않는다. 향후 문제가 생기면 검증한 수정 또는 revert 커밋을 같은 절차로 재배포하는 방식이 기본이다. 이전 검증 artifact 재사용은 해당 SHA/digest·보관 여부·환경 보호를 확인한 별도 복구 절차가 필요하다. 검증을 위해 공개 사이트를 일부러 망가뜨리지 않는다.

원시 공개 검토/CI 관측/브라우저 로그·다운로드·캐시는 ignored `.local/publication-pages/`, 기존 로컬 인수 원본은 `.local/static-showcase/`에 보존한다. 공개 문서에는 필요한 요약·검토한 캡처·실제 링크만 남긴다. source 저장소에 배포 폴더를 통째 커밋하지 않는다.

`REAL_AI_INTEGRATION=NOT_RUN`, `BACKEND_PRODUCTION_READY=false`, `BACKEND_DATA=NOT_TOUCHED`를 유지한다. 실제 청취·VoiceOver·WCAG 인증·모바일 실기기는 이번 공개 확인과 구분하며 수행하지 않으면 NOT_RUN이다.

## 최신 원본 UI 공개 반영 (2026-10-01)

사용자가 승인한 `a187bf09b017984feea48153d79e02b81a9e23a5`의 교사 원본 UI·학생 앱 및 줄바꿈 보완을 [PR #4](https://github.com/rladbstn1000/DO-DREAM/pull/4)로 병합했다. 실제 배포 source는 `1aafe5a32a4a66e55629255277355aeb9f06f551`, [Pages 실행 36800980482](https://github.com/rladbstn1000/DO-DREAM/actions/runs/36800980482)는 build/deploy 성공이다. 기존 [공개 URL](https://rladbstn1000.github.io/DO-DREAM/)을 유지한다.

현재 원격 artifact는 13파일/6,720,716 bytes이며 공개 파일 bytes/hash 대조와 새 UI 공개 인수 108개를 통과했다. 위 최초 공개 기록의 3파일·이전 해시·검사 수는 당시 이력으로 보존한다. 승인·누적 공개 검토·PR/main CI·현재 manifest 전체·최종 공개 캡처와 한계는 [21번의 원본 UI 공개 배포와 인수](21-original-ui-showcase-results.md#원본-ui-공개-배포와-인수)에 기록했다. 후속 문서/검사 PR의 main SHA와 실제 앱 배포 SHA는 구분한다. **USER_VISUAL_APPROVAL=APPROVED**, **UPDATED_PUBLIC_DEPLOYMENT=true**이며 실제 AI/백엔드 운영 준비 상태는 변경하지 않았다.
