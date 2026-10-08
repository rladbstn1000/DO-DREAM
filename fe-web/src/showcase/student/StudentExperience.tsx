/**
 * Browser expression layer of the team's fe_app screens at 4c763af.
 * It keeps the native screen order, text controls and StyleSheet geometry, but
 * receives only reviewed static data. No native entry, auth, API or device bridge.
 */
import {
  Fragment,
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import type { ShowcasePort } from '../port';
import type { ShowcaseSnapshot } from '../store';
import type { Sample } from '../samples';
import {
  writtenQuestions,
  type OriginalSnapshot,
  type OriginalStore,
} from '../originalStore';
import { createReaderSpeech, type SpeechView } from '../../student/speech';
import './original-student.css';

export type StudentExperienceProps = {
  port: ShowcasePort;
  state: ShowcaseSnapshot;
  uiStore: OriginalStore;
  uiState: OriginalSnapshot;
};
type ModalContent = { title: string; content: ReactNode };
type StudentContextValue = StudentExperienceProps & {
  openModal: (value: ModalContent) => void;
  closeModal: () => void;
};
const StudentContext = createContext<StudentContextValue | null>(null);
const useStudent = () => useContext(StudentContext)!;
const materialPath = (sample: Sample, screen: string) =>
  `/app/material/${sample.id}/${screen}`;
const normalise = (value: string) => value.trim().replace(/\s+/g, ' ');

export function StudentExperience(props: StudentExperienceProps) {
  const [modal, setModal] = useState<ModalContent | null>(null);
  const location = useLocation();
  const screenRoot = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setModal(null);
  }, [location.pathname]);
  useLayoutEffect(() => {
    const heading = screenRoot.current?.querySelector<HTMLElement>('h1');
    heading?.focus({ preventScroll: true });
  }, [location.pathname]);
  const className = `original-student app-font-${Math.round(
    props.uiState.settings.fontScale * 10,
  )
    .toString()
    .padStart(
      2,
      '0',
    )}${props.uiState.settings.highContrast ? ' app-high-contrast' : ''}`;
  return (
    <StudentContext.Provider
      value={{
        ...props,
        openModal: setModal,
        closeModal: () => setModal(null),
      }}
    >
      <section className={className} aria-label="학생 앱 샘플 체험">
        <div className="app-phone" data-testid="student-phone">
          <div className="app-viewport">
            <div className="app-screen" ref={screenRoot}>
              <Routes>
                <Route index element={<Navigate to="library" replace />} />
                <Route path="library" element={<Library />} />
                <Route path="settings" element={<Settings />} />
                <Route
                  path="material/:sampleId/playback"
                  element={
                    <WithSample>
                      {(sample) => <Playback sample={sample} />}
                    </WithSample>
                  }
                />
                <Route
                  path="material/:sampleId/player"
                  element={
                    <WithSample>
                      {(sample) => <Player sample={sample} />}
                    </WithSample>
                  }
                />
                <Route
                  path="material/:sampleId/question"
                  element={
                    <WithSample>
                      {(sample) => <Question sample={sample} />}
                    </WithSample>
                  }
                />
                <Route
                  path="material/:sampleId/questions"
                  element={
                    <WithSample>
                      {(sample) => <QuestionList sample={sample} />}
                    </WithSample>
                  }
                />
                <Route
                  path="material/:sampleId/bookmarks"
                  element={
                    <WithSample>
                      {(sample) => <Bookmarks sample={sample} />}
                    </WithSample>
                  }
                />
                <Route
                  path="material/:sampleId/quizzes"
                  element={
                    <WithSample>
                      {(sample) => <QuizList sample={sample} />}
                    </WithSample>
                  }
                />
                <Route
                  path="material/:sampleId/quiz"
                  element={
                    <WithSample>
                      {(sample) => <Quiz sample={sample} />}
                    </WithSample>
                  }
                />
                <Route
                  path="material/:sampleId/result"
                  element={
                    <WithSample>
                      {(sample) => <Result sample={sample} />}
                    </WithSample>
                  }
                />
                <Route
                  path="*"
                  element={
                    <>
                      <Header back="/app/library" />
                      <div className="app-scroll app-quiz-content">
                        <h1 tabIndex={-1}>이 앱 화면을 찾을 수 없습니다.</h1>
                        <Link
                          to="/app/library"
                          className="app-large app-primary"
                        >
                          서재로
                        </Link>
                      </div>
                    </>
                  }
                />
              </Routes>
            </div>
            {modal && (
              <PhoneModal
                title={modal.title}
                onClose={() => setModal(null)}
                screenRoot={screenRoot}
              >
                {modal.content}
              </PhoneModal>
            )}
          </div>
        </div>
      </section>
    </StudentContext.Provider>
  );
}

