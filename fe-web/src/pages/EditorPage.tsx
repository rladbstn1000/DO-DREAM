// src/pages/EditorPage.tsx

import { useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import AdvancedEditor from './AdvancedEditor';

type Chapter = {
  id: string;
  title: string;
  content: string;
  type?: 'content' | 'quiz';
};

type NavState = {
  fileName?: string;
  extractedText?: string;
  chapters?: Chapter[];
  from?: string;
  pdfId?: number;
  materialId?: string;
  mode?: 'create' | 'edit';
  initialLabel?: string;
};

type SessionPayload = {
  fileName?: string;
  extractedText?: string;
  chapters?: Chapter[];
  pdfId?: number;
  materialId?: string;
  mode?: 'create' | 'edit';
};

export default function EditorPage() {
  const navigate = useNavigate();
  const { state } = useLocation();
  const [editorData, setEditorData] = useState<NavState | null>(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {

    const sessionData = sessionStorage.getItem('editor_payload_v1');
    let finalData: NavState | null = null;

    if (sessionData) {
      try {
        const parsed = JSON.parse(sessionData) as SessionPayload;

        finalData = {
          fileName: parsed.fileName || '새로운 자료',
          extractedText: parsed.extractedText,
          chapters: parsed.chapters,
          pdfId: parsed.pdfId,
          materialId: parsed.materialId,
          mode: parsed.mode || 'create',
        };
      } catch (err) {
        console.error('[EditorPage] 세션 파싱 오류:');
      }
    }

    if (!finalData && state) {

      finalData = state as NavState;
    }

    if (!finalData) {

      finalData = {
        fileName: '새로운 자료',
        extractedText: '<p>내용을 입력하세요...</p>',
        mode: 'create',
      };
    }

    setEditorData(finalData);
    setIsReady(true);
  }, [state]);

  if (!isReady || !editorData) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          fontSize: '18px',
          color: '#192b55',
        }}
      >
        로딩 중...
      </div>
    );
  }

  const {
    fileName = '새로운 자료',
    extractedText = '<p>내용을 입력하세요...</p>',
    chapters,
    pdfId,
    materialId,
    mode = 'create',
    initialLabel,
  } = editorData;

  return (
    <AdvancedEditor
      key={`editor-${fileName}-${chapters?.length || 0}`}
      initialTitle={fileName}
      extractedText={extractedText}
      initialChapters={chapters}
      pdfId={pdfId}
      materialId={materialId}
      mode={mode}
      initialLabel={initialLabel}
      onBack={() => navigate(-1)}
      onPublish={(title, publishedChapters, label) => {

        sessionStorage.removeItem('editor_payload_v1');
        navigate('/', { replace: true });
      }}
    />
  );
}
