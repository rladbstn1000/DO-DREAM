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

판정은 **PASS_WITH_DOCUMENTED_LIMITATIONS**다. 정규식·문맥·이미지 검토가 모든 비밀이나 저작권 문제의 부재를 보장하는 것은 아니다. 신규 workflow/공개 검사/문서 8개 변경분도 최종 staged diff에서 별도 공개 검토한다. 검토 범위·오탐 유형·미검증 바이너리는 ignored `source-publication-classification.json`에 보존한다. 신규 실제 비밀이 발견되면 최신본만 지워 과거 커밋과 push하는 우회를 하지 않는다.

## 공개 검토 B: 정적 산출물

배포 대상은 **`fe-web/dist-showcase/` 안의 `index.html`과 검토한 assets만**이다. 같은 lock과 `verify:showcase`를 재사용한다. 전용 envDir/publicDir/base/production·outDir/symlink·파일명·모듈 graph·CSP·합성 환경값 경계를 검사하며 소스·docs·.local·DB·로그·trace·source map은 배포하지 않는다.

의존성 `npm audit --json`은 이번에도 exit 1이며 영향 패키지 14개(high 9/moderate 3/low 2/critical 0)다. 이전 19 검토의 advisory 기록과 완전히 같고 lock 변경이 없어 기존 공개 runtime/빌드 경로 영향 분석을 재사용한다. 새 Pages 계약 검사에서 js-yaml은 체크인된 workflow만 읽으며 공개 방문자의 YAML·파일 업로드를 처리하지 않는다. 경고를 삭제하거나 force/major update하지 않는다. 실제 서버 모드 전체 의존성 안전성을 선언하지 않는다.

## 실행과 확인 상태

아직 원격 CI·Pages 배포·공개 URL 확인을 완료하지 않았다. 배포 링크는 **배포 준비 중**이며 성공 배지나 추측한 주소를 넣지 않는다.

| 상태 | 현재 판정 |
|---|---|
| SOURCE_PUBLICATION_REVIEW | PASS_WITH_DOCUMENTED_LIMITATIONS — 기준 소스·이력 및 release delta |
| REMOTE_SOURCE_SYNC | NOT_RUN |
| REMOTE_REQUIRED_CI | NOT_RUN |
| REMOTE_OPTIONAL_INTEGRATION | NOT_RUN — 정적 배포의 필수 조건이 아닌 별도 서버 통합 범위 |
| PAGES_WORKFLOW | PASS — 수동/main/최소 권한/산출물 계약 로컬 검증 |
| PAGES_DEPLOYMENT | NOT_RUN |
| PUBLIC_SITE_ACCEPTANCE | NOT_RUN |
| RELEASE_ARTIFACT_PROVENANCE | NOT_RUN |
| PORTFOLIO_LINKS | 배포 준비 중 |
| PUBLIC_DEMO_DEPLOYED | false |

로컬 최종 `verify:showcase`는 2026-09-30 15:38:41 UTC에 PASS했다. 기존 웹 회귀 115개, showcase 계약 50개, 브라우저 92개, Pages 계약 7개, CI 경계 6개를 각각 통과했다. 브라우저 정적 요청 63건, 금지 요청/API 시도/CSP 위반 0건이다. root·저장소 하위 경로의 정적 서버 검사 14개도 통과했다. 검증 전후 소스와 산출물은 같으며 공개 파일 3개/272,609 bytes, 로컬 manifest digest는 `646dfe49c131d283223381db6b71f764d307cdb8c5ecc41bad936a4f58609760`이다. 일반 서버용 빌드의 500 kB chunk 경고는 유지된다. 이 결과는 아직 원격 Linux/공개 사이트 결과가 아니다.

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

## 실패·재배포·되돌리기

검증 실패 시 deploy를 실행하지 않고 run/실패 로그를 보존한다. 원인을 최소 수정한 새 커밋으로 PR 검사→일반 merge→main 검사→수동 배포를 반복한다. 테스트 skip/삭제/continue-on-error나 main 직접 push를 쓰지 않는다. 보호 규칙이나 권한 때문에 막히면 해당 상태를 별도로 보고한다.

첫 공개에서는 이전 정상 배포가 없으므로 rollback 검증 완료라고 쓰지 않는다. 향후 문제가 생기면 검증한 수정 또는 revert 커밋을 같은 절차로 재배포하는 방식이 기본이다. 이전 검증 artifact 재사용은 해당 SHA/digest·보관 여부·환경 보호를 확인한 별도 복구 절차가 필요하다. 검증을 위해 공개 사이트를 일부러 망가뜨리지 않는다.

원시 공개 검토/CI 관측/브라우저 로그·다운로드·캐시는 ignored `.local/publication-pages/`, 기존 로컬 인수 원본은 `.local/static-showcase/`에 보존한다. 공개 문서에는 필요한 요약·검토한 캡처·실제 링크만 남긴다. source 저장소에 배포 폴더를 통째 커밋하지 않는다.

`REAL_AI_INTEGRATION=NOT_RUN`, `BACKEND_PRODUCTION_READY=false`, `BACKEND_DATA=NOT_TOUCHED`를 유지한다. 실제 청취·VoiceOver·WCAG 인증·모바일 실기기는 이번 공개 확인과 구분하며 수행하지 않으면 NOT_RUN이다.