function PhoneModal({
  title,
  children,
  onClose,
  screenRoot,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  screenRoot: React.RefObject<HTMLDivElement | null>;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useLayoutEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const root = screenRoot.current;
    if (root) root.inert = true;
    const focusables = () => [
      ...(panel.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),[tabindex="0"]',
      ) ?? []),
    ];
    (focusables()[0] ?? panel.current)?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close.current();
      }
      if (event.key === 'Tab') {
        const items = focusables();
        const first = items[0];
        const last = items[items.length - 1];
        if (!first) {
          event.preventDefault();
          panel.current?.focus();
        } else if (
          event.shiftKey &&
          (document.activeElement === first ||
            !panel.current?.contains(document.activeElement))
        ) {
          event.preventDefault();
          last?.focus();
        } else if (
          !event.shiftKey &&
          (document.activeElement === last ||
            !panel.current?.contains(document.activeElement))
        ) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    const focus = (event: FocusEvent) => {
      if (!panel.current?.contains(event.target as Node))
        (focusables()[0] ?? panel.current)?.focus();
    };
    document.addEventListener('keydown', key);
    document.addEventListener('focusin', focus);
    return () => {
      document.removeEventListener('keydown', key);
      document.removeEventListener('focusin', focus);
      if (root) root.inert = false;
      if (previous?.isConnected) previous.focus({ preventScroll: true });
    };
  }, [screenRoot]);
  return (
    <div
      className="app-modal-overlay"
      data-testid="app-modal-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="app-modal"
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="app-modal-title"
        tabIndex={-1}
      >
        <h2 id="app-modal-title">{title}</h2>
        {children}
        <button className="app-large app-plain" onClick={onClose}>
          닫기
        </button>
      </div>
    </div>
  );
}

function WithSample({ children }: { children: (sample: Sample) => ReactNode }) {
  const { sampleId } = useParams();
  const { port } = useStudent();
  const sample = port.findSample(sampleId);
  return sample ? (
    <Fragment key={sample.id}>{children(sample)}</Fragment>
  ) : (
    <>
      <Header back="/app/library" />
      <div className="app-empty">
        <h1 tabIndex={-1}>샘플 교재를 찾을 수 없습니다.</h1>
        <Link to="/app/library">서재로 돌아가기</Link>
      </div>
    </>
  );
}

function Header({
  back,
  title,
  library = false,
  settings = false,
  bookmark,
  clear,
  onVoice,
}: {
  back?: string;
  title?: string;
  library?: boolean;
  settings?: boolean;
  bookmark?: { active: boolean; toggle: () => void };
  clear?: () => void;
  onVoice?: () => void;
}) {
  const { openModal, closeModal, port } = useStudent();
  const navigate = useNavigate();
  const location = useLocation();
  const voice =
    onVoice ??
    (() =>
      openModal({
        title: '말하기 체험',
        content: (
          <>
            <p>
              이 웹 체험은 마이크를 사용하지 않습니다. 아래 예시 명령을 직접
              선택해 보세요.
            </p>
            {port.samples.map((sample) => (
              <button
                className="app-option"
                key={sample.id}
                onClick={() => {
                  closeModal();
                  navigate(materialPath(sample, 'playback'));
                }}
              >
                {sample.title} 열기
              </button>
            ))}
            <button
              className="app-option"
              onClick={() => {
                closeModal();
                navigate('/app/settings');
              }}
            >
              설정 열기
            </button>
          </>
        ),
      }));
  return (
    <header className="app-header">
      {library ? (
        <h1 className="app-student-name" tabIndex={-1}>
          샘플
        </h1>
      ) : (
        <Link
          className="app-back"
          to={back ?? '/app/library'}
          aria-label={
            back === '/app/library' && title === '결과'
              ? '서재로 돌아가기'
              : '뒤로가기'
          }
        >
          {title === '결과' ? '← 서재로' : '←  뒤로'}
        </Link>
      )}
      {title && title !== '결과' && (
        <h1 className="app-header-title" tabIndex={-1}>
          {title}
        </h1>
      )}
      <div className="app-header-right">
        {settings && (
          <Link
            className="app-header-button"
            to={`/app/settings?from=${encodeURIComponent(location.pathname)}`}
            aria-label="사용자 설정"
          >
            설정
          </Link>
        )}
        {bookmark && (
          <button
            className="app-header-button app-bookmark"
            aria-label={
              bookmark.active ? '현재 챕터 저장 해제하기' : '현재 챕터 저장하기'
            }
            aria-pressed={bookmark.active}
            onClick={bookmark.toggle}
          >
            {bookmark.active ? '저장 해제' : '저장하기'}
          </button>
        )}
        {clear && (
          <button
            className="app-header-button app-clear"
            onClick={clear}
            aria-label="대화 지우기"
          >
            지우기
          </button>
        )}
        <button className="app-header-button app-voice" onClick={voice}>
          말하기
        </button>
      </div>
    </header>
  );
}

function Library() {
  const { port, uiState } = useStudent();
  return (
    <>
      <Header library settings />
      <div className="app-scroll app-library-list" aria-label="서재 교재 목록">
        {port.samples.map((sample) => {
          const material = uiState.materials[sample.id];
          const index = Math.max(
            0,
            material.chapters.findIndex(
              (section) => section.id === uiState.positions[sample.id],
            ),
          );
          return (
            <Link
              to={materialPath(sample, 'playback')}
              className="app-material"
              key={sample.id}
              data-testid={`material-${sample.id}`}
            >
              <span>
                <strong>{material.title}</strong>
                <small>현재 {index + 1}챕터</small>
                <small className="app-count">
                  {index + 1} / {material.chapters.length} 챕터
                </small>
              </span>
              <span className="app-continue">이어듣기</span>
            </Link>
          );
        })}
      </div>
    </>
  );
}

