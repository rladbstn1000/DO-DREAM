import assert from 'node:assert/strict';
import test from 'node:test';
import { findSample, samples, SAMPLE_VERSION } from '../src/showcase/samples.ts';
import {
  createShowcaseStore, MAX_RESULTS, MAX_STATE_BYTES, MEMORY_NOTICE, RECOVERY_NOTICE, RESET_NOTICE,
  SHOWCASE_STORAGE_KEY, type StorageLike, type ShowcaseStore,
} from '../src/showcase/store.ts';

class MemoryStorage implements StorageLike {
  values = new Map<string, string>();
  writes = 0;
  removed: string[] = [];
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.writes++; this.values.set(key, value); }
  removeItem(key: string) { this.removed.push(key); this.values.delete(key); }
}
const waterId = 'water-journey';
const recyclingId = 'recycling-day';
function complete(store: ShowcaseStore, sampleId = waterId, allCorrect = true) {
  const sample = findSample(sampleId)!;
  sample.quiz.forEach((question) => {
    const choice = allCorrect ? question.correctChoiceId : question.choices.find((option) => option.id !== question.correctChoiceId)!.id;
    store.setAnswer(sampleId, question.id, choice);
  });
  return store.submit(sampleId)!;
}
function fixture() {
  const storage = new MemoryStorage();
  complete(createShowcaseStore(storage));
  return JSON.parse(storage.getItem(SHOWCASE_STORAGE_KEY)!);
}

test('two public samples have readable unique IDs and resolvable local references', () => {
  assert.equal(samples.length, 2);
  assert.equal(new Set(samples.map((sample) => sample.id)).size, 2);
  samples.forEach((sample) => {
    assert.match(sample.id, /^[a-z]+(?:-[a-z]+)+$/);
    assert.equal(sample.sections.length, 3);
    assert.equal(sample.quiz.length, 2);
    sample.recommendations.forEach((question) => {
      const section = sample.sections.find((item) => item.id === question.source.sectionId);
      assert.ok(section?.paragraphs[question.source.paragraphIndex]);
      assert.ok(question.question.length && question.answer.length);
    });
    sample.quiz.forEach((question) => {
      assert.equal(question.choices.filter((choice) => choice.id === question.correctChoiceId).length, 1);
      assert.equal(new Set(question.choices.map((choice) => choice.id)).size, question.choices.length);
    });
  });
  assert.equal(findSample('https://evil.invalid'), undefined);
  assert.equal(findSample('__proto__'), undefined);
});

test('snapshot is stable until a valid change and deeply immutable', () => {
  const store = createShowcaseStore(new MemoryStorage());
  const before = store.getSnapshot();
  assert.equal(before, store.getSnapshot());
  assert.equal(before, store.getCurrentSnapshot());
  assert.equal(store.setSection(waterId, 'water-1'), false);
  assert.equal(before, store.getSnapshot());
  assert.equal(store.setSection(waterId, 'water-2'), true);
  assert.notEqual(before, store.getSnapshot());
  assert.ok(Object.isFrozen(store.getSnapshot()));
  assert.ok(Object.isFrozen(store.getSnapshot().samples[waterId].draft));
  assert.ok(Object.isFrozen(store.getSnapshot().samples[waterId].results));
});

test('read position, font, supported question IDs and draft survive reload', () => {
  const storage = new MemoryStorage();
  const store = createShowcaseStore(storage);
  store.setSection(waterId, 'water-3');
  store.setFontSize(waterId, 26);
  store.rememberQuestion(waterId, 'water-ice');
  store.setAnswer(waterId, 'water-quiz-ice', 'ice');
  const restored = createShowcaseStore(storage).getSnapshot().samples[waterId];
  assert.equal(restored.sectionId, 'water-3');
  assert.equal(restored.fontSize, 26);
  assert.deepEqual(restored.questionIds, ['water-ice']);
  assert.deepEqual(restored.draft, { 'water-quiz-ice': 'ice' });
  assert.equal(restored.result, null);
});

