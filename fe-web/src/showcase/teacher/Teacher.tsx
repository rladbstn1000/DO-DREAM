/**
 * Team teacher UI at 4c763af: Join / ClassroomList / Classroom / StudentRoom /
 * ChatHistory. Presentation copied into an explicit local sample port. No service
 * entry, authentication, upload or server fallback is imported.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, Route, Routes, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Award,
  BookOpen,
  Download,
  FileText,
  Home,
  LogOut,
  MessageCircle,
  Plus,
  Search,
  Send,
  SortAsc,
  SortDesc,
  Tag,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import type { ShowcasePort } from '../port';
import type { OriginalSnapshot, WrittenResult } from '../originalStore';
import type { ShowcaseSnapshot, QuizResult } from '../store';
import type { Sample } from '../samples';
import teacherAvatar from '../../assets/classList/teacher.png';
import schoolImg from '../../assets/classList/school.png';
import maleImg from '../../assets/classroom/male.png';
import femaleImg from '../../assets/classroom/female.png';
import MaterialSendModal from './MaterialSendModal';
import { TeacherEditor } from './TeacherEditor';
import './Join.css';
import './ClassroomList.css';
import './Classroom.css';
import './StudentRoom.css';
import './ChatHistory.css';
import './AdvancedEditor.css';
import './MaterialSendModal.css';
import './teacher.css';

export type TeacherProps = {
  port: ShowcasePort;
  state: ShowcaseSnapshot;
  uiState: OriginalSnapshot;
};
export const LABELS = [
  ['red', '빨강'],
  ['orange', '주황'],
  ['yellow', '노랑'],
  ['green', '초록'],
  ['blue', '파랑'],
  ['purple', '보라'],
  ['gray', '회색'],
] as const;
const classrooms = [
  { id: '1-1', name: '1학년 1반' },
  { id: '1-2', name: '1학년 2반' },
  { id: '2-1', name: '2학년 1반' },
  { id: '2-2', name: '2학년 2반' },
];
const students = [
  {
    id: 'demo-student',
    name: '체험 학생',
    gender: 'female' as const,
    grade: '1학년 1반',
    avatarUrl: femaleImg,
  },
  {
    id: 'sample-student',
    name: '예시 학생',
    gender: 'male' as const,
    grade: '1학년 1반',
    avatarUrl: maleImg,
  },
];

export function TeacherJoin() {
  const [mode, setMode] = useState<'sign-in' | 'sign-up'>('sign-in');
  const entries = (
    <>
      <div className="input-group">
        <p className="join-demo-title">DO:DREAM 체험 시작</p>
      </div>
      <Link
        className="join-demo-button"
        data-testid="start-teacher"
        to="/teacher"
      >
        교사 체험
      </Link>
      <Link
        className="join-demo-button secondary"
        data-testid="start-student"
        to="/app"
      >
        학생 앱 체험
      </Link>
      <p>가입 없이 공개 샘플로 둘러보세요.</p>
      <button
        className="join-toggle"
        onClick={() => setMode(mode === 'sign-in' ? 'sign-up' : 'sign-in')}
      >
        다른 시작 배경 보기
      </button>
    </>
  );
  return (
    <div className="original-teacher original-join">
      <div className={`container ${mode}`}>
        <div className="row">
          <div className="col align-items-center flex-col sign-up">
            <div className="form-wrapper align-items-center">
              <div className="form sign-up" inert={mode !== 'sign-up'}>
                {entries}
              </div>
            </div>
          </div>
          <div className="col align-items-center flex-col sign-in">
            <div className="form-wrapper align-items-center">
              <div className="form sign-in" inert={mode !== 'sign-in'}>
                {entries}
              </div>
            </div>
          </div>
        </div>
        <div className="row content-row">
          <div className="col align-items-center flex-col">
            <div className="text sign-in">
              <h2>DO:DREAM</h2>
            </div>
          </div>
          <div className="col align-items-center flex-col">
            <div className="text sign-up">
              <h2>DO:DREAM</h2>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function TeacherExperience(props: TeacherProps) {
  return (
    <div className="original-teacher">
      <Routes>
        <Route index element={<TeacherList {...props} />} />
        <Route
          path="classroom/:classId"
          element={<TeacherClassroom {...props} />}
        />
        <Route
          path="student/:studentId"
          element={<TeacherStudent {...props} />}
        />
        <Route
          path="history/:sampleId"
          element={<TeacherHistory {...props} />}
        />
        <Route path="editor/:sampleId" element={<TeacherEditor {...props} />} />
        <Route
          path="*"
          element={
            <>
              <TeacherHeader />
              <p className="teacher-missing">
                이 체험 화면을 찾을 수 없습니다.{' '}
                <Link to="/teacher">자료 목록으로</Link>
              </p>
            </>
          }
        />
      </Routes>
    </div>
  );
}

export function TeacherHeader({ back = false }: { back?: boolean }) {
  return (
    <header className="cl-header">
      <div className="cl-header-wrapper">
        <Link className="cl-header-title" to="/teacher">
          DO:DREAM
        </Link>
        <Link className="cl-logout-button" to={back ? '/teacher' : '/'}>
          {back ? <ArrowLeft size={18} /> : <LogOut size={18} />}
          <span>{back ? '목록으로' : '체험 나가기'}</span>
        </Link>
      </div>
    </header>
  );
}
function TeacherSidebar({
  port,
  uiState,
  label = '선생님',
}: Pick<TeacherProps, 'port' | 'uiState'> & { label?: string }) {
  return (
    <aside className="cl-sidebar">
      <div className="cl-sidebar-content">
        <div className="cl-profile-mini">
          <img
            className="cl-profile-avatar-mini"
            src={teacherAvatar}
            alt="교사 아바타"
          />
          <h2 className="cl-profile-name-mini">샘플 선생님</h2>
          <p className="cl-profile-email-mini">teacher@example.invalid</p>
          <p className="cl-profile-label-mini">{label}</p>
        </div>
        <div className="cl-sidebar-divider" />
        <div className="cl-memo">
          <div className="cl-memo-stage">
            <div className="cl-memo-zoom">
              <div className="cl-memo-header">
                <div className="cl-memo-latest">
                  <span>현재 탭의 메모</span>
                </div>
              </div>
              <textarea
                className="cl-memo-input"
                aria-label="수업 준비/할 일 메모"
                placeholder="수업 준비/할 일 메모"
                maxLength={1000}
                value={uiState.memo}
                onChange={(e) => port.uiStore.setMemo(e.target.value)}
              />
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
export function TeacherModal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const last =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const dialog = ref.current;
    dialog
      ?.querySelector<HTMLElement>(
        'button,input,textarea,select,[tabindex="0"]',
      )
      ?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !dialog) return;
      const items = [
        ...dialog.querySelectorAll<HTMLElement>(
          'button:not(:disabled),a[href],input,textarea,select,[tabindex="0"]',
        ),
      ].filter((item) => !item.hidden && item.getClientRects().length > 0);
      if (!items.length) {
        event.preventDefault();
        return;
      }
      const index = items.indexOf(document.activeElement as HTMLElement);
      if (event.shiftKey && index <= 0) {
        event.preventDefault();
        items[items.length - 1]?.focus();
      } else if (!event.shiftKey && (index === items.length - 1 || index < 0)) {
        event.preventDefault();
        items[0].focus();
      }
    };
    dialog?.addEventListener('keydown', onKey);
    return () => {
      dialog?.removeEventListener('keydown', onKey);
      last?.focus();
    };
  }, []);
  return (
    <div className="msm-overlay">
      <div
        className="msm-modal"
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <div className="msm-header">
          <h2>{title}</h2>
          <button className="msm-close-btn" aria-label="닫기" onClick={onClose}>
            <X size={24} />
          </button>
        </div>
        <div className="msm-content">{children}</div>
      </div>
    </div>
  );
}
function Filters({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (value: string[]) => void;
}) {
  return (
    <div className="cl-filter-chips">
      {LABELS.map(([id, text]) => (
        <button
          key={id}
          className={`cl-chip label-${id} ${selected.includes(id) ? 'active' : ''}`}
          aria-pressed={selected.includes(id)}
          onClick={() =>
            onChange(
              selected.includes(id)
                ? selected.filter((item) => item !== id)
                : [...selected, id],
            )
          }
        >
          {text}
        </button>
      ))}
      {selected.length > 0 && (
        <button className="cl-chip reset" onClick={() => onChange([])}>
          초기화
        </button>
      )}
    </div>
  );
}
function TeacherList({ port, state, uiState }: TeacherProps) {
  const navigate = useNavigate();
  const [labels, setLabels] = useState<string[]>([]);
  const [dialog, setDialog] = useState<{
    type: 'sample' | 'send' | 'label' | 'delete' | 'download';
    id?: string;
  } | null>(null);
  const [hidden, setHidden] = useState<string[]>([]);
  const [notice, setNotice] = useState('');
  const visible = port.samples.filter(
    (sample) =>
      !hidden.includes(sample.id) &&
      (!labels.length || labels.includes(uiState.materials[sample.id].label)),
  );
  const selected = port.samples.find((sample) => sample.id === dialog?.id);
  return (
    <div className="cl-root teacher-list">
      <TeacherHeader />
      <div className="cl-layout">
        <TeacherSidebar port={port} uiState={uiState} />
        <main className="cl-main-content">
          <div className="cl-classrooms-section">
            <div className="cl-section-header">
              <h2 className="cl-section-title">4개 반 담당</h2>
            </div>
            <div className="cl-classrooms-grid">
              {classrooms.map((classroom) => (
                <Link
                  key={classroom.id}
                  className="cl-classroom-card"
                  to={`/teacher/classroom/${classroom.id}`}
                >
                  <div className="cl-classroom-header">
                    <div className="cl-classroom-title">
                      <h3>{classroom.name}</h3>
                    </div>
                  </div>
                  <div className="cl-classroom-stats">
                    <div className="cl-stat">
                      <Users size={18} />
                      <div className="cl-stat-info">
                        <p className="cl-stat-num">2</p>
                        <p className="cl-stat-text">학생</p>
                      </div>
                    </div>
                    <div className="cl-divider" />
                    <div className="cl-stat">
                      <BookOpen size={18} />
                      <div className="cl-stat-info">
                        <p className="cl-stat-num">{port.samples.length}</p>
                        <p className="cl-stat-text">자료</p>
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
          <div className="cl-materials-section">
            <div className="cl-materials-header">
              <div className="cl-section-header">
                <h2 className="cl-section-title">
                  내 자료 ({visible.length}개)
                </h2>
                <Filters selected={labels} onChange={setLabels} />
              </div>
              <div className="cl-last-updated">공개 샘플 자료</div>
              <div className="cl-cta-row">
                <div className="cl-feature-explain">
                  <p className="cl-feature-title">자료 만들기란?</p>
                  <ul className="cl-feature-list">
                    <li>공개 샘플 자료를 불러와 편집</li>
                    <li>에디터에서 내용 편집 · 단원 분리</li>
                    <li>완성된 자료를 반/학생에게 공유 체험</li>
                    <li>앱에서 음성 학습 지원</li>
                  </ul>
                </div>
                <button
                  className="cl-create-material-btn"
                  data-testid="teacher-new-material"
                  onClick={() => setDialog({ type: 'sample' })}
                >
                  <Plus size={20} />
                  <span>새 자료 만들기</span>
                </button>
              </div>
            </div>
            {notice && (
              <p className="teacher-inline-notice" role="status">
                {notice}
              </p>
            )}
            <div className="cl-materials-list">
              {!visible.length && (
                <div className="cl-empty-materials">
                  <FileText size={48} />
                  <p>선택한 라벨의 자료가 없습니다</p>
                  <button
                    className="cl-chip reset"
                    onClick={() => {
                      setLabels([]);
                      setHidden([]);
                    }}
                  >
                    자료 다시 보기
                  </button>
                </div>
              )}
              {visible.map((sample) => (
                <div className="cl-material-item" key={sample.id}>
                  <div
                    className={`cl-material-label-bar label-${uiState.materials[sample.id].label}`}
                  />
                  <Link
                    className="cl-material-clickable"
                    to={`/teacher/editor/${sample.id}`}
                    data-testid={`teacher-material-${sample.id}`}
                  >
                    <div className="cl-material-icon">
                      <FileText size={18} />
                    </div>
                    <div className="cl-material-info">
                      <h3 className="cl-material-title">
                        {uiState.materials[sample.id].title}
                      </h3>
                      <div className="cl-material-meta">
                        <span className="cl-material-date">2026.09.30</span>
                        <span
                          className={`cl-material-status ${uiState.materials[sample.id].published ? 'published' : 'draft'}`}
                        >
                          {uiState.materials[sample.id].published
                            ? '발행됨'
                            : '작성중'}
                        </span>
                      </div>
                    </div>
                  </Link>
                  <div className="cl-material-actions">
                    {(
                      [
                        ['download', Download, '자료 내보내기'],
                        ['send', Send, '자료 공유'],
                        ['label', Tag, '라벨 편집'],
                        ['delete', Trash2, '삭제'],
                      ] as const
                    ).map(([type, Icon, label]) => (
                      <button
                        className={`cl-material-action-btn ${type}-btn`}
                        key={type}
                        aria-label={`${sample.title} ${label}`}
                        title={label}
                        onClick={() => setDialog({ type, id: sample.id })}
                      >
                        <Icon size={16} />
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </main>
      </div>
      {dialog?.type === 'sample' && (
        <TeacherModal
          title="샘플 자료 불러오기"
          onClose={() => setDialog(null)}
        >
          <p>파일 업로드·OCR 대신 직접 작성한 공개 자료를 선택합니다.</p>
          <div className="teacher-sample-choices">
            {port.samples.map((sample) => (
              <button
                className="msm-student-item"
                key={sample.id}
                onClick={() => {
                  setDialog(null);
                  navigate(`/teacher/editor/${sample.id}`);
                }}
              >
                <FileText size={22} />
                <span>{sample.title}</span>
              </button>
            ))}
          </div>
        </TeacherModal>
      )}
      {dialog?.type === 'send' && selected && (
        <TeacherSend
          port={port}
          sample={selected}
          onClose={() => setDialog(null)}
          onSent={(count) => {
            setDialog(null);
            setNotice(
              `현재 탭의 ${count}명에게 샘플 공유를 표시했습니다. 다른 기기로 전송하지 않습니다.`,
            );
          }}
        />
      )}
      {dialog?.type === 'label' && selected && (
        <TeacherModal title="라벨 선택" onClose={() => setDialog(null)}>
          <div className="cl-label-grid">
            {LABELS.map(([id, label]) => (
              <button
                key={id}
                aria-label={label}
                aria-pressed={uiState.materials[selected.id].label === id}
                className={`cl-label-option label-${id} ${uiState.materials[selected.id].label === id ? 'active' : ''}`}
                onClick={() => {
                  port.uiStore.updateMaterial(selected.id, { label: id });
                  setDialog(null);
                }}
              >
                {uiState.materials[selected.id].label === id ? '✓' : ''}
              </button>
            ))}
          </div>
        </TeacherModal>
      )}
      {dialog?.type === 'delete' && selected && (
        <TeacherModal title="자료 숨기기" onClose={() => setDialog(null)}>
          <p>
            이 목록에서 샘플을 잠시 숨깁니다. 원본 자료와 학생 기록은
            보존됩니다.
          </p>
          <button
            className="msm-send-btn"
            onClick={() => {
              setHidden((value) => [...value, selected.id]);
              setDialog(null);
              setNotice(
                '목록에서 잠시 숨겼습니다. 페이지를 다시 열면 돌아옵니다.',
              );
            }}
          >
            숨기기
          </button>
        </TeacherModal>
      )}
      {dialog?.type === 'download' && selected && (
        <TeacherModal
          title="샘플 본문 내보내기"
          onClose={() => setDialog(null)}
        >
          <p>
            원본의 Word 내보내기 위치입니다. 체험에서는 아래 본문을 선택해
            복사할 수 있습니다.
          </p>
          <textarea
            className="teacher-export"
            aria-label="내보낼 샘플 본문"
            readOnly
            value={uiState.materials[selected.id].chapters
              .map((chapter) => `${chapter.title}\n${chapter.text}`)
              .join('\n\n')}
          />
        </TeacherModal>
      )}
      <span className="teacher-sr-only">
        현재 탭의 질문{' '}
        {Object.values(state.samples).reduce(
          (sum, value) => sum + value.questionIds.length,
          0,
        )}
        개
      </span>
    </div>
  );
}
function TeacherSend({
  port,
  sample,
  onClose,
  onSent,
}: {
  port: ShowcasePort;
  sample: Sample;
  onClose: () => void;
  onSent: (count: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const last = document.activeElement as HTMLElement;
    const el = ref.current;
    el?.querySelector<HTMLElement>('button')?.focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        const controls = [
          ...el!.querySelectorAll<HTMLElement>(
            'button:not(:disabled),input,[tabindex="0"]',
          ),
        ];
        const index = controls.indexOf(document.activeElement as HTMLElement);
        if (event.shiftKey && index <= 0) {
          event.preventDefault();
          controls[controls.length - 1]?.focus();
        } else if (!event.shiftKey && index === controls.length - 1) {
          event.preventDefault();
          controls[0]?.focus();
        }
      }
    };
    el?.addEventListener('keydown', handler);
    return () => {
      el?.removeEventListener('keydown', handler);
      last?.focus();
    };
  }, [onClose]);
  return (
    <div ref={ref}>
      <MaterialSendModal
        classrooms={classrooms.map((item) => ({ ...item, count: 2 }))}
        studentsByClassroom={Object.fromEntries(
          classrooms.map((item) => [
            item.id,
            students.map((student) => ({ ...student, grade: item.name })),
          ]),
        )}
        selectedMaterial={{
          id: sample.id,
          title: port.uiStore.getSnapshot().materials[sample.id].title,
          uploadDate: '2026.09.30',
          content: '',
        }}
        onClose={onClose}
        onSend={(ids) => {
          port.uiStore.updateMaterial(sample.id, { published: true });
          onSent(ids.length);
        }}
        schoolImage={schoolImg}
        maleImage={maleImg}
        femaleImage={femaleImg}
      />
    </div>
  );
}
function TeacherClassroom({ port, state, uiState }: TeacherProps) {
  const { classId } = useParams();
  const [query, setQuery] = useState('');
  const [studentQuery, setStudentQuery] = useState('');
  const [sort, setSort] = useState(false);
  const [studentSort, setStudentSort] = useState(false);
  const [labels, setLabels] = useState<string[]>([]);
  const classroom = classrooms.find((item) => item.id === classId);
  const materials = port.samples.filter(
    (sample) =>
      uiState.materials[sample.id].title.includes(query) &&
      (!labels.length || labels.includes(uiState.materials[sample.id].label)),
  );
  const progress = Math.round(
    (port.samples.filter(
      (sample) =>
        uiState.quizzes[sample.id].result || state.samples[sample.id].result,
    ).length /
      port.samples.length) *
      100,
  );
  const visibleStudents = students.filter((student) =>
    `${student.name}${classroom?.name}`.includes(studentQuery),
  );
  if (!classroom)
    return (
      <>
        <TeacherHeader back />
        <p className="teacher-missing">이 샘플 반은 없습니다.</p>
      </>
    );
  return (
    <div className="cl-root classroom-page">
      <TeacherHeader back />
      <TeacherSidebar port={port} uiState={uiState} label={classroom.name} />
      <main className="cl-main-fixed">
        <div className="cl-two-columns">
          <section className="cl-card">
            <div className="cl-card-head">
              <div className="cl-head-left">
                <h3>공유된 학습 자료</h3>
              </div>
              <div className="cl-head-right">
                <div className="cl-input-wrap cl-control">
                  <Search size={16} />
                  <input
                    className="cl-input"
                    aria-label="자료 제목 검색"
                    placeholder="자료 제목 검색"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
                <button
                  className="cl-sort-btn cl-control"
                  onClick={() => setSort(!sort)}
                >
                  {sort ? <SortAsc size={16} /> : <SortDesc size={16} />}
                  <span>{sort ? '오래된 순' : '최신 순'}</span>
                </button>
              </div>
            </div>
            <Filters selected={labels} onChange={setLabels} />
            <div className="cl-section-scroll">
              <div className="cl-materials-list">
                {(sort ? [...materials].reverse() : materials).map((sample) => (
                  <Link
                    className="cl-material-item"
                    key={sample.id}
                    to={`/teacher/editor/${sample.id}`}
                  >
                    <div
                      className={`cl-material-label-bar label-${uiState.materials[sample.id].label}`}
                    />
                    <div className="cl-material-icon">
                      <FileText size={18} />
                    </div>
                    <div className="cl-material-info">
                      <h3 className="cl-material-title">
                        {uiState.materials[sample.id].title}
                      </h3>
                      <span className="cl-material-date">공개 샘플</span>
                    </div>
                  </Link>
                ))}
                {!materials.length && (
                  <p className="cl-empty-hint">검색 결과가 없습니다.</p>
                )}
              </div>
            </div>
          </section>
          <section className="cl-card">
            <div className="cl-card-head">
              <div className="cl-head-left">
                <h3>학생 관리 ({visibleStudents.length}명)</h3>
              </div>
              <div className="cl-head-right">
                <div className="cl-input-wrap cl-control">
                  <Search size={16} />
                  <input
                    className="cl-input"
                    aria-label="학생 검색"
                    placeholder="이름 또는 학년/반 검색"
                    value={studentQuery}
                    onChange={(e) => setStudentQuery(e.target.value)}
                  />
                </div>
                <button
                  className="cl-sort-btn cl-control"
                  onClick={() => setStudentSort(!studentSort)}
                >
                  {studentSort ? <SortAsc size={16} /> : <SortDesc size={16} />}
                  <span>{studentSort ? '이름순' : '진행률순'}</span>
                </button>
              </div>
            </div>
            <div className="cl-section-scroll cl-students-grid">
              {(studentSort
                ? [...visibleStudents].sort((a, b) =>
                    a.name.localeCompare(b.name, 'ko'),
                  )
                : visibleStudents
              ).map((student) => (
                <Link
                  className="cl-student-card"
                  key={student.id}
                  to={`/teacher/student/${student.id}`}
                >
                  <div className="cl-student-top">
                    <img
                      className="cl-student-avatar"
                      src={student.avatarUrl}
                      alt="학생 아바타"
                    />
                    <div className="cl-student-info">
                      <h4>{student.name}</h4>
                      <p>{classroom.name}</p>
                    </div>
                  </div>
                  <div className="cl-progress">
                    <progress
                      className="teacher-progress"
                      max={100}
                      value={student.id === 'demo-student' ? progress : 0}
                    />
                    <span className="cl-progress-text">
                      {student.id === 'demo-student' ? progress : 0}%
                    </span>
                  </div>
                </Link>
              ))}
              {visibleStudents.length > 0 && Array.from({length: Math.max(0, 6 - visibleStudents.length)}, (_, index) => <div className="cl-student-card cl-student-card-empty" key={`empty-${index}`} aria-hidden="true" />)}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
function TeacherStudent({ port, state, uiState }: TeacherProps) {
  const { studentId } = useParams();
  const student = students.find((item) => item.id === studentId);
  const active = studentId === 'demo-student';
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState(false);
  const results = active
    ? port.samples.flatMap<{
        sample: Sample;
        result: WrittenResult | QuizResult;
      }>((sample) => {
        const written = uiState.quizzes[sample.id].results;
        return written.length
          ? written.map((result) => ({ sample, result }))
          : state.samples[sample.id].results.map((result) => ({
              sample,
              result,
            }));
      })
    : [];
  const questions = active
    ? port.samples.flatMap((sample) =>
        state.samples[sample.id].questionIds.map((id) => ({
          sample,
          question: sample.recommendations.find((q) => q.id === id)!,
        })),
      )
    : [];
  const completed = new Set(results.map(({ sample }) => sample.id)).size;
  const percent = Math.round((completed / port.samples.length) * 100);
  const accuracy = results.length
    ? Math.round(
        (results.reduce(
          (sum, { result }) => sum + result.score / result.total,
          0,
        ) /
          results.length) *
          100,
      )
    : 0;
  const filtered = port.samples.filter((sample) =>
    uiState.materials[sample.id].title.includes(query),
  );
  if (!student)
    return (
      <>
        <TeacherHeader back />
        <p className="teacher-missing">이 샘플 학생은 없습니다.</p>
      </>
    );
  return (
    <div className="sr-root student-room-page">
      <TeacherHeader back />
      <aside className="cl-sidebar">
        <div className="cl-sidebar-content">
          <div className="cl-profile-mini">
            <img
              className="cl-profile-avatar-mini"
              src={student.avatarUrl}
              alt="학생 아바타"
            />
            <h2 className="cl-profile-name-mini">{student.name}</h2>
            <p className="cl-profile-email-mini">{student.grade}</p>
          </div>
          <div className="sr-sidebar-stats">
            {[
              ['전체 학습 진도', `${percent}%`],
              ['완료한 자료', `${completed}/${port.samples.length}`],
              ['평균 정답률', `${accuracy}%`],
              ['질문 & 답변', String(questions.length)],
            ].map(([label, value]) => (
              <div className="sr-sidebar-stat-item" key={label}>
                <div className="sr-sidebar-stat-label">{label}</div>
                <div className="sr-sidebar-stat-value">{value}</div>
              </div>
            ))}
          </div>
        </div>
      </aside>
      <main className="cl-main-fixed">
        <div className="sr-content-wrapper">
          <section className="cl-card">
            <div className="cl-card-head">
              <div className="cl-head-left">
                <h3>받은 학습 자료</h3>
              </div>
              <div className="cl-head-right">
                <div className="cl-input-wrap cl-control">
                  <Search size={16} />
                  <input
                    className="cl-input"
                    aria-label="자료 제목 검색"
                    placeholder="자료 제목 검색"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
                <button
                  className="cl-sort-btn cl-control"
                  onClick={() => setSort(!sort)}
                >
                  {sort ? <SortAsc size={16} /> : <SortDesc size={16} />}
                  <span>{sort ? '오래된 순' : '최신 순'}</span>
                </button>
              </div>
            </div>
            <div className="cl-section-scroll">
              <div className="cl-materials-list">
                {(sort ? [...filtered].reverse() : filtered).map((sample) => (
                  <Link
                    className="cl-material-item"
                    key={sample.id}
                    to={`/teacher/editor/${sample.id}`}
                  >
                    <div className="cl-material-icon">
                      <FileText size={18} />
                    </div>
                    <div className="cl-material-info">
                      <h3 className="cl-material-title">
                        {uiState.materials[sample.id].title}
                      </h3>
                      <div className="cl-material-meta">
                        <span>공개 샘플 · 샘플 선생님 발행</span>
                      </div>
                    </div>
                    <span className="sr-status-badge">
                      {results.some((item) => item.sample.id === sample.id)
                        ? '완료'
                        : '학습 전'}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          </section>
          <section className="cl-card">
            <div className="cl-card-head">
              <div className="cl-head-left">
                <Award size={20} />
                <h3>퀴즈 성적</h3>
              </div>
            </div>
            <div className="cl-section-scroll">
              {results.length ? (
                <div className="sr-quiz-grid">
                  {results.map(({ sample, result }) => (
                    <article
                      className="sr-quiz-card"
                      key={`${sample.id}-${result.attemptNumber}`}
                    >
                      <div className="sr-quiz-card-header">
                        <h4 className="sr-quiz-card-title">
                          {uiState.materials[sample.id].title} ·{' '}
                          {result.attemptNumber}회
                        </h4>
                      </div>
                      <div className="sr-quiz-card-body">
                        <div className="sr-quiz-card-row">
                          <span className="sr-quiz-card-label">
                            전체 문제 수
                          </span>
                          <span className="sr-quiz-card-value">
                            총 {result.total}개의 문제 중에서
                          </span>
                        </div>
                        <div className="sr-quiz-card-row">
                          <span className="sr-quiz-card-label">정답 개수</span>
                          <span className="sr-quiz-card-value">
                            {result.score}개 정답
                          </span>
                        </div>
                        <div className="sr-quiz-card-row">
                          <span className="sr-quiz-card-label">정답률</span>
                          <span className="sr-quiz-card-value sr-quiz-rate">
                            {Math.round((result.score / result.total) * 100)}%
                          </span>
                        </div>
                        <p className="teacher-quiet">
                          현재 탭 · 준비된 예시 판정
                        </p>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="cl-empty-hint">
                  퀴즈 결과가 없습니다. 학생 앱 체험에서 문제를 풀어보세요.
                </p>
              )}
            </div>
          </section>
          <section className="cl-card">
            <div className="cl-card-head">
              <div className="cl-head-left">
                <MessageCircle size={20} />
                <h3>질문 &amp; 답변</h3>
              </div>
            </div>
            <div className="cl-section-scroll">
              {questions.length ? (
                <div className="sr-qa-list">
                  {questions.map(({ sample, question }) => (
                    <Link
                      className="sr-qa-item"
                      key={question.id}
                      to={`/teacher/history/${sample.id}`}
                    >
                      <div className="sr-qa-preview-left">
                        <p className="sr-qa-preview-text">
                          {question.question}
                        </p>
                      </div>
                      <div className="sr-qa-preview-right">
                        <span className="sr-topic-badge">{sample.title}</span>
                        <span className="sr-qa-date">현재 탭</span>
                      </div>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="cl-empty-hint">
                  질문 &amp; 답변이 없습니다. 학생 앱 체험에서 질문해보세요.
                </p>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
function TeacherHistory({ port, state, uiState }: TeacherProps) {
  const { sampleId } = useParams();
  const sample = port.findSample(sampleId);
  const ids = sample ? state.samples[sample.id].questionIds : [];
  return (
    <div className="chat-history-page">
      <header className="ch-header">
        <div className="ch-header-wrapper">
          <Link
            className="ch-back-button"
            aria-label="학생 결과로 돌아가기"
            to="/teacher/student/demo-student"
          >
            <ArrowLeft size={24} />
          </Link>
          <div className="ch-header-info">
            <h1>{sample ? uiState.materials[sample.id].title : '자료를 찾을 수 없습니다'}</h1>
            <p>체험 학생 · 현재 탭의 질문/대화 이력</p>
          </div>
        </div>
      </header>
      <main className="ch-main">
        {sample && ids.length ? (
          <div className="ch-messages">
            {ids.flatMap((id) => {
              const question = sample.recommendations.find(
                (item) => item.id === id,
              )!;
              return [
                <div className="ch-message ch-user" key={`${id}-q`}>
                  <div className="ch-bubble">
                    <p>{question.question}</p>
                    <span className="ch-time">체험 학생</span>
                  </div>
                </div>,
                <div className="ch-message ch-ai" key={`${id}-a`}>
                  <div className="ch-bubble">
                    <p>{question.answer}</p>
                    <span className="ch-time">준비된 샘플 답변</span>
                  </div>
                </div>,
              ];
            })}
          </div>
        ) : (
          <div className="ch-empty">
            <MessageCircle size={48} />
            <p>아직 대화 이력이 없습니다.</p>
            <Link to="/app">학생 앱에서 질문하기</Link>
          </div>
        )}
      </main>
    </div>
  );
}