function Playback({ sample }: { sample: Sample }) {
  const { uiState, uiStore, port } = useStudent();
  const navigate = useNavigate();
  const material = uiState.materials[sample.id];
  const [index, setIndex] = useState(
    Math.max(
      0,
      material.chapters.findIndex(
        (section) => section.id === uiState.positions[sample.id],
      ),
    ),
  );
  const chapter = material.chapters[index] ?? material.chapters[0];
  function start(fromStart: boolean) {
    uiStore.setSection(sample.id, chapter.id);
    port.store.setSection(sample.id, chapter.id);
    navigate(
      `${materialPath(sample, 'player')}?section=${chapter.id}${fromStart ? '&paragraph=0' : ''}`,
    );
  }
  return (
    <>
      <Header back="/app/library" settings />
      <div className="app-scroll app-playback app-playback-content">
        <h1 className="app-subject" tabIndex={-1}>
          {material.title}
        </h1>
        <div className="app-chapter-select">
          <button
            className="app-round"
            aria-label="이전 챕터"
            onClick={() =>
              setIndex(
                (index + material.chapters.length - 1) %
                  material.chapters.length,
              )
            }
          >
            ◀
          </button>
          <div className="app-chapter-info">
            <strong>{chapter.title}</strong>
            <span>○ 미완료</span>
            <span>
              {index + 1} / {material.chapters.length}
            </span>
          </div>
          <button
            className="app-round"
            aria-label="다음 챕터"
            onClick={() => setIndex((index + 1) % material.chapters.length)}
          >
            ▶
          </button>
        </div>
        <button className="app-choice" onClick={() => start(false)}>
          <strong>이어서 듣기</strong>
          <small>마지막 위치부터</small>
        </button>
        <button className="app-choice" onClick={() => start(true)}>
          <strong>처음부터 듣기</strong>
          <small>챕터 처음부터</small>
        </button>
        <Link className="app-choice" to={materialPath(sample, 'questions')}>
          <strong>질문 목록</strong>
          <small>이전 질문 보기</small>
        </Link>
        <Link className="app-choice" to={materialPath(sample, 'bookmarks')}>
          <strong>저장 목록</strong>
          <small>저장한 내용 보기</small>
        </Link>
        <Link className="app-choice" to={materialPath(sample, 'quizzes')}>
          <strong>퀴즈 풀기</strong>
          <small>학습 내용 확인</small>
        </Link>
      </div>
    </>
  );
}

function useLocalSpeech() {
  const { uiState, port, openModal } = useStudent();
  const settings = useRef(uiState.settings);
  settings.current = uiState.settings;
  const controller = useRef<ReturnType<typeof createReaderSpeech> | null>(null);
  const [view, setView] = useState<SpeechView>({
    state: 'idle',
    part: 0,
    total: 0,
    truncated: false,
  });
  useLayoutEffect(() => {
    let speech: SpeechSynthesis;
    try {
      speech = window.speechSynthesis;
    } catch {
      return;
    }
    if (!speech || typeof SpeechSynthesisUtterance === 'undefined') return;
    controller.current = createReaderSpeech({
      getEpoch: port.getEpoch,
      voices: () => speech.getVoices(),
      utterance: (text) => new SpeechSynthesisUtterance(text),
      speak: (value) => {
        const utterance = value as SpeechSynthesisUtterance;
        utterance.rate = settings.current.rate;
        utterance.pitch = settings.current.pitch;
        utterance.volume = settings.current.volume;
        speech.speak(utterance);
      },
      pause: () => speech.pause(),
      resume: () => speech.resume(),
      cancel: () => speech.cancel(),
      changed: setView,
    });
    return () => {
      controller.current?.dispose();
      controller.current = null;
    };
  }, [port]);
  const unavailable = () =>
    openModal({
      title: '본문 듣기 안내',
      content: (
        <p>
          이 브라우저에서 로컬 한국어 음성을 사용할 수 없습니다. 글을 읽고
          이전·다음 버튼으로 계속 학습할 수 있습니다.
        </p>
      ),
    });
  return {
    view,
    stop: () => controller.current?.stop(),
    toggle(text: string) {
      if (!controller.current) {
        unavailable();
        return;
      }
      if (view.state === 'speaking') controller.current.pause();
      else if (view.state === 'paused') controller.current.resume();
      else {
        controller.current.start(text);
        if (
          ['unavailable', 'error'].includes(controller.current.getView().state)
        )
          unavailable();
      }
    },
  };
}

