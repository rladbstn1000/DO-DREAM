import React, { useMemo, useState, useEffect } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import BoldMark from '@tiptap/extension-bold';
import Underline from '@tiptap/extension-underline';
import Link from '@tiptap/extension-link';
import Highlight from '@tiptap/extension-highlight';
import TextAlign from '@tiptap/extension-text-align';
import Image from '@tiptap/extension-image';
import Subscript from '@tiptap/extension-subscript';
import Superscript from '@tiptap/extension-superscript';
import HorizontalRule from '@tiptap/extension-horizontal-rule';
import Swal from 'sweetalert2';
import {
  Home,
  Bold,
  Italic,
  Underline as UnderlineIcon,
  List,
  ListOrdered,
  Highlighter,
  AlignLeft,
  AlignCenter,
  AlignRight,
  AlignJustify,
  Heading1,
  Heading2,
  Heading3,
  Plus,
  Trash2,
  Edit2,
  Sun,
  Moon,
  Scissors,
} from 'lucide-react';
import './AdvancedEditor.css';

/* ---------- TipTap Command 타입 보강: setChapterBreak 추가 ---------- */
declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    chapterBreak: {
      /** 커서 위치에 챕터 분할선(hr) 삽입 */
      setChapterBreak: () => ReturnType;
    };
  }
}

type Chapter = {
  id: string;
  title: string;
  content: string;
};

type EditorProps = {
  extractedText: string;
  onPublish: (title: string, chapters: Chapter[]) => void;
  onBack: () => void;
};

/** 커스텀 분할선: data-chapter-break="true" 를 가진 HR + 전용 커맨드 제공 */
const ChapterBreak = HorizontalRule.extend({
  name: 'chapterBreak',

  addAttributes() {
    return {
      'data-chapter-break': {
        default: 'true',
        parseHTML: () => 'true',
        renderHTML: () => ({ 'data-chapter-break': 'true' }),
      },
      class: {
        default: 'ae-chapter-break',
      },
    };
  },

  addCommands() {
    return {
      setChapterBreak:
        () =>
        ({ commands }) =>
          commands.insertContent({ type: this.name }),
    };
  },
});

