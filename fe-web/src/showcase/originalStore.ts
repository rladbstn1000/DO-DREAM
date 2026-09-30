import { samples, findSample } from './samples.ts';
import {
  MEMORY_NOTICE,
  RECOVERY_NOTICE,
  RESET_NOTICE,
  type StorageLike,
} from './store.ts';

/** Presentation-only state for the original UI port. Never an identity or server adapter. */
export const ORIGINAL_STORAGE_KEY = 'dodream.showcase.original-ui.v1';
export const ORIGINAL_MAX_BYTES = 128 * 1024;
export type OriginalChapter = { id: string; title: string; text: string };
export type OriginalMaterial = {
  title: string;
  chapters: OriginalChapter[];
  published: boolean;
  label: string;
};
export type OriginalSettings = {
  highContrast: boolean;
  fontScale: 1 | 1.2 | 1.5;
  rate: number;
  pitch: number;
  volume: number;
};
export type WrittenQuestion = {
  id: string;
  prompt: string;
  expectedAnswer: string;
  acceptedAnswers: readonly string[];
  explanation: string;
};
export type WrittenResult = {
  attemptNumber: number;
  score: number;
  total: number;
  answers: {
    questionId: string;
    answer: string;
    expectedAnswer: string;
    correct: boolean;
    explanation: string;
  }[];
};
type Submission = { attemptNumber: number; answers: Record<string, string> };
type QuizProgress = {
  attemptNumber: number;
  draft: Record<string, string>;
  submissions: Submission[];
};
type Saved = {
  version: 1;
  materials: Record<string, OriginalMaterial>;
  memo: string;
  settings: OriginalSettings;
  bookmarks: Record<string, string[]>;
  positions: Record<string, string>;
  quizzes: Record<string, QuizProgress>;
};
export type OriginalSnapshot = Omit<Saved, 'quizzes'> & {
  notice: string | null;
  quizzes: Record<
    string,
    Omit<QuizProgress, 'submissions'> & {
      result: WrittenResult | null;
      results: WrittenResult[];
    }
  >;
};
const labels = ['red', 'orange', 'yellow', 'green', 'blue', 'purple', 'gray'];
const settings = (): OriginalSettings => ({
  highContrast: false,
  fontScale: 1,
  rate: 1,
  pitch: 1,
  volume: 1,
});
const normalize = (text: string) => text.trim().replace(/\s+/g, ' ');
const accepted: Record<string, readonly string[]> = {
  'water-quiz-ice': ['얼음', '얼음이 됩니다', '얼음이 됩니다.'],
  'water-quiz-vapor': ['증발', '증발입니다', '증발입니다.'],
  'recycling-quiz-empty': [
    '비워요',
    '먼저 비워요',
    '내용물을 비워요',
    '내용물을 먼저 비웁니다.',
  ],
  'recycling-quiz-guide': [
    '거주 지역의 안내를 확인해요',
    '지역 안내를 확인해요',
    '거주 지역의 분리배출 안내를 확인합니다.',
  ],
};
export function writtenQuestions(sampleId: string): WrittenQuestion[] {
  return (findSample(sampleId)?.quiz ?? []).map((q) => ({
    id: q.id,
    prompt: q.prompt,
    expectedAnswer: q.choices.find((c) => c.id === q.correctChoiceId)!.text,
    acceptedAnswers: accepted[q.id],
    explanation: q.explanation,
  }));
}
function defaults(): Saved {
  return {
    version: 1,
    materials: Object.fromEntries(
      samples.map((s, i) => [
        s.id,
        {
          title: s.title,
          chapters: s.sections.map((c) => ({
            id: c.id,
            title: c.title,
            text: c.paragraphs.join('\n\n'),
          })),
          published: true,
          label: labels[i],
        },
      ]),
    ),
    memo: '',
    settings: settings(),
    positions: Object.fromEntries(samples.map((s) => [s.id, s.sections[0].id])),
    bookmarks: Object.fromEntries(samples.map((s) => [s.id, []])),
    quizzes: Object.fromEntries(
      samples.map((s) => [
        s.id,
        { attemptNumber: 1, draft: {}, submissions: [] },
      ]),
    ),
  };
}
const object = (x: unknown): x is Record<string, unknown> =>
  typeof x === 'object' &&
  x !== null &&
  !Array.isArray(x) &&
  Object.getPrototypeOf(x) === Object.prototype;