function Player({ sample }: { sample: Sample }) {
  const { port, uiState, uiStore, openModal, closeModal } = useStudent();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const material = uiState.materials[sample.id];
  const chapter =
    material.chapters.find(
      (item) =>
        item.id === (search.get('section') ?? uiState.positions[sample.id]),
    ) ?? material.chapters[0];
  const index = material.chapters.indexOf(chapter);
  const contentParagraphs = chapter.text
    .split(/\n\s*\n/)
    .filter((text) => text.trim());
  const emptyChapter = contentParagraphs.length === 0;
  const paragraphs = emptyChapter
    ? ['아직 본문이 없습니다. 교사 편집 화면에서 내용을 입력해 주세요.']
    : contentParagraphs;
  const paragraphIndex = Math.min(
    paragraphs.length - 1,
    Math.max(
      0,
      Number.isInteger(Number(search.get('paragraph')))
        ? Number(search.get('paragraph'))
        : 0,
    ),
  );
  const paragraph = paragraphs[paragraphIndex] ?? chapter.text;
  const [mode, setMode] = useState<'single' | 'continuous' | 'repeat'>(
    'single',
  );
  const speech = useLocalSpeech();
  const reader = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    uiStore.setSection(sample.id, chapter.id);
    port.store.setSection(sample.id, chapter.id);
    speech.stop();
    reader.current?.scrollTo(0, 0);
  }, [chapter.id, paragraphIndex]);
  const move = (position: number) =>
    setSearch({ section: chapter.id, paragraph: String(position) });
  const openOptions = () =>
    openModal({
      title: '학습 옵션',
      content: (
        <>
          <p>재생 모드를 선택하세요. 로컬 한국어 음성이 있을 때 사용합니다.</p>
          {(
            [
              ['single', '한 섹션씩'],
              ['continuous', '연속 재생'],
              ['repeat', '반복 재생'],
            ] as const
          ).map(([value, label]) => (
            <button
              className="app-option"
              aria-pressed={mode === value}
              key={value}
              onClick={() => {
                setMode(value);
                speech.stop();
                closeModal();
              }}
            >
              {label}
            </button>
          ))}
          <Link className="app-large app-primary" to="/app/settings">
            재생 속도·화면 설정
          </Link>
        </>
      ),
    });
  const complete = () => {
    speech.stop();
    if (index + 1 < material.chapters.length)
      setSearch({ section: material.chapters[index + 1].id, paragraph: '0' });
    else navigate(materialPath(sample, 'playback'));
  };
  return (
    <>
      <Header
        back={materialPath(sample, 'playback')}
        bookmark={{
          active: uiState.bookmarks[sample.id].includes(chapter.id),
          toggle: () => uiStore.toggleBookmark(sample.id, chapter.id),
        }}
        onVoice={() => {
          speech.stop();
          openModal({
            title: '말하기 체험',
            content: (
              <>
                <p>마이크 대신 예시 명령을 선택하세요.</p>
                <button
                  className="app-option"
                  onClick={() => {
                    closeModal();
                    navigate(materialPath(sample, 'question'));
                  }}
                >
                  질문하기
                </button>
                <button
                  className="app-option"
                  onClick={() => {
                    closeModal();
                    navigate(materialPath(sample, 'quizzes'));
                  }}
                >
                  퀴즈 풀기
                </button>
                <button className="app-option" onClick={openOptions}>
                  학습 옵션
                </button>
              </>
            ),
          });
        }}
      />
      <div className="app-player-info">
        <h1 tabIndex={-1}>
          {index + 1}. {chapter.title}
        </h1>
        <button
          className="app-mode"
          aria-label="학습 옵션 열기"
          onClick={openOptions}
        >
          {'모드: '}
          {mode === 'single'
            ? '한 섹션씩'
            : mode === 'continuous'
              ? '연속 재생'
              : '반복 재생'}
        </button>
      </div>
      <div className="app-scroll app-reader" ref={reader}>
        <div className="app-paragraph" data-testid="player-paragraph">
          {paragraph}
        </div>
        <p className="app-counter">
          {emptyChapter
            ? '본문 없음'
            : `${paragraphIndex + 1} / ${paragraphs.length}`}
        </p>
        <span className="app-sr-only" role="status">
          {speech.view.state === 'speaking'
            ? '본문을 읽고 있습니다.'
            : speech.view.state === 'paused'
              ? '읽기를 일시정지했습니다.'
              : ''}
        </span>
      </div>
      <div className="app-controls">
        <button
          className="app-control"
          disabled={paragraphIndex === 0}
          aria-label="이전 섹션"
          onClick={() => move(paragraphIndex - 1)}
        >
          ← 이전
        </button>
        <button
          className="app-control app-play"
          disabled={emptyChapter}
          onClick={() =>
            speech.toggle(
              mode === 'continuous'
                ? paragraphs.slice(paragraphIndex).join('\n\n')
                : mode === 'repeat'
                  ? `${paragraph}\n\n${paragraph}`
                  : paragraph,
            )
          }
        >
          {speech.view.state === 'speaking' ? '일시정지' : '재생'}
        </button>
        <button
          className={`app-control ${paragraphIndex === paragraphs.length - 1 ? 'app-complete' : ''}`}
          aria-label={
            emptyChapter
              ? index + 1 < material.chapters.length
                ? '다음 챕터'
                : '교재로 돌아가기'
              : paragraphIndex === paragraphs.length - 1
                ? '학습 완료'
                : '다음 섹션'
          }
          onClick={() =>
            paragraphIndex === paragraphs.length - 1
              ? complete()
              : move(paragraphIndex + 1)
          }
        >
          {emptyChapter
            ? index + 1 < material.chapters.length
              ? '다음 →'
              : '교재로'
            : paragraphIndex === paragraphs.length - 1
              ? '완료'
              : '다음 →'}
        </button>
      </div>
      <div className="app-bottom">
        <Link className="app-large" to={materialPath(sample, 'question')}>
          질문하기
        </Link>
      </div>
    </>
  );
}

