import { htmlText, htmlLines } from '../utils/htmlText';
import { authenticatedFetch } from '../auth/client';
import { useNavigate } from 'react-router-dom';
import Swal from 'sweetalert2';
import {
  BookOpen,
  LogOut,
  Users,
  Plus,
  FileText,
  Trash2,
  Tag,
  Send,
  Download,
} from 'lucide-react';
import { useEffect, useMemo, useState, useRef, ChangeEvent } from 'react';
import { useGlobalMemo } from '@/contexts/MemoContext';
import teacherAvatar from '../assets/classList/teacher.png';
import './ClassroomList.css';
import IndexingStatus from '../component/IndexingStatus';

import MaterialSendModal2Step from '@/component/MaterialSendModal2step';
import schoolImg from '../assets/classList/school.png';
import maleImg from '../assets/classroom/male.png';
import femaleImg from '../assets/classroom/female.png';

type ClassroomData = {
  id: string; // classroomId
  grade: string; // "3학년"
  class: string; // "1반"
  studentCount: number;
  materialCount: number;
};

type Material = {
  id: string;
  title: string;
  uploadDate: string;
  label?: string;
  status: 'draft' | 'published';
  uploadedFileId?: number;
  rawUpdatedAt: Date;
  indexing?: unknown;
};

type ClassroomListProps = {
  onLogout: () => Promise<void>;
  onNavigateToEditor?: () => void;
};

const LABEL_OPTIONS = [
  { id: 'red', color: '#ef4444', name: '빨강' },
  { id: 'orange', color: '#f97316', name: '주황' },
  { id: 'yellow', color: '#eab308', name: '노랑' },
  { id: 'green', color: '#2ea058ff', name: '초록' },
  { id: 'blue', color: '#3c71c7ff', name: '파랑' },
  { id: 'purple', color: '#8e4fc8ff', name: '보라' },
  { id: 'gray', color: '#8b8f97ff', name: '회색' },
];

// ===== 자료 정렬 함수 추가 (컴포넌트 외부) =====
const sortMaterialsByLabel = (materials: Material[]): Material[] => {
  const labelOrder = LABEL_OPTIONS.map((opt) => opt.id);

  return [...materials].sort((a, b) => {
    // 둘 다 라벨이 없으면 날짜 순
    if (!a.label && !b.label) {
      const parseDate = (d: string) => {
        const [y, m, day] = d.split('.').map((v) => parseInt(v, 10));
        return new Date(y, m - 1, day).getTime();
      };
      return parseDate(b.uploadDate) - parseDate(a.uploadDate);
    }
    // a만 라벨이 없으면 b가 앞으로
    if (!a.label) return 1;
    // b만 라벨이 없으면 a가 앞으로
    if (!b.label) return -1;

    // 둘 다 라벨이 있으면 라벨 순서대로
    const aIndex = labelOrder.indexOf(a.label);
    const bIndex = labelOrder.indexOf(b.label);

    // 같은 라벨이면 날짜 순
    if (aIndex === bIndex) {
      const parseDate = (d: string) => {
        const [y, m, day] = d.split('.').map((v) => parseInt(v, 10));
        return new Date(y, m - 1, day).getTime();
      };
      return parseDate(b.uploadDate) - parseDate(a.uploadDate);
    }

    return aIndex - bIndex;
  });
};

/** KST 기준 날짜 포맷 유틸 */
function formatKST(date: Date, withTime = false) {
  const tzDate = new Date(
    date.toLocaleString('en-US', { timeZone: 'Asia/Seoul' }),
  );
  const yyyy = tzDate.getFullYear();
  const mm = String(tzDate.getMonth() + 1).padStart(2, '0');
  const dd = String(tzDate.getDate()).padStart(2, '0');
  if (!withTime) return `${yyyy}.${mm}.${dd}`;
  const HH = String(tzDate.getHours()).padStart(2, '0');
  const MM = String(tzDate.getMinutes()).padStart(2, '0');
  return `${yyyy}년 ${mm}월 ${dd}일 (${HH}시 ${MM}분)`;
}

type ParsedPdfPayload = {
  indexes?: string[];
  data?: Array<{
    index: string;
    index_title: string;
    titles: Array<{
      title: string;
      s_titles?: Array<{
        s_title?: string;
        contents?: string | null;
        ss_titles?: Array<{
          ss_title?: string;
          contents?: string | null;
        }>;
      }>;
    }>;
  }>;
};

type ParsedPdfResponse = ParsedPdfPayload & {
  filename?: string;
  pdfId?: number;
  parsedData?: ParsedPdfPayload;
};

type ParsedChapter = {
  id: string;
  title: string;
  content: string;
  type?: 'content' | 'quiz';
};

type PublishedMaterialDto = {
  materialId: number;
  uploadedFileId: number;
  title: string;
  originalFileName: string;
  label:
    | 'RED'
    | 'ORANGE'
    | 'YELLOW'
    | 'GREEN'
    | 'BLUE'
    | 'PURPLE'
    | 'GRAY'
    | null;
  createdAt: string; // ISO 문자열
  updatedAt: string; // ISO 문자열
  indexing?: unknown;
};

type PublishedMaterialsResponse = {
  materials: PublishedMaterialDto[];
  totalCount: number;
};

type StudentLite = {
  id: string; // studentId
  name: string; // studentName
  grade: string; // "3학년 1반"
  gender?: 'male' | 'female';
  avatarUrl?: string;
  avatar?: string;
};

/** 담당 반 목록 API 응답 타입 */
type TeacherClassroomDto = {
  classroomId: number;
  year: number;
  gradeLevel: number;
  classNumber: number;
  displayName: string;
  schoolName: string;
  studentCount: number;
  materialCount: number;
};

type TeacherClassesResponse = {
  teacherId: number;
  teacherName: string;
  totalCount: number;
  classrooms: TeacherClassroomDto[];
};

/** 담당 학생 전체 조회 API 응답 타입 */
type ClassStudentsDto = {
  classroomId: number;
  year: number;
  gradeLevel: number;
  classNumber: number;
  displayName: string;
  schoolName: string;
  totalCount: number;
  students: {
    studentId: number;
    studentName: string;
    studentNumber: string;
    gender?: 'MALE' | 'FEMALE';
  }[];
};