export default function AdvancedEditor({
  extractedText,
  onPublish,
  onBack,
}: EditorProps) {
  const [materialTitle, setMaterialTitle] = useState('새로운 자료');
  const [showTitleInput, setShowTitleInput] = useState(false);
  const [darkMode, setDarkMode] = useState(false);

  const [chapters, setChapters] = useState<Chapter[]>([
    {
      id: '1',
      title: '챕터 1',
      content: extractedText || '<p>내용을 입력하세요...</p>',
    },
  ]);

  const [activeChapterId, setActiveChapterId] = useState('1');
  const [editingChapterId, setEditingChapterId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [hasSelection, setHasSelection] = useState(false);

  const activeChapter = useMemo(
    () => chapters.find((c) => c.id === activeChapterId),
    [chapters, activeChapterId]
  );

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        bold: false,            // Bold는 별도 확장으로 등록
        horizontalRule: false,  // 기본 HR 비활성화 (ChapterBreak만 사용)
      }),
      BoldMark,
      ChapterBreak,
      Underline,
      Link.configure({ openOnClick: false }),
      Highlight.configure({ multicolor: true }),
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      Image,
      Subscript,
      Superscript,
    ],
    content: activeChapter?.content || '<p>내용을 입력하세요...</p>',
  });

  // 드래그 선택이 있을 때만 툴버튼 active 표시
  useEffect(() => {
    if (!editor) return;
    const update = () => setHasSelection(!editor.state.selection.empty);
    editor.on('selectionUpdate', update);
    editor.on('transaction', update);
    return () => {
      editor.off('selectionUpdate', update);
      editor.off('transaction', update);
    };
  }, [editor]);

  // 챕터 전환 시 에디터 업데이트
  useEffect(() => {
    if (editor && activeChapter) {
      editor.commands.setContent(activeChapter.content);
    }
  }, [activeChapterId, editor, activeChapter]);

  // 에디터 내용 저장
  const saveChapterContent = () => {
    if (editor && activeChapter) {
      setChapters((prev) =>
        prev.map((ch) =>
          ch.id === activeChapterId ? { ...ch, content: editor.getHTML() } : ch
        )
      );
    }
  };

  const handleAddChapter = () => {
    saveChapterContent();
    const newId = String(
      Math.max(...chapters.map((c) => parseInt(c.id)), 0) + 1
    );
    const newChapter: Chapter = {
      id: newId,
      title: `챕터 ${newId}`,
      content: '<p>새 챕터의 내용을 입력하세요...</p>',
    };
    setChapters((prev) => [...prev, newChapter]);
    setActiveChapterId(newId);
  };

  const handleDeleteChapter = (id: string) => {
    if (chapters.length === 1) {
      Swal.fire({
        icon: 'warning',
        title: '최소 하나의 챕터가 필요합니다',
        confirmButtonColor: '#192b55',
      });
      return;
    }

    Swal.fire({
      title: '챕터를 삭제하시겠습니까?',
      text: '이 작업은 되돌릴 수 없습니다',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#d1d5db',
      confirmButtonText: '삭제',
      cancelButtonText: '취소',
    }).then((result) => {
      if (result.isConfirmed) {
        const newChapters = chapters.filter((c) => c.id !== id);
        setChapters(newChapters);
        if (activeChapterId === id && newChapters.length > 0) {
          setActiveChapterId(newChapters[0].id);
        }
        Swal.fire({
          icon: 'success',
          title: '챕터가 삭제되었습니다',
          confirmButtonColor: '#192b55',
        });
      }
    });
  };

  const handleEditChapterTitle = (id: string, title: string) => {
    setEditingChapterId(id);
    setEditingTitle(title);
  };

  const handleSaveChapterTitle = (id: string) => {
    if (!editingTitle.trim()) {
      Swal.fire({
        icon: 'warning',
        title: '제목을 입력하세요',
        confirmButtonColor: '#192b55',
      });
      return;
    }

    setChapters((prev) =>
      prev.map((ch) => (ch.id === id ? { ...ch, title: editingTitle } : ch))
    );
    setEditingChapterId(null);
  };

  /** 커서 위치에 챕터 분할선 삽입 */
  const insertChapterBreak = () => {
    editor?.chain().focus().setChapterBreak().run();
  };

  /** HTML에서 분할선으로 쪼개고 새 챕터 생성 */
  const splitByChapterBreaks = () => {
    if (!editor || !activeChapter) return;

    saveChapterContent();
    const html = editor.getHTML();

    // 분할선 HR 패턴 (data-chapter-break="true")
    const parts = html
      .split(/<hr[^>]*data-chapter-break=["']true["'][^>]*>/gi)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    if (parts.length <= 1) {
      Swal.fire({
        icon: 'info',
        title: '분할할 위치가 없어요',
        text: '본문에 “챕터 분할선”을 먼저 추가해 주세요.',
        confirmButtonColor: '#192b55',
      });
      return;
    }

    // 각 조각의 제목 추출: 첫 번째 Heading 텍스트
    const extractTitle = (fragmentHtml: string, fallback: string) => {
      try {
        const doc = new DOMParser().parseFromString(fragmentHtml, 'text/html');
        const h = doc.querySelector('h1, h2, h3, h4, h5, h6');
        const t = h?.textContent?.trim();
        return t && t.length > 0 ? t : fallback;
      } catch {
        return fallback;
      }
    };

    const baseIndex = Math.max(...chapters.map((c) => parseInt(c.id))) + 1;

    // 첫 조각은 현재 챕터에 세팅, 나머지는 새 챕터로 추가
    const first = parts[0];
    const rest = parts.slice(1);

    setChapters((prev) => {
      const updated = prev.map((ch) =>
        ch.id === activeChapterId
          ? {
              ...ch,
              content: first,
              title: extractTitle(first, ch.title || '챕터'),
            }
          : ch
      );

      const newOnes: Chapter[] = rest.map((content, idx) => {
        const nextId = String(baseIndex + idx);
        return {
          id: nextId,
          title: extractTitle(content, `챕터 ${nextId}`),
          content,
        };
      });

      return [...updated, ...newOnes];
    });

    Swal.fire({
      icon: 'success',
      title: `${parts.length}개의 챕터로 분리했어요`,
      confirmButtonColor: '#192b55',
    });
  };

  const handlePublish = () => {
    saveChapterContent();

    if (!materialTitle.trim()) {
      Swal.fire({
        icon: 'warning',
        title: '제목을 입력하세요',
        text: '자료의 제목을 입력해주세요.',
        confirmButtonColor: '#192b55',
      });
      return;
    }

    if (chapters.some((ch) => !ch.content || ch.content === '<p></p>')) {
      Swal.fire({
        icon: 'warning',
        title: '모든 챕터에 내용이 필요합니다',
        text: '비어있는 챕터가 있습니다',
        confirmButtonColor: '#192b55',
      });
      return;
    }

    window.dispatchEvent(
      new CustomEvent('materialPublished', {
        detail: { title: materialTitle, chapters },
      })
    );

    Swal.fire({
      icon: 'success',
      title: '자료가 발행되었습니다!',
      text: '자료함으로 돌아갑니다',
      confirmButtonColor: '#192b55',
      confirmButtonText: '확인',
    }).then(() => {
      onPublish(materialTitle, chapters);
    });
  };

  if (!editor) return null;

  // 선택이 있는 경우에만 active 클래스를 적용
  const activeIf = (cond: boolean) => (hasSelection && cond ? 'active' : '');

  return (
    <div className={`ae-root ${darkMode ? 'dark' : 'light'}`}>
      <header className="ae-header">
        <div className="ae-header-wrapper">
          <div className="ae-header-spacer" />

          <div className="ae-title-section">
            {showTitleInput ? (
              <input
                type="text"
                value={materialTitle}
                onChange={(e) => setMaterialTitle(e.target.value)}
                className="ae-title-input"
                onBlur={() => setShowTitleInput(false)}
                autoFocus
                maxLength={100}
              />
            ) : (
              <h1
                className="ae-title"
                onClick={() => setShowTitleInput(true)}
                title="클릭하여 제목 수정"
              >
                {materialTitle}
              </h1>
            )}
          </div>

          <div className="ae-header-actions">
            <button
              className="ae-icon-btn"
              onClick={() => setDarkMode(!darkMode)}
              title={darkMode ? '라이트 모드' : '다크 모드'}
              aria-label="테마 전환"
            >
              {darkMode ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            <button className="ae-btn-filled" onClick={onBack}>
              <Home size={18} />
              <span>돌아가기</span>
            </button>

            <button className="ae-btn-filled ae-publish" onClick={handlePublish}>
              <span>발행하기</span>
            </button>
          </div>
        </div>
      </header>

      <div className="ae-container">
        {/* Left Panel - Chapters */}
        <aside className="ae-chapters-panel">
          <div className="ae-chapters-header">
            <h2>챕터</h2>
            <button className="ae-add-chapter-btn" onClick={handleAddChapter} aria-label="챕터 추가">
              <Plus size={18} />
            </button>
          </div>

          <div className="ae-chapters-list">
            {chapters.map((chapter) => (
              <div
                key={chapter.id}
                className={`ae-chapter-item ${activeChapterId === chapter.id ? 'active' : ''}`}
                onClick={() => {
                  saveChapterContent();
                  setActiveChapterId(chapter.id);
                }}
              >
                {editingChapterId === chapter.id ? (
                  <input
                    type="text"
                    value={editingTitle}
                    onChange={(e) => setEditingTitle(e.target.value)}
                    className="ae-chapter-input"
                    onBlur={() => handleSaveChapterTitle(chapter.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveChapterTitle(chapter.id);
                    }}
                    onClick={(e) => e.stopPropagation()}
                    autoFocus
                  />
                ) : (
                  <span className="ae-chapter-name">{chapter.title}</span>
                )}

                <div className="ae-chapter-actions">
                  <button
                    className="ae-chapter-action-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleEditChapterTitle(chapter.id, chapter.title);
                    }}
                    title="편집"
                    aria-label="챕터 제목 편집"
                  >
                    <Edit2 size={16} />
                  </button>
                  <button
                    className="ae-chapter-action-btn delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteChapter(chapter.id);
                    }}
                    title="삭제"
                    aria-label="챕터 삭제"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </aside>

        {/* Main Editor Area */}
        <main className="ae-editor-area">
          {/* Toolbar */}
          <div className="ae-toolbar">
            <div className="ae-toolbar-group">
              <button
                onClick={() => editor.chain().focus().toggleBold().run()}
                className={`ae-tool-btn ${activeIf(editor.isActive('bold'))}`}
                title="Bold"
                aria-label="Bold"
              >
                <Bold size={18} />
              </button>

              <button
                onClick={() => editor.chain().focus().toggleItalic().run()}
                className={`ae-tool-btn ${activeIf(editor.isActive('italic'))}`}
                title="Italic"
                aria-label="Italic"
              >
                <Italic size={18} />
              </button>

              <button
                onClick={() => editor.chain().focus().toggleUnderline().run()}
                className={`ae-tool-btn ${activeIf(editor.isActive('underline'))}`}
                title="Underline"
                aria-label="Underline"
              >
                <UnderlineIcon size={18} />
              </button>

              <div className="ae-divider" />

              <button
                onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
                className={`ae-tool-btn ${activeIf(editor.isActive('heading', { level: 1 }))}`}
                title="Heading 1"
                aria-label="Heading 1"
              >
                <Heading1 size={18} />
              </button>

              <button
                onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
                className={`ae-tool-btn ${activeIf(editor.isActive('heading', { level: 2 }))}`}
                title="Heading 2"
                aria-label="Heading 2"
              >
                <Heading2 size={18} />
              </button>

              <button
                onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
                className={`ae-tool-btn ${activeIf(editor.isActive('heading', { level: 3 }))}`}
                title="Heading 3"
                aria-label="Heading 3"
              >
                <Heading3 size={18} />
              </button>
            </div>

            <div className="ae-toolbar-group">
              <button
                onClick={() => editor.chain().focus().toggleBulletList().run()}
                className={`ae-tool-btn ${activeIf(editor.isActive('bulletList'))}`}
                title="Bullet List"
                aria-label="Bullet List"
              >
                <List size={18} />
              </button>

              <button
                onClick={() => editor.chain().focus().toggleOrderedList().run()}
                className={`ae-tool-btn ${activeIf(editor.isActive('orderedList'))}`}
                title="Ordered List"
                aria-label="Ordered List"
              >
                <ListOrdered size={18} />
              </button>

              <div className="ae-divider" />

              <button
                onClick={() => editor.chain().focus().setTextAlign('left').run()}
                className={`ae-tool-btn ${activeIf(editor.isActive({ textAlign: 'left' }))}`}
                title="Align Left"
                aria-label="Align Left"
              >
                <AlignLeft size={18} />
              </button>

              <button
                onClick={() => editor.chain().focus().setTextAlign('center').run()}
                className={`ae-tool-btn ${activeIf(editor.isActive({ textAlign: 'center' }))}`}
                title="Align Center"
                aria-label="Align Center"
              >
                <AlignCenter size={18} />
              </button>

              <button
                onClick={() => editor.chain().focus().setTextAlign('right').run()}
                className={`ae-tool-btn ${activeIf(editor.isActive({ textAlign: 'right' }))}`}
                title="Align Right"
                aria-label="Align Right"
              >
                <AlignRight size={18} />
              </button>

              <button
                onClick={() => editor.chain().focus().setTextAlign('justify').run()}
                className={`ae-tool-btn ${activeIf(editor.isActive({ textAlign: 'justify' }))}`}
                title="Align Justify"
                aria-label="Align Justify"
              >
                <AlignJustify size={18} />
              </button>
            </div>

            <div className="ae-toolbar-group">
              <button
                onClick={() => editor.chain().focus().toggleHighlight().run()}
                className={`ae-tool-btn ${activeIf(editor.isActive('highlight'))}`}
                title="Highlight"
                aria-label="Highlight"
              >
                <Highlighter size={18} />
              </button>

              <button
                onClick={() => editor.chain().focus().toggleSubscript().run()}
                className={`ae-tool-btn ${activeIf(editor.isActive('subscript'))}`}
                title="Subscript"
                aria-label="Subscript"
              >
                <span className="ae-subscript">x₂</span>
              </button>

              <button
                onClick={() => editor.chain().focus().toggleSuperscript().run()}
                className={`ae-tool-btn ${activeIf(editor.isActive('superscript'))}`}
                title="Superscript"
                aria-label="Superscript"
              >
                <span className="ae-superscript">x²</span>
              </button>
            </div>

            {/* === 챕터 분할 툴 === */}
            <div className="ae-toolbar-group">
              <button
                onClick={insertChapterBreak}
                className="ae-tool-btn"
                title="챕터 분할선 추가"
                aria-label="챕터 분할선 추가"
              >
                <Scissors size={18} />
              </button>
              <button
                onClick={splitByChapterBreaks}
                className="ae-tool-btn ae-primary"
                title="분할 적용"
                aria-label="분할 적용"
              >
                분할
              </button>
            </div>

            <div className="ae-toolbar-group">
              <button
                onClick={() => editor.chain().focus().toggleBlockquote().run()}
                className={`ae-tool-btn ${activeIf(editor.isActive('blockquote'))}`}
                title="Blockquote"
                aria-label="Blockquote"
              >
                <span>❝</span>
              </button>

              <button
                onClick={() => editor.chain().focus().undo().run()}
                className="ae-tool-btn"
                title="Undo"
                aria-label="Undo"
              >
                <span>↶</span>
              </button>

              <button
                onClick={() => editor.chain().focus().redo().run()}
                className="ae-tool-btn"
                title="Redo"
                aria-label="Redo"
              >
                <span>↷</span>
              </button>

              <button
                onClick={() => editor.chain().focus().clearContent().run()}
                className="ae-tool-btn danger"
                title="Clear All"
                aria-label="Clear All"
              >
                <span>⊘</span>
              </button>
            </div>
          </div>

          {/* Editor */}
          <div className="ae-editor-wrapper">
            <EditorContent editor={editor} className="ae-editor" />
          </div>
        </main>
      </div>
    </div>
  );
}
