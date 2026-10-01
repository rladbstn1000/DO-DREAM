import assert from 'node:assert/strict';
import test from 'node:test';
import {
  createOriginalStore,
  ORIGINAL_STORAGE_KEY,
  ORIGINAL_MAX_BYTES,
  writtenQuestions,
} from '../src/showcase/originalStore.ts';
import { createShowcaseStore } from '../src/showcase/store.ts';
function memory(seed?: string) {
  const data = new Map<string, string>([['unrelated', 'keep']]);
  if (seed !== undefined) data.set(ORIGINAL_STORAGE_KEY, seed);
  return {
    data,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => {
      data.set(k, v);
    },
    removeItem: (k: string) => {
      data.delete(k);
    },
  };
}
const answer = (s: ReturnType<typeof createOriginalStore>) => {
  s.setWrittenAnswer('water-journey', 'water-quiz-ice', '얼음');
  s.setWrittenAnswer('water-journey', 'water-quiz-vapor', '증발');
};
test('sample edits, settings and bookmarks persist only in the owned tab state', () => {
  const storage = memory();
  const a = createOriginalStore(storage);
  const m = a.getSnapshot().materials['water-journey'];
  assert.equal(
    a.updateMaterial('water-journey', {
      title: '함께 읽는 물의 여행',
      chapters: m.chapters.map((c, i) =>
        i === 0 ? { ...c, text: '직접 고친 샘플 본문입니다.' } : c,
      ),
      published: false,
    }),
    true,
  );
  a.setSettings({ highContrast: true, fontScale: 1.5, rate: 1.2 });
  a.toggleBookmark('water-journey', 'water-2');
  a.setMemo('샘플 수업 준비');
  const b = createOriginalStore(storage);
  assert.equal(
    b.getSnapshot().materials['water-journey'].chapters[0].text,
    '직접 고친 샘플 본문입니다.',
  );
  assert.equal(b.getSnapshot().settings.fontScale, 1.5);
  assert.deepEqual(b.getSnapshot().bookmarks['water-journey'], ['water-2']);
  assert.equal(b.getSnapshot().memo, '샘플 수업 준비');
  assert.equal(storage.data.get('unrelated'), 'keep');
});
test('written quiz requires every nonempty answer and grades only listed exact examples', () => {
  const s = createOriginalStore(memory());
  assert.equal(s.submitWrittenQuiz('water-journey'), null);
  s.setWrittenAnswer('water-journey', 'water-quiz-ice', '얼음');
  s.setWrittenAnswer('water-journey', 'water-quiz-vapor', '   ');
  assert.equal(s.submitWrittenQuiz('water-journey'), null);
  s.setWrittenAnswer('water-journey', 'water-quiz-vapor', '증발과 비슷한 현상');
  assert.equal(s.submitWrittenQuiz('water-journey')?.score, 1);
  assert.equal(writtenQuestions('water-journey')[0].expectedAnswer, '얼음');
});
test('duplicate submit and reload retain one immutable written result', () => {
  const storage = memory(),
    s = createOriginalStore(storage);
  answer(s);
  const result = s.submitWrittenQuiz('water-journey');
  assert.equal(s.submitWrittenQuiz('water-journey'), result);
  assert.equal(
    s.setWrittenAnswer('water-journey', 'water-quiz-ice', '모래'),
    false,
  );
  assert.equal(
    createOriginalStore(storage).getSnapshot().quizzes['water-journey'].results
      .length,
    1,
  );
  assert.equal(result?.score, 2);
  assert.throws(() => {
    result!.score = 0;
  });
});
test('retry is explicit, capped to recent ten results, and other sample remains separate', () => {
  const storage = memory(),
    s = createOriginalStore(storage);
  assert.equal(s.retryWrittenQuiz('water-journey'), false);
  for (let i = 0; i < 12; i++) {
    answer(s);
    s.submitWrittenQuiz('water-journey');
    if (i < 11) assert.equal(s.retryWrittenQuiz('water-journey'), true);
  }
  const q = createOriginalStore(storage).getSnapshot().quizzes;
  assert.equal(q['water-journey'].results.length, 10);
  assert.equal(q['water-journey'].results[0].attemptNumber, 3);
  assert.equal(q['recycling-day'].results.length, 0);
});
test('score injection and malformed state are rejected rather than trusted', () => {
  const storage = memory(),
    s = createOriginalStore(storage);
  answer(s);
  s.submitWrittenQuiz('water-journey');
  const valid = JSON.parse(storage.getItem(ORIGINAL_STORAGE_KEY)!);
  for (const alter of [
    (x: any) => (x.quizzes['water-journey'].submissions[0].score = 999),
    (x: any) => (x.settings.highContrast = 'true'),
    (x: any) => (x.materials['water-journey'].chapters[0].id = 'unknown'),
    (x: any) => (x.bookmarks['water-journey'] = ['water-1', 'water-1']),
    (x: any) => (x.quizzes['water-journey'].draft['unknown'] = 'answer'),
    (x: any) => (x.version = 999),
  ]) {
    const x = structuredClone(valid);
    alter(x);
    const fresh = createOriginalStore(memory(JSON.stringify(x)));
    assert.match(fresh.getSnapshot().notice!, /처음부터/);
    assert.equal(fresh.getSnapshot().quizzes['water-journey'].result, null);
  }
});
test('limits and unknown identifiers fail without changing state', () => {
  const s = createOriginalStore(memory());
  const before = s.getSnapshot();
  for (const ok of [
    s.updateMaterial('missing', { title: 'x' }),
    s.updateMaterial('water-journey', { title: 'x'.repeat(121) }),
    s.setSettings({ rate: 99 }),
    s.setWrittenAnswer('water-journey', 'missing', 'x'),
    s.setWrittenAnswer('water-journey', 'water-quiz-ice', 'x'.repeat(501)),
    s.toggleBookmark('water-journey', 'unknown'),
    s.setMemo('x'.repeat(1001)),
  ])
    assert.equal(ok, false);
  assert.equal(s.getSnapshot(), before);
  assert.equal(
    createOriginalStore(
      memory('x'.repeat(ORIGINAL_MAX_BYTES + 1)),
    ).getSnapshot().quizzes['water-journey'].result,
    null,
  );
});
test('raw HTML is only sample text, never evaluated or promoted to a URL', () => {
  const s = createOriginalStore(memory());
  const payload = '<img src="https://not-allowed.invalid" onerror="alert(1)">';
  const m = s.getSnapshot().materials['water-journey'];
  s.updateMaterial('water-journey', {
    chapters: m.chapters.map((c, i) => (i === 0 ? { ...c, text: payload } : c)),
  });
  s.setWrittenAnswer('water-journey', 'water-quiz-ice', payload);
  s.setWrittenAnswer('water-journey', 'water-quiz-vapor', '증발');
  assert.equal(s.submitWrittenQuiz('water-journey')!.score, 1);
  assert.equal(
    s.getSnapshot().materials['water-journey'].chapters[0].text,
    payload,
  );
});
test('storage access/write/delete failure remains usable and explains restoration limits', () => {
  const s = createOriginalStore({
    getItem() {
      throw Error('blocked');
    },
    setItem() {
      throw Error('quota');
    },
    removeItem() {
      throw Error('blocked');
    },
  });
  assert.match(s.getSnapshot().notice!, /현재 화면/);
  answer(s);
  assert.equal(s.submitWrittenQuiz('water-journey')!.score, 2);
  s.reset();
  assert.match(s.getSnapshot().notice!, /지우지 못/);
  assert.equal(s.getSnapshot().quizzes['water-journey'].result, null);
});
test('quota failure still attempts explicit owned-key removal and retains unrelated data', () => {
  const storage = memory(),
    s = createOriginalStore({
      ...storage,
      setItem() {
        throw Error('quota');
      },
    });
  s.setMemo('temporary');
  assert.match(s.getSnapshot().notice!, /임시 저장소/);
  s.reset();
  assert.equal(storage.data.get('unrelated'), 'keep');
  assert.equal(storage.data.has(ORIGINAL_STORAGE_KEY), false);
});
test('question list deletion updates both student and teacher shared sample history', () => {
  const s = createShowcaseStore(memory());
  s.rememberQuestion('water-journey', 'water-ice');
  s.rememberQuestion('water-journey', 'water-evaporation');
  assert.equal(s.removeQuestion('water-journey', 'missing'), false);
  assert.equal(s.removeQuestion('water-journey', 'water-ice'), true);
  assert.deepEqual(s.getSnapshot().samples['water-journey'].questionIds, [
    'water-evaporation',
  ]);
  assert.equal(s.clearQuestions('water-journey'), true);
  assert.deepEqual(s.getSnapshot().samples['water-journey'].questionIds, []);
});
test('restoring a sample restores material only, not questions or written results', () => {
  const s = createOriginalStore(memory());
  answer(s);
  s.submitWrittenQuiz('water-journey');
  s.updateMaterial('water-journey', { title: '수정함' });
  s.restoreMaterial('water-journey');
  assert.equal(s.getSnapshot().materials['water-journey'].title, '물의 여행');
  assert.equal(s.getSnapshot().quizzes['water-journey'].results.length, 1);
});