test('only known IDs are stored; unsupported and cross-sample inputs are no-ops', () => {
  const storage = new MemoryStorage();
  const store = createShowcaseStore(storage);
  const before = store.getSnapshot();
  const malicious = '<img src="https://evil.invalid/" onerror="alert(1)">';
  assert.equal(store.setSection(waterId, malicious), false);
  assert.equal(store.setSection(waterId, 'recycling-1'), false);
  assert.equal(store.rememberQuestion(waterId, malicious), false);
  assert.equal(store.rememberQuestion(waterId, 'recycling-guide'), false);
  assert.equal(store.setAnswer(waterId, 'water-quiz-ice', 'javascript:alert(1)'), false);
  assert.equal(store.setAnswer(waterId, 'recycling-quiz-empty', 'empty'), false);
  assert.equal(store.setAnswer('__proto__', 'water-quiz-ice', 'ice'), false);
  assert.equal(store.setFontSize(waterId, 100 as 18), false);
  assert.equal(store.getSnapshot(), before);
  assert.equal(storage.writes, 0);
});

test('supported question history is unique and bounded by the sample', () => {
  const store = createShowcaseStore(new MemoryStorage());
  for (let index = 0; index < 100; index++) {
    store.rememberQuestion(waterId, 'water-ice');
    store.rememberQuestion(waterId, 'water-evaporation');
  }
  assert.deepEqual(store.getSnapshot().samples[waterId].questionIds, ['water-ice', 'water-evaporation']);
});

test('incomplete submission and result lookup never invent a result', () => {
  const store = createShowcaseStore(new MemoryStorage());
  assert.equal(store.submit(waterId), null);
  store.setAnswer(waterId, 'water-quiz-ice', 'ice');
  assert.equal(store.submit(waterId), null);
  assert.equal(store.submit('unknown'), null);
  assert.deepEqual(store.getSnapshot().samples[waterId].results, []);
  assert.equal(store.retry(waterId), false);
});

test('deterministic grading records correct and wrong choices', () => {
  const store = createShowcaseStore(new MemoryStorage());
  store.setAnswer(waterId, 'water-quiz-ice', 'ice');
  store.setAnswer(waterId, 'water-quiz-vapor', 'freeze');
  const result = store.submit(waterId)!;
  assert.equal(result.attemptNumber, 1);
  assert.equal(result.score, 1);
  assert.equal(result.total, 2);
  assert.deepEqual(result.answers.map((answer) => answer.correct), [true, false]);
  assert.ok(Object.isFrozen(result));
  assert.ok(Object.isFrozen(result.answers[0]));
});

test('repeated submission returns the same result without writes or extra attempts', () => {
  const storage = new MemoryStorage();
  const store = createShowcaseStore(storage);
  const result = complete(store);
  const writes = storage.writes;
  for (let index = 0; index < 50; index++) assert.equal(store.submit(waterId), result);
  assert.equal(storage.writes, writes);
  assert.equal(store.getSnapshot().samples[waterId].results.length, 1);
  assert.equal(store.setAnswer(waterId, 'water-quiz-ice', 'cloud'), false);
});

test('explicit retry is a separate attempt and keeps previous results', () => {
  const storage = new MemoryStorage();
  const store = createShowcaseStore(storage);
  const first = complete(store);
  assert.equal(store.retry(waterId), true);
  assert.equal(store.retry(waterId), false);
  let progress = store.getSnapshot().samples[waterId];
  assert.equal(progress.attemptNumber, 2);
  assert.equal(progress.result, null);
  assert.deepEqual(progress.draft, {});
  assert.deepEqual(progress.results, [first]);
  assert.equal(createShowcaseStore(storage).getSnapshot().samples[waterId].result, null);
  const second = complete(store, waterId, false);
  progress = createShowcaseStore(storage).getSnapshot().samples[waterId];
  assert.equal(second.attemptNumber, 2);
  assert.equal(second.score, 0);
  assert.deepEqual(progress.results, [first, second]);
});

test('only the latest ten attempts are retained with bounded serialization', () => {
  const storage = new MemoryStorage();
  const store = createShowcaseStore(storage);
  for (let index = 1; index <= 15; index++) {
    if (index > 1) store.retry(waterId);
    complete(store);
  }
  const progress = createShowcaseStore(storage).getSnapshot().samples[waterId];
  assert.equal(progress.results.length, MAX_RESULTS);
  assert.deepEqual(progress.results.map((result) => result.attemptNumber), [6, 7, 8, 9, 10, 11, 12, 13, 14, 15]);
  assert.equal(progress.results.find((result) => result.attemptNumber === 1), undefined);
  assert.ok(new TextEncoder().encode(storage.getItem(SHOWCASE_STORAGE_KEY)!).byteLength < MAX_STATE_BYTES);
});

