import { findSample, samples, SAMPLE_VERSION, type Sample } from './samples.ts';

export const SHOWCASE_STORAGE_KEY = 'dodream.showcase.v1.state';
export const MAX_STATE_BYTES = 64 * 1024;
export const MAX_RESULTS = 10;
const MAX_ATTEMPT = 99_999;
export const RECOVERY_NOTICE = '저장된 체험 상태를 읽을 수 없어 처음부터 시작합니다.';
export const MEMORY_NOTICE = '브라우저 임시 저장소를 사용할 수 없어 현재 화면에서만 체험합니다. 새로고침하면 현재 체험이 보존되지 않을 수 있습니다.';
export const RESET_NOTICE = `${MEMORY_NOTICE} 이전 체험의 저장 상태를 지우지 못했습니다.`;

export type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
export type FontSize = 18 | 22 | 26;
type Answers = Record<string, string>;
type Submission = { attemptNumber: number; answers: Answers };
type SavedProgress = {
  sectionId: string;
  fontSize: FontSize;
  questionIds: string[];
  attemptNumber: number;
  draft: Answers;
  submissions: Submission[];
};
type SavedState = { version: 1; sampleVersion: typeof SAMPLE_VERSION; samples: Record<string, SavedProgress> };
export type QuizResult = {
  readonly attemptNumber: number;
  readonly score: number;
  readonly total: number;
  readonly answers: readonly {
    readonly questionId: string;
    readonly choiceId: string;
    readonly correct: boolean;
    readonly correctChoiceId: string;
    readonly explanation: string;
  }[];
};
export type SampleProgress = {
  readonly sectionId: string;
  readonly fontSize: FontSize;
  readonly questionIds: readonly string[];
  readonly attemptNumber: number;
  readonly draft: Readonly<Answers>;
  readonly result: QuizResult | null;
  readonly results: readonly QuizResult[];
};
export type ShowcaseSnapshot = {
  readonly version: 1;
  readonly notice: string | null;
  readonly samples: Readonly<Record<string, SampleProgress>>;
};

function defaults(): SavedState {
  return {
    version: 1, sampleVersion: SAMPLE_VERSION,
    samples: Object.fromEntries(samples.map((sample) => [sample.id, {
      sectionId: sample.sections[0].id, fontSize: 18, questionIds: [],
      attemptNumber: 1, draft: {}, submissions: [],
    }])),
  };
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    && Object.getPrototypeOf(value) === Object.prototype;
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));
}

function validAnswers(value: unknown, sample: Sample, complete: boolean): value is Answers {
  if (!record(value) || Object.keys(value).length > sample.quiz.length) return false;
  if (complete && Object.keys(value).length !== sample.quiz.length) return false;
  return Object.entries(value).every(([questionId, choiceId]) => {
    const question = sample.quiz.find((item) => item.id === questionId);
    return question !== undefined && question.choices.some((choice) => choice.id === choiceId);
  });
}

function validSavedState(value: unknown): value is SavedState {
  if (!record(value) || !exactKeys(value, ['version', 'sampleVersion', 'samples'])
    || value.version !== 1 || value.sampleVersion !== SAMPLE_VERSION || !record(value.samples)
    || !exactKeys(value.samples, samples.map((sample) => sample.id))) return false;
  return samples.every((sample) => {
    const progress = value.samples[sample.id];
    if (!record(progress) || !exactKeys(progress, ['sectionId', 'fontSize', 'questionIds', 'attemptNumber', 'draft', 'submissions'])
      || !sample.sections.some((section) => section.id === progress.sectionId)
      || ![18, 22, 26].includes(progress.fontSize as number)
      || !Array.isArray(progress.questionIds) || progress.questionIds.length > sample.recommendations.length
      || new Set(progress.questionIds).size !== progress.questionIds.length
      || !progress.questionIds.every((id) => sample.recommendations.some((question) => question.id === id))
      || !Number.isInteger(progress.attemptNumber) || (progress.attemptNumber as number) < 1 || (progress.attemptNumber as number) > MAX_ATTEMPT
      || !validAnswers(progress.draft, sample, false)
      || !Array.isArray(progress.submissions) || progress.submissions.length > MAX_RESULTS) return false;
    let lastAttempt = 0;
    for (const submission of progress.submissions) {
      if (!record(submission) || !exactKeys(submission, ['attemptNumber', 'answers'])
        || !Number.isInteger(submission.attemptNumber) || (submission.attemptNumber as number) <= lastAttempt
        || (lastAttempt > 0 && submission.attemptNumber !== lastAttempt + 1)
        || (submission.attemptNumber as number) > (progress.attemptNumber as number)
        || !validAnswers(submission.answers, sample, true)) return false;
      lastAttempt = submission.attemptNumber as number;
    }
    if (progress.submissions.length !== Math.min(lastAttempt, MAX_RESULTS)
      || (progress.submissions.length === 0 ? progress.attemptNumber !== 1 : lastAttempt < (progress.attemptNumber as number) - 1)) return false;
    const current = progress.submissions.find((item) => item.attemptNumber === progress.attemptNumber);
    return !current || sample.quiz.every((question) => current.answers[question.id] === progress.draft[question.id]);
  });
}

function grade(sample: Sample, submission: Submission): QuizResult {
  const answers = sample.quiz.map((question) => Object.freeze({
    questionId: question.id, choiceId: submission.answers[question.id],
    correct: submission.answers[question.id] === question.correctChoiceId,
    correctChoiceId: question.correctChoiceId, explanation: question.explanation,
  }));
  return Object.freeze({
    attemptNumber: submission.attemptNumber, score: answers.filter((answer) => answer.correct).length,
    total: sample.quiz.length, answers: Object.freeze(answers),
  });
}

