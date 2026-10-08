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

## 시각 검수 후 표시 보완

2026-10-01, 전달받은 브랜치 `codex/dodream-original-ui-showcase`와 HEAD `1586b7e56b0a9ba99ab14883996c51acc5417ddb`가 실제 상태와 일치함을 확인하고 소폭 보완했다. 기존 미추적 `docs/.DS_Store`는 작업에서 제외했다. 아래는 이번 추가 검증이며 위 복원 기록과 판정을 덮어쓰지 않는다.

- **교사 학급 상세:** 실제 수정 전 정적 빌드의 1280px 화면에서 제목·인원·정렬 문구 분리를 재현했다. 줄바꿈 없는 헤더 flex 안에서 검색 input의 기본 최소 폭과 양쪽 그룹의 `flex-shrink`가 제목/버튼을 압축했다. `teacher/teacher.css`에서 학급 상세에만 제목·정렬 버튼의 축소/줄바꿈을 막고 검색 그룹에 `flex: 1 1 288px`, 검색 래퍼에 `flex: 1 1 172px`와 `min-width: 0`을 적용했다. 고정 viewport 분기 대신 실제 내용 폭이 부족하면 그룹이 다음 행으로 이동한다. 1280px에서는 두 행, 1366/1440px에서는 한 행이며 제목 18px·정렬 12px는 그대로다. 긴 자료명이 grid item의 기본 최소 폭을 밀어내던 문제는 패널의 `min-width: 0`으로 해결했다. 원래 두 열 폭(각 448/491/528px), 패널·색·서체를 유지했다.
- **학생 어절:** 기본 `word-break: normal`이 한글 음절 사이 줄바꿈을 허용했다. `student/original-student.css`의 본문·질문 안내·문제 제목에만 `word-break: keep-all; overflow-wrap: anywhere`를 적용했다. `StudentExperience.tsx`는 퀴즈 링크에 전용 클래스만 추가했다. 제목은 남은 폭을 사용하고 단답형 배지는 축소하지 않는다. 기본 392px 화면에서 보이지·말하기·눌러·차가워지면·되나요?가 어절 단위로 표시된다. 320px/150%에서는 어절 자체가 제목 열보다 긴 경우에만 fallback으로 나뉜다(관측 168.675px > 165.656px). 글자 크기·본문·휴대폰 폭/프레임·큰 버튼·남색/노란색·주요 컨트롤은 유지했고, 카드 높이는 내용에 따라 증가한다. 앱 축소·문제 생략·전역 nowrap·추가 `!important`는 사용하지 않았다.
- **재생 방식 스크롤:** 수정 전부터 정상이다. 내부 392px, 320px 모바일, 각각 기본/150% 글자와 짧은 PC 높이를 확인했다. 내부를 끝까지 스크롤하면 저장 목록과 실제 마지막 메뉴인 퀴즈 풀기가 완전히 보이고, 클릭·Tab/Enter 및 초점 자동 노출이 동작한다. 수정 전후 5조건의 scrollHeight/clientHeight가 같아 Playback DOM/CSS는 변경하지 않았다. 최종 회귀에서는 높이 500px 조합도 확인했다.
- **실제 체험 기록:** 새 샘플 탭의 초기 0%/빈 결과를 확인한 뒤 말하기의 추천 질문 1개와 퀴즈 1회(두 문제)를 실행했다. 교사 학생 상세에 질문 1개·퀴즈 1회·2개 정답이 표시된다. 기존 완료 자료 1/2 정의에 따라 진도는 50%이며 전체 완료로 바꾸지 않았다. 음성 답하기의 예시 선택/마이크 미사용 안내도 확인했다. 가짜 성과를 초기 상태에 채우거나 실제 마이크·AI를 구현하지 않았다.

아래 10개 PNG를 직접 열어 검토했다. 수정 전은 전달된 HEAD의 정적 산출물이며, 수정 후 집중 검토 산출물 13파일은 최종 전체 검증 산출물과 SHA-256이 모두 같다. 교사 전후는 1280×900, 학생 전후는 1280×1000/내부 392px로 조건을 맞췄다. 최하단과 체험 기록은 최종 전체 실행의 캡처다(1280×920 viewport, 학생 상세는 전체 페이지 978px 높이).