test('saved state contains IDs and choices, never prepared prose or trusted scores', () => {
  const storage = new MemoryStorage();
  complete(createShowcaseStore(storage));
  const raw = storage.getItem(SHOWCASE_STORAGE_KEY)!;
  assert.equal(raw.includes('score'), false);
  assert.equal(raw.includes('correct'), false);
  assert.equal(raw.includes(samples[0].quiz[0].explanation), false);
  const altered = JSON.parse(raw);
  altered.samples[waterId].submissions[0].answers['water-quiz-ice'] = 'cloud';
  altered.samples[waterId].draft['water-quiz-ice'] = 'cloud';
  storage.values.set(SHOWCASE_STORAGE_KEY, JSON.stringify(altered));
  const result = createShowcaseStore(storage).getSnapshot().samples[waterId].result!;
  assert.equal(result.score, 1, 'derived again from explicit choices; local state is not a security boundary');
});

const invalidCases: [string, (state: ReturnType<typeof fixture>) => void][] = [
  ['old schema version', (state) => { state.version = 0; }],
  ['old sample version', (state) => { state.sampleVersion = `${SAMPLE_VERSION}-old`; }],
  ['unknown sample ID', (state) => { state.samples['other-document'] = state.samples[waterId]; }],
  ['missing sample', (state) => { delete state.samples[recyclingId]; }],
  ['unexpected top-level auth field', (state) => { state.accessToken = 'synthetic-token'; }],
  ['unknown section', (state) => { state.samples[waterId].sectionId = 'javascript:alert(1)'; }],
  ['malicious stored HTML', (state) => { state.samples[waterId].questionIds = ['<img src=x onerror=alert(1)>']; }],
  ['cross-sample question', (state) => { state.samples[waterId].questionIds = ['recycling-guide']; }],
  ['duplicate question IDs', (state) => { state.samples[waterId].questionIds = ['water-ice', 'water-ice']; }],
  ['invalid font', (state) => { state.samples[waterId].fontSize = 999999; }],
  ['excessive attempt counter', (state) => { state.samples[waterId].attemptNumber = 100000; }],
  ['forged score field', (state) => { state.samples[waterId].submissions[0].score = 999; }],
  ['unknown quiz option', (state) => { state.samples[waterId].submissions[0].answers['water-quiz-ice'] = 'javascript:alert(1)'; }],
  ['submitted draft mismatch', (state) => { state.samples[waterId].draft['water-quiz-ice'] = 'cloud'; }],
  ['duplicate attempt', (state) => { state.samples[waterId].submissions.push(state.samples[waterId].submissions[0]); }],
  ['missing submitted answer', (state) => { delete state.samples[waterId].submissions[0].answers['water-quiz-vapor']; }],
  ['attempt gap', (state) => { state.samples[waterId].attemptNumber = 3; }],
];
for (const [name, mutate] of invalidCases) {
  test(`reject ${name} and recover only the owned state`, () => {
    const state = fixture();
    mutate(state);
    const storage = new MemoryStorage();
    storage.values.set('accessToken', 'synthetic-token');
    storage.values.set(SHOWCASE_STORAGE_KEY, JSON.stringify(state));
    const store = createShowcaseStore(storage);
    assert.equal(store.getSnapshot().notice, RECOVERY_NOTICE);
    assert.equal(store.getSnapshot().samples[waterId].result, null);
    assert.equal(store.getSnapshot().samples[waterId].attemptNumber, 1);
    assert.equal(storage.getItem('accessToken'), 'synthetic-token');
    assert.deepEqual(storage.removed, [SHOWCASE_STORAGE_KEY]);
  });
}

for (const [name, raw] of [
  ['broken JSON', '{'],
  ['null JSON', 'null'],
  ['array JSON', '[]'],
  ['oversized ASCII', 'x'.repeat(MAX_STATE_BYTES + 1)],
  ['oversized UTF-8', '가'.repeat(Math.floor(MAX_STATE_BYTES / 2))],
  ['prototype-shaped object', '{"__proto__":{"role":"teacher"}}'],
] as const) {
  test(`reject ${name} without rendering or evaluating it`, () => {
    const storage = new MemoryStorage();
    storage.values.set(SHOWCASE_STORAGE_KEY, raw);
    assert.equal(createShowcaseStore(storage).getSnapshot().notice, RECOVERY_NOTICE);
    assert.equal(storage.getItem(SHOWCASE_STORAGE_KEY), null);
  });
}

