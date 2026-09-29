# 07. 2-B 객체 접근권한 정책

기준 체크포인트: `ef91856cdc8a96c0e0d28a63e89f6efc8e85be3b`. 아래 정책을 먼저 정하고 구현/API 검증을 연결한다. 실제 검증 결과는 08 결과 문서에 구분한다. 정책을 적었다는 사실은 구현/검증 PASS를 의미하지 않는다.

## 실제 ID와 관계

- JWT `sub`는 `users.id`다. 자료 `teacher_id`, 공유 `teacher_id/student_id`, 파일 `uploader_id`도 User ID다.
- 교사의 학급 배정 `classrooms_teachers.teacher_id`는 TeacherProfile ID다. User → TeacherProfile → 배정 학급 → StudentProfile의 현재 학급 → 학생 User를 따라 담당 관계를 판정한다.
- 학생 목록과 RAG `student_id`는 User ID다. StudentProfile ID와 비교하지 않는다. 검증 fixture에는 User/Profile ID가 다른 교사·학생을 포함한다.
- `/api/pdf/{pdfId}`와 초기 임베딩 `pdf_id`는 현재 구현에서 UploadedFile ID를 받는다. 별도 `pdfs.id`로 해석하지 않는다.
- 발행 RAG `document_id`는 canonical 양의 십진 Material ID, 초기본은 `pdf_<UploadedFile ID>`만 허용한다. 문자열 제거/잘라내기로 다른 컬렉션에 충돌시키지 않는다. 기존 비정상 식별자 데이터는 삭제/재소유하지 않고 접근을 거부한다.
- 직접/학급 공유 모두 `material_shares`의 학생별 행을 사용한다. 같은 반이라는 사실만으로 개별 공유 자료를 허용하지 않는다.

## 일관된 거부와 최소 권한

무인증은401, 역할 자체가 허용되지 않는 작업은403이다. 인증된 사용자가 소유·공유·담당 관계를 충족하지 못한 객체와 존재하지 않는 객체는404로 통일해 존재를 드러내지 않는다. canonical 형식이나 요청 내부 식별자 모순은400, 기존 세션의 자료 교체는409로 구분한다. AI의 잘못된 요청 스키마/금지된 추가 필드는422, 권한 DB 조회 오류는503으로 구분한다. 각 테스트는 해당 정책의 정확한 상태코드를 요구한다.

학생 자료 접근은 PUBLISHED·미삭제 자료와 정확한 학생 공유 행, 일치하는 공유 교사/자료 소유자, 현재 담당 관계가 모두 필요하다. CLASS 공유는 행의 학급과 학생의 현재 학급도 일치해야 한다. INDIVIDUAL 공유도 담당 관계 해제 시 더 이상 허용하지 않는다. 교사 자료 접근/관리는 소유 자료에 한정한다. 같은 학교 또는 담당 학생 관계만으로 다른 교사의 자료를 허용하지 않는다.

DB 관계 조회 오류는 서버/서비스 오류로 실패하며 공개 자료로 취급하거나 기본 user1을 넣지 않는다. 권한 검증은 서명·파일 쓰기·채점·메시지 저장·작업 예약·검색·LLM 호출 전에 수행한다.

## 권한표와 적용 경로