function Question({ sample }: { sample: Sample }) {
  const { port, state, openModal, closeModal } = useStudent();
  const [text, setText] = useState('');
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useSearchParams();
  const focusedQuestion = search.get('question');
  const questions = state.samples[sample.id].questionIds
    .map((id) => sample.recommendations.find((item) => item.id === id)!)
    .filter(Boolean);
  const visibleQuestions = focusedQuestion
    ? questions.filter((item) => item.id === focusedQuestion)
    : questions;
  const chat = useRef<HTMLDivElement>(null);
  useEffect(() => {
    chat.current?.scrollTo(0, chat.current.scrollHeight);
  }, [questions.length, notice]);
  const choose = (value: string) => {
    setText(value);
    setNotice('');
    closeModal();
  };
  const examples = () =>
    openModal({
      title: '예시 질문 선택',
      content: (
        <>
          <p>
            마이크를 요청하지 않습니다. 준비된 질문을 선택하거나 같은 질문을
            직접 입력해 보세요.
          </p>
          {sample.recommendations.map((question) => (
            <button
              className="app-option"
              key={question.id}
              onClick={() => choose(question.question)}
            >
              {question.question}
            </button>
          ))}
        </>
      ),
    });
  const send = () => {
    const question = sample.recommendations.find(
      (item) => normalise(item.question) === normalise(text),
    );
    if (!question) {
      setNotice(
        '이 체험은 준비된 질문에만 답합니다. 말하기 버튼에서 예시 질문을 선택해 주세요. 입력한 내용은 서버로 전송하지 않습니다.',
      );
      return;
    }
    port.store.rememberQuestion(sample.id, question.id);
    setSearch({});
    setText('');
    setNotice('');
  };
  const source = (question: (typeof sample.recommendations)[number]) => {
    const section = sample.sections.find(
      (item) => item.id === question.source.sectionId,
    )!;
    openModal({
      title: `참고 구간 · ${section.title}`,
      content: (
        <>
          <p>{section.paragraphs[question.source.paragraphIndex]}</p>
          <p className="app-note">
            준비된 공개 샘플의 참고 문장입니다. 편집한 본문에 대한 AI 검색은
            제공하지 않습니다.
          </p>
        </>
      ),
    });
  };
  return (
    <>
      <Header
        back={materialPath(sample, 'player')}
        clear={() => {
          port.store.clearQuestions(sample.id);
          setNotice('');
        }}
        onVoice={examples}
      />
      <h1 className="app-sr-only" tabIndex={-1}>
        두드림 질문
      </h1>
      <div className="app-scroll app-chat" ref={chat}>
        {!visibleQuestions.length && (
          <div className="app-welcome">
            두드림에게 물어보세요. 오른쪽 위 말하기 버튼에서 예시 질문을
            고르거나, 아래 입력창에 질문을 적고 확인을 눌러 주세요.
            <small className="app-note">
              준비된 답변으로 진행하는 샘플 체험입니다.
            </small>
          </div>
        )}
        <div className="app-messages">
          {visibleQuestions.map((question) => (
            <div key={question.id}>
              <div className="app-message-row app-user-row">
                <div className="app-bubble app-user-bubble">
                  {question.question}
                </div>
              </div>
              <div className="app-message-row">
                <div className="app-bubble app-answer-bubble">
                  {question.answer}
                  <small>준비된 예시 답변</small>
                  <button
                    className="app-source"
                    onClick={() => source(question)}
                  >
                    참고 구간 보기
                  </button>
                </div>
              </div>
            </div>
          ))}
          {notice && (
            <div className="app-message-row">
              <p className="app-bubble app-answer-bubble" role="status">
                {notice}
              </p>
            </div>
          )}
        </div>
      </div>
      <form
        className="app-input-row"
        onSubmit={(event) => {
          event.preventDefault();
          send();
        }}
      >
        <textarea
          className="app-question-input"
          aria-label="질문 입력창"
          placeholder="질문 입력"
          maxLength={1200}
          rows={1}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <button className="app-send" disabled={!text.trim()}>
          확인
        </button>
      </form>
    </>
  );
}