test('dynamic chapters propagate with safe identifiers, bounded counts and owned progress/bookmark cleanup', () => {
  const storage = memory(),
    s = createOriginalStore(storage);
  const m = s.getSnapshot().materials['water-journey'];
  assert.equal(
    s.updateMaterial('water-journey', {
      chapters: [
        ...m.chapters,
        { id: 'chapter-extra', title: '새 챕터', text: '' },
      ],
    }),
    true,
  );
  assert.equal(s.setSection('water-journey', 'chapter-extra'), true);
  s.toggleBookmark('water-journey', 'chapter-extra');
  assert.equal(
    createOriginalStore(storage).getSnapshot().positions['water-journey'],
    'chapter-extra',
  );
  assert.equal(
    s.updateMaterial('water-journey', { chapters: m.chapters }),
    true,
  );
  assert.equal(s.getSnapshot().positions['water-journey'], 'water-1');
  assert.deepEqual(s.getSnapshot().bookmarks['water-journey'], []);
  for (const chapters of [
    [],
    [m.chapters[0], m.chapters[0]],
    [{ id: '<script>', title: 'unsafe id', text: '' }],
    Array.from({ length: 21 }, (_, i) => ({
      id: `chapter-${i}`,
      title: 'test',
      text: '',
    })),
  ])
    assert.equal(s.updateMaterial('water-journey', { chapters }), false);
});
test('settings accept original tenth steps and reject nonfinite or out of range values', () => {
  const s = createOriginalStore(memory());
  assert.equal(s.setSettings({ rate: 1.1, pitch: 0.9, volume: 0.8 }), true);
  for (const rate of [NaN, Infinity, 0.49, 2.1, 1.15])
    assert.equal(s.setSettings({ rate }), false);
});
