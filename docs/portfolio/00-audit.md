# 00. 1차 실행 기반 감사

## 기준과 보존

- 조사일: 2026-09-29 (Asia/Seoul).
- 실제 루트: `/Users/yoonsu/Desktop/projects/DO-DREAM`.
- origin: `https://github.com/rladbstn1000/DO-DREAM.git` (fetch/push 동일, 변경하지 않음).
- 팀 구현 기준 HEAD: `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`.
- 기본/시작 브랜치: `main` (`origin/HEAD -> origin/main`). 시작 시 staged/unstaged/untracked 모두 없음.
- 진행 중 merge/rebase/cherry-pick/revert/bisect 없음. 저장소와 상위 적용 경로의 AGENTS.md 없음.
- 사용자 지시에 따라 `codex/dodream-phase1-runtime` 생성. Git 참조 쓰기 sandbox 제한은 승인된 실행으로 해결. stage/commit/push/PR/merge 없음.
- 기존 README, 팀 기여 설명, 포팅 문서 보존. 이번 개인 개선 범위는 이 문서군과 미커밋 diff에 한정한다. 기존 성능·접근성·정확도 주장은 이번에 재검증하지 않았다.

## 실행 구조: 문서보다 실제 호출 우선

| 영역 | 실제 역할 / 호출 | 1차 경로 |
|---|---|---|
| `be` | Spring Boot 3.5.7 / Gradle 8.14.3 / Java toolchain17. JWT, MySQL 도메인, Redis refresh·임시 문서, 자료·퀴즈 API. `file/service/PdfService.java`가 AI 문서 파서, `quiz/service/QuizService.java`가 AI 채점 호출. | 실제 Spring/JPA/Security 유지. local 프로필만 Vault 대신 생성 설정, 외부 저장소 읽기 fixture·OCR/FCM unavailable. |
| `ai` | `app/main.py` → 사용자·문서·RAG 라우터. 공유 MySQL 사용자 조회, SQLite 채팅, Redis/Celery 비동기 임베딩. `/document/parse-pdf-from-cloudfront`는 Spring에서 호출하는 경로. | 원래 FastAPI 라우터/JWT/DB/Celery 유지. 공급자 경계만 local 대역. |
| `python-service` | 별도 PDF 구조 추출 FastAPI. 실제 PyMuPDF 텍스트 분석·헤딩·읽기순서·TipTap 파이프라인과 Gemini 경계. | 독립 기동/기존 텍스트 파이프라인 검증. Spring의 주 문서 흐름은 ai로 연결되므로 중복이라고 삭제/통합하지 않음. |
| `fe-web` | React19/Vite7/TS5.9 교사 로그인·교실·자료 편집·학생 이력. 기존 `/api` 요청과 운영 AI 절대 URL 혼재. | 기존 UI 유지. phase1 모드 same-origin `/api`와 `/ai` → local nginx → 실제 서비스. |
| `fe_app` | Expo/React Native 학생 클라이언트. `src/api/authApi.ts`, `quizApi.ts`, `ragApi.ts`, `interceptors.ts` 등에서 Spring 인증·공용 퀴즈 및 AI 계약 사용. | 계약 읽기만. npm 설치·네이티브 빌드·웹 전환 안 함. |
| `exec` | `포팅_매뉴얼.md`: Vault/AWS/Clova/Firebase/운영 포팅 및 수동 시연 설명. | 원문 보존. 로컬 실행은 별도 runbook. |

AI의 기존 의존성 파일은 추적된 실행 명세가 없었다. python-service에는 핀된 기존 requirements와 Dockerfile이 있으나 무거운 LayoutParser/Detectron2 경로가 포함되어 있다. 이번 local lock은 모델을 내려받지 않는다. **python-service DTO는 원래 존재**한다. 기존 `.dockerignore`의 `models/`가 `app/models`까지 제외하던 빌드 문제를 예외 규칙으로 수정했으며 모델 재작성은 하지 않았다.

## 초기 도구·자원 확인

- 기본 Java 23.0.1. 설치된 Corretto 17.0.14를 실제 컴파일에 선택; Java 도구체인 요구를 23으로 바꾸지 않음.
- Node 22.14.0 / npm 10.9.2, 호스트 Python 3.9.6. 컨테이너 Python 3.11.
- Docker 28.0.1 / Compose 2.33.1. daemon socket 최초 접근 제한 후 승인된 read-only inventory 수행.
- 기존 실행 컨테이너 18개. 해당 ID/이름/포트와 기존 볼륨/네트워크 **이름만** `.local/results/resources-before.json`에 기록. 다른 프로젝트 내부 파일/환경/DB/로그는 열람하지 않음.
- 18080/18081, 5173/5174, 5184/5185 등 기존 점유 확인. 이번 포트 18082/18000/18001/15173은 첫 확인 당시 비어 있었음.
- host Redis6379와 기존 MySQL/Redis 컨테이너를 사용하지 않음. 전용 Compose의 내부 MySQL/Redis 사용.

## 문제·근거

13개 기존 지적의 파일/줄/영향/정적 판정은 [security-evidence.md](security-evidence.md)에 있다. 이 표는 기준 커밋 줄 번호를 고정하여 원본 팀 구현과 개인 변경을 분리한다. 런타임으로 재현한 안전 정책 위반과 미실행 항목은 [03-phase1-results.md](03-phase1-results.md)를 따른다.

확인된 직접 빌드 결함은 `be/.../material/entity/Material.java`의 미사용 JUnit production import와 python-service dockerignore의 DTO 제외다. 변경 전 코드에 존재하던 원인을 최소 수정했다. 공급자 키 부재는 서버 전체를 대체하는 이유로 삼지 않고 외부 호출 경계에서만 분리했다.

보안 전체 수정, 데이터 마이그레이션 체계 전환, RAG 개선, 모바일 전환, UI 개편, 성능 벤치마크, 공개 배포는 범위 밖이다.
