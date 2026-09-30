/** Original AdvancedEditor layout/toolbars; local text-only persistence adapter. */
import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { EditorContent, useEditor, type JSONContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import {
  ChevronLeft,
  Download,
  Edit2,
  FileQuestion,
  Merge,
  Moon,
  Plus,
  PlusCircle,
  Save,
  Scissors,
  Sun,
  Tag,
  X,
} from 'lucide-react';
import { LABELS, TeacherModal, type TeacherProps } from './Teacher';

type Chapter = { id: string; title: string; text: string };
const documentFromText = (text: string) => ({
  type: 'doc',
  content: text.split('\n').map((line) => ({
    type: 'paragraph',
    ...(line ? { content: [{ type: 'text', text: line }] } : {}),
  })),
});

export function TeacherEditor({ port, uiState }: TeacherProps) {
  const { sampleId } = useParams();
  const sample = port.findSample(sampleId);
  return sample ? (
    <Editor
      key={sample.id}
      port={port}
      materialId={sample.id}
      initial={uiState.materials[sample.id]}
    />
  ) : (
    <div className="teacher-missing">
      <p>자료를 찾을 수 없습니다.</p>
      <Link to="/teacher">목록으로</Link>
    </div>
  );
}
function Editor({
  port,
  materialId,
  initial,
}: {
  port: TeacherProps['port'];
  materialId: string;
  initial: TeacherProps['uiState']['materials'][string];
}) {
  const [title, setTitle] = useState(initial.title);
  const [chapters, setChapters] = useState<Chapter[]>(
    initial.chapters.map((chapter) => ({ ...chapter })),
  );
  const [active, setActive] = useState(initial.chapters[0].id);
  const [dark, setDark] = useState(false);
  const [editTitle, setEditTitle] = useState(false);
  const [rename, setRename] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [merge, setMerge] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [dragged, setDragged] = useState<string | null>(null);
  const [split, setSplit] = useState(false);
  const [dialog, setDialog] = useState<
    'label' | 'restore' | 'ai' | 'quiz' | null
  >(null);
  const [notice, setNotice] = useState(
    '본문은 현재 탭에 임시 저장할 수 있습니다. 서식은 편집 중에만 유지됩니다.',
  );
  const [quizPrompt, setQuizPrompt] = useState('');
  const activeRef = useRef(active);
  const chaptersRef = useRef(chapters);
  const changing = useRef(false);
  const chapterDocuments = useRef<Record<string, JSONContent>>({});
  activeRef.current = active;
  chaptersRef.current = chapters;
  const editor = useEditor({
    extensions: [StarterKit.configure({ link: false, trailingNode: false })],
    injectCSS: false,
    content: documentFromText(initial.chapters[0].text),
    editorProps: {
      attributes: {
        'aria-label': '샘플 본문 편집',
        role: 'textbox',
        'aria-multiline': 'true',
        spellcheck: 'false',
      },
      // Paste plain text only. No untrusted HTML, image or external URL survives.
      handlePaste(view, event) {
        event.preventDefault();
        const text =
          event.clipboardData?.getData('text/plain').slice(0, 5000) ?? '';
        view.dispatch(view.state.tr.insertText(text));
        return true;
      },
      handleDrop(_view, event) {
        event.preventDefault();
        return true;
      },
    },
    onUpdate: ({ editor: current }) => {
      if (changing.current) return;
      chapterDocuments.current[activeRef.current] = current.getJSON();
      const text = current.getText({ blockSeparator: '\n' }).slice(0, 5000);
      setChapters((old) =>
        old.map((chapter) =>
          chapter.id === activeRef.current ? { ...chapter, text } : chapter,
        ),
      );
    },
  });
  useEffect(() => {
    if (!editor) return;
    changing.current = true;
    editor.commands.setContent(
      chapterDocuments.current[active] ??
        documentFromText(
          chaptersRef.current.find((chapter) => chapter.id === active)?.text ??
            '',
        ),
      { emitUpdate: false },
    );
    changing.current = false;
    setSplit(false);
  }, [active, editor]);
  const save = (published?: boolean) => {
    const current = port.uiStore.getSnapshot().materials[materialId];
    const next = {
      ...current,
      title: title.trim() || initial.title,
      chapters,
      ...(published !== undefined ? { published } : {}),
    };
    const saved =
      JSON.stringify(current) === JSON.stringify(next) ||
      port.uiStore.updateMaterial(materialId, next);
    if (!saved) {
      setNotice(
        '저장할 수 없습니다. 제목·본문의 길이와 챕터 구성을 확인해주세요.',
      );
      return;
    }
    setNotice(
      published
        ? '현재 탭에 발행 상태를 표시했습니다. 서버에 저장하거나 전송하지 않습니다.'
        : '현재 탭에 본문을 임시 저장했습니다. 글자 서식은 다시 열면 기본 서식으로 표시됩니다.',
    );
  };
  const addChapter = (chapterTitle = '새 챕터', text = '', quiz = false) => {
    if (chapters.length >= 20) {
      setNotice('샘플 챕터는 20개까지 추가할 수 있습니다.');
      return;
    }
    const id = `${quiz ? 'quiz' : 'chapter'}-${Date.now()}-${chapters.length}`;
    setChapters((value) => [...value, { id, title: chapterTitle, text }]);
    setActive(id);
    setMerge(false);
  };
  const renameChapter = (id: string) => {
    if (renameValue.trim())
      setChapters((value) =>
        value.map((chapter) =>
          chapter.id === id
            ? { ...chapter, title: renameValue.trim().slice(0, 120) }
            : chapter,
        ),
      );
    setRename(null);
  };
  const mergeSelected = () => {
    const picked = chapters.filter((chapter) => selected.includes(chapter.id));
    if (picked.length < 2) return;
    for (const chapter of picked) delete chapterDocuments.current[chapter.id];
    const merged = {
      ...picked[0],
      text: picked
        .map((chapter) => chapter.text)
        .join('\n\n')
        .slice(0, 5000),
    };
    const updated = chapters.flatMap((chapter) =>
      chapter.id === merged.id
        ? [merged]
        : selected.includes(chapter.id)
          ? []
          : [chapter],
    );
    setChapters(updated);
    setActive(merged.id);
    setMerge(false);
    setSelected([]);
    editor?.commands.setContent(documentFromText(merged.text), {
      emitUpdate: false,
    });
    setNotice('선택한 챕터를 합쳤습니다. 임시 저장으로 현재 탭에 보관하세요.');
  };
  const splitChapter = () => {
    if (!editor) return;
    const parts: string[] = [''];
    editor.state.doc.forEach((node) => {
      if (node.type.name === 'horizontalRule') parts.push('');
      else
        parts[parts.length - 1] +=
          `${parts[parts.length - 1] ? '\n' : ''}${node.textContent}`;
    });
    const filled = parts.map((text) => text.trim()).filter(Boolean);
    if (filled.length < 2) {
      setNotice('나눌 두 본문 사이에 분할선을 넣어주세요.');
      return;
    }
    if (chapters.length + filled.length - 1 > 20) {
      setNotice('챕터는 20개까지 나눌 수 있습니다.');
      return;
    }
    const base = chapters.find((chapter) => chapter.id === active)!;
    delete chapterDocuments.current[active];
    const items = filled.map((text, index) => ({
      id: index ? `chapter-${Date.now()}-${index}` : base.id,
      title: index ? `${base.title} (${index + 1})` : base.title,
      text,
    }));
    setChapters((value) =>
      value.flatMap((chapter) => (chapter.id === active ? items : [chapter])),
    );
    editor.commands.setContent(documentFromText(items[0].text), {
      emitUpdate: false,
    });
    setSplit(false);
    setNotice('챕터를 나눴습니다. 임시 저장으로 현재 탭에 보관하세요.');
  };
  const activeChapter = chapters.find((chapter) => chapter.id === active);
  return (
    <div className={`ae-root ${dark ? 'dark' : ''}`}>
      <header className="ae-header">
        <div className="ae-header-wrapper">
          <Link
            className="ae-back-btn"
            to="/teacher"
            aria-label="자료 목록으로"
          >
            <ChevronLeft size={20} />
          </Link>
          <div className="ae-title-section">
            {editTitle ? (
              <input
                autoFocus
                className="ae-title-input"
                aria-label="자료 제목"
                maxLength={120}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onBlur={() => setEditTitle(false)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') setEditTitle(false);
                }}
              />
            ) : (
              <button
                className="ae-title"
                title="클릭하여 제목 편집"
                onClick={() => setEditTitle(true)}
              >
                {title}
              </button>
            )}
          </div>
          <div className="ae-header-actions">
            <button
              className="ae-icon-btn"
              onClick={() => setDark(!dark)}
              aria-label={dark ? '라이트 모드' : '다크 모드'}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button
              className="ae-icon-btn"
              onClick={() => setDialog('label')}
              aria-label="라벨 선택"
            >
              <Tag size={18} />
            </button>
            <button
              className="ae-icon-btn"
              onClick={() => save()}
              title="현재 탭에 임시 저장"
              aria-label="임시 저장"
            >
              <Save size={18} />
            </button>
            <button className="ae-btn-publish" onClick={() => save(true)}>
              발행하기
            </button>
          </div>
        </div>
      </header>
      <div className="ae-layout">
        <aside className="ae-chapter-sidebar">
          <div className="ae-sidebar-header">
            <div className="ae-sidebar-title-wrapper">
              <h3>챕터 목록</h3>
              <span className="ae-sidebar-hint">드래그하여 순서 변경</span>
            </div>
            <button
              className="ae-sidebar-add-btn"
              aria-label="새 챕터"
              onClick={() => addChapter()}
            >
              <Plus size={16} />
            </button>
          </div>
          <div className="ae-chapter-list">
            {chapters.map((chapter) => (
              <div
                key={chapter.id}
                className={`ae-chapter-item ${active === chapter.id ? 'active' : ''} ${chapter.id.startsWith('quiz-') ? 'quiz-item' : ''} ${merge && selected.includes(chapter.id) ? 'selected' : ''}`}
                draggable={!merge && !rename}
                onDragStart={() => setDragged(chapter.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (!dragged || dragged === chapter.id) return;
                  setChapters((items) => {
                    const copy = items.filter((item) => item.id !== dragged);
                    copy.splice(
                      copy.findIndex((item) => item.id === chapter.id),
                      0,
                      items.find((item) => item.id === dragged)!,
                    );
                    return copy;
                  });
                  setDragged(null);
                }}
                onDragEnd={() => setDragged(null)}
              >
                {rename === chapter.id ? (
                  <input
                    autoFocus
                    className="ae-chapter-input"
                    aria-label="챕터 제목"
                    maxLength={120}
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => renameChapter(chapter.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') renameChapter(chapter.id);
                    }}
                  />
                ) : (
                  <>
                    <button
                      className="ae-chapter-select"
                      onClick={() =>
                        merge
                          ? setSelected((value) =>
                              value.includes(chapter.id)
                                ? value.filter((id) => id !== chapter.id)
                                : [...value, chapter.id],
                            )
                          : setActive(chapter.id)
                      }
                      aria-pressed={
                        merge
                          ? selected.includes(chapter.id)
                          : active === chapter.id
                      }
                    >
                      {merge && <span className="ae-chapter-checkbox" />}
                      <span className="ae-chapter-title">{chapter.title}</span>
                    </button>
                    {!merge && (
                      <div className="ae-chapter-actions">
                        <button
                          className="ae-chapter-action"
                          title="편집"
                          aria-label={`${chapter.title} 제목 편집`}
                          onClick={() => {
                            setRename(chapter.id);
                            setRenameValue(chapter.title);
                          }}
                        >
                          <Edit2 size={12} />
                        </button>
                        <button
                          className="ae-chapter-action delete"
                          title="삭제"
                          aria-label={`${chapter.title} 삭제`}
                          disabled={chapters.length === 1}
                          onClick={() => {
                            const next = chapters.filter(
                              (item) => item.id !== chapter.id,
                            );
                            setChapters(next);
                            if (active === chapter.id) setActive(next[0].id);
                          }}
                        >
                          <X size={12} />
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        </aside>
        <div className="ae-main">
          <div className="ae-toolbar-enhanced">
            <div className="ae-toolbar-section">
              <button
                className={`ae-tool-btn-new split ${split ? 'active' : ''}`}
                onClick={() => {
                  editor?.chain().focus().setHorizontalRule().run();
                  setSplit(true);
                }}
              >
                <Scissors size={18} />
                <span>분할선</span>
              </button>
              {split && (
                <button
                  className="ae-tool-btn-new split active"
                  onClick={splitChapter}
                >
                  분할하기
                </button>
              )}
            </div>
            <div className="ae-toolbar-divider" />
            <div className="ae-toolbar-section">
              <button
                className={`ae-tool-btn-new merge ${merge ? 'active' : ''}`}
                onClick={() => {
                  setMerge(!merge);
                  setSelected([]);
                }}
              >
                <Merge size={18} />
                <span>{merge ? '병합 모드 종료' : '항목 병합 모드'}</span>
              </button>
              {merge && (
                <button
                  className="ae-tool-btn-new merge active"
                  onClick={mergeSelected}
                  disabled={selected.length < 2}
                >
                  병합하기 ({selected.length})
                </button>
              )}
            </div>
            <div className="ae-toolbar-divider" />
            <div className="ae-toolbar-section">
              <button
                className="ae-tool-btn-new quiz"
                onClick={() => setDialog('ai')}
              >
                <Download size={18} />
                <span>AI 퀴즈 생성</span>
              </button>
              <button
                className="ae-tool-btn-new quiz"
                onClick={() => setDialog('quiz')}
              >
                <PlusCircle size={18} />
                <span>직접 퀴즈 추가</span>
              </button>
            </div>
          </div>
          {merge && (
            <div className="ae-merge-hint">
              병합할 항목을 2개 이상 선택한 후 “병합하기”를 클릭하세요.
            </div>
          )}
          {split && (
            <div className="ae-split-hint">
              분할선 앞뒤에 본문을 입력한 후 “분할하기”를 클릭하세요.
            </div>
          )}
          <div
            className={`ae-editor-wrapper ${activeChapter?.id.startsWith('quiz-') ? 'quiz-editor' : ''}`}
          >
            {activeChapter?.id.startsWith('quiz-') && (
              <div className="quiz-badge">
                <FileQuestion size={16} />
                <span>문제 챕터</span>
              </div>
            )}
            <div className="ae-editor-menu">
              <button
                aria-label="기울임"
                title="기울임 (Ctrl+I)"
                className={editor?.isActive('italic') ? 'is-active' : ''}
                onClick={() => editor?.chain().focus().toggleItalic().run()}
              >
                <i>I</i>
              </button>
              <button
                aria-label="밑줄"
                title="밑줄 (Ctrl+U)"
                className={editor?.isActive('underline') ? 'is-active' : ''}
                onClick={() => editor?.chain().focus().toggleUnderline().run()}
              >
                <u>U</u>
              </button>
              <div className="menu-divider" />
              {([1, 2, 3] as const).map((level) => (
                <button
                  key={level}
                  title={`제목 ${level}`}
                  className={
                    editor?.isActive('heading', { level }) ? 'is-active' : ''
                  }
                  onClick={() =>
                    editor?.chain().focus().toggleHeading({ level }).run()
                  }
                >
                  H{level}
                </button>
              ))}
              <div className="menu-divider" />
              <button
                title="글머리 기호"
                onClick={() => editor?.chain().focus().toggleBulletList().run()}
              >
                ●
              </button>
              <button
                title="번호 매기기"
                onClick={() =>
                  editor?.chain().focus().toggleOrderedList().run()
                }
              >
                1.
              </button>
              <div className="menu-divider" />
              <button
                title="인용구"
                onClick={() => editor?.chain().focus().toggleBlockquote().run()}
              >
                “”
              </button>
              <button
                title="코드 블록"
                onClick={() => editor?.chain().focus().toggleCodeBlock().run()}
              >
                {'</>'}
              </button>
            </div>
            <EditorContent editor={editor} className="ae-editor" />
          </div>
          <div className="teacher-editor-footer">
            <p className="teacher-inline-notice" role="status">
              {notice}
            </p>
            <button
              className="cl-chip reset"
              onClick={() => setDialog('restore')}
            >
              샘플 자료 불러오기
            </button>
          </div>
        </div>
      </div>
      {dialog === 'label' && (
        <TeacherModal title="라벨 선택" onClose={() => setDialog(null)}>
          <div className="cl-label-grid">
            {LABELS.map(([id, label]) => (
              <button
                key={id}
                className={`cl-label-option label-${id}`}
                aria-label={label}
                onClick={() => {
                  port.uiStore.updateMaterial(materialId, { label: id });
                  setDialog(null);
                  setNotice(
                    `현재 탭의 자료 라벨을 ${label}(으)로 변경했습니다.`,
                  );
                }}
              />
            ))}
          </div>
        </TeacherModal>
      )}
      {dialog === 'restore' && (
        <TeacherModal
          title="샘플 자료 불러오기"
          onClose={() => setDialog(null)}
        >
          <p>이 자료의 편집 내용을 원래 공개 샘플 본문으로 바꿉니다.</p>
          <button
            className="msm-send-btn"
            onClick={() => {
              port.uiStore.restoreMaterial(materialId);
              chapterDocuments.current = {};
              const restored = port.uiStore.getSnapshot().materials[materialId];
              setTitle(restored.title);
              setChapters(restored.chapters.map((chapter) => ({ ...chapter })));
              setActive(restored.chapters[0].id);
              editor?.commands.setContent(
                documentFromText(restored.chapters[0].text),
                { emitUpdate: false },
              );
              setDialog(null);
              setNotice('공개 샘플 본문을 불러왔습니다.');
            }}
          >
            샘플로 되돌리기
          </button>
        </TeacherModal>
      )}
      {dialog === 'ai' && (
        <TeacherModal title="AI 퀴즈 생성 체험" onClose={() => setDialog(null)}>
          <p>
            실제 AI를 호출하지 않습니다. 이 자료에 준비된 예시 문제를 편집기에
            추가합니다. 학생 앱의 예시 판정 규칙은 바뀌지 않습니다.
          </p>
          <button
            className="msm-send-btn"
            onClick={() => {
              const sample = port.findSample(materialId)!;
              addChapter(
                '예시 문제',
                sample.quiz
                  .map((question, index) => `${index + 1}. ${question.prompt}`)
                  .join('\n\n'),
                true,
              );
              setDialog(null);
            }}
          >
            예시 문제 불러오기
          </button>
        </TeacherModal>
      )}
      {dialog === 'quiz' && (
        <TeacherModal title="직접 퀴즈 추가" onClose={() => setDialog(null)}>
          <label className="teacher-field">
            문제 내용
            <textarea
              aria-label="추가할 문제 내용"
              maxLength={1000}
              value={quizPrompt}
              onChange={(e) => setQuizPrompt(e.target.value)}
            />
          </label>
          <p className="teacher-quiet">
            편집용 문제입니다. 학생 앱의 예시 판정 규칙은 바뀌지 않습니다.
          </p>
          <button
            className="msm-send-btn"
            disabled={!quizPrompt.trim()}
            onClick={() => {
              addChapter('직접 만든 문제', quizPrompt.trim(), true);
              setQuizPrompt('');
              setDialog(null);
            }}
          >
            문제 추가
          </button>
        </TeacherModal>
      )}
    </div>
  );
}