const keys = (x: Record<string, unknown>, expected: string[]) =>
  Object.keys(x).length === expected.length &&
  expected.every((k) => Object.prototype.hasOwnProperty.call(x, k));
const text = (x: unknown, max: number, empty = true): x is string =>
  typeof x === 'string' && x.length <= max && (empty || x.trim().length > 0);
function answers(
  x: unknown,
  sampleId: string,
  complete: boolean,
): x is Record<string, string> {
  const qs = writtenQuestions(sampleId);
  return (
    object(x) &&
    Object.keys(x).length <= qs.length &&
    (!complete || Object.keys(x).length === qs.length) &&
    Object.entries(x).every(
      ([id, value]) =>
        qs.some((q) => q.id === id) && text(value, 500, !complete),
    )
  );
}
const stepNumber = (x: unknown, min: number, max: number) =>
  typeof x === 'number' &&
  Number.isFinite(x) &&
  x >= min &&
  x <= max &&
  Math.abs(x * 10 - Math.round(x * 10)) < 1e-8;
function valid(x: unknown): x is Saved {
  if (
    !object(x) ||
    !keys(x, [
      'version',
      'materials',
      'memo',
      'settings',
      'bookmarks',
      'positions',
      'quizzes',
    ]) ||
    x.version !== 1 ||
    !text(x.memo, 1000) ||
    !object(x.settings) ||
    !keys(x.settings, [
      'highContrast',
      'fontScale',
      'rate',
      'pitch',
      'volume',
    ]) ||
    typeof x.settings.highContrast !== 'boolean' ||
    ![1, 1.2, 1.5].includes(x.settings.fontScale as number) ||
    !stepNumber(x.settings.rate, 0.5, 2) ||
    !stepNumber(x.settings.pitch, 0.5, 2) ||
    !stepNumber(x.settings.volume, 0, 1)
  )
    return false;
  const ids = samples.map((s) => s.id);
  if (
    ![x.materials, x.bookmarks, x.positions, x.quizzes].every(
      (v) => object(v) && keys(v, ids),
    )
  )
    return false;
  return samples.every((s) => {
    const m = (x.materials as Record<string, unknown>)[s.id],
      bookmarks = (x.bookmarks as Record<string, unknown>)[s.id],
      q = (x.quizzes as Record<string, unknown>)[s.id];
    if (
      !object(m) ||
      !keys(m, ['title', 'chapters', 'published', 'label']) ||
      !text(m.title, 120, false) ||
      typeof m.published !== 'boolean' ||
      !labels.includes(m.label as string) ||
      !Array.isArray(m.chapters) ||
      m.chapters.length < 1 ||
      m.chapters.length > 20 ||
      !m.chapters.every(
        (c) =>
          object(c) &&
          keys(c, ['id', 'title', 'text']) &&
          typeof c.id === 'string' &&
          /^[a-z0-9-]{1,80}$/.test(c.id) &&
          text(c.title, 120, false) &&
          text(c.text, 5000),
      ) ||
      new Set(m.chapters.map((c) => c.id)).size !== m.chapters.length
    )
      return false;
    if (
      !Array.isArray(bookmarks) ||
      bookmarks.length > m.chapters.length ||
      new Set(bookmarks).size !== bookmarks.length ||
      !bookmarks.every((id) =>
        (m.chapters as OriginalChapter[]).some((c) => c.id === id),
      ) ||
      !(m.chapters as OriginalChapter[]).some(
        (c) => c.id === (x.positions as Record<string, string>)[s.id],
      )
    )
      return false;
    if (
      !object(q) ||
      !keys(q, ['attemptNumber', 'draft', 'submissions']) ||
      !Number.isInteger(q.attemptNumber) ||
      Number(q.attemptNumber) < 1 ||
      Number(q.attemptNumber) > 99999 ||
      !answers(q.draft, s.id, false) ||
      !Array.isArray(q.submissions) ||
      q.submissions.length > 10
    )
      return false;
    let last = 0;
    for (const row of q.submissions) {
      if (
        !object(row) ||
        !keys(row, ['attemptNumber', 'answers']) ||
        !Number.isInteger(row.attemptNumber) ||
        Number(row.attemptNumber) <= last ||
        (last > 0 && Number(row.attemptNumber) !== last + 1) ||
        Number(row.attemptNumber) > Number(q.attemptNumber) ||
        !answers(row.answers, s.id, true)
      )
        return false;
      last = Number(row.attemptNumber);
    }
    if (
      q.submissions.length !== Math.min(last, 10) ||
      (!last ? q.attemptNumber !== 1 : Number(q.attemptNumber) > last + 1)
    )
      return false;
    const current = q.submissions.find(
      (row) => row.attemptNumber === q.attemptNumber,
    );
    return (
      !current ||
      writtenQuestions(s.id).every(
        (item) =>
          current.answers[item.id] ===
          (q.draft as Record<string, string>)[item.id],
      )
    );
  });
}
function grade(sampleId: string, row: Submission): WrittenResult {
  const result = writtenQuestions(sampleId).map((q) => ({
    questionId: q.id,
    answer: row.answers[q.id],
    expectedAnswer: q.expectedAnswer,
    correct: q.acceptedAnswers.includes(normalize(row.answers[q.id])),
    explanation: q.explanation,
  }));
  return {
    attemptNumber: row.attemptNumber,
    score: result.filter((r) => r.correct).length,
    total: result.length,
    answers: result,
  };
}
function freeze<T>(value: T): T {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}
export function createOriginalStore(storage?: StorageLike) {
  let saved = defaults(),
    activeStorage = storage;
  let notice: string | null = storage ? null : MEMORY_NOTICE;
  const listeners = new Set<() => void>();
  if (storage)
    try {
      const raw = storage.getItem(ORIGINAL_STORAGE_KEY);
      if (raw !== null) {
        try {
          if (new TextEncoder().encode(raw).length > ORIGINAL_MAX_BYTES)
            throw Error('size');
          const value: unknown = JSON.parse(raw);
          if (!valid(value)) throw Error('schema');
          saved = value;
        } catch {
          notice = RECOVERY_NOTICE;
          storage.removeItem(ORIGINAL_STORAGE_KEY);
        }
      }
    } catch {
      activeStorage = undefined;
      notice = MEMORY_NOTICE;
    }
  function snapshot(): OriginalSnapshot {
    const copy = structuredClone(saved);
    return freeze({
      ...copy,
      notice,
      quizzes: Object.fromEntries(
        samples.map((s) => {
          const q = copy.quizzes[s.id];
          const results = q.submissions.map((row) => grade(s.id, row));
          return [
            s.id,
            {
              attemptNumber: q.attemptNumber,
              draft: q.draft,
              results,
              result:
                results.find((r) => r.attemptNumber === q.attemptNumber) ??
                null,
            },
          ];
        }),
      ),
    });
  }
  let current = snapshot();
  function publish(persist = true) {
    if (persist && activeStorage)
      try {
        activeStorage.setItem(ORIGINAL_STORAGE_KEY, JSON.stringify(saved));
      } catch {
        activeStorage = undefined;
        notice = MEMORY_NOTICE;
      }
    current = snapshot();
    listeners.forEach((listener) => listener());
  }
  function update(change: (next: Saved) => void) {
    const next = structuredClone(saved);
    change(next);
    if (
      !valid(next) ||
      new TextEncoder().encode(JSON.stringify(next)).length >
        ORIGINAL_MAX_BYTES ||
      JSON.stringify(next) === JSON.stringify(saved)
    )
      return false;
    saved = next;
    publish();
    return true;
  }
  return {
    getSnapshot: () => current,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    updateMaterial(id: string, patch: Partial<OriginalMaterial>) {
      if (!findSample(id)) return false;
      return update((next) => {
        next.materials[id] = { ...next.materials[id], ...patch };
        const ids = next.materials[id].chapters.map((c) => c.id);
        next.bookmarks[id] = next.bookmarks[id].filter((b) => ids.includes(b));
        if (!ids.includes(next.positions[id])) next.positions[id] = ids[0];
      });
    },
    restoreMaterial(id: string) {
      if (!findSample(id)) return false;
      return update((next) => {
        next.materials[id] = defaults().materials[id];
        next.bookmarks[id] = [];
        next.positions[id] = next.materials[id].chapters[0].id;
      });
    },
    setSection(sampleId: string, sectionId: string) {
      if (
        !current.materials[sampleId]?.chapters.some((s) => s.id === sectionId)
      )
        return false;
      return update((next) => {
        next.positions[sampleId] = sectionId;
      });
    },
    setMemo(memo: string) {
      return update((next) => {
        next.memo = memo;
      });
    },
    setSettings(patch: Partial<OriginalSettings>) {
      return update((next) => {
        next.settings = { ...next.settings, ...patch };
      });
    },
    resetSettings() {
      return update((next) => {
        next.settings = settings();
      });
    },
    toggleBookmark(sampleId: string, sectionId: string) {
      if (
        !current.materials[sampleId]?.chapters.some((s) => s.id === sectionId)
      )
        return false;
      return update((next) => {
        const list = next.bookmarks[sampleId];
        next.bookmarks[sampleId] = list.includes(sectionId)
          ? list.filter((id) => id !== sectionId)
          : [...list, sectionId];
      });
    },
    setWrittenAnswer(sampleId: string, questionId: string, answer: string) {
      if (
        !writtenQuestions(sampleId).some((q) => q.id === questionId) ||
        current.quizzes[sampleId].result
      )
        return false;
      return update((next) => {
        next.quizzes[sampleId].draft[questionId] = answer;
      });
    },
    submitWrittenQuiz(sampleId: string): WrittenResult | null {
      if (!findSample(sampleId)) return null;
      const q = current.quizzes[sampleId];
      if (q.result) return q.result;
      if (!answers(q.draft, sampleId, true)) return null;
      update((next) => {
        const quiz = next.quizzes[sampleId];
        quiz.submissions = [
          ...quiz.submissions,
          { attemptNumber: quiz.attemptNumber, answers: { ...quiz.draft } },
        ].slice(-10);
      });
      return current.quizzes[sampleId].result;
    },
    retryWrittenQuiz(sampleId: string) {
      if (
        !findSample(sampleId) ||
        !current.quizzes[sampleId].result ||
        current.quizzes[sampleId].attemptNumber >= 99999
      )
        return false;
      return update((next) => {
        next.quizzes[sampleId].attemptNumber++;
        next.quizzes[sampleId].draft = {};
      });
    },
    reset() {
      saved = defaults();
      notice = activeStorage ? null : MEMORY_NOTICE;
      if (storage)
        try {
          storage.removeItem(ORIGINAL_STORAGE_KEY);
        } catch {
          activeStorage = undefined;
          notice = RESET_NOTICE;
        }
      publish(false);
    },
    dispose() {
      listeners.clear();
    },
  };
}
export type OriginalStore = ReturnType<typeof createOriginalStore>;