| 화면 | 수정 전 | 수정 후 / 확인 결과 |
|---|---|---|
| 교사 학급 상세 | [이전](assets/original-ui-polish/teacher-classroom-before.png) | [제목·도구 영역](assets/original-ui-polish/teacher-classroom-after.png) |
| 학생 퀴즈 목록 | [이전](assets/original-ui-polish/student-quizzes-before.png) | [어절·배지](assets/original-ui-polish/student-quizzes-after.png) |
| 학생 플레이어 본문 | [이전](assets/original-ui-polish/student-player-before.png) | [어절 유지](assets/original-ui-polish/student-player-after.png) |
| 학생 질문 안내 | [이전](assets/original-ui-polish/student-question-before.png) | [어절 유지](assets/original-ui-polish/student-question-after.png) |
| 재생 방식 최하단 | 레이아웃 유지 | [저장 목록·마지막 메뉴](assets/original-ui-polish/playback-bottom.png) |
| 질문·풀이 후 교사 학생 상세 | 초기 0%/빈 기록 유지 | [실제 체험 후 기록](assets/original-ui-polish/teacher-student-history.png) |

최종 `verify:showcase`는 **2026-09-30 17:31:47–17:32:03 UTC (10월 1일 02:31–02:32 KST)**에 단일 실행 PASS했다. 기존 교사 자료 목록·편집기·학생 서재/재생 방식/플레이어/질문/퀴즈 목록/문제/결과와 교사 상세 흐름, 모드 분리·CSP·키보드 기대값을 유지했다. `tests/showcase-layout.mjs`를 기존 브라우저 검증에 연결해 1280/1366/1440px의 제목/검색/버튼, 긴 검색어/자료명, 392/320px와 큰 글자, 내부 스크롤 및 체험 후 기록을 검사한다. 검증용 긴 단일 문자열은 저장하지 않는 DOM 레이아웃 점검이며 샘플 콘텐츠나 성과로 남기지 않는다.

| 이번 실행 | 결과 |
|---|---|
| 타입 검사 / showcase sentinel 빌드 / 기존 phase1 웹 빌드 | PASS (서버·DB 실행 없음) |
| 상태·빌드 경계 계약 / 정적 서버 경계 | 66 PASS / 40 PASS |
| 최종 정적 산출물 Chrome 전체 인수 | 184 PASS |
| 기존 웹 인증·권한·제출·색인·학생·HTML 경계 회귀 | 115 PASS |
| 정적 요청 / 금지 요청 / API / WebSocket / 마이크 / CSP 위반 | 117 / 0 / 0 / 0 / 0 / 0 |
| 브라우저 page/console/HTTP 오류 / 소스·산출물 실행 전후 동일 | 0 / PASS |
| 별도 집중 시각 검토(전체 인수 수에 합산하지 않음) | 교사 36 PASS, 학생 35 PASS |
| push / PR / merge / Pages 재배포 | NOT_RUN |

기존 build/preview/verify를 재사용하며 `scripts/showcase-paths.mjs`와 해당 계약 검사는 고정 증거 경로 `original-ui-polish`만 추가했다. 새 기록은 `.local/original-ui-polish/`의 `before/`, `after/`, `results/verify-showcase-2026-09-30T17-32-03-223Z.json`, `results/showcase-browser-2026-09-30T173151833Z.json`, `existing-web-regression.log`에 보존한다. 이전 `.local/original-ui/results/`와 `assets/original-ui/`의 209파일 SHA-256은 작업 시작과 동일하다. 재현 과정의 진단 기록도 남겼다. 의존성·lock·원본 자산은 변경하지 않았으며 기존 500kB chunk 경고는 남아 있다.

최종 산출물 **13파일 / 6,720,716 bytes**, manifest SHA-256 `df92f54237021357c8faa78e2de42a1544aac9fa450bb216886fe53984b60d42`, 전체 검증 소스 digest `847b00cbf524c54a365e0cb0b1ce744ffd1a69c9c570da7c6944bb369db49412`이다. 추가 PNG는 문서 전용이며 공개 번들에 들어가지 않는다.

```sh
DODREAM_SHOWCASE_EVIDENCE=original-ui-polish npm --prefix fe-web run verify:showcase
DODREAM_SHOWCASE_EVIDENCE=original-ui-polish npm --prefix fe-web run preview:showcase
```

