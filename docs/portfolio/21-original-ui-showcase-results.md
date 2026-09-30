# 21. 원본 UI 기반 정적 체험 이식

2026-10-01 KST. 이 작업은 팀 프런트엔드의 디자인과 화면 구조를 복원해 정적 샘플에 연결한 **개인 개선**이다. 로고·배경·일러스트·웹 레이아웃·앱 화면과 스타일의 원래 팀 기여를 개인의 새 디자인으로 주장하지 않는다. [19단계](19-static-showcase-results.md)와 [20단계](20-publication-and-pages-results.md)는 당시 구현·배포 기록으로 그대로 보존한다.

## 기준과 변경 범위

- 팀 원본 읽기 전용 기준: `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`.
- 시작 HEAD 및 확인한 origin/main: `f9042b57c326b2aa5aad6f94b7f3345f9c1378c9`. 원격 main을 읽기 전용 fetch로 확인했으며 차이는 없었다.
- 작업 브랜치: `codex/dodream-original-ui-showcase`. 커밋은 이 문서와 검증한 변경만 포함한 로컬 커밋이다. 최종 SHA는 해당 커밋의 이력과 작업 완료 보고에 기록한다.
- 기존 공개 앱 기준: `c3d9617768392903085a246a1520229b22eeb674`. **이번 UI를 공개 배포하지 않았다.** push·PR·merge·원격 CI·Pages 실행은 없다.
- 시작 시 유일한 사용자 미추적 파일 `docs/.DS_Store`를 읽거나 삭제하거나 stage하지 않았다. 실제 서버/앱 인증·권한·채점·색인 구현, Docker·DB·기존 환경 파일을 변경하거나 실행하지 않았다.

## 화면 대응과 원본 근거

원본 `img/DODREAM_main_page.png`, `img/DODREAM_app_library.jpg`, `img/DODREAM_app_player.jpg`를 실제로 열어 확인했다. 아래 원본 파일은 모두 팀 기준 커밋을 읽어 확인했다. 앱의 현재 QuizList/QuizScreen에는 이후 제출 안정화 개선이 있지만 표현 구조는 원본을 기준으로 이식했고 개선 코드를 되돌리지 않았다.

| 원본 화면·파일 | showcase 구현 | 재사용·이식한 표현 | 샘플·플랫폼 차이 |
|---|---|---|---|
| `fe-web/src/pages/Join.tsx`, `Join.css` | `teacher/Teacher.tsx`의 TeacherJoin, `teacher/Join.css` | container/row/col/form 구조, 남색 곡면, 배경과 signin/signup 삽화, 잘난체 로고 | 같은 폼 위치에 교사/학생 체험 링크. 개인정보 불필요. 시작은 sign-in 상태이며 원본 기본 sign-up과 전환 상태가 다름 |
| `ClassroomList.tsx/.css` | TeacherList, `teacher/ClassroomList.css` | 70px 헤더, 280px 사이드바, 교사·메모 이미지, 4개 반 카드, 가로 자료 행·라벨·작업 아이콘 | 합성 학급 4개/공개 자료 2개. 검색·라벨·공유 경로는 로컬 상태 |
| `Classroom.tsx/.css` | TeacherClassroom, `teacher/Classroom.css` | 자료/학생 두 열, 학생 카드, 원본 빈 슬롯 배치, 정렬·필터·선택 | 합성 학생만 표시. 실제 학급 저장 없음 |
| `EditorPage.tsx`, `AdvancedEditor.tsx/.css` | `teacher/TeacherEditor.tsx`, 원본 범위 CSS | 60px 헤더, 280px 챕터 패널, 원래 서식/분할/병합/퀴즈/발행 도구 위치, 기존 Tiptap | 본문·제목·챕터를 탭에 저장. 서식은 편집 중에만 유지. 외부 생성은 명시적 예시/설명 |
| `StudentRoom.tsx/.css`, `ChatHistory.tsx/.css` | TeacherStudent, TeacherHistory, 대응 CSS | 사이드바 통계·성적 카드·질문 목록·대화 말풍선 | 같은 탭의 실제 체험 기록. 이전 선택형 결과와 새 서술형 결과 구분 |
| `component/MaterialSendModal2step.tsx`, `MaterialSendModal.css` | `teacher/MaterialSendModal.tsx/.css` | 원래 반→학생 2단계 선택·전송 모달 | 탭의 샘플 발행 표시만 변경. 서버 전송 성공으로 표현하지 않음 |
| `fe_app/src/screens/library/LibraryScreen.tsx` | `student/StudentExperience.tsx` Library | 24px 좌우 여백, 20px 카드 간격, 3px 남색 테두리, 16px 라운드, 큰 제목·이어듣기 버튼 | 네이티브 View/Touchable을 DOM으로 이식. 합성 이름·공개 교재·현재 챕터 위치 |
| `player/PlaybackChoiceScreen.tsx`, `PlayerScreen.tsx` | Playback, Player | 챕터 선택→재생 방식→학습 순서, 큰 본문, 이전/재생/다음과 노란 질문 버튼 | 392×780 내부 화면, 로컬 음성만 선택 사용. 빈 챕터는 본문 없음 안내와 이동 버튼 |
| `player/QuestionScreen.tsx`, `QuestionListScreen.tsx` | Question, QuestionList | 원래 질문 입력/말풍선/하단 확인·질문 목록·삭제 | 말하기는 예시 선택. 준비된 질문만 지정 답변·참고 구간 표시 |
| `quiz/QuizListScreen.tsx`, `QuizScreen.tsx`, `QuizResultScreen.tsx` | QuizList, Quiz, Result | 목록→한 문항씩 서술형 입력→결과, 점수 상자·오답·접기·다시 풀기 | 미리 정한 단답/허용 문구만 비교하는 예시 판정. 의미 이해·AI 채점 아님 |
| `settings/SettingsScreen.tsx`, `library/BookmarkListScreen.tsx` | Settings, Bookmarks | 원래 설정 행·+/− 조절·고대비·글자 크기·북마크 목록 | 속도/높낮이 0.5–2.0, 볼륨 0–1을 0.1씩, 글자 100/120/150%. 기기 알림·하드웨어 기능 없음 |

