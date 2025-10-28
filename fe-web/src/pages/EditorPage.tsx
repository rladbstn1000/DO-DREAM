import { useLocation, useNavigate } from 'react-router-dom';
import AdvancedEditor from './AdvancedEditor';

type NavState = {
  fileName?: string;
  extractedText?: string;
};

export default function EditorPage() {
  const navigate = useNavigate();
  const { state } = useLocation();
  
  // ✅ state가 없으면 기본값 설정, 있으면 그대로 사용
  const {
    fileName = '새로운 자료',
    extractedText = '<p>내용을 입력하세요...</p>',
  } = (state as NavState) || {};

  return (
    <AdvancedEditor
      // ✅ 파일명이 제대로 전달되는지 확인
      initialTitle={fileName}
      extractedText={extractedText}
      onBack={() => navigate(-1)}
      onPublish={(title, chapters, label) => {
        // ✅ 발행 데이터를 백엔드로 전송하거나 상태에 저장
        console.log('발행된 데이터:', { title, chapters, label });
        navigate('/', { replace: true });
      }}
    />
  );
}