/** 자료 공유 API body 타입 */
type MaterialShareRequest = {
  materialId: number;
  shares: {
    [classroomId: string]: {
      type: 'CLASS';
      studentIds: number[];
    };
  };
};

export default function ClassroomList({ onLogout }: ClassroomListProps) {
  const [selectedLabel, setSelectedLabel] = useState<string | undefined>();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '');
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const [classrooms, setClassrooms] = useState<ClassroomData[]>([]);
  const [studentsByClassroom, setStudentsByClassroom] = useState<
    Record<string, StudentLite[]>
  >({});

  const [activeLabels, setActiveLabels] = useState<string[]>([]);

  const toggleLabel = (id: string) => {
    setActiveLabels((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const clearLabels = () => setActiveLabels([]);

  const readTextFile = async (file: File): Promise<string> => {
    if (!/\.txt$/i.test(file.name)) throw new Error('PDF 또는 TXT 파일을 선택해주세요.');
    if (file.size > 1024 * 1024) throw new Error('TXT 파일은 1MiB까지 열 수 있습니다.');
    return `<p>${htmlLines(await file.text())}</p>`;
  };

  async function uploadAndParsePdf(
    file: File,
    API_BASE: string,
  ): Promise<ParsedPdfResponse> {
    if (file.size > 10 * 1024 * 1024) throw new Error('PDF 파일은 10MiB까지 올릴 수 있습니다.');
    const token = localStorage.getItem('accessToken');

    const url = `${API_BASE}/api/pdf/upload-and-parse?filename=${encodeURIComponent(
      file.name,
    )}`;

    const res = await authenticatedFetch(url, {
      method: 'POST',
      headers: {
        accept: '*/*',
        'Content-Type': 'application/pdf',
        ...(token ? { Authorization: `Bearer ${token}` } : {}), // ✅ 토큰 추가
      },
      body: file,
      credentials: 'include',
    });

    if (!res.ok) {
      console.error('❌ [PDF Upload] 오류:');

      throw new Error(
        `PDF 파싱 요청에 실패했습니다. (status: ${res.status})`,
      );
    }

    const json = (await res.json()) as ParsedPdfResponse;

    return json;
  }

  function buildChaptersFromParsedData(parsed: any): ParsedChapter[] {
    const root = parsed.parsedData ?? parsed;
    const data = root.data;

    const chapters: ParsedChapter[] = [];
    if (!data || data.length === 0) return chapters;

    let idCounter = 1;

    data.forEach((section: any) => {
      section.titles?.forEach((t: any) => {
        const htmlParts: string[] = [];

        t.s_titles?.forEach((s: any) => {
          if (s.s_title) {
            htmlParts.push(`<h3>${htmlText(s.s_title)}</h3>`);
          }

          if (s.contents) {
            htmlParts.push(`<p>${htmlLines(s.contents)}</p>`);
          }

          if (s.ss_titles && s.ss_titles.length > 0) {
            htmlParts.push('<ul>');
            s.ss_titles.forEach((ss: any) => {
              const strong = ss.ss_title
                ? `<strong>${htmlText(ss.ss_title)}</strong> `
                : '';
              const text = htmlLines(ss.contents);
              htmlParts.push(`<li>${strong}${text}</li>`);
            });
            htmlParts.push('</ul>');
          }
        });

        chapters.push({
          id: String(idCounter++),
          title: t.title || `챕터 ${idCounter}`,
          content:
            htmlParts.join('\n') || '<p>이 챕터에 대한 내용이 없습니다.</p>',
          type: 'content',
        });
      });
    });

    return chapters;
  }

  const handleViewMaterial = async (materialId: string) => {
    try {
      const material = materials.find((m) => m.id === materialId);
      if (!material) {
        await Swal.fire({
          icon: 'error',
          title: '자료를 찾을 수 없습니다',
          confirmButtonColor: '#192b55',
        });
        return;
      }

      const pdfId = material.uploadedFileId;

      if (!pdfId) {
        await Swal.fire({
          icon: 'error',
          title: '자료 정보가 부족합니다',
          text: '파일 ID를 찾을 수 없습니다.',
          confirmButtonColor: '#192b55',
        });
        return;
      }

      void Swal.fire({
        title: '자료를 불러오는 중입니다',
        allowOutsideClick: false,
        showConfirmButton: false,
        didOpen: () => Swal.showLoading(),
      });

      const accessToken = localStorage.getItem('accessToken');

      const pdfRes = await authenticatedFetch(`${API_BASE}/api/pdf/${pdfId}/json`, {
        method: 'GET',
        headers: {
          accept: '*/*',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        credentials: 'include',
      });

      if (!pdfRes.ok) {
        const text = await pdfRes.text().catch(() => '');
        throw new Error(
          `자료 내용을 불러오지 못했습니다. (status: ${pdfRes.status})`,
        );
      }

      const parsedData = await pdfRes.json();

      // 올바른 경로에서 chapters 추출
      let chapters: any[] = [];

      // 1) parsedData.chapters가 배열이면 사용
      if (parsedData.chapters && Array.isArray(parsedData.chapters)) {
        chapters = parsedData.chapters;

      }
      // 2) parsedData.parsedData.chapters가 배열이면 사용
      else if (
        parsedData.parsedData?.chapters &&
        Array.isArray(parsedData.parsedData.chapters)
      ) {
        chapters = parsedData.parsedData.chapters;

      }
      // 3) parsedData.editedJson?.chapters가 배열이면 사용 (발행된 자료일 경우)
      else if (
        parsedData.editedJson?.chapters &&
        Array.isArray(parsedData.editedJson.chapters)
      ) {
        chapters = parsedData.editedJson.chapters;

      }
      // 4) chapters가 객체 형태라면 Object.values로 변환
      else if (parsedData.chapters && typeof parsedData.chapters === 'object') {
        chapters = Object.values(parsedData.chapters);

      }
      // 5) parsedData.parsedData.chapters가 객체라면 변환
      else if (
        parsedData.parsedData?.chapters &&
        typeof parsedData.parsedData.chapters === 'object'
      ) {
        chapters = Object.values(parsedData.parsedData.chapters);

      }
      // 6) parsedData.editedJson?.chapters가 객체라면 변환
      else if (
        parsedData.editedJson?.chapters &&
        typeof parsedData.editedJson.chapters === 'object'
      ) {
        chapters = Object.values(parsedData.editedJson.chapters);

      } else {
        console.error('❌ chapters를 찾을 수 없습니다. parsedData 구조:');
      }

      // 라벨 정보 추출
      let labelColor: string | undefined = undefined;

      // 1) parsedData.labelColor 확인
      if (parsedData.labelColor) {
        labelColor = parsedData.labelColor.toLowerCase();

      }
      // 2) parsedData.label 확인
      else if (parsedData.label) {
        labelColor = parsedData.label.toLowerCase();

      }
      // 3) material.label 사용 (로컬 state - 가장 확실!)
      else if (material.label) {
        labelColor = material.label;

      }

      // 검증: chapters가 올바른 형태인지 확인
      if (chapters.length > 0) {
        if (chapters[0]?.id !== undefined && chapters[0]?.title !== undefined) {

        } else {
          console.warn('⚠️ Chapter 객체 구조가 예상과 다릅니다:');
        }
      }

      await Swal.close();

      if (!chapters || chapters.length === 0) {
        await Swal.fire({
          icon: 'warning',
          title: '내용이 없습니다',
          text: '이 자료에는 표시할 내용이 없습니다.',
          confirmButtonColor: '#192b55',
        });
        return;
      }

      // 에디터로 이동
      navigate('/editor', {
        state: {
          fileName: material.title,
          chapters: chapters,
          pdfId: pdfId,
          materialId: materialId,
          mode: 'edit',
          from: 'classroom',
          initialLabel: labelColor,
        },
      });
    } catch (err: any) {
      console.error('자료 조회 실패');
      await Swal.close();
      await Swal.fire({
        icon: 'error',
        title: '자료를 불러올 수 없습니다',
        text: err?.message ?? '잠시 후 다시 시도해 주세요.',
        confirmButtonColor: '#192b55',
      });
    }
  };

  const handleCreateMaterial = () => {
    if (fileInputRef.current) fileInputRef.current.click();
  };

  const handlePickFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;

    const docTitle = file.name.replace(/\.[^.]+$/, '') || '새로운 자료';

    void Swal.fire({
      title: '텍스트 추출 중입니다',
      html: `
      <div style="display: flex; flex-direction: column; align-items: center; gap: 1rem;">
        <div style="width: 50px; height: 50px; border: 4px solid #192b55; border-top: 4px solid transparent; border-radius: 50%; animation: spin 1s linear infinite;"></div>
        <p style="color: #192b55; font-size: 18px;">파일을 처리하는 중입니다...</p>
      </div>
      <style>
      @keyframes spin { to { transform: rotate(360deg); } }
      </style>
    `,
      showConfirmButton: false,
      allowOutsideClick: false,
      allowEscapeKey: false,
      heightAuto: false,
    });

    const MIN_SHOW_MS = 500;

    try {
      const isPdf =
        file.type === 'application/pdf' || /\.pdf$/i.test(file.name);

      if (isPdf) {

        const [parsed] = await Promise.all([
          uploadAndParsePdf(file, API_BASE),
          sleep(MIN_SHOW_MS),
        ]);

        const chapters = buildChaptersFromParsedData(parsed);
        const pdfId = parsed.pdfId;

        await Swal.close();

        if (!chapters.length) {
          await Swal.fire({
            icon: 'error',
            title: '파싱 결과가 없습니다',
            text: 'PDF에서 챕터 정보를 찾지 못했어요. 직접 입력해 주세요.',
            confirmButtonColor: '#192b55',
          });
          return;
        }

        navigate('/editor', {
          state: {
            fileName: docTitle,
            chapters: chapters,
            pdfId: pdfId,
            from: 'classroom',
          },
        });
      } else {
        const [text] = await Promise.all([
          readTextFile(file),
          sleep(MIN_SHOW_MS),
        ]);

        await Swal.close();

        navigate('/editor', {
          state: {
            fileName: docTitle,
            extractedText: text,
            from: 'classroom',
          },
        });
      }
    } catch (err) {
      console.error('❌ [handlePickFile] 파일 처리 실패:');

      await Swal.close();
      await Swal.fire({
        icon: 'error',
        title: '파일 처리 실패',
        html: `
        <div style="text-align: left;">
          <p style="margin-bottom: 12px;">
            <strong>오류:</strong> 요청을 완료하지 못했습니다. PDF·TXT 형식과 파일 크기를 확인해주세요.
          </p>
          <p style="margin-bottom: 12px; font-size: 14px; color: #666;">
            다음을 확인해 주세요:
          </p>
          <ul style="text-align: left; padding-left: 20px; font-size: 14px;">
            <li>PDF 파일이 손상되지 않았는지</li>
            <li>파일 크기가 너무 크지 않은지</li>
            <li>인터넷 연결 상태</li>
          </ul>
        </div>
      `,
        confirmButtonColor: '#192b55',
        heightAuto: false,
      });
    }
  };

  const handleDownloadWord = async (materialId: string) => {
    try {
      const material = materials.find((m) => m.id === materialId);
      if (!material) {
        await Swal.fire({
          icon: 'error',
          title: '자료를 찾을 수 없습니다',
          confirmButtonColor: '#192b55',
        });
        return;
      }

      const pdfId = material.uploadedFileId;
      if (!pdfId) {
        await Swal.fire({
          icon: 'error',
          title: '자료 정보가 부족합니다',
          text: '파일 ID를 찾을 수 없습니다.',
          confirmButtonColor: '#192b55',
        });
        return;
      }

      void Swal.fire({
        title: '워드 파일을 생성하는 중입니다',
        html: `
      <div style="display: flex; flex-direction: column; align-items: center; gap: 1rem;">
        <div style="width: 50px; height: 50px; border: 4px solid #192b55; border-top: 4px solid transparent; border-radius: 50%; animation: spin 1s linear infinite;"></div>
        <p style="color: #192b55; font-size: 18px;">파일을 생성하는 중입니다...</p>
      </div>
      <style>
      @keyframes spin { to { transform: rotate(360deg); } }
      </style>
    `,
        allowOutsideClick: false,
        showConfirmButton: false,
      });

      const accessToken = localStorage.getItem('accessToken');

      // JSON 데이터 가져오기
      const pdfRes = await authenticatedFetch(`${API_BASE}/api/pdf/${pdfId}/json`, {
        method: 'GET',
        headers: {
          accept: '*/*',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        credentials: 'include',
      });

      if (!pdfRes.ok) {
        const text = await pdfRes.text().catch(() => '');
        throw new Error(
          `자료 내용을 불러오지 못했습니다. (status: ${pdfRes.status})`,
        );
      }

      const parsedData = await pdfRes.json();

      // chapters 추출 (기존 로직 재사용)
      let chapters: any[] = [];
      if (parsedData.chapters && Array.isArray(parsedData.chapters)) {
        chapters = parsedData.chapters;
      } else if (
        parsedData.parsedData?.chapters &&
        Array.isArray(parsedData.parsedData.chapters)
      ) {
        chapters = parsedData.parsedData.chapters;
      } else if (
        parsedData.editedJson?.chapters &&
        Array.isArray(parsedData.editedJson.chapters)
      ) {
        chapters = parsedData.editedJson.chapters;
      } else if (
        parsedData.chapters &&
        typeof parsedData.chapters === 'object'
      ) {
        chapters = Object.values(parsedData.chapters);
      } else if (
        parsedData.parsedData?.chapters &&
        typeof parsedData.parsedData.chapters === 'object'
      ) {
        chapters = Object.values(parsedData.parsedData.chapters);
      } else if (
        parsedData.editedJson?.chapters &&
        typeof parsedData.editedJson.chapters === 'object'
      ) {
        chapters = Object.values(parsedData.editedJson.chapters);
      }

      if (chapters.length === 0) {
        await Swal.close();
        await Swal.fire({
          icon: 'warning',
          title: '내용이 없습니다',
          text: '이 자료에는 표시할 내용이 없습니다.',
          confirmButtonColor: '#192b55',
        });
        return;
      }

      // docx 라이브러리 동적 import
      const {
        Document,
        Packer,
        Paragraph,
        TextRun,
        HeadingLevel,
        AlignmentType,
      } = await import('docx');

      // 워드 문서 생성
      const docChildren: any[] = [
        new Paragraph({
          text: material.title,
          heading: HeadingLevel.TITLE,
          alignment: AlignmentType.CENTER,
          spacing: { after: 400 },
        }),
      ];

      chapters.forEach((chapter: any, index: number) => {
        // 챕터 제목
        docChildren.push(
          new Paragraph({
            text: chapter.title || `챕터 ${index + 1}`,
            heading: HeadingLevel.HEADING_1,
            spacing: { before: 400, after: 200 },
          }),
        );

        // 챕터 내용 (HTML 태그 제거 및 정리)
        const content = (chapter.content || '')
          .replace(/<br\s*\/?>/gi, '\n')
          .replace(/<\/p>/gi, '\n\n')
          .replace(/<\/h[1-6]>/gi, '\n')
          .replace(/<\/li>/gi, '\n')
          .replace(/<[^>]*>/g, '')
          .replace(/&nbsp;/g, ' ')
          .replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>')
          .replace(/&amp;/g, '&')
          .trim();

        if (content) {
          // 줄바꿈을 기준으로 문단 분리
          const paragraphs = content.split('\n').filter((p) => p.trim());

          paragraphs.forEach((para) => {
            docChildren.push(
              new Paragraph({
                children: [
                  new TextRun({
                    text: para.trim(),
                    size: 24, // 12pt
                  }),
                ],
                spacing: { after: 200 },
              }),
            );
          });
        }

        // 챕터 사이 구분선 (마지막 챕터 제외)
        if (index < chapters.length - 1) {
          docChildren.push(
            new Paragraph({
              text: '',
              spacing: { after: 200 },
              border: {
                bottom: {
                  color: 'CCCCCC',
                  space: 1,
                  style: 'single',
                  size: 6,
                },
              },
            }),
          );
        }
      });

      const doc = new Document({
        sections: [
          {
            properties: {},
            children: docChildren,
          },
        ],
      });

      // 문서 생성 및 다운로드
      const blob = await Packer.toBlob(doc);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${material.title}.docx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      await Swal.close();
      await Swal.fire({
        icon: 'success',
        title: '다운로드 완료!',
        text: `${material.title}.docx 파일이 다운로드되었습니다.`,
        confirmButtonColor: '#192b55',
        timer: 2000,
      });
    } catch (err: any) {
      console.error('워드 다운로드 실패');
      await Swal.close();
      await Swal.fire({
        icon: 'error',
        title: '워드 파일 생성에 실패했습니다',
        text: err?.message ?? '잠시 후 다시 시도해 주세요.',
        confirmButtonColor: '#192b55',
      });
    }
  };

  const { memo, setMemo } = useGlobalMemo();

  const [materials, setMaterials] = useState<Material[]>([]);

  const lastUpdatedAt = useMemo(() => {
    if (materials.length === 0) return new Date(); // 자료가 없으면 현재 시간

    // 배열을 순회하며 가장 늦은 시간 찾기
    return materials.reduce((latest, current) => {
      return current.rawUpdatedAt > latest ? current.rawUpdatedAt : latest;
    }, materials[0].rawUpdatedAt);
  }, [materials]);

  // 발행 자료 목록 조회
  useEffect(() => {

    const fetchPublishedMaterials = async () => {
      try {
        const accessToken = localStorage.getItem('accessToken');

        if (!accessToken) {
          console.warn('accessToken 이 없습니다. 로그인 상태를 확인해 주세요.');
        }

        const res = await authenticatedFetch(`${API_BASE}/api/documents/published`, {
          method: 'GET',
          headers: {
            accept: '*/*',
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          },
          credentials: 'include',
        });

        if (!res.ok) {
          throw new Error(
            `발행 자료 목록 조회에 실패했습니다. (status: ${res.status})`,
          );
        }

        const data = (await res.json()) as PublishedMaterialsResponse;

        const mapped: Material[] = data.materials.map((m) => {
          // 1. 수정일(updatedAt)이 있으면 쓰고, 없으면 생성일(createdAt) 사용
          const dateStr = m.updatedAt || m.createdAt;

          // 2. 날짜 변환 (끝에 Z가 없으면 붙여서 UTC로 인식시킴 -> 브라우저가 KST로 자동 변환)
          const dateObj = new Date(
            dateStr.endsWith('Z') ? dateStr : dateStr + 'Z',
          );

          return {
            id: String(m.materialId),
            title: m.title,
            uploadDate: formatKST(new Date(m.createdAt)),
            label: m.label ? m.label.toLowerCase() : undefined,
            status: 'published',
            uploadedFileId: m.uploadedFileId,
            indexing: m.indexing,

            // ✅ 여기에 실제 날짜 객체를 저장
            rawUpdatedAt: dateObj,
          };
        });

        // 라벨 색상 순서대로 정렬 (정의된 순서: 빨강 > 주황 > 노랑 > 초록 > 파랑 > 보라 > 회색)
        // 라벨이 없는 자료는 맨 뒤로
        const labelOrder = LABEL_OPTIONS.map((opt) => opt.id);

        mapped.sort((a, b) => {
          // 둘 다 라벨이 없으면 날짜 순
          if (!a.label && !b.label) {
            const parseDate = (d: string) => {
              const [y, m, day] = d.split('.').map((v) => parseInt(v, 10));
              return new Date(y, m - 1, day).getTime();
            };
            return parseDate(b.uploadDate) - parseDate(a.uploadDate);
          }
          // a만 라벨이 없으면 b가 앞으로
          if (!a.label) return 1;
          // b만 라벨이 없으면 a가 앞으로
          if (!b.label) return -1;

          // 둘 다 라벨이 있으면 라벨 순서대로
          const aIndex = labelOrder.indexOf(a.label);
          const bIndex = labelOrder.indexOf(b.label);

          // 같은 라벨이면 날짜 순
          if (aIndex === bIndex) {
            const parseDate = (d: string) => {
              const [y, m, day] = d.split('.').map((v) => parseInt(v, 10));
              return new Date(y, m - 1, day).getTime();
            };
            return parseDate(b.uploadDate) - parseDate(a.uploadDate);
          }

          return aIndex - bIndex;
        });

        setMaterials(mapped);
      } catch (err: any) {
        console.error('발행 자료 목록 조회 실패');
        Swal.fire({
          icon: 'error',
          title: '발행된 자료를 불러오지 못했습니다',
          text: err?.message ?? '잠시 후 다시 시도해 주세요.',
          confirmButtonColor: '#192b55',
        });
      }
    };

    void fetchPublishedMaterials();
  }, [API_BASE]);

  const filteredMaterials = useMemo(() => {
    if (activeLabels.length === 0) {
      return materials;
    }
    return materials.filter((m) => m.label && activeLabels.includes(m.label));
  }, [materials, activeLabels]);

  // 담당 반 / 학생 목록 조회
  useEffect(() => {

    const fetchClassesAndStudents = async () => {
      try {
        const accessToken = localStorage.getItem('accessToken');
        const commonHeaders: HeadersInit = {
          accept: '*/*',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        };

        // 1) 내 담당 반 목록
        const classesRes = await authenticatedFetch(`${API_BASE}/api/classes/teacher`, {
          method: 'GET',
          headers: commonHeaders,
          credentials: 'include',
        });

        if (!classesRes.ok) {
          const text = await classesRes.text().catch(() => '');
          throw new Error(
            text ||
              `담당 반 목록 조회에 실패했습니다. (status: ${classesRes.status})`,
          );
        }

        const classesJson = (await classesRes.json()) as TeacherClassesResponse;

        const mappedClassrooms: ClassroomData[] =
          classesJson.classrooms?.map((c) => ({
            id: String(c.classroomId),
            grade: `${c.gradeLevel}학년`,
            class: `${c.classNumber}반`,
            studentCount: c.studentCount,
            materialCount: c.materialCount,
          })) ?? [];

        setClassrooms(mappedClassrooms);

        if (mappedClassrooms.length === 0) {
          setStudentsByClassroom({});
          return;
        }

        // 2) 담당 학생 전체 조회
        const classroomIds = mappedClassrooms.map((c) => Number(c.id));
        const query = classroomIds
          .map((id) => `classroomIds=${encodeURIComponent(String(id))}`)
          .join('&');

        const studentsRes = await authenticatedFetch(
          `${API_BASE}/api/classes/students?${query}`,
          {
            method: 'GET',
            headers: commonHeaders,
            credentials: 'include',
          },
        );

        if (!studentsRes.ok) {
          const text = await studentsRes.text().catch(() => '');
          throw new Error(
            text ||
              `담당 학생 목록 조회에 실패했습니다. (status: ${studentsRes.status})`,
          );
        }

        const studentsJson = (await studentsRes.json()) as ClassStudentsDto[];

        const map: Record<string, StudentLite[]> = {};
        studentsJson.forEach((cls) => {
          const students =
            cls.students?.map((s) => {

              return {
                id: String(s.studentId),
                name: s.studentName,
                grade: `${cls.gradeLevel}학년 ${cls.classNumber}반`,
                gender: s.gender
                  ? (s.gender.toLowerCase() as 'male' | 'female')
                  : undefined,
              };
            }) ?? [];

          map[String(cls.classroomId)] = students;
        });

        setStudentsByClassroom(map);
      } catch (err: any) {
        console.error('담당 반/학생 목록 조회 실패');
        Swal.fire({
          icon: 'error',
          title: '반/학생 정보를 불러오지 못했습니다',
          text: err?.message ?? '잠시 후 다시 시도해 주세요.',
          confirmButtonColor: '#192b55',
        });
      }
    };

    void fetchClassesAndStudents();
  }, [API_BASE]);

  const [showSendModal, setShowSendModal] = useState(false);
  const [selectedMaterial, setSelectedMaterial] = useState<Material | null>(
    null,
  );

  const teacher = {
    name: '김싸피',
    email: 'teacher@school.com',
    avatar: teacherAvatar,
  };

  const handleSelectClassroom = (classroomId: string) => {
    navigate(`/classroom/${classroomId}`);
  };

  const getLabelColor = (label?: string) =>
    LABEL_OPTIONS.find((l) => l.id === label)?.color || 'transparent';

  const handleLabelMaterial = async (
    materialId: string,
    currentLabel?: string,
  ) => {
    let picked: string | undefined = currentLabel;

    const result = await Swal.fire({
      title: '라벨 선택',
      html: `
      <div class="ae-label-grid" id="labelGrid">
        ${LABEL_OPTIONS.map(
          (label) => `
          <button
            class="ae-label-option ${picked === label.id ? 'active' : ''}"
            data-label="${label.id}"
            style="background-color: ${label.color}; ${
              picked === label.id ? `border: 3px solid ${label.color};` : ''
            }"
            title="${label.name}"
          >
            <span>${picked === label.id ? '✓' : ''}</span>
          </button>
        `,
        ).join('')}
      </div>
    `,
      showCancelButton: true,
      confirmButtonText: '저장',
      cancelButtonText: '취소',
      confirmButtonColor: '#192b55',
      cancelButtonColor: '#d1d5db',
      reverseButtons: true,

      didOpen: () => {
        const grid = document.getElementById('labelGrid');
        if (!grid) return;

        const buttons = Array.from(
          grid.querySelectorAll('.ae-label-option'),
        ) as HTMLElement[];

        const render = () => {
          buttons.forEach((btn) => {
            const id = btn.getAttribute('data-label');
            const active = id === picked;
            btn.classList.toggle('active', active);
            btn.style.border = active ? '3px solid #000' : '';
            btn.innerHTML = `<span>${active ? '✓' : ''}</span>`;
          });
        };

        grid.addEventListener('click', (e) => {
          const target = (e.target as HTMLElement).closest(
            '.ae-label-option',
          ) as HTMLElement | null;
          if (!target) return;
          picked = target.getAttribute('data-label') || undefined;
          render();
        });
      },

      preConfirm: () => picked,
    });

    if (!result.isConfirmed) return;

    const selectedLabel = result.value as string | undefined;

    // ✅ API 호출
    try {
      void Swal.fire({
        title: '라벨을 저장하는 중입니다',
        allowOutsideClick: false,
        showConfirmButton: false,
        didOpen: () => Swal.showLoading(),
      });

      const accessToken = localStorage.getItem('accessToken');
      const headers: HeadersInit = {
        accept: '*/*',
        'Content-Type': 'application/json',
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      };

      const res = await authenticatedFetch(`${API_BASE}/api/documents/label`, {
        method: 'PATCH',
        headers,
        credentials: 'include',
        body: JSON.stringify({
          materialId: Number(materialId),
          label: selectedLabel ? selectedLabel.toUpperCase() : 'RED', // null 대신 기본값
        }),
      });

      if (!res.ok) {
        throw new Error(
          `라벨 수정에 실패했습니다. (status: ${res.status})`,
        );
      }

      await Swal.close();

      setMaterials((prev) => {
        const updated = prev.map((mat) =>
          mat.id === materialId ? { ...mat, label: selectedLabel } : mat,
        );
        return sortMaterialsByLabel(updated);
      });

      await Swal.fire({
        icon: 'success',
        title: '라벨이 저장되었습니다',
        timer: 1500,
        showConfirmButton: false,
      });
    } catch (err: any) {
      console.error('라벨 수정 실패');
      await Swal.close();
      await Swal.fire({
        icon: 'error',
        title: '라벨 저장에 실패했습니다',
        text: err?.message ?? '잠시 후 다시 시도해 주세요.',
        confirmButtonColor: '#192b55',
      });
    }
  };

  const handleSendMaterial = (materialId: string) => {
    const m = materials.find((mt) => mt.id === materialId);
    if (!m) return;
    setSelectedMaterial(m);
    setShowSendModal(true);
  };

  // 자료 공유 API 호출
  const shareMaterial = async (
    studentIds: string[],
    classroomIds: string[],
    material: Material,
  ) => {

    try {
      const accessToken = localStorage.getItem('accessToken');
      const headers: HeadersInit = {
        accept: '*/*',
        'Content-Type': 'application/json',
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      };

      // classroomId별 선택된 학생만 묶어서 body 생성
      const body: MaterialShareRequest = {
        materialId: Number(material.id),
        shares: {},
      };

      classroomIds.forEach((cid) => {
        const allStudents = studentsByClassroom[cid] || [];
        const selectedInClass = allStudents.filter((s) =>
          studentIds.includes(s.id),
        );
        if (selectedInClass.length === 0) return;
        body.shares[cid] = {
          type: 'CLASS',
          studentIds: selectedInClass.map((s) => Number(s.id)),
        };
      });

      if (Object.keys(body.shares).length === 0) {
        await Swal.fire({
          icon: 'warning',
          title: '선택된 학생이 없습니다',
          text: '공유할 학생을 선택해 주세요.',
          confirmButtonColor: '#192b55',
        });
        return;
      }

      void Swal.fire({
        title: '자료를 공유하는 중입니다',
        allowOutsideClick: false,
        showConfirmButton: false,
        didOpen: () => Swal.showLoading(),
      });

      const res = await authenticatedFetch(`${API_BASE}/api/materials/share`, {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        throw new Error(
          `자료 공유에 실패했습니다. (status: ${res.status})`,
        );
      }

      setClassrooms((prev) =>
        prev.map((classroom) => {
          if (classroomIds.includes(classroom.id)) {
            return {
              ...classroom,
              materialCount: classroom.materialCount + 1,
            };
          }
          return classroom;
        }),
      );

      await Swal.close();

      // 성공 메시지용 정보 구성
      const allSelectedStudents = classroomIds.flatMap((cid) =>
        (studentsByClassroom[cid] || []).filter((s) =>
          studentIds.includes(s.id),
        ),
      );
      const names = allSelectedStudents.map((s) => s.name);

      const classroomNames = classroomIds
        .map((cid) => {
          const c = classrooms.find((cl) => cl.id === cid);
          return c ? `${c.grade} ${c.class}` : cid;
        })
        .join(', ');

      await Swal.fire({
        icon: 'success',
        title: '자료가 공유되었습니다!',
        html: `
          <div style="text-align:left;line-height:1.5">
            <p style="margin:0 0 8px 0"><strong>"${htmlText(material.title)}"</strong></p>
            <p style="margin:0 0 6px 0;color:#374151;"><strong>공유한 반</strong> ${htmlText(classroomNames)}</p>
            <p style="margin:0 0 6px 0;color:#374151;"><strong>공유한 학생</strong> ${htmlText(names.join(', '))}</p>
            <p style="margin:4px 0 0 0;color:#6b7280;font-size:14px;">${names.length}명에게 공유되었습니다</p>
          </div>
        `,
        confirmButtonColor: '#192b55',
      });

      setShowSendModal(false);
      setSelectedMaterial(null);
    } catch (err: any) {
      console.error('자료 공유 실패');
      await Swal.close();
      await Swal.fire({
        icon: 'error',
        title: '자료 공유에 실패했습니다',
        text: err?.message ?? '잠시 후 다시 시도해 주세요.',
        confirmButtonColor: '#192b55',
      });
    }
  };

  const handleDeleteMaterial = async (materialId: string) => {
    const result = await Swal.fire({
      title: '자료를 삭제하시겠습니까?',
      text: '이 작업은 되돌릴 수 없습니다',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#d1d5db',
      reverseButtons: true,
      confirmButtonText: '삭제',
      cancelButtonText: '취소',
    });

    if (!result.isConfirmed) return;

    try {
      void Swal.fire({
        title: '자료를 삭제하는 중입니다',
        allowOutsideClick: false,
        showConfirmButton: false,
        didOpen: () => Swal.showLoading(),
      });

      const accessToken = localStorage.getItem('accessToken');
      const headers: HeadersInit = {
        accept: '*/*',
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      };

      const res = await authenticatedFetch(`${API_BASE}/api/documents/${materialId}`, {
        method: 'DELETE',
        headers,
        credentials: 'include',
      });

      if (!res.ok) {
        throw new Error(
          `자료 삭제에 실패했습니다. (status: ${res.status})`,
        );
      }

      await Swal.close();

      // 로컬 state 업데이트
      setMaterials((prev) => prev.filter((mat) => mat.id !== materialId));

      await Swal.fire({
        icon: 'success',
        title: '자료가 삭제되었습니다',
        confirmButtonColor: '#192b55',
      });

      setClassrooms((prev) =>
        prev.map((classroom) => ({
          ...classroom,
          materialCount: Math.max(0, classroom.materialCount - 1), // ✅ 감소!
        })),
      );
    } catch (err: any) {
      console.error('자료 삭제 실패');
      await Swal.close();
      await Swal.fire({
        icon: 'error',
        title: '자료 삭제에 실패했습니다',
        text: err?.message ?? '잠시 후 다시 시도해 주세요.',
        confirmButtonColor: '#192b55',
      });
    }
  };

  const handleLogout = async () => {
    if (isLoggingOut) return;
    const ask = await Swal.fire({
      icon: 'question',
      title: '로그아웃 하시겠습니까?',
      showCancelButton: true,
      confirmButtonColor: '#192b55',
      cancelButtonColor: '#d1d5db',
      reverseButtons: true,
      confirmButtonText: '로그아웃',
      cancelButtonText: '취소',
    });
    if (!ask.isConfirmed) return;

    setIsLoggingOut(true);
    void Swal.fire({
      title: '로그아웃 중…',
      allowOutsideClick: false,
      showConfirmButton: false,
      didOpen: () => Swal.showLoading(),
    });

    try {
      await onLogout();

      await Swal.close();
      await Swal.fire({
        toast: true,
        position: 'top-end',
        icon: 'success',
        title: '로그아웃 되었습니다',
        timer: 1200,
        showConfirmButton: false,
      });

      navigate('/', { replace: true });
    } catch (err: any) {
      await Swal.close();
      Swal.fire({
        icon: 'error',
        titleText: err?.message || '로그아웃 중 오류가 발생했습니다',
        confirmButtonColor: '#192b55',
      });
    } finally {
      setIsLoggingOut(false);
    }
  };

  const latestUploadDate = useMemo(() => {
    if (materials.length === 0) return '-';
    return materials
      .map((m) => m.uploadDate)
      .sort()
      .reverse()[0];
  }, [materials]);

  return (
    <div className="cl-root">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.txt,.doc,.docx,application/pdf,text/plain,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        style={{ display: 'none' }}
        onChange={handlePickFile}
      />
      <header className="cl-header">
        <div className="cl-header-wrapper">
          <h1 className="cl-header-title">DO:DREAM</h1>
          <button
            className="cl-logout-button"
            onClick={handleLogout}
            disabled={isLoggingOut}
          >
            <LogOut size={18} />
            <span>{isLoggingOut ? '로그아웃 중…' : '로그아웃'}</span>
          </button>
        </div>
      </header>

      <div className="cl-layout">
        <aside className="cl-sidebar">
          <div className="cl-sidebar-content">
            <div className="cl-profile-mini">
              <img
                className="cl-profile-avatar-mini"
                src={teacher.avatar}
                alt={`${teacher.name} 아바타`}
              />
              <h2 className="cl-profile-name-mini">{teacher.name}</h2>
              <p className="cl-profile-email-mini">{teacher.email}</p>
              <p className="cl-profile-label-mini">선생님</p>
            </div>

            <div className="cl-sidebar-divider" />

            <div className="cl-memo">
              <div className="cl-memo-stage">
                <div className="cl-memo-zoom">
                  <div className="cl-memo-header">
                    <div className="cl-memo-latest" title="오늘 날짜">
                      <span>Today : {formatKST(new Date())}</span>
                    </div>
                  </div>

                  <textarea
                    className="cl-memo-input"
                    placeholder="수업 준비/할 일 메모"
                    value={memo}
                    onChange={(e) => setMemo(e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>
        </aside>

        <main className="cl-main-content">
          {/* 반 목록 */}
          <div className="cl-classrooms-section">
            <div className="cl-section-header">
              <h2 className="cl-section-title">
                {classrooms.length}개 반 담당
              </h2>
            </div>

            <div className="cl-classrooms-grid">
              {classrooms.map((classroom) => (
                <div
                  key={classroom.id}
                  className="cl-classroom-card"
                  onClick={() => handleSelectClassroom(classroom.id)}
                >
                  <div className="cl-classroom-header">
                    <div className="cl-classroom-title">
                      <h3>
                        {classroom.grade} {classroom.class}
                      </h3>
                    </div>
                  </div>

                  <div className="cl-classroom-stats">
                    <div className="cl-stat">
                      <Users size={18} />
                      <div className="cl-stat-info">
                        <p className="cl-stat-num">{classroom.studentCount}</p>
                        <p className="cl-stat-text">학생</p>
                      </div>
                    </div>
                    <div className="cl-divider" />
                    <div className="cl-stat">
                      <BookOpen size={18} />
                      <div className="cl-stat-info">
                        <p className="cl-stat-num">{classroom.materialCount}</p>
                        <p className="cl-stat-text">자료</p>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 자료함 */}
          <div className="cl-materials-section">
            <div className="cl-materials-header">
              {/* ✅ 첫 번째 줄: 제목 + 라벨 필터 + 업데이트 시간 */}
              <div
                className="cl-section-header"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '16px',
                  flex: 1,
                }}
              >
                <h2 className="cl-section-title">
                  내 자료 ({filteredMaterials.length}개)
                </h2>

                {/* ✅ 라벨 필터 칩 */}
                <div
                  className="cl-filter-chips"
                  style={{
                    padding: 0,
                    margin: 0,
                    flex: 1,
                  }}
                >
                  {LABEL_OPTIONS.map((l) => (
                    <button
                      key={l.id}
                      className={`cl-chip ${activeLabels.includes(l.id) ? 'active' : ''}`}
                      style={{ '--chip-color': l.color } as React.CSSProperties}
                      onClick={() => toggleLabel(l.id)}
                    >
                      {l.name}
                    </button>
                  ))}
                  {activeLabels.length > 0 && (
                    <button className="cl-chip reset" onClick={clearLabels}>
                      초기화
                    </button>
                  )}
                </div>
              </div>

              <div className="cl-last-updated">
                최근 업데이트: {formatKST(lastUpdatedAt, true)}
              </div>

              <div className="cl-cta-row" style={{ gridColumn: '1 / -1' }}>
                <div className="cl-feature-explain">
                  <p className="cl-feature-title">자료 만들기란?</p>
                  <ul className="cl-feature-list">
                    <li>
                      <span>PDF나 TXT 파일 업로드 시 텍스트 자동 추출</span>
                    </li>
                    <li>
                      <span>에디터에서 내용 편집 · 단원 분리</span>
                    </li>
                    <li>
                      <span>완성된 자료를 반/학생에게 전송</span>
                    </li>
                    <li>
                      <span>앱에서 음성 학습 지원</span>
                    </li>
                  </ul>
                </div>

                <button
                  className="cl-create-material-btn"
                  onClick={handleCreateMaterial}
                >
                  <Plus size={20} />
                  <span>새 자료 만들기</span>
                </button>
              </div>
            </div>

            <div className="cl-materials-list">
              {filteredMaterials.length === 0 ? (
                activeLabels.length > 0 ? (
                  <div className="cl-empty-materials">
                    <FileText size={48} />
                    <p>선택한 라벨의 자료가 없습니다</p>
                    <p className="cl-empty-hint">
                      다른 라벨을 선택하거나 초기화하세요
                    </p>
                  </div>
                ) : (
                  <div className="cl-empty-materials">
                    <FileText size={48} />
                    <p>자료가 없습니다</p>
                    <p className="cl-empty-hint">
                      "새 자료 만들기" 버튼을 눌러 시작하세요
                    </p>
                  </div>
                )
              ) : (
                filteredMaterials.map((material) => (
                  // 기존 코드에서 수정
                  <div key={material.id} className="cl-material-item">
                    {material.label && (
                      <div
                        className="cl-material-label-bar"
                        style={{
                          backgroundColor: getLabelColor(material.label),
                        }}
                      />
                    )}

                    {/* ✅ 클릭 가능한 영역 추가 */}
                    <div
                      className="cl-material-clickable"
                      onClick={() => handleViewMaterial(material.id)}
                      style={{
                        flex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        cursor: 'pointer',
                        minWidth: 0, // overflow 처리용
                      }}
                    >
                      <div className="cl-material-icon">
                        <FileText size={18} />
                      </div>
                      <div className="cl-material-info">
                        <h3 className="cl-material-title">{material.title}</h3>
                        <div className="cl-material-meta">
                          <span className="cl-material-date">
                            {material.uploadDate}
                          </span>
                          {material.status === 'draft' && <span className="cl-material-status draft">작성중</span>}
                        </div>
                        {material.status === 'published' && <IndexingStatus
                          resourcePath={`/api/documents/${material.id}/indexing`} initial={material.indexing} />}
                      </div>
                    </div>

                    {/* ✅ 액션 버튼들은 이벤트 전파 방지 */}
                    <div className="cl-material-actions">
                      <button
                        className="cl-material-action-btn download-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDownloadWord(material.id);
                        }}
                        title="워드 파일 다운로드"
                      >
                        <Download size={16} />
                      </button>
                      <button
                        className="cl-material-action-btn send-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSendMaterial(material.id);
                        }}
                        title="자료 공유"
                      >
                        <Send size={16} />
                      </button>
                      <button
                        className="cl-material-action-btn label-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleLabelMaterial(material.id, material.label);
                        }}
                        title="라벨 편집"
                      >
                        <Tag size={16} />
                      </button>
                      <button
                        className="cl-material-action-btn delete-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteMaterial(material.id);
                        }}
                        title="삭제"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </main>
      </div>

      {showSendModal && selectedMaterial && (
        <MaterialSendModal2Step
          classrooms={classrooms.map((c) => ({
            id: c.id,
            name: `${c.grade} ${c.class}`,
            count: (studentsByClassroom[c.id] || []).length,
          }))}
          studentsByClassroom={studentsByClassroom}
          selectedMaterial={{
            id: selectedMaterial.id,
            title: selectedMaterial.title,
            uploadDate: selectedMaterial.uploadDate,
            content: '',
          }}
          onClose={() => {
            setShowSendModal(false);
            setSelectedMaterial(null);
          }}
          onSend={(studentIds, classroomIds) => {
            void shareMaterial(studentIds, classroomIds, selectedMaterial);
          }}
          schoolImage={schoolImg}
          maleImage={maleImg}
          femaleImage={femaleImg}
        />
      )}
    </div>
  );
}