구현 경로의 접두사는 [`fe-web/src/showcase/`](../../fe-web/src/showcase/)다. 학생은 `ThemeContext`, `commonStyles`, `constants/colors.ts`, `dimensions.ts`, Back/Settings/Voice/Bookmark/PlayerHeader/Choice/SectionRenderer 컴포넌트의 실제 사용 규칙을 추출했다. 전체 네이티브 진입점·Expo·Firebase·auth store·기기 bridge를 가져오거나 설치하지 않았다. 기존 `fe-web/src/student`의 새로운 웹 디자인은 사용하지 않으며, 검토된 순수 `speech.ts`만 재사용한다.

## 프레임과 접근성

같은 문서 안의 `.original-teacher`와 `.original-student`로 스타일을 격리했다. 교사용 원본의 전역 선택자는 namespace 안으로 옮기고 fixed header/sidebar는 바깥 40px 도구 모음 높이를 반영했다. 정상 상태에 큰 데모 배너는 없으며 직접 주소로 들어가도 작은 `샘플 체험` 표시와 안내를 볼 수 있다. 저장소 오류 때만 안내 행을 추가한다.

PC는 폭 414px 외곽 프레임과 **392×780 CSS px 내부 화면**을 사용한다. 화면은 실제 버튼·텍스트 입력·내부 스크롤로 작동한다. 짧은 PC에서는 외부 페이지 스크롤을 허용하고 전체 transform 축소를 쓰지 않는다. 모바일에서는 장식 테두리와 바깥 여백을 제거하며, 380px 미만에서는 헤더 여백 24→12px, 버튼 폭 106→88px로 줄여 원래 메뉴 순서를 유지한다. 앱에 없는 하단 탭바를 추가하지 않았다.

학생 모달은 phone viewport의 absolute overlay로 표시하고 body portal을 쓰지 않는다. 내부 페이지 inert·Tab 순환·Escape·닫힌 후 초점 복귀를 확인했다. 원래 네이티브 SafeArea/OS 상태 표시줄은 가짜로 그리지 않았다. 실제 VoiceOver·모바일 실기기·청취 검증과 WCAG 인증은 **NOT_RUN**이다.

## 공유 상태와 실제 가능한 체험

기존 공개 샘플 2개와 `dodream.showcase.v1.state` 저장소를 유지했다. `originalStore.ts`의 별도 소유 키 `dodream.showcase.original-ui.v1`에 편집 본문/챕터/현재 위치/북마크/설정/서술 답안만 저장한다. sessionStorage 실패는 메모리 모드와 재접속 한계를 알린다. 초기화는 두 소유 키만 지우고 다른 인증·사용자 키를 보존한다.

