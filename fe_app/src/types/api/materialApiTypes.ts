/**
 * 공유받은 단일 학습 자료 정보 (목록용)
 * GET /api/materials/shared 응답의 materials 요소
 */
export interface SharedMaterialSummary {
  shareId: number;
  materialId: number;
  materialTitle: string;
  teacherId: number;
  teacherName: string;
  sharedAt: string;   // ISO 문자열
  accessedAt: string | null; // 아직 열어보지 않았다면 null 또는 빈 값일 수 있음
  accessed: boolean;  // true면 한 번 이상 열어봄
}

/**
 * 공유받은 학습 자료 목록 응답
 * GET /api/materials/shared
 */
export interface SharedMaterialsResponse {
  studentId: number;
  studentName: string;
  totalCount: number;
  materials: SharedMaterialSummary[];
}

/**
 * 학생 교재 JSON의 문제 구조. 정답은 정상 제출 후 결과에서만 제공한다.
 * - type === "quiz" 인 chapter에서 사용
 */
export interface MaterialJsonQA {
  question: string;
}

/**
 * 교재 JSON의 단일 챕터 구조
 * - type: "content" | "quiz"
 * - content: HTML 문자열
 * - qa: quiz일 때만 존재
 */
export interface MaterialJsonChapter {
  id: string;
  title: string;
  content: string;
  type: "content" | "quiz";
  qa?: MaterialJsonQA[];
}

/**
 * 공유받은 자료 JSON 전체 구조
 * GET /api/materials/shared/{materialId}/json
 */
export interface MaterialJson {
  chapters: MaterialJsonChapter[];
}