function QuestionList({ sample }: { sample: Sample }) {
  const { port, state, uiState, openModal, closeModal } = useStudent();
  const navigate = useNavigate();
  const questions = state.samples[sample.id].questionIds
    .map((id) => sample.recommendations.find((item) => item.id === id)!)
    .filter(Boolean);
  return (
    <>
      <Header back={materialPath(sample, 'playback')} title="질문 목록" />
      <div className="app-list-info">
        <h2>{uiState.materials[sample.id].title}</h2>
        <p>총 {questions.length}개의 질문</p>
      </div>
      <div className="app-scroll app-history-list">
        {!questions.length && (
          <p className="app-empty">
            아직 질문한 내역이 없습니다.
            <br />
            학습 중에 질문하기 버튼을 눌러 질문해보세요.
          </p>
        )}
        {questions.map((question) => (
          <article className="app-history-card" key={question.id}>
            <button
              className="app-history-open"
              onClick={() =>
                navigate(
                  `${materialPath(sample, 'question')}?question=${question.id}`,
                )
              }
            >
              <small>질문</small>
              <strong>{question.question}</strong>
              <span>대화 1회 · 현재 탭</span>
            </button>
            <button
              className="app-delete"
              aria-label={`질문 삭제: ${question.question}`}
              onClick={() =>
                openModal({
                  title: '질문 삭제',
                  content: (
                    <>
                      <p>현재 탭에서 이 질문 기록을 삭제할까요?</p>
                      <button
                        className="app-large app-danger"
                        onClick={() => {
                          port.store.removeQuestion(sample.id, question.id);
                          closeModal();
                        }}
                      >
                        삭제
                      </button>
                    </>
                  ),
                })
              }
            >
              삭제
            </button>
          </article>
        ))}
      </div>
    </>
  );
}

function Bookmarks({ sample }: { sample: Sample }) {
  const { uiState, uiStore, openModal, closeModal } = useStudent();
  const navigate = useNavigate();
  const material = uiState.materials[sample.id];
  const chapters = material.chapters.filter((item) =>
    uiState.bookmarks[sample.id].includes(item.id),
  );
  const speech = useLocalSpeech();
  return (
    <>
      <Header back={materialPath(sample, 'playback')} title="저장 목록" />
      <div className="app-list-info">
        <h2>{material.title}</h2>
        <p>총 {chapters.length}개의 저장된 내용</p>
      </div>
      <div className="app-scroll app-history-list">
        {!chapters.length && (
          <p className="app-empty">
            저장한 내용이 없습니다
            <br />
            학습 중 중요한 부분에서
            <br />
            저장 버튼을 눌러 보세요
          </p>
        )}
        {chapters.map((chapter, index) => (
          <article className="app-history-card" key={chapter.id}>
            <button
              className="app-history-open"
              onClick={() =>
                navigate(
                  `${materialPath(sample, 'player')}?section=${chapter.id}`,
                )
              }
            >
              <small>#{index + 1}</small>
              <strong>{chapter.title}</strong>
              <span>현재 탭에 저장</span>
            </button>
            <button
              className="app-delete"
              aria-label={`저장 삭제: ${chapter.title}`}
              onClick={() =>
                openModal({
                  title: '저장 삭제',
                  content: (
                    <>
                      <p>{chapter.title} 항목을 삭제할까요?</p>
                      <button
                        className="app-large app-danger"
                        onClick={() => {
                          uiStore.toggleBookmark(sample.id, chapter.id);
                          closeModal();
                        }}
                      >
                        삭제
                      </button>
                    </>
                  ),
                })
              }
            >
              삭제
            </button>
          </article>
        ))}
      </div>
      {!!chapters.length && (
        <div className="app-bottom">
          <button
            className="app-large app-primary"
            onClick={() =>
              speech.toggle(
                chapters
                  .map((chapter) => `${chapter.text}\n\n${chapter.text}`)
                  .join('\n\n'),
              )
            }
          >
            {speech.view.state === 'speaking' ? '복습 일시정지' : '복습 모드'}
            <br />
            <small>2회씩 반복 재생</small>
          </button>
        </div>
      )}
    </>
  );
}

function QuizList({ sample }: { sample: Sample }) {
  const { uiState } = useStudent();
  const questions = writtenQuestions(sample.id);
  return (
    <>
      <Header back={materialPath(sample, 'playback')} />
      <div className="app-scroll app-library-list">
        <h1 className="app-subject" tabIndex={-1}>
          {uiState.materials[sample.id].title}
        </h1>
        <p className="app-note">전체 퀴즈 목록</p>
        {questions.map((question, index) => (
          <Link
            to={`${materialPath(sample, 'quiz')}?question=${index + 1}`}
            key={question.id}
            className="app-choice app-quiz-choice"
          >
            <strong>
              {index + 1}. {question.prompt}
            </strong>
            <span className="app-quiz-badge">단답형</span>
          </Link>
        ))}
      </div>
    </>
  );
}