- 교사 편집: 본문·제목·챕터 추가/삭제/분할/병합/순서·라벨·임시 저장·발행 표시. 추가된 챕터는 학생 앱에 나타나며 삭제한 챕터의 위치/북마크를 안전하게 정리한다. 편집 서식은 열린 편집기 안의 챕터 전환에만 유지되고 다시 열면 일반 텍스트가 된다는 안내가 있다.
- 학생 학습: 서재→재생 방식→본문 이동→질문/참고 구간→서술형 퀴즈→결과→다시 풀기. 질문과 결과는 같은 탭의 교사 샘플 학생 화면에서 확인한다.
- 답안 판정: 문항별 공개된 허용 답안을 공백 정리 후 정확히 비교한다. 원본 샘플의 규칙이며 교사 본문 수정으로 새로운 질문·정답을 생성하지 않는다. 중복 제출은 같은 불변 결과, 명시적 재도전은 새 회차, 최근 10회만 보관한다. 저장된 점수를 신뢰하지 않고 답안에서 재계산한다.
- 말하기 버튼은 원래 위치/형태를 유지하지만 마이크를 요청하지 않고 예시 질문/답안/명령을 선택한다. 브라우저에 설치된 로컬 한국어 TTS가 없거나 조회에 실패하면 제한을 안내한다. 음성 없이 모든 주요 흐름을 완료할 수 있다.
- 이전 `/learn`·본문·퀴즈 주소는 대응 앱 경로로 이동한다. 이전 선택형 결과 주소는 해당 기록과 변경 안내를 표시하며 새 서술형 점수로 바꾸어 표시하지 않는다.

실제 로그인, 회원가입, 파일 업로드, OCR, AI 생성·검색·채점, 서버 저장·공유, 다른 탭/기기 동기화, 마이크, 생체인증, 네이티브 알림·볼륨키는 제공하지 않는다.

## 자산·글꼴·공개 런타임

기존 원본 이미지 8개를 그대로 사용했다: `join/background.jpg`, `signin.png`, `signup.png`, `classList/teacher.png`, `memo.png`, `school.png`, `classroom/male.png`, `female.png`. 실제로 열고 팀 기준과 바이트가 같은 것을 확인했다. 새 로고·삽화·아이콘을 생성하지 않았다. Lucide는 설치된 기존 패키지를 사용한다.

