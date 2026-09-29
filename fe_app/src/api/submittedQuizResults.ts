import type { QuizQuestion } from '../types/quiz';
import type { QuizGradingResultItem, RawQuizGradingResult } from '../types/api/quizApiTypes';

/** Answers are supplied only by the successful submission response, never a cached question. */
export function mergeSubmittedQuizResults(
  questions: QuizQuestion[], results: RawQuizGradingResult[],
): QuizGradingResultItem[] {
  const byId = new Map(results.map(result => [result.question_id, result]));
  if (byId.size !== results.length || results.length !== questions.length) {
    throw new Error('채점 결과를 확인하지 못했습니다. 다시 시도해주세요.');
  }
  return questions.map(question => {
    const result = byId.get(question.id);
    if (!result || typeof result.correct_answer !== 'string' ||
        typeof result.student_answer !== 'string' || typeof result.is_correct !== 'boolean' ||
        typeof result.ai_feedback !== 'string') {
      throw new Error('채점 결과를 확인하지 못했습니다. 다시 시도해주세요.');
    }
    return {
      id: question.id,
      question_type: question.question_type,
      question_number: question.question_number,
      title: question.title,
      content: question.content,
      chapter_reference: question.chapter_reference,
      correct_answer: result.correct_answer,
      userAnswer: result.student_answer,
      isCorrect: result.is_correct,
      feedback: result.ai_feedback,
    };
  });
}