function Quiz({ sample }: { sample: Sample }) {
  const { uiState, uiStore, openModal, closeModal } = useStudent();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const questions = writtenQuestions(sample.id);
  const requested = Number(search.get('question') ?? '1');
  const index =
    Number.isInteger(requested) &&
    requested > 0 &&
    requested <= questions.length
      ? requested - 1
      : 0;
  const question = questions[index];
  const progress = uiState.quizzes[sample.id];
  const answer = progress.draft[question.id] ?? '';
  const last = index === questions.length - 1;
  const input = useRef<HTMLInputElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scroller.current?.scrollTo(0, 0);
  }, [index]);
  const dictate = () =>
    openModal({
      title: '음성으로 답하기 체험',
      content: (
        <>
          <p>
            마이크를 사용하지 않습니다. 예시 답을 입력한 뒤 직접 수정할 수
            있습니다.
          </p>
          <button
            className="app-option"
            onClick={() => {
              uiStore.setWrittenAnswer(
                sample.id,
                question.id,
                question.expectedAnswer,
              );
              closeModal();
              input.current?.focus();
            }}
          >
            {question.expectedAnswer} 입력
          </button>
        </>
      ),
    });
  const grade = () => {
    if (progress.result) {
      navigate(materialPath(sample, 'result'));
      return;
    }
    const missing = questions.findIndex(
      (item) => !(progress.draft[item.id] ?? '').trim(),
    );
    if (missing !== -1) {
      setSearch({ question: String(missing + 1) });
      openModal({
        title: '답을 입력해 주세요',
        content: (
          <p>
            모든 문제에 답을 입력하면 준비된 규칙으로 결과를 확인할 수 있습니다.
          </p>
        ),
      });
      return;
    }
    if (uiStore.submitWrittenQuiz(sample.id))
      navigate(materialPath(sample, 'result'));
  };
  return (
    <>
      <Header back={materialPath(sample, 'quizzes')} onVoice={dictate} />
      <div className="app-scroll app-quiz-content" ref={scroller}>
        <div className="app-quiz-heading">
          <h1 tabIndex={-1}>문제 {index + 1}</h1>
          <span>
            {index + 1} / {questions.length}
          </span>
        </div>
        <p className="app-quiz-prompt">{question.prompt}</p>
        <input
          className="app-answer-input"
          ref={input}
          aria-label="답 입력란"
          placeholder="답을 입력하세요"
          value={answer}
          maxLength={500}
          readOnly={!!progress.result}
          onChange={(event) =>
            uiStore.setWrittenAnswer(sample.id, question.id, event.target.value)
          }
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              if (last) grade();
              else setSearch({ question: String(index + 2) });
            }
          }}
        />
        <button
          className="app-large"
          disabled={!!progress.result}
          onClick={dictate}
        >
          음성으로 답하기
        </button>
        <button
          className={`app-large ${last ? 'app-success' : 'app-primary'}`}
          disabled={last && !answer.trim()}
          onClick={() =>
            last ? grade() : setSearch({ question: String(index + 2) })
          }
        >
          {last ? (progress.result ? '결과 확인' : '채점하기') : '다음 문제'}
        </button>
        {index > 0 && (
          <button
            className="app-large app-primary"
            onClick={() => setSearch({ question: String(index) })}
          >
            이전 문제
          </button>
        )}
        <p className="app-note">
          공개 샘플의 지정 답안과 비교하는 예시 판정입니다. 의미 이해나 AI
          채점은 하지 않습니다. 편집한 본문에서 새 문제를 만들지 않습니다.
        </p>
      </div>
    </>
  );
}

function Result({ sample }: { sample: Sample }) {
  const { uiState, uiStore } = useStudent();
  const navigate = useNavigate();
  const [showCorrect, setShowCorrect] = useState(false);
  const result = uiState.quizzes[sample.id].result;
  const questions = writtenQuestions(sample.id);
  if (!result)
    return (
      <>
        <Header back={materialPath(sample, 'quizzes')} />
        <div className="app-quiz-content">
          <h1 tabIndex={-1}>아직 풀이 결과가 없습니다.</h1>
          <Link
            className="app-large app-primary"
            to={materialPath(sample, 'quiz')}
          >
            퀴즈 풀기
          </Link>
        </div>
      </>
    );
  const card = (answer: (typeof result.answers)[number]) => (
    <article
      key={answer.questionId}
      className={`app-result-card${answer.correct ? '' : ' app-incorrect'}`}
    >
      <h3>
        {questions.findIndex((item) => item.id === answer.questionId) + 1}
        {'번 · '}
        {answer.correct ? '정답' : '오답'}
      </h3>
      <p>{questions.find((item) => item.id === answer.questionId)?.prompt}</p>
      <dl>
        <dt>내 답</dt>
        <dd>{answer.answer}</dd>
        {!answer.correct && (
          <>
            <dt>정답</dt>
            <dd>{answer.expectedAnswer}</dd>
          </>
        )}
      </dl>
      <p>{answer.explanation}</p>
    </article>
  );
  return (
    <>
      <Header back="/app/library" title="결과" />
      <div className="app-scroll app-result-content">
        <section className="app-result-summary">
          <h1 tabIndex={-1}>퀴즈 완료!</h1>
          <p>{uiState.materials[sample.id].title}</p>
          <div className="app-score" data-testid="quiz-score">
            <strong>{result.score}</strong> / {result.total}
          </div>
          <p className="app-percentage">
            정답률 {Math.round((result.score / result.total) * 100)}%
          </p>
          <small className="app-note">
            예시 판정 · {result.attemptNumber}회차
          </small>
        </section>
        {result.score === result.total ? (
          <section className="app-perfect">
            <h2>완벽해요!</h2>
            <p>모든 예시 답안을 맞혔습니다</p>
          </section>
        ) : (
          <>
            <section className="app-wrong">
              <h2>틀린 문제: {result.total - result.score}개</h2>
              <p>복습이 필요합니다</p>
            </section>
            {result.answers.filter((answer) => !answer.correct).map(card)}
          </>
        )}
        {result.score > 0 && (
          <>
            <button
              className="app-result-toggle"
              aria-expanded={showCorrect}
              onClick={() => setShowCorrect(!showCorrect)}
            >
              {showCorrect ? '▼' : '▶'} 맞은 문제: {result.score}
              {'개 '}
              {showCorrect ? '접기' : '펼치기'}
            </button>
            {showCorrect &&
              result.answers.filter((answer) => answer.correct).map(card)}
          </>
        )}
        <p className="app-note">
          지정된 예시 답안과 비교한 결과입니다. 이 탭의 교사 화면에서도 확인할
          수 있습니다.
        </p>
      </div>
      <div className="app-bottom">
        <button
          className="app-large app-primary"
          onClick={() => {
            uiStore.retryWrittenQuiz(sample.id);
            navigate(materialPath(sample, 'quiz'));
          }}
        >
          다시 풀기
        </button>
      </div>
    </>
  );
}