이번 로컬 미리보기는 `http://127.0.0.1:61097/DO-DREAM/#/teacher/classroom/1-1`이다(임시 loopback 서버, 재실행 시 포트 변경 가능). 검토한 파일만 로컬 커밋 대상으로 삼으며 현재 공개 사이트는 변경하지 않는다. **USER_VISUAL_APPROVAL=PENDING**, **UPDATED_PUBLIC_DEPLOYMENT=false**를 유지한다. 이번 시각 검토 의견은 공개 배포 승인이 아니다.

## 원본 UI 공개 반영 승인과 준비

2026-10-01 KST, 사용자가 기존 교사 웹·학생 앱 형태와 표시 보완의 공개 반영을 승인했다. **USER_VISUAL_APPROVAL=APPROVED**의 대상은 `a187bf09b017984feea48153d79e02b81a9e23a5`이며, 앞선 복원 커밋 `1586b7e56b0a9ba99ab14883996c51acc5417ddb`를 포함한다. 위 PENDING·미배포 문단은 당시 기록으로 보존한다. 새 디자인·기능 확장은 승인 범위가 아니다.

작업 시작 HEAD가 승인 후보와 일치했다. main 하나를 prune 없이 fetch한 결과 `f9042b57c326b2aa5aad6f94b7f3345f9c1378c9`이며, main 이후 누적 변경은 위 두 커밋·56경로다. 진행 중 merge/rebase/cherry-pick과 열린 PR은 없었고 기존 미추적 `docs/.DS_Store`를 제외했다. 공개 검토는 마지막 표시 보완만이 아니라 두 커밋의 신규 Git blob·문서·자산 전체를 대상으로 한다.

**SOURCE_DELTA_PUBLICATION_REVIEW=PASS_WITH_DOCUMENTED_LIMITATIONS.** 신규 63blob(42 text/21 binary, 3,787,215 bytes), 중간 버전 7blob까지 확인했다. 후보 6건은 테스트 sentinel 4건·합성 이메일 1건·공식 글꼴 notice 연락처 1건이며 실제 비밀·신규 비공개 자료 발견은 0건이다. 새 PNG 20개를 실제 열어 확인했고 Git blob과 동일하며 text/EXIF metadata가 없다. 새 WOFF/notice는 공식 배포 조건과 일치하고 기존 8개 이미지는 원격·팀 기준과 SHA가 같다. 원래 팀 기여를 보존하고 자산에 새 라이선스를 추정하지 않았다. 검토는 신규 공개 범위의 패턴·문맥·이미지 확인이며 모든 비밀/권리 문제의 부재를 보장하지 않는다. 근거는 `.local/original-ui-release/source-review/`에 보존한다.

후속 준비 변경은 공개 브라우저 검사와 새 증거 경로에 한정한다. 새 교사/학생 경로, 서술형 퀴즈, 같은 탭 기록, 한국어 줄바꿈·내부 스크롤, 입력 안전·옛 해시 경로를 기존 공개 harness에서 검사한다. `original-ui-release` 고정 증거 경로는 이전 검증 기록을 덮어쓰지 않기 위한 구분이다. 앱 UI·인증·권한·채점·색인 구현 및 의존성·workflow는 승인 후보 그대로 유지한다.

준비 소스의 로컬 최종 `verify:showcase`는 2026-10-01 01:17:01–01:17:15 UTC(10:17 KST)에 PASS했다. 상태/빌드 계약 66개·정적 서버 경계 40개·Chrome 인수 184개, 별도 웹 회귀 115개·Pages 계약 8개 PASS이며 금지 요청/API/마이크/CSP 위반은 0건이다. 산출물은 실제 13파일/6,720,716 bytes, manifest digest `df92f54237021357c8faa78e2de42a1544aac9fa450bb216886fe53984b60d42`로 승인된 앱과 같다. 공개 UI 함수의 별도 로컬 리허설 78개도 통과했으나 이를 공개 인수로 세지 않는다. 리허설에서 발견한 검사 selector 및 문제 전환 대기 누락만 바로잡았고, 초기 실패 3회와 최종 성공 기록을 모두 새 폴더에 보존했다. 공개 URL/manifest/자산 해시·네트워크 기대값은 낮추지 않았다.

기존 Pages source=`workflow`, HTTPS/기존 URL, `github-pages`의 정확한 main branch 제한을 확인했다. main 보호와 ruleset은 시작 시 설정되지 않았으며 이를 변경하지 않는다. 그래도 PR과 병합 main 각각의 `web`, `python (ai)`, `python (python-service)`, `backend`, `offline-tools` 다섯 기대 작업의 실제 성공을 확인한 뒤 배포한다. 기존 `showcase-pages.yml`의 `expected_sha`와 생성 manifest를 사용하며, 원격에서 검증한 산출물을 재빌드 없이 업로드·배포한다.