| 역할 | 작업/대상 | 필요한 관계 | 거부 조건 | 실제 API 범위 | 검증 |
|---|---|---|---|---|---|
| 교사 | 원본 업로드/URL·편집 JSON·임시본 | 본인 User ID 업로더, 연결 자료도 본인 소유 | 타인 파일/모순된 자료 관계/미인증 | `/api/files/**`, `/api/pdf/**` | 본인200·타교사404·학생403·무토큰401, 서명/쓰기 없음 |
| 교사 | 자료 발행·수정·삭제·퀴즈 편집 | 파일 업로더와 자료 소유자 일치 | 타인 파일/자료, 임의 ID 대입 | `/api/documents/**`, 교사 quiz save/generate | 저장 후 재조회 양성, 타교사 거부·원본 불변 |
| 교사 | 공유 생성/회수 | 본인 자료 + 모든 대상 학생/학급의 현재 담당 관계 | 일부라도 부적격 대상 | `/api/materials/share` 등 공유 관리 | 직접/CLASS 각각, 부분 저장/알림 없음 |
| 학생 | 발행 자료·학습 JSON·문제 | 위 유효 공유 규칙 | 미발행·비공유·해제·타학생·초기본 | `/api/materials/shared/**`, 문제 GET | 양성/반만같음/타반·학교/회수 후 거부 |
| 학생 | 풀이 제출 | 본인 + 유효 자료 + 모든 quiz가 해당 material 소속 | quiz/material 모순, 임의 기록 소유자 | quiz submit, AI grade-batch | DB기준 문제/정답, 거부 시 채점/기록 없음 |
| 학생 | 자기 북마크·풀이/대화 이력 | 본인 + 현재 자료 접근권한 | 타학생·공유 해제 | bookmarks, history, RAG sessions | 목록·직접 상세·공유 해제 |
| 교사 | 학생 학습·대화 이력 | 현재 담당 AND 소유 자료 AND 학생의 현재 공유 | 비담당·타교사 자료·해제 | progress/stats/history, RAG sessions | User/Profile ID 상이, 담당 해제·직접 session ID |
| 학생/교사 | RAG 채팅 | 현재 자료권한, 기존 session.user/document 정확히 일치 | 타인 session·자료 교체 | `/rag/chat` | 두 자료 모두 접근가능해도 세션 전환409, 저장/검색 없음 |
| 교사 | 임베딩 생성·상태/문서 가공 | 소유 UploadedFile/Material + 요청 URL의 객체 일치 | 학생·타인·다른 URL/작업 ID | `/rag/embeddings/**`, `/document/**` | task 소유/자료 연결, 권한 거부 시 enqueue 없음 |

## 학생 정답과 제출 후 피드백

학생 문제 응답은 허용 필드를 명시한 DTO다. 정답/교사용 채점기준은 문제 GET, 공유 자료 JSON, 다운로드, 북마크, 학생 RAG 입력에서 제외한다. 교사 편집용 JSON과 응답은 소유 교사에게 유지한다. 학생에게 원본/교사 편집 파일의 서명 URL을 우회 제공하지 않고 학생용 안전 자료 조회를 사용한다.

정상 제출 후에는 **해당 제출 문제에 한해 서버 DB의 정답·채점 결과·학습 피드백**을 공개한다. 임의 정답·점수·studentId를 추가해 기록 소유자나 채점 기준을 바꿀 수 없다. 같은 요청에 다른 자료의 quiz가 섞이면 부작용 전에 거부한다. 일반 교재의 지식으로 정답을 추론하는 행위까지 방지한다고 주장하지 않는다.

## 데이터·외부 경계

기존 자료/공유/사용자를 재소유하거나 전체 DB를 만들지 않는다. 추가 합성 fixture는 구별되는 계정/키로 idempotent하게 추가하며 기존 fixture는 보존한다. 현재 읽기 전용인 local 저장 대역은 정상 교사 저장 검증에 필요한 합성 객체의 쓰기/읽기만 지원하도록 좁게 확장할 수 있다. 실제 AWS/LLM/OCR 호출은 하지 않는다.

새 객체가 commit되기 전에 AI가 권한 DB를 조회하면 잘못404가 되므로 필요한 호출만 commit 이후로 옮기거나 기존 트랜잭션 경계를 최소 조정한다. 채점 비동기화·멱등성·임베딩 버전 전환 전체 개편은 하지 않는다. 이미 발급된 서명 URL의 즉시 철회, SSRF 전면 방어, 운영 배포 검증은 별도 미완료 항목이다.

## 구현·검증 연결

Spring 정책은 `be/src/main/java/A704/DODREAM/authorization/AuthorizationPolicy.java`, 학생 JSON 허용 목록은 같은 폴더의 `StudentContent.java`, 학생 퀴즈는 `quiz/dto/StudentQuizDto.java`에 있다. FastAPI의 대응 정책은 `ai/app/security/authorization.py`다. 실제 기존 파일 컬럼 이름은 `s3key/jsons3key`이며 Python ORM 속성 이름과 구분한다.

