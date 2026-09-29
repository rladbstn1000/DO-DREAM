import apiClient from './apiClient';
import type { QuizQuestion } from '../types/quiz';
import { createQuizSubmission } from './quizSubmission';
import type { SubmissionView } from './quizSubmission';
import { nativeAuth } from './interceptors';
import { getAccessToken } from '../services/authStorage';
import { mergeSubmittedQuizResults } from './submittedQuizResults';

/**
 * 특정 학습자료의 퀴즈 목록을 조회합니다.
 * @param materialId 학습자료 ID
 * @returns Promise<QuizQuestion[]>
 */
export const fetchQuizzes = async (materialId: number | string): Promise<QuizQuestion[]> => {
  try {
    const response = await apiClient.get<QuizQuestion[]>(`/api/materials/${materialId}/quizzes`);
    return response.data;
  } catch (error) {
    console.error('[API] fetchQuizzes 에러:', error);
    throw error;
  }
};

/** A logical submission owns its key, immutable request and explicit recovery state. */
export function createNativeQuizSubmission(
  materialId: number | string, questions: QuizQuestion[], changed: (view: SubmissionView) => void,
) {
  return createQuizSubmission({ materialId, questions, changed, mergeResults: mergeSubmittedQuizResults,
    session: () => getAccessToken() ? nativeAuth.getEpoch() : null,
    request: async request => {
      // The existing interceptor reuses this header and body after its one AT refresh.
      // Non-auth responses are interpreted here without propagating Axios request/token data.
      const response = await apiClient.request({ method: request.method, url: request.path, data: request.body,
        headers: { 'Idempotency-Key': request.key }, timeout: 20000,
        validateStatus: status => status !== 401 });
      return { status: response.status, data: response.data,
        attemptId: response.headers['x-grading-attempt-id'], state: response.headers['x-grading-state'] };
    },
  });
}