이 준비 커밋 시점의 배포는 **NOT_RUN**, **UPDATED_PUBLIC_DEPLOYMENT=false**다. 원격 PR/CI·배포·실제 공개 bytes/hash와 새 UI 인수 결과는 완료 후 아래 후속 구역에 기록한다. 실제 AI·마이크·백엔드 서비스·Docker·DB는 실행하지 않는다.

## 원본 UI 공개 배포와 인수

2026-10-01 KST, 승인 후보 `a187bf09b017984feea48153d79e02b81a9e23a5`(복원 `1586b7e56b0a9ba99ab14883996c51acc5417ddb` 포함)의 UI를 **[기존 공개 URL](https://rladbstn1000.github.io/DO-DREAM/)**에 반영했다. 승인 후 앱·실제 인증/API·권한·채점·색인·의존성·workflow는 변경하지 않았다. 공개 검사·증거 경로 준비 커밋은 `4754349a9a292fea4c29457be9fcdab91418a8f1`이다.

| 구분 | 실제 SHA / 실행 결과 |
|---|---|
| 공개 반영 PR | [#4](https://github.com/rladbstn1000/DO-DREAM/pull/4), head `4754349a9a292fea4c29457be9fcdab91418a8f1` |
| PR 검사 | [36800510834](https://github.com/rladbstn1000/DO-DREAM/actions/runs/36800510834), 실제 checkout merge SHA `ac0904803876111464ae25478c913018afff93c7` |
| 일반 merge commit | `1aafe5a32a4a66e55629255277355aeb9f06f551` (01:22:07 UTC) |
| 병합 main 검사 | [36800763860](https://github.com/rladbstn1000/DO-DREAM/actions/runs/36800763860), checkout/source `1aafe5a32a4a66e55629255277355aeb9f06f551` |
| 수동 Pages 실행 | [36800980482](https://github.com/rladbstn1000/DO-DREAM/actions/runs/36800980482), build·deploy 모두 SUCCESS |
| 실제 배포 source | **`1aafe5a32a4a66e55629255277355aeb9f06f551`**, deployment `6773921680`, 공개 URL 출력 01:26:26 UTC |

PR 및 병합 main에서 `web`, `python (ai)`, `python (python-service)`, `backend`, `offline-tools` **다섯 작업과 하위 단계 모두 SUCCESS**였고 skip은 없다. PR head와 PR 검사용 merge SHA를 구분했다. 브랜치 하나만 일반 push하고 일반 merge commit으로 병합했다. main 직접 push·force·이력 재작성·보호 우회는 없었다. `expected_sha`에 위 배포 SHA 전체를 전달했으며, 기존 Pages source·github-pages 환경/main 제한·최소 권한·HTTPS·도메인은 전후 동일하다.

### 원격 artifact와 공개 파일 대응

현재 Pages 실행에서 내려받은 `github-pages` artifact ID **11135800957**(ZIP 5,701,280 bytes, digest `b22053803641654d17ddc7cbd64e048c29dd833a2259b43c339c7a887846fe02`)와 `showcase-provenance` ID **11135561093**(ZIP 1,462 bytes, digest `38b6e56aa81b9a077ead3d88ba1de4037184efe0f435185c0cc4132a47bfeb22`)를 연결했다. 검증된 `artifact.tar` SHA-256은 `56f524294c8292021800bb835306d73901ecd20c7d38bdbb739a5ae333f4549a`다. 보관 기간은 기존대로 각각 1일/7일이며 만료 후에는 아래 파일 해시와 run 기록으로 식별한다.

원격 Node 22.22.0/npm 10.9.4/Chrome 154.0.8037.57/Playwright 1.62.1로 검증한 산출물을 **다시 빌드하지 않고 그대로 업로드·배포**했다. tar 경로·파일 형식·허용 목록을 검사해 안전하게 추출했고 소스·DB·로그·비밀 파일은 없다. 이번 run의 manifest 및 추출 파일과 공개 HTTPS 응답 **13파일 / 6,720,716 bytes**의 크기·SHA-256이 모두 일치했다. manifest digest는 `df92f54237021357c8faa78e2de42a1544aac9fa450bb216886fe53984b60d42`다. 과거 로컬/최초 공개 manifest를 대신 사용하지 않았다.

| 공개 파일 | bytes | SHA-256 |
|---|---:|---|
| `assets/background-cFpxG_42.jpg` | 893,557 | `80e3a354750edb7ef8a2ad2f4f8ded72d8e6f15234c370605fbd25616d9ad00a` |
| `assets/female-DlBoi81V.png` | 274,444 | `9010cc74df152fccb43ce805f01586cd73d3c22a1fff7f90812540788569df49` |
| `assets/index-DWcuaV5g.js` | 723,524 | `e454ecbe43a8c19852e63c42b5ab9e4687ba3b0b2b4e133a0b20501b5d8b385f` |
| `assets/index-DxqGNCZv.css` | 102,303 | `851c321991f6f8af278188d645d9004aa4d158ce3e7fc63792b273411954c7d5` |
| `assets/jalnan-LICENSE-CfcFbgMf.txt` | 2,014 | `a503432ebbb2aef98af241a61ce93f876176aafd5af81cd136ce099745467d1e` |
| `assets/male-CR3wiWdN.png` | 222,433 | `0fea7ba29352dcb172bb851fc7236a3b3064fd43ebe087912df112b24ecf2f56` |
| `assets/memo-HUZ20Veg.png` | 417,870 | `f61fd42eb44485b6e043915d0d080194d9575656594006b9040e6733f3ac3d52` |
| `assets/school-B7FUhzuY.png` | 1,008,593 | `323bc8040f13ffac74a74061cb3617b3a17c1d0389bb770822858a0bdb7920ec` |
| `assets/signin-BVNG55Xn.png` | 1,248,501 | `2ee696167b7bf4b182bb17d2ea7a3d2106d106ee354eafceeeb56f6ce0481702` |
| `assets/signup-qOpSqZ9T.png` | 179,709 | `8d2c0e9b6350787d7ef1ede9d04c551e4372fa10b7799a8bef9ccab5798c7156` |
| `assets/teacher-EkXGA_59.png` | 1,108,881 | `2ffe378092d1ad39a36ae43fe653ac628231f8367e90eb3e2e9b2f1f38d0b850` |
| `assets/yg-jalnan-2iK9oszh.woff` | 537,996 | `606c8ff7146886d42bacecdf1df92c4088ab18e2b3f4de77764b02e136510140` |
| `index.html` | 891 | `bc7b9f9c30a27d0d29d62cd8cc410dc54e3fbdc05dee336573c9e2c0ba852961` |

### 공개 인수와 캡처

최종 공개 검사는 **2026-10-01 01:38:33–01:38:39 UTC (10:38 KST)**, Mac Chrome 154.0.8037.59의 새 독립 context 5개에서 **108 PASS**다. 배포 결과 URL과 위 실행의 다운로드 manifest/artifact를 입력으로 사용했다. 모든 파일의 직접 HTTP 대조 **13개**와 브라우저가 실제 요청한 정적 응답 **35개/고유 경로 10개**는 별도 집계다. 로컬 184개를 공개 통과 수에 합산하지 않았다.

- 교사 시작·자료·학급·편집기, 휴대폰 안의 서재·재생 방식·플레이어·준비된 질문/참고 구간·서술형 퀴즈/결과와 같은 탭 교사 기록을 통과했다. 질문 1개와 퀴즈 1회(2문제)를 실제 샘플 UI로 실행했고, 교사에 질문 1개/퀴즈 1회/정답 2개가 표시됐다. 기존 진도 정의는 1/2 자료, **50%**로 유지했다.
- 교사 1280/1366/1440px에서 제목·인원·정렬 문구와 검색 영역, 학생 내부 392px 및 320px/큰 글자 150%에서 본문·안내·퀴즈 어절과 배지 폭을 확인했다. 짧은 높이 500px를 포함해 내부 스크롤 끝의 저장 목록과 실제 마지막 퀴즈 메뉴에 도달하고 Tab/Enter로 선택했다. 긴 내용의 자연스러운 스크롤과 접근 불가능한 잘림을 구분했다.
- 직접 해시 경로·새로고침·뒤로 가기·기존 공개 해시의 호환 이동·입력의 안전한 텍스트 표시·저장소 소유 키 2개만 초기화/타 키 보존을 통과했다. 말하기/음성 답하기는 기존 예시 선택으로 연결되며 실제 마이크를 쓰지 않는다.
- **금지 요청/API/WebSocket/마이크 시도/CSP 위반 모두 0**, console/page/request 오류 0이다. API 응답을 가로채 성공으로 바꾸지 않았다. HTTP 파일 대조는 처음부터 새 파일과 일치해 CDN 지연 재시도는 필요하지 않았다.

초기 공개 실행 `2026-10-01T012855425Z`는 UI 검사와 직접 HTTP 13파일 대조를 통과했으나 reset 후 빠른 화면 이동으로 배경 이미지 응답 하나가 취소되어 전체 **FAIL**이었다. 실패 원본을 보존했다. `showcase-public-journey.mjs`에서 해당 실제 이미지 decode 및 응답 수집 완료를 기다리고, `showcase-public-browser.mjs`에서 request 실패 0 기대값을 추가했다. 뒤이은 96 PASS 캡처에서도 SPA 전환의 `networkidle`만으로 새 이미지 표시 완료를 보장할 수 없음을 실제 캡처로 발견했다. DOM 이미지와 표시되는 교사 CSS 배경의 decode를 확인하는 캡처 검사 12개를 추가한 **최종 108 PASS**를 채택한다. 기대값을 낮추거나 앱 UI·자산을 수정하지 않았고 배포를 다시 하지 않았다. 중간 실행·진단·최종 원본은 모두 보존한다.

아래 8개는 최종 공개 실행의 캡처를 그대로 복사해 직접 열어 확인했다. 교사 아바타/메모 등 실제 자산 표시와 줄바꿈·하단 접근·체험 기록을 포함한다. README 대표 캡처와 시연 안내도 현재 교사 웹/학생 앱 경로를 설명하도록 갱신했으며 팀 원본 캡처와 기여 표시는 보존했다.

| 화면 | 최종 공개 캡처 |
|---|---|
| 교사 자료 목록 / 학급 상세 | [자료](assets/original-ui-public/teacher-materials.png) · [학급](assets/original-ui-public/teacher-classroom.png) |
| 학생 서재 / 퀴즈 목록 | [서재](assets/original-ui-public/student-library.png) · [퀴즈](assets/original-ui-public/student-quizzes.png) |
| 플레이어 / 준비된 질문·참고 구간 | [본문](assets/original-ui-public/student-player.png) · [질문](assets/original-ui-public/student-question.png) |
| 재생 방식 마지막 메뉴 / 체험 후 교사 기록 | [최하단](assets/original-ui-public/playback-bottom.png) · [학생 상세](assets/original-ui-public/teacher-student-history.png) |

후속 검사 소스의 최종 로컬 `verify:showcase`도 01:38 UTC에 다시 수행해 **184 PASS / 정적 요청 117 / 금지 요청 0**, 상태·빌드 계약 66개/서버 경계 40개 PASS, 소스·산출물 동일을 확인했다. source digest는 `bb13a2835ce2925c5a3ead7a2a7b189d3470855e0ede31a8af9658260e580b45`다. 별도 기존 웹 회귀 115개 및 Pages 계약 8개 PASS이며 실제 백엔드 서비스를 다시 실행하지 않았다. 기존 chunk 크기 경고와 고정 action 런타임 전환 경고는 삭제하거나 숨기지 않았다.

공개 원본은 `.local/original-ui-release/results/showcase-public-browser-2026-10-01T013833507Z.json`, `public-browser-2026-10-01T013833507Z/`, 다운로드는 `downloads/36800980482/`, 최종 로컬 검증은 `results/verify-showcase-2026-10-01T01-38-48-713Z.json`에 있다. 이전 복원/표시 보완 기록과 캡처 343파일의 SHA-256은 그대로다. 이 후속 기록·README·시연·캡처 및 검사 보완도 PR/필수 CI/일반 merge 절차로 반영한다. **그 후속 main SHA는 앱 배포 source SHA가 아니며 이 문서의 실제 배포 SHA를 대체하지 않는다.** 문서/검사만을 위해 다시 배포하지 않는다.

```sh
node fe-web/tests/showcase-public-browser.mjs --url https://rladbstn1000.github.io/DO-DREAM/ --manifest .local/original-ui-release/downloads/36800980482/showcase-provenance/release-manifest.json --artifact-dir .local/original-ui-release/downloads/36800980482/verified-pages
DODREAM_SHOWCASE_EVIDENCE=original-ui-release npm --prefix fe-web run verify:showcase
```

| 현재 상태 | 판정 |
|---|---|
| USER_VISUAL_APPROVAL | APPROVED — a187bf0까지 |
| SOURCE_DELTA_PUBLICATION_REVIEW | PASS_WITH_DOCUMENTED_LIMITATIONS — 신규 이력·소스·캡처 검토 |
| REMOTE_REQUIRED_CI | PASS — 공개 반영 PR와 배포 main의 실제 5작업/단계 성공 |
| PAGES_DEPLOYMENT | PASS — build/deploy 성공, 기존 URL 유지 |
| PUBLIC_ORIGINAL_UI_ACCEPTANCE | PASS — 최종 공개 108개, 로컬 수와 별도 |
| RELEASE_ARTIFACT_PROVENANCE | PASS — 현재 원격 artifact/manifest/공개 13파일 일치 |
| UPDATED_PUBLIC_DEPLOYMENT | true — 실제 새 UI 공개 확인 완료 |

`REAL_AI_INTEGRATION=NOT_RUN`, `BACKEND_PRODUCTION_READY=false`, `BACKEND_DATA=NOT_TOUCHED`를 유지한다. 실제 음성 청취·VoiceOver·네이티브 앱/실기기 검증은 **NOT_RUN**이며 자동 브라우저 검사를 그 검증으로 대체하지 않는다. 이번 검증이 연 브라우저·임시 검증 서버는 종료했고 이전 작업의 사용자 미리보기는 건드리지 않았다. 새 기능·추가 디자인 개선은 수행하지 않았다.

## 채용 제출용 제목·메모 보완 — 로컬 검증 (2026-10-08)

공개 평가에서 드러난 시작 화면의 제목 구조와 1024px 메모 겹침을 이번 로컬 빌드에서 재현하고 수정했다. 작업 시작 checkout은 `37e7fed820627529c8531e4d63f5a4b32d1c735c`였고, prune 없이 조회한 main `bce567b5afd8fdef45958dbb2edd16f90cc5b973`과 파일 내용이 같았다. 동명 브랜치가 없음을 확인해 main에서 `codex/dodream-portfolio-polish`를 만들었다. 기존 `.DS_Store` 두 파일은 제외했다. 아래 검증은 이번 실행이며, 앞선 공개 인수의 범위를 소급해 확대하지 않는다.

- **시작 화면:** `TeacherJoin`의 화면 제목이 문단이고 두 장식 로고 h2는 CSS 이동만으로 숨겨져, Chrome 실제 접근성 트리에 두 제목이 노출됐다. 대표 제목을 h1으로 바꾸고 장식 로고 영역만 `aria-hidden` 처리했다. 비활성 form의 기존 `inert`와 명시적 `aria-hidden`을 함께 유지하며, 배경 전환 후 활성 제목으로 초점을 옮긴다. 소개·샘플 안내는 보조기술에서도 읽을 수 있다. 제목의 실제 기존 스타일(데스크톱16px/375px13px, 회색·800 굵기), 원본 이미지·로고·버튼 크기와 두 배경 배치를 유지했다. 제목 태그 변경으로 기존 문단 CSS가 빠지는 차이를 명시적으로 보정했다.
- **작은 소개와 소스 링크:** 기존 폼에 서비스 소개 한 문장과 `GitHub 소스` 링크를 추가했다. 정확한 저장소 href, `_blank`/`noopener noreferrer`를 확인했다. 정적 참조 URL 목록에 그 주소 하나만 분류했으며 다른 저장소·추가 경로·쿼리는 계속 거부한다. 자동 preload/fetch를 추가하지 않았고 CSP `connect-src 'none'`과 모든 네트워크 차단 기대값은 그대로다. 링크 속성·키보드 접근을 검사했으며 외부 GitHub 페이지 이동은 이 로컬 인수에서 실행하지 않았다.
- **메모:** `max-width:1024px`에서 작은 원본 그림 위의 라벨 `top:15px`가 클립과 겹쳤다. 해당 분기에서 라벨40px/입력64px로 내려 클립·라벨·입력을 분리했다. 그림·사이드바·라벨은 유지하고 실제 label과 textarea를 연결했다. 1023/1024/1025/1280px의 배치, label 클릭 및 Tab/Shift+Tab 초점, 메모 입력·같은 탭 이동/새로고침 보존·초기화를 통과했다. 375px에서는 기존 메모 숨김 정책을 그대로 유지하고 숨겨진 초점 대상·가로 넘침이 없음을 검사했다.
- **접근성과 회귀:** `showcase-portfolio-polish.mjs`를 기존 정적 빌드 harness에 연결했다. Chrome CDP의 실제 접근성 트리에서 두 배경 각각 활성 h1 하나·소개·컨트롤 하나씩 노출됨을 확인하고 실제 Tab/Enter로 이동했다. 기존 원본 폼 버튼의 `outline:none`이 배경 전환 버튼의 초점 표시를 가리던 문제도 이 검사에서 발견해 폼의 `:focus-visible` 우선순위를 좁게 보완했다. reduced motion과 일반 애니메이션 모두 배경 전환 후 활성 제목 초점을 확인했다. 실제 VoiceOver·음성 청취·네이티브 앱 검증은 NOT_RUN이다.

전후 캡처는 독립 Chrome에서 **빌드된 정적 산출물**을 열어 저장했다. 시작 데스크톱1280×920, 모바일375×812, 교사1024×920 viewport를 전후 동일하게 사용했다(교사 캡처는 전체 페이지). 아래 8장을 직접 열어 확인했다. 새 그림을 생성하거나 원본 기록을 덮어쓰지 않았다.

| 화면 | 수정 전 | 최종 빌드 |
|---|---|---|
| 기본 시작 배경 | [이전](assets/submission-polish/start-before.png) | [h1·소개·소스 링크](assets/submission-polish/start-after.png) |
| 다른 시작 배경 | [이전](assets/submission-polish/start-alternate-before.png) | [같은 제목/초점 정책](assets/submission-polish/start-alternate-after.png) |
| 교사1024px | [클립 겹침](assets/submission-polish/teacher-1024-before.png) | [라벨·입력·키보드 초점](assets/submission-polish/teacher-1024-after.png) |
| 시작375px | [이전](assets/submission-polish/start-375-before.png) | [원본 모바일 배치 유지](assets/submission-polish/start-375-after.png) |

최종 `DODREAM_SHOWCASE_EVIDENCE=portfolio-polish npm --prefix fe-web run verify:showcase`는 **2026-10-08 01:51:16–01:51:40 UTC (10:51 KST)**에 종료0/PASS했다. 타입 검사, showcase sentinel 빌드와 실제 phase1 모드 빌드, 상태·빌드 계약66개, 정적 서버 경계40개, 기존 학생/교사 흐름과 추가 검사를 포함한 Chrome **244 PASS**, 정적 요청153건이다. 금지 요청/API/WebSocket/마이크/CSP 위반은 각각0, 브라우저 오류0이며 검증 전후 소스·산출물이 동일했다. 별도 웹 회귀115개와 Pages 계약8개도 종료0/PASS다. 기존 chunk 경고는 유지했다.

최종 산출물은 **13파일/6,721,625 bytes**, manifest digest `88f6e64ad7a662233c24b5596623479458d6796a1c0dbd08202807025fd44fad`, 소스 digest `15d7deb504f6e9fdc227d3fe2f0a030d82f95d9c6e519e47144d0e11302e90d4`다. 근거는 새 ignored `.local/portfolio-polish/`의 `before/report.json`, `results/verify-showcase-2026-10-08T01-51-40-656Z.json`, `results/showcase-browser-2026-10-08T015122056Z.json`, `selected-captures.json`과 실행별 로그에 보존했다. 수정 전 캡처 selector 중복 실패, 새 GitHub URL 미분류 실패, 실제 포커스 테두리 실패를 보존했으며, 수정 후 최종 전체 실행을 새로 수행했다. 테스트 삭제·skip·안전 기대값 약화는 없다.

이번 결과는 **LOCAL_POLISH_VERIFICATION=PASS**, **USER_VISUAL_APPROVAL=PENDING(이번 보완 화면)**, **UPDATED_PUBLIC_DEPLOYMENT=false(이번 작업)**다. push·PR·merge·Pages 실행은 NOT_RUN이며, 공개 사이트는 앞서 승인·배포한 `1aafe5a32a4a66e55629255277355aeb9f06f551`을 유지한다. README·AI 활용·JDBC 근거·대표 코드 포맷은 [18번 후속 요약](18-portfolio-code-review.md#채용-제출용-보완-2026-10-08)에 연결한다. 이번에 시작한 임시 검증 서버와 독립 브라우저는 종료했다. `REAL_AI_INTEGRATION=NOT_RUN`, `BACKEND_PRODUCTION_READY=false`, `BACKEND_DATA=NOT_TOUCHED`를 유지한다.