| 정책 | 실제 검증 식별자/메서드 |
|---|---|
| 소유 파일/자료, 역할과 객체 구분 | HTTP `owner_download_positive`, `other_download`, `student_signed_raw_url`; Spring `realOwnerAndExplicitSharedStudentAreAllowed`, `fileOperationsRejectStudentRoleBeforeObjectLookup` |
| 직접/CLASS 공유와 서로 다른 User/Profile ID | HTTP `user_profile_ids_are_distinct`, `class_share_positive`, `unshared_quiz_denied`; 양측 DB 테스트의 `classShareRequiresExplicitRowAndCurrentClass` / `test_direct_and_class_share_positive_with_distinct_profile_ids` |
| 공유·담당 회수 | HTTP `share_revoked_quiz`, `share_revoked_rag`, `current_assignment_revoked_ai`; Spring `revokingAssignmentAlsoRevokesIndividualShareAndTeacherHistory`; AI `test_assignment_revocation_applies_to_individual_and_class_share` |
| 학생 응답·연결 JSON·북마크 | HTTP `student_quiz_allowlist`, `student_json_nested_answer_exclusion`, `bookmark_answer_exclusion`; Spring `nestedTeacherAnswersAreNotLearningContent`; AI `test_legacy_quiz_answer_chunks_are_excluded_from_student_search` |
| 제출 ID 일치와 서버 정답/기록 소유자 | HTTP `quiz_cross_material_be`, `quiz_cross_material_ai`, `submit_feedback_uses_server_answer`, `submit_ignores_forged_record_owner` |
| 소유/담당/현재 공유가 모두 필요한 이력 | HTTP `assigned_owner_history_positive`, `other_history_detail`, `cross_student_history`; AI `test_history_list_and_detail_require_owner_assignment_and_current_share` |
| 세션 사용자와 자료 고정 | HTTP `session_cross_document_both_shared`, `session_cross_user`; AI `test_accessible_document_switch_is_409_and_other_user_session_is_404` |
| 초기본·문자열 충돌·작업 소유·삭제 자료 | HTTP `initial_url_mismatch`, `other_task_status`, `softdeleted_initial_ai`; AI `test_noncanonical_and_colliding_document_ids_are_400`, `test_deleted_linked_file_is_not_an_initial_document_bypass` |
| 부작용 전 검증 | HTTP `denial_group_no_mysql_or_rag_rows_changed`; Spring `realDatabaseDenialDoesNotSignOrAccessObjectStorage`, `mixedShareTargetsCauseNoPartialWriteStorageOrNotification`; AI `test_embedding_denials_happen_before_metadata_and_enqueue`, `test_database_permission_error_is_503_and_has_no_side_effects` |

실제 HTTP 식별자는 `scripts/local/verify_authorization.py`, Spring DB 검사는 `be/src/test/java/A704/DODREAM/authorization/AuthorizationDatabaseTests.java`, AI DB 검사는 `ai/tests/test_object_authorization.py`에 있다. Spring은 실제 MySQL/JPA, AI 단위검사는 동일 FK 의미의 임시 SQLite와 실제 JWT 검증을 사용한다. 서비스 간 같은 합성 관계는 실제 MySQL에 연결한 HTTP 검사에서 추가로 확인한다.

교사 목록은 이름이 `/published`여도 기존 계약에 따라 본인 DRAFT를 포함한다. 학생에게 DRAFT를 허용한다는 뜻은 아니다. 학생 자신의 RAG 목록·상세 조회는 본인 student_id와 현재 유효 공유로 제한한다. 교사의 기존 목록·상세 계약도 유지하며 비담당·다른 소유자 자료는 거부/필터한다.

정상 퀴즈 편집은 같은 question_number의 행 ID를 유지하여 기존 풀이 FK를 보존한다. 풀이가 존재하는 문제 삭제는 저장/외부 쓰기 전409로 거부한다. 과거 풀이에는 정답 버전 snapshot이 없으므로 이력의 정답은 현재 서버 문제 기준이며 과거 시점 정답 보존을 보장하지 않는다. 전체 채점 멱등성/버전 전환 설계는 다음 단계다.