test('missing or unreadable storage preserves a memory-only experience with a notice', () => {
  const throwing: StorageLike = {
    getItem() { throw new Error('denied'); },
    setItem() { throw new Error('denied'); },
    removeItem() { throw new Error('denied'); },
  };
  for (const storage of [undefined, throwing]) {
    const store = createShowcaseStore(storage);
    assert.equal(store.getSnapshot().notice, MEMORY_NOTICE);
    assert.equal(complete(store).score, 2);
    store.reset();
    assert.equal(store.getSnapshot().samples[waterId].result, null);
    assert.equal(store.getSnapshot().notice, storage ? RESET_NOTICE : MEMORY_NOTICE);
  }
});

test('write failure changes to memory mode without losing the current result', () => {
  const storage = new MemoryStorage();
  const store = createShowcaseStore(storage);
  storage.setItem = () => { throw new Error('quota'); };
  assert.equal(complete(store).score, 2);
  assert.equal(store.getSnapshot().notice, MEMORY_NOTICE);
  assert.equal(store.submit(waterId), store.getSnapshot().samples[waterId].result);
});

test('quota failure may retain older progress, but reset still removes the owned key', () => {
  const storage = new MemoryStorage();
  const store = createShowcaseStore(storage);
  store.setSection(waterId, 'water-2');
  storage.setItem = () => { throw new Error('quota'); };
  store.setFontSize(waterId, 26);
  assert.equal(store.getSnapshot().samples[waterId].fontSize, 26);
  assert.equal(createShowcaseStore(storage).getSnapshot().samples[waterId].fontSize, 18);
  assert.equal(store.getSnapshot().notice, MEMORY_NOTICE);
  store.reset();
  assert.equal(storage.getItem(SHOWCASE_STORAGE_KEY), null);
  assert.equal(createShowcaseStore(storage).getSnapshot().samples[waterId].sectionId, 'water-1');
});

test('failed reset clears memory and explicitly reports that older stored results may remain', () => {
  const storage = new MemoryStorage();
  const store = createShowcaseStore(storage);
  complete(store);
  storage.removeItem = () => { throw new Error('denied'); };
  store.reset();
  assert.equal(store.getSnapshot().samples[waterId].result, null);
  assert.equal(store.getSnapshot().notice, RESET_NOTICE);
  assert.equal(createShowcaseStore(storage).getSnapshot().samples[waterId].result?.score, 2);
  store.reset();
  assert.equal(store.getSnapshot().notice, RESET_NOTICE);
});

test('unreadable corrupt-key removal still enters memory mode', () => {
  const storage = new MemoryStorage();
  storage.values.set(SHOWCASE_STORAGE_KEY, 'broken');
  storage.removeItem = () => { throw new Error('denied'); };
  const store = createShowcaseStore(storage);
  assert.equal(store.getSnapshot().notice, MEMORY_NOTICE);
  assert.equal(complete(store).score, 2);
});

test('reset removes exactly the showcase key and retains synthetic real-service keys', () => {
  const storage = new MemoryStorage();
  for (const key of ['accessToken', 'isLoggedIn', 'role', 'pending', 'unrelated.preference']) storage.values.set(key, 'synthetic');
  const store = createShowcaseStore(storage);
  complete(store);
  store.reset();
  assert.deepEqual(storage.removed, [SHOWCASE_STORAGE_KEY]);
  assert.equal(storage.getItem(SHOWCASE_STORAGE_KEY), null);
  for (const key of ['accessToken', 'isLoggedIn', 'role', 'pending', 'unrelated.preference']) assert.equal(storage.getItem(key), 'synthetic');
  assert.equal(createShowcaseStore(storage).getSnapshot().notice, null);
});

test('independent contexts and samples do not share progress', () => {
  const first = createShowcaseStore(new MemoryStorage());
  const second = createShowcaseStore(new MemoryStorage());
  complete(first);
  assert.equal(first.getSnapshot().samples[recyclingId].result, null);
  assert.equal(second.getSnapshot().samples[waterId].result, null);
  assert.equal(complete(second, recyclingId, false).score, 0);
  assert.equal(first.getSnapshot().samples[recyclingId].result, null);
});

test('subscription cleanup and disposal prevent late notifications', () => {
  const store = createShowcaseStore(new MemoryStorage());
  let calls = 0;
  const unsubscribe = store.subscribe(() => { calls++; });
  store.setSection(waterId, 'water-2');
  assert.equal(calls, 1);
  unsubscribe();
  store.setSection(waterId, 'water-3');
  assert.equal(calls, 1);
  store.subscribe(() => { calls++; });
  store.dispose();
  store.reset();
  assert.equal(calls, 1);
});