function Settings() {
  const { uiState, uiStore, openModal } = useStudent();
  const { settings } = uiState;
  const speech = useLocalSpeech();
  const [search] = useSearchParams();
  const from = search.get('from');
  const returnPath =
    from &&
    /^\/app\/material\/(water-journey|recycling-day)\/(playback|player)$/.test(
      from,
    )
      ? from
      : '/app/library';
  const control = (
    label: string,
    value: number,
    unit: string,
    decrease: () => void,
    increase: () => void,
    minimum: boolean,
    maximum: boolean,
  ) => (
    <div className="app-setting">
      <h3>{label}</h3>
      <div className="app-setting-row">
        <output className="app-setting-value">
          {unit === '%' ? Math.round(value * 100) : value.toFixed(1)}
          <small>{unit}</small>
        </output>
        <button
          className="app-setting-control"
          aria-label={`${label} 줄이기`}
          disabled={minimum}
          onClick={decrease}
        >
          −
        </button>
        <button
          className="app-setting-control"
          aria-label={`${label} 늘리기`}
          disabled={maximum}
          onClick={increase}
        >
          +
        </button>
      </div>
    </div>
  );
  const numeric = (key: 'rate' | 'pitch' | 'volume', amount: number) =>
    uiStore.setSettings({ [key]: Number((settings[key] + amount).toFixed(1)) });
  const scales = [1, 1.2, 1.5] as const;
  const scaleIndex = scales.indexOf(settings.fontScale);
  return (
    <>
      <Header back={returnPath} title="설정" />
      <div className="app-scroll app-settings-content">
        <section className="app-settings-section">
          <h2>음성 설정</h2>
          {control(
            '재생 속도',
            settings.rate,
            '배',
            () => numeric('rate', -0.1),
            () => numeric('rate', 0.1),
            settings.rate <= 0.5,
            settings.rate >= 2,
          )}
          {control(
            '높낮이',
            settings.pitch,
            '',
            () => numeric('pitch', -0.1),
            () => numeric('pitch', 0.1),
            settings.pitch <= 0.5,
            settings.pitch >= 2,
          )}
          {control(
            '볼륨',
            settings.volume,
            '%',
            () => numeric('volume', -0.1),
            () => numeric('volume', 0.1),
            settings.volume <= 0,
            settings.volume >= 1,
          )}
          <h3>목소리</h3>
          <button
            className="app-option"
            onClick={() =>
              openModal({
                title: '목소리 안내',
                content: (
                  <p>
                    기기에 설치된 로컬 한국어 음성이 있을 때만 재생합니다. 웹
                    체험에서는 서버 음성과 네이티브 앱의 음성 목록을 사용하지
                    않습니다.
                  </p>
                ),
              })
            }
          >
            기기의 로컬 한국어 음성
          </button>
          <button
            className="app-large"
            onClick={() => speech.toggle('두드림과 함께 나의 속도로 배워요.')}
          >
            {speech.view.state === 'speaking' ? '재생 중…' : '테스트'}
          </button>
        </section>
        <section className="app-settings-section">
          <h2>화면 설정</h2>
          <label className="app-switch">
            고대비 모드
            <input
              type="checkbox"
              checked={settings.highContrast}
              onChange={(event) =>
                uiStore.setSettings({ highContrast: event.target.checked })
              }
            />
          </label>
          {control(
            '글자 크기',
            settings.fontScale,
            '%',
            () =>
              uiStore.setSettings({
                fontScale: scales[Math.max(0, scaleIndex - 1)],
              }),
            () =>
              uiStore.setSettings({
                fontScale: scales[Math.min(scales.length - 1, scaleIndex + 1)],
              }),
            scaleIndex === 0,
            scaleIndex === scales.length - 1,
          )}
        </section>
        <section className="app-settings-section">
          <h2>앱 정보</h2>
          <p>브라우저 샘플 체험</p>
          <p className="app-note">
            네이티브 알림, 생체 인증, 하드웨어 볼륨키는 제공하지 않습니다.
          </p>
          <button
            className="app-large app-danger"
            onClick={() => uiStore.resetSettings()}
          >
            기본값으로 되돌리기
          </button>
        </section>
      </div>
    </>
  );
}
