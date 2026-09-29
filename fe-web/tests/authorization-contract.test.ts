import test from 'node:test';
import assert from 'node:assert/strict';
import { quizDocumentId } from '../src/utils/quizDocumentId.ts';
import { createAuthSession } from '../src/auth/session.ts';
import { mergeSubmittedQuizResults } from '../../fe_app/src/api/submittedQuizResults.ts';
import type { QuizQuestion } from '../../fe_app/src/types/quiz.ts';

test('teacher quiz generation separates Material IDs from initial UploadedFile IDs', () => {
  assert.equal(quizDocumentId('edit', '23', 71), '23');
  assert.equal(quizDocumentId('create', undefined, 71), 'pdf_71');
  assert.equal(quizDocumentId('edit', '9223372036854775807', 71), '9223372036854775807');
});

test('an editor without its Material ID never falls back to a numeric UploadedFile ID', () => {
  assert.throws(() => quizDocumentId('edit', undefined, 71));
});

test('identifiers are rejected rather than normalized into a different resource', () => {
  for (const id of ['', '01', '+1', '1.0', ' 1', '1 ', 'pdf_1', '1/2', '9223372036854775808']) {
    assert.throws(() => quizDocumentId('edit', id, 71));
  }
  for (const id of [undefined, 0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => quizDocumentId('create', undefined, id));
  }
});

const question = (id: number): QuizQuestion => ({ id, question_type: 'SHORT_ANSWER',
  question_number: id, title: '합성 문제', content: '합성 질문', chapter_reference: '합성 단원' });
const result = (id: number) => ({ question_id: id, student_answer: '학생 제출 답변',
  is_correct: false, ai_feedback: '제출 이후 피드백', correct_answer: '서버 DB 정답 ' + id });

test('student results use only submitted server feedback matched by quiz ID', () => {
  const cached = { ...question(23), correct_answer: '과거 캐시 정답', marking_rubric: '교사 전용' };
  const merged = mergeSubmittedQuizResults([cached, question(71)], [result(71), result(23)]);
  assert.equal(merged[0].correct_answer, '서버 DB 정답 23');
  assert.equal(merged[1].correct_answer, '서버 DB 정답 71');
  assert.equal(merged[0].userAnswer, '학생 제출 답변');
  assert.equal(merged[0].feedback, '제출 이후 피드백');
  assert.equal(Object.hasOwn(merged[0], 'marking_rubric'), false);
});

test('missing, duplicate or unrelated submission results cannot fabricate feedback', () => {
  const questions = [question(23), question(71)];
  for (const results of [[result(23)], [result(23), result(23)], [result(23), result(99)]]) {
    assert.throws(() => mergeSubmittedQuizResults(questions, results));
  }
  const { correct_answer: _omitted, ...incomplete } = result(23);
  assert.throws(() => mergeSubmittedQuizResults([question(23)], [incomplete as ReturnType<typeof result>]));
});

for (const status of [400, 403, 404, 409]) {
  test(`authorization HTTP ${status} is returned without refresh or session deletion`, async () => {
    const storage = new Map([['accessToken', 'synthetic-access'], ['isLoggedIn', 'true']]);
    let calls = 0;
    const client = createAuthSession({ origin: 'http://127.0.0.1:15173',
      storage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => { storage.set(key, value); },
        removeItem: key => { storage.delete(key); } },
      fetch: (async () => { calls++; return new Response('{}', { status }); }) as typeof fetch });
    const response = await client.authenticatedFetch('/api/materials/23/quizzes');
    assert.equal(response.status, status);
    assert.equal(client.getToken(), 'synthetic-access');
    assert.equal(storage.get('isLoggedIn'), 'true');
    assert.equal(calls, 1);
  });
}