function snapshotFor(state: SavedState, notice: string | null): ShowcaseSnapshot {
  return Object.freeze({
    version: 1, notice,
    samples: Object.freeze(Object.fromEntries(samples.map((sample) => {
      const progress = state.samples[sample.id];
      const results = Object.freeze(progress.submissions.map((submission) => grade(sample, submission)));
      return [sample.id, Object.freeze({
        sectionId: progress.sectionId, fontSize: progress.fontSize,
        questionIds: Object.freeze([...progress.questionIds]), attemptNumber: progress.attemptNumber,
        draft: Object.freeze({ ...progress.draft }), results,
        result: results.find((result) => result.attemptNumber === progress.attemptNumber) ?? null,
      })];
    }))),
  });
}

/** Browser storage is convenience only: it is never an identity or permission boundary. */
export function createShowcaseStore(storage?: StorageLike) {
  let saved = defaults();
  let notice: string | null = storage ? null : MEMORY_NOTICE;
  let activeStorage = storage;
  const listeners = new Set<() => void>();
  if (activeStorage) {
    try {
      const raw = activeStorage.getItem(SHOWCASE_STORAGE_KEY);
      if (raw !== null) {
        let parsed: unknown;
        try {
          if (raw.length > MAX_STATE_BYTES || new TextEncoder().encode(raw).byteLength > MAX_STATE_BYTES) throw new Error('size');
          parsed = JSON.parse(raw);
          if (!validSavedState(parsed)) throw new Error('schema');
          saved = parsed;
        } catch {
          notice = RECOVERY_NOTICE;
          activeStorage.removeItem(SHOWCASE_STORAGE_KEY);
        }
      }
    } catch {
      activeStorage = undefined;
      notice = MEMORY_NOTICE;
    }
  }
  let snapshot = snapshotFor(saved, notice);

  function publish(persist = true) {
    if (persist && activeStorage) {
      try {
        activeStorage.setItem(SHOWCASE_STORAGE_KEY, JSON.stringify(saved));
      } catch {
        activeStorage = undefined;
        notice = MEMORY_NOTICE;
      }
    }
    snapshot = snapshotFor(saved, notice);
    listeners.forEach((listener) => listener());
  }

  function change(sampleId: string, update: (current: SavedProgress, sample: Sample) => SavedProgress | null): boolean {
    const sample = findSample(sampleId);
    if (!sample) return false;
    const next = update(saved.samples[sampleId], sample);
    if (!next) return false;
    saved = { ...saved, samples: { ...saved.samples, [sampleId]: next } };
    publish();
    return true;
  }

  return {
    getSnapshot: () => snapshot,
    getCurrentSnapshot: () => snapshot,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    setSection(sampleId: string, sectionId: string) {
      return change(sampleId, (progress, sample) => sample.sections.some((section) => section.id === sectionId) && progress.sectionId !== sectionId
        ? { ...progress, sectionId } : null);
    },
    setFontSize(sampleId: string, fontSize: FontSize) {
      return change(sampleId, (progress) => [18, 22, 26].includes(fontSize) && progress.fontSize !== fontSize ? { ...progress, fontSize } : null);
    },
    rememberQuestion(sampleId: string, questionId: string) {
      return change(sampleId, (progress, sample) => sample.recommendations.some((question) => question.id === questionId) && !progress.questionIds.includes(questionId)
        ? { ...progress, questionIds: [...progress.questionIds, questionId] } : null);
    },
    removeQuestion(sampleId: string, questionId: string) {
      return change(sampleId, progress => progress.questionIds.includes(questionId) ? { ...progress, questionIds: progress.questionIds.filter(id => id !== questionId) } : null);
    },
    clearQuestions(sampleId: string) {
      return change(sampleId, progress => progress.questionIds.length ? { ...progress, questionIds: [] } : null);
    },
    setAnswer(sampleId: string, questionId: string, choiceId: string) {
      return change(sampleId, (progress, sample) => {
        const question = sample.quiz.find((item) => item.id === questionId);
        if (!question?.choices.some((choice) => choice.id === choiceId)
          || progress.submissions.some((submission) => submission.attemptNumber === progress.attemptNumber)
          || progress.draft[questionId] === choiceId) return null;
        return { ...progress, draft: { ...progress.draft, [questionId]: choiceId } };
      });
    },
    submit(sampleId: string): QuizResult | null {
      const sample = findSample(sampleId);
      if (!sample) return null;
      if (snapshot.samples[sampleId].result) return snapshot.samples[sampleId].result;
      const progress = saved.samples[sampleId];
      if (!validAnswers(progress.draft, sample, true)) return null;
      change(sampleId, () => ({
        ...progress,
        submissions: [...progress.submissions, { attemptNumber: progress.attemptNumber, answers: { ...progress.draft } }].slice(-MAX_RESULTS),
      }));
      return snapshot.samples[sampleId].result;
    },
    retry(sampleId: string) {
      return change(sampleId, (progress) => {
        if (!progress.submissions.some((submission) => submission.attemptNumber === progress.attemptNumber)
          || progress.attemptNumber >= MAX_ATTEMPT) return null;
        return { ...progress, attemptNumber: progress.attemptNumber + 1, draft: {} };
      });
    },
    reset() {
      saved = defaults();
      notice = activeStorage ? null : MEMORY_NOTICE;
      // A quota error can disable writes while deletion still works. Keep using
      // the originally supplied handle for this explicit, owned-key cleanup.
      if (storage) {
        try { storage.removeItem(SHOWCASE_STORAGE_KEY); }
        catch { activeStorage = undefined; notice = RESET_NOTICE; }
      }
      publish(false);
    },
    dispose() { listeners.clear(); },
  };
}

export type ShowcaseStore = ReturnType<typeof createShowcaseStore>;