원본 CSS의 외부 Jalnan URL을 그대로 호출하지 않고, [공식 글꼴 안내](https://www.goodchoice.kr/font/mobile), [공식 배포 CSS](https://static.goodchoice.kr/fonts/jalnan/font.css), [이용 조건 전문](https://image.goodchoice.kr/images/jalnan_font/jalnan-font-202004ver.pdf)을 확인했다. 공식 `yg-jalnan.woff` 537,996 bytes를 변환 없이 저장했고 SHA-256은 `606c8ff7146886d42bacecdf1df92c4088ab18e2b3f4de77764b02e136510140`이다. 전문 저작권·이용 조건 TXT를 번들에 포함하고 안내에서 연결한다. 개인/상업 이용과 조건부 번들 재배포 허용, 글꼴 자체 판매·수정 재배포 금지 조건을 보존했다. 원본 CDN 파일과 공식 배포본의 바이트 동일성을 주장하지 않는다. 앱은 원래 시스템 글꼴 기반이므로 OS별 자형과 줄바꿈 차이가 남는다.

패키지 설치·업데이트·lock 변경은 없다. 기존 Tiptap React/StarterKit와 Lucide를 필요한 표현에 한정해 가져온다. 편집기는 JSON text node로 초기화하고 붙여넣기는 일반 텍스트만 허용하며 외부 drop·링크 기능을 차단했다. `injectCSS:false`와 class CSS로 기존 정책 **script-src 'self'; style-src 'self'; connect-src 'none'**를 유지했다. unsafe-inline/unsafe-eval을 추가하지 않았다.

`publicDir:false`, 환경 파일 미로딩, 독립 entry, 정적 출력 고정, symlink/경로 탈출 차단은 유지한다. 원본 자산/폰트/라이선스는 고정 SHA-256으로 승인하며 미검토 이미지·문서·폰트는 빌드/manifest/서버 단계에서 거부한다. runtime import 허용 목록은 관측한 44개 패키지로 제한했고 실제 번들에 남는 패키지는 40개다. 실제 서비스 entry에 showcase 데이터가 섞이지 않는지 반대 방향 그래프도 검사한다.

최신 `npm audit --omit=dev --json`은 exit 1, production 영향 패키지 `docx/node_modules/nanoid` high 1개다. GHSA-28wg-ghj8-5hjv/GHSA-xwg4-73v4-xw9w는 20단계 full audit 기록의 production 부분과 같으며 공개 showcase의 import/emitted 집합에는 docx/nanoid가 없다. 과거 full audit의 14개와 이번 production 1개는 범위가 다르며 취약점 해결로 보고하지 않는다. 기존 전체 서비스/개발 의존성의 안전을 선언하지 않는다. 추가된 편집기와 원본 이미지로 공개 번들 크기가 커졌으며 500kB JS chunk 경고는 숨기지 않고 남겼다.

## 원본/복원 시각 비교

아래 10개 비교 PNG를 실제로 열어 검토했다. 왼쪽의 실제 원본 이미지가 있는 것은 **자료 목록·앱 서재·앱 플레이어 3개**다. 나머지 7개는 왼쪽에 원본 소스/StyleSheet 규칙을 명시하고 오른쪽에 실제 정적 복원 화면을 둔 **소스 기준 검토**이며 원본 실행 캡처로 부르지 않는다. 새 구현의 첫 캡처를 자동 baseline으로 사용하지 않았다.

| 비교 | 기준과 남은 차이 |
|---|---|
| [교사 시작](assets/original-ui/01-teacher-start.png) | 원본 Join 구조/자산. 필수 자격정보 대신 체험 진입 |
| [교사 자료 목록](assets/original-ui/02-teacher-material-list.png) | 실제 팀 PNG 1911×1079와 복원 1600×920. 자료/학생·배율·바깥 도구 모음 차이 |
| [교사 편집기](assets/original-ui/03-teacher-editor.png) | 원본 소스/도구 모음. 서버 관련 동작은 탭 상태·명시적 예시 |
| [교사 학생 결과](assets/original-ui/04-teacher-student-result.png) | 원본 소스. 합성 학생과 실제 로컬 체험 점수 |
| [교사 질문 이력](assets/original-ui/05-teacher-question-history.png) | 원본 소스. 준비된 질문·답변 |
| [앱 서재](assets/original-ui/06-app-library.png) | 실제 팀 JPG와 내부 392px 화면. 이름·교재 수/제목·현재 위치 표시 차이 |
| [앱 플레이어](assets/original-ui/07-app-player.png) | 실제 팀 JPG. 공개 본문은 짧으며 OS 상태 표시줄·시스템 글꼴 차이 |
| [앱 질문](assets/original-ui/08-app-question.png) | QuestionScreen/StyleSheet. 음성 대신 예시 선택·준비된 답변 |
| [앱 서술형 퀴즈](assets/original-ui/09-app-written-quiz.png) | 원본 소스. 단답형 샘플 규칙·500자 입력 제한 |
| [앱 결과](assets/original-ui/10-app-quiz-result.png) | 원본 소스. 예시 판정과 탭 내 저장 |

원본 네이티브 앱/서비스 전체는 실행하지 않았다. 동일 데이터/OS/뷰포트의 이미지가 아니므로 픽셀 일치율은 산출하지 않는다. 시각 검토는 주요 원본 구조·자산·치수·버튼 배치를 근거로 한 구현 검토이고 **USER_VISUAL_APPROVAL=PENDING**이다.

## 실행 검증과 산출물

최종 `verify:showcase`는 **2026-09-30 17:02:40–17:02:55 UTC (10월 1일 02:02 KST)**에 PASS했다. Node 22.14.0 / macOS / 독립 Chrome 154.0.8037.59 환경이며 사용자 브라우저 프로필을 사용하지 않았다.

| 검증 | 결과 |
|---|---|
| 타입 검사 / sentinel 포함 showcase 빌드 / 기존 phase1 웹 빌드 | PASS (서비스 실행 없음) |
| 기존 sample 상태 42 + 새 상태 13 + 빌드 경계 11 | 66 PASS |
| 기존 웹 인증·권한·제출·색인·학생·HTML 경계 회귀 | 115 PASS |
| 로컬 Pages manifest/배포 조건 순수 계약 | 8 PASS (원격 실행 아님) |
| 기존 CI 격리 순수 계약 | 6 PASS (Docker 실행 아님) |
| 일반 정적 서버 root 및 /DO-DREAM/ 파일별 MIME/bytes/hash/거부 경계 | 40 PASS |
| 실제 정적 산출물의 독립 Chrome 인수 | 104 PASS |
| 정적 요청 / 금지 요청 / API / WebSocket / 마이크 / CSP 위반 | 90 / 0 / 0 / 0 / 0 / 0 |
| 브라우저 page/console/HTTP 오류 | 0 |
| 검증 실행 전후 소스·산출물 동일 | PASS |
| 원격 CI / 새 공개 UI 인수 / Pages 배포 | NOT_RUN / NOT_RUN / NOT_RUN |

브라우저 인수는 두 배치 경로의 교사↔학생 흐름, 본문 편집·새로고침, 준비된/미지원/악성 질문, 참고 모달, 서술형 정답/오답, 재도전, 중복 제출, 별도 context 기록 격리, 이전 주소와 특수 `__proto__`/`constructor` 주소, 저장소 손상·버전·크기·읽기/쓰기 거부·초기화, 키보드·320px·짧은 PC와 로컬 음성 이벤트의 늦은 도착 방어를 포함한다. 음성 이벤트는 명시적인 합성 플랫폼 검사이며 실제 청취 성공으로 계산하지 않는다. 앱 코드의 fetch를 가로채 샘플로 바꾼 것이 아니며, 테스트의 요청 감시는 차단된 시도까지 FAIL로 센다.

추가 시각/상호작용 검토는 최종 산출물의 교사 16개·학생 9개와, 동일 편집기 코드의 직전 진단 산출물에서 수행한 도구 11개를 별도 기록했다. 이 개수를 104개 정식 인수와 합쳐 하나의 숫자로 주장하지 않는다. 추가 검토에는 원래 라벨 필터·학생 검색/정렬·반/학생 선택 공유·분할/병합·서식 왕복·발행 안내·빈 챕터·고대비·휴대폰 모달을 포함한다.

재현 명령(저장소 루트; 설치된 기존 의존성 사용):

```sh
DODREAM_SHOWCASE_EVIDENCE=original-ui npm --prefix fe-web run verify:showcase
node --experimental-strip-types --test fe-web/tests/auth-session.test.ts fe-web/tests/native-contract.test.ts fe-web/tests/authorization-contract.test.ts fe-web/tests/grading-submission.test.ts fe-web/tests/indexing-status.test.ts fe-web/tests/student-*.test.ts fe-web/tests/html-boundaries.test.ts
node --test fe-web/tests/pages-release.test.mjs
python3 -m unittest discover -s scripts/ci/tests -p 'test_ci_contract.py'
DODREAM_SHOWCASE_EVIDENCE=original-ui npm --prefix fe-web run preview:showcase
```

이번 검증의 임시 증거는 ignored `.local/original-ui/results/`에 저장한다. `verify-showcase.json`, `artifact-review.json`, `showcase-browser-latest.json`, `teacher-browser/report.json`, `teacher-editor-controls.json`, `student-visual-latest.json`, `comparison-manifest.json`에 실행과 캡처 근거를 보존한다. 기존 static-showcase/배포 증거를 덮어쓰지 않았다.

초기 실패도 보존했다. sandbox의 loopback bind 거부는 scoped 실행에서 해소했다. 새 Tiptap의 CommonJS 가상 모듈 ID와 ProseMirror 오류 문서 URL을 검토해 빌드 계약에 정확히 분류했다. 옛 화면 selector·실제 질문 문구·React 화면 전환 대기 누락으로 난 검사 실패는 새 화면의 정확한 상태를 기다리도록 수정했다. 교사 공유 모달의 0높이 wrapper에 있던 dialog 역할, 학급의 누락된 원본 빈 카드 슬롯, 자동 초점의 불필요한 제목 윤곽, 빈 챕터 표시와 특수 이전 결과 경로 오류는 실제 구현에서 수정했다. staged 검토의 CSS 끝 공백 1곳도 정리한 뒤 전체 검증을 다시 실행했으며 배포 파일 해시는 바뀌지 않았다. FAIL을 지우거나 skip하지 않았으며 최종 단일 실행은 전부 PASS다.

최종 산출물은 **13파일 / 6,719,677 bytes**다. manifest SHA-256은 `25dbd2277db5bc6258155911ccb42623c2e0137b9d7c5037d972c2de8d6cda48`, 단일 검증 소스 digest는 `b8928739aeffd240f571f114b4b8163947e5e62cdba2519c9041dd93d2d1e4d1`다. 19단계의 3파일/272,609 bytes를 재사용하지 않았다. 비교 PNG 10개는 문서 자산이며 배포 산출물에는 들어가지 않는다.

| 산출물 (`fe-web/dist-showcase/`) | bytes | SHA-256 |
|---|---:|---|


| `assets/background-cFpxG_42.jpg` | 893,557 | `80e3a354750edb7ef8a2ad2f4f8ded72d8e6f15234c370605fbd25616d9ad00a` |
| `assets/female-DlBoi81V.png` | 274,444 | `9010cc74df152fccb43ce805f01586cd73d3c22a1fff7f90812540788569df49` |
| `assets/index-CQhb5zWm.css` | 101,280 | `188db21d4896ef472eef886299e48548212e7195da67bb014018365d7b5586b1` |
| `assets/index-YgJ49Skn.js` | 723,508 | `05f6cbf70e492784873d5822161e9bcc1171258d96125cb828c4e9f019b65de2` |
| `assets/jalnan-LICENSE-CfcFbgMf.txt` | 2,014 | `a503432ebbb2aef98af241a61ce93f876176aafd5af81cd136ce099745467d1e` |
| `assets/male-CR3wiWdN.png` | 222,433 | `0fea7ba29352dcb172bb851fc7236a3b3064fd43ebe087912df112b24ecf2f56` |
| `assets/memo-HUZ20Veg.png` | 417,870 | `f61fd42eb44485b6e043915d0d080194d9575656594006b9040e6733f3ac3d52` |
| `assets/school-B7FUhzuY.png` | 1,008,593 | `323bc8040f13ffac74a74061cb3617b3a17c1d0389bb770822858a0bdb7920ec` |
| `assets/signin-BVNG55Xn.png` | 1,248,501 | `2ee696167b7bf4b182bb17d2ea7a3d2106d106ee354eafceeeb56f6ce0481702` |
| `assets/signup-qOpSqZ9T.png` | 179,709 | `8d2c0e9b6350787d7ef1ede9d04c551e4372fa10b7799a8bef9ccab5798c7156` |
| `assets/teacher-EkXGA_59.png` | 1,108,881 | `2ffe378092d1ad39a36ae43fe653ac628231f8367e90eb3e2e9b2f1f38d0b850` |
| `assets/yg-jalnan-2iK9oszh.woff` | 537,996 | `606c8ff7146886d42bacecdf1df92c4088ab18e2b3f4de77764b02e136510140` |
| `index.html` | 891 | `6b341a59df5f809ffebf7cdbd7b7dbd087749d3b7dccc38c02cf8d98492fac7f` |

## 최종 판정과 다음 검수

| 항목 | 판정 |
|---|---|
| ORIGINAL_TEACHER_UI_FIDELITY | PASS_WITH_DOCUMENTED_DIFFERENCES — 실제 원본 자료목록 이미지 + 나머지 소스/CSS 비교 |
| ORIGINAL_STUDENT_APP_UI_FIDELITY | PASS_WITH_DOCUMENTED_DIFFERENCES — 실제 서재/플레이어 이미지 + 나머지 StyleSheet 비교 |
| MOBILE_FRAME_INTERACTION | PASS |
| BACKEND_FREE_JOURNEY | PASS |
| SHOWCASE_MODE_ISOLATION | PASS |
| VISUAL_COMPARISON_REVIEW | PASS_WITH_DOCUMENTED_DIFFERENCES — 10개 비교를 직접 열어 검토 |
| EXISTING_WEB_REGRESSION | PASS |
| LOCAL_PREVIEW_READY | PASS |
| USER_VISUAL_APPROVAL | PENDING |
| UPDATED_PUBLIC_DEPLOYMENT | false |

최종 확인용 loopback 미리보기: `http://127.0.0.1:59134/`와 `http://127.0.0.1:59134/DO-DREAM/#/app/library`. 이 주소는 현재 컴퓨터의 임시 로컬 서버이며 재실행하면 포트가 달라질 수 있다. 위 재현 명령으로 새 주소를 확인할 수 있다. [현재 공개 페이지](https://rladbstn1000.github.io/DO-DREAM/)는 기존 배포 그대로이며 이번 UI를 표시하지 않는다.

사용자가 비교 캡처와 로컬 화면을 확인한 뒤에도 별도의 공개 반영 요청이 있어야 새 원격 검증·배포를 진행한다. `REAL_AI_INTEGRATION=NOT_RUN`, `BACKEND_PRODUCTION_READY=false`, `BACKEND_DATA=NOT_TOUCHED`를 유지한다.
