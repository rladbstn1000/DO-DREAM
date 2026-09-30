import { authenticatedFetch } from '../auth/client';
import { useState, useMemo, useEffect } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import {
  ArrowLeft,
  FileText,
  MessageCircle,
  Award,
  Home,
  Search,
  SortDesc,
  SortAsc,
} from 'lucide-react';
import Swal from 'sweetalert2';
import './StudentRoom.css';

type Student = {
  id: string;
  name: string;
  grade: string;
  avatarUrl?: string;
  progressRate: number;
};

type ReceivedMaterial = {
  id: string;
  title: string;
  teacher: string;
  receivedDate: string;
  status: 'not-started' | 'in-progress' | 'completed';
  progressRate: number;
  pdfId?: number;
};

type QuizResult = {
  materialId: number;
  materialTitle: string;
  correctCount: number;
  tryCount: number;
  totalQuizCount: number;
  correctRate: number;
};

type StudentStats = {
  studentId: number;
  solvedMaterialCount: number;
  averageCorrectRate: number;
};

type StudentQuestion = {
  id: string;
  document_id: string;
  material_title: string;
  session_title: string;
  created_at: string;
  last_message_preview: string;
};

type ChatMessage = {
  role: 'user' | 'ai';
  content: string;
  created_at: string;
};

type ChatSession = {
  session_id: string;
  material_title: string;
  messages: ChatMessage[];
};

type SharedMaterialItemDto = {
  shareId: number;
  materialId: number;
  materialTitle: string;
  teacherId: number;
  teacherName: string;
  labelColor:
    | 'RED'
    | 'ORANGE'
    | 'YELLOW'
    | 'GREEN'
    | 'BLUE'
    | 'PURPLE'
    | 'GRAY'
    | null;
  sharedAt: string;
  accessedAt: string | null;
  accessed: boolean;
  pdfId?: number;
};

type StudentSharedMaterialsDto = {
  studentId: number;
  studentName: string;
  totalCount: number;
  materials: SharedMaterialItemDto[];
};

const formatYmdFromIso = (iso: string | null | undefined) => {
  if (!iso) return '';

  // ISO 형태가 아닌 경우: "2025-11-19T04:40:39.3595648"라면 T 앞부분만 잘라서 사용
  const [datePart] = iso.split('T');
  if (!datePart) return iso;

  // 혹시 타임존 보정까지 하고 싶으면 아래처럼 Date로 한 번 감싸도 됨
  // const d = new Date(iso);
  // if (Number.isNaN(d.getTime())) return datePart;
  // const yyyy = d.getFullYear();
  // const mm = String(d.getMonth() + 1).padStart(2, '0');
  // const dd = String(d.getDate()).padStart(2, '0');
  // return `${yyyy}-${mm}-${dd}`;

  return datePart; // "2025-11-19"
};

const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '');
const RAG_BASE = (import.meta.env.VITE_RAG_BASE || '/ai').replace(/\/+$/, '');

export default function StudentRoom() {
  const navigate = useNavigate();
  const location = useLocation();
  const { studentId } = useParams<{ studentId: string }>();

  const [selectedSession, setSelectedSession] = useState<ChatSession | null>(
    null,
  );
  const [showChatModal, setShowChatModal] = useState(false);

  // ✅ 전달받은 데이터만 사용
  const student = location.state?.student as Student | undefined;
  const classroomId = location.state?.classroomId as string | undefined;
  const classLabel = location.state?.classLabel as string | undefined;

  // ✅ 학생 데이터가 없으면 리다이렉트
  useEffect(() => {
    if (!student) {
      navigate('/classrooms', { replace: true });
    }
  }, [student, navigate]);

  const [matQuery, setMatQuery] = useState('');
  const [matSort, setMatSort] = useState<'new' | 'old'>('new');
  const [isLoading, setIsLoading] = useState(false);

  // ✅ API로 받아올 데이터들 (현재는 빈 배열)
  const [receivedMaterials, setReceivedMaterials] = useState<
    ReceivedMaterial[]
  >([]);
  const [quizResults, setQuizResults] = useState<QuizResult[]>([]);
  const [studentQuestions, setStudentQuestions] = useState<StudentQuestion[]>(
    [],
  );

  const [studentStats, setStudentStats] = useState<StudentStats | null>(null);

  // ✅ 특정 학생에게 공유된 학습자료 / 진행률 불러오기
  useEffect(() => {
    if (!student) return;

    const fetchStudentData = async () => {
      try {
        setIsLoading(true);

        const accessToken = localStorage.getItem('accessToken');
        const headers: HeadersInit = {
          accept: '*/*',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        };

        // 1) 이 학생에게 공유된 학습 자료 조회
        const sharedRes = await authenticatedFetch(
          `${API_BASE}/api/materials/shared/student/${student.id}`,
          { method: 'GET', headers, credentials: 'include' },
        );

        let shared: StudentSharedMaterialsDto | undefined;

        if (sharedRes.ok) {
          const raw = await sharedRes.json();

          // Swagger 스타일 { success, code, message, data } 래핑 처리
          const payload =
            raw && typeof raw === 'object' && 'data' in raw
              ? (raw as any).data
              : raw;

          if (
            payload &&
            typeof payload === 'object' &&
            Array.isArray((payload as any).materials)
          ) {
            shared = payload as StudentSharedMaterialsDto;
          }
        } else {
          console.warn("화면 요청 처리 실패");
        }

        // 2) 이 학생의 자료별 진행률 조회
        const progressMap = new Map<
          number,
          { progressPercent: number; completedAt: string | null }
        >();

        const progressRes = await authenticatedFetch(
          `${API_BASE}/api/progress/students/${student.id}/all`,
          { method: 'GET', headers, credentials: 'include' },
        );

        if (progressRes.ok) {
          const raw = await progressRes.json();

          const payload =
            raw && typeof raw === 'object' && 'data' in raw
              ? (raw as any).data
              : raw;

          const items = Array.isArray(payload) ? payload : [];

          items.forEach((item: any) => {
            const rawValue = item.overallProgressPercentage ?? 0;
            const percent = rawValue <= 1 ? rawValue * 100 : rawValue; // 0~1 or 0~100 대응
            progressMap.set(item.materialId, {
              progressPercent: percent,
              completedAt: item.completedAt ?? null,
            });
          });
        } else {
          console.warn("화면 요청 처리 실패");
        }

        // 3) UI에서 사용할 형태로 변환
        if (shared) {
          const materials: ReceivedMaterial[] = (shared.materials ?? []).map(
            (m) => {
              const prog = progressMap.get(m.materialId);
              const percent = Math.round(prog?.progressPercent ?? 0);

              let status: ReceivedMaterial['status'] = 'not-started';
              if (percent >= 99) status = 'completed';
              else if (percent > 0 || m.accessed) status = 'in-progress';

              return {
                id: String(m.materialId),
                title: m.materialTitle,
                teacher: m.teacherName,
                receivedDate: m.sharedAt, // 정렬은 ISO 문자열 그대로 사용
                status,
                progressRate: percent,
                pdfId: m.pdfId,
              };
            },
          );

          setReceivedMaterials(materials);
        } else {
          setReceivedMaterials([]);
        }

        // 4) 학생 통계 조회 (평균 정답률)
        const statsRes = await authenticatedFetch(
          `${API_BASE}/api/stats/student/${student.id}/overall`,
          { method: 'GET', headers, credentials: 'include' },
        );

        if (statsRes.ok) {
          const raw = await statsRes.json();

          const payload =
            raw && typeof raw === 'object' && 'data' in raw
              ? (raw as any).data
              : raw;

          if (payload) {
            const rawRate = payload.averageCorrectRate || 0;
            // 0~1 범위면 100 곱하기, 이미 0~100이면 그대로
            const rate = rawRate <= 1 ? rawRate * 100 : rawRate;

            setStudentStats({
              studentId: payload.studentId || Number(student.id),
              solvedMaterialCount: payload.solvedMaterialCount || 0,
              averageCorrectRate: Math.round(rate),
            });
          }
        } else {
          console.warn("화면 요청 처리 실패");
          setStudentStats(null);
        }

        // 5) 자료별 퀴즈 성적 조회
        const quizRes = await authenticatedFetch(
          `${API_BASE}/api/stats/student/${student.id}/materials`,
          { method: 'GET', headers, credentials: 'include' },
        );

        if (quizRes.ok) {
          const raw = await quizRes.json();

          const payload =
            raw && typeof raw === 'object' && 'data' in raw
              ? (raw as any).data
              : raw;

          const items = Array.isArray(payload) ? payload : [];

          const quizResults: QuizResult[] = items.map((item: any) => {
            const rawRate = item.correctRate || 0;
            const rate = rawRate <= 1 ? rawRate * 100 : rawRate;

            return {
              materialId: item.materialId || 0,
              materialTitle: item.materialTitle || '',
              correctCount: item.correctCount || 0,
              tryCount: item.tryCount || 0,
              totalQuizCount: item.totalQuizCount || 0,
              correctRate: Math.round(rate),
            };
          });

          setQuizResults(quizResults);
        } else {
          console.warn("화면 요청 처리 실패");
          setQuizResults([]);
        }

        const qaRes = await authenticatedFetch(
          `${RAG_BASE}/rag/chat/sessions?student_id=${student.id}`,
          { method: 'GET', headers, credentials: 'include' },
        );

        if (qaRes.ok) {
          const raw = await qaRes.json();

          const items = Array.isArray(raw) ? raw : [];

          const questions: StudentQuestion[] = items.map((item: any) => ({
            id: item.id || '',
            document_id: item.document_id || '',
            material_title: item.material_title || '',
            session_title: item.session_title || '',
            created_at: item.created_at || '',
            last_message_preview: item.last_message_preview || '',
          }));

          // 최신순 정렬
          questions.sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime(),
          );

          setStudentQuestions(questions);
        } else {
          console.warn("화면 요청 처리 실패");
          setStudentQuestions([]);
        }
      } catch (err) {
        console.error('학생 데이터 로딩 실패');
        setReceivedMaterials([]);
        setQuizResults([]);
        setStudentQuestions([]);
        setStudentStats(null);
      } finally {
        setIsLoading(false);
      }
    };

    void fetchStudentData();
  }, [student?.id]);

  const filteredMaterials = useMemo(() => {
    const q = matQuery.trim().toLowerCase();
    let list = receivedMaterials.filter((m) =>
      q ? m.title.toLowerCase().includes(q) : true,
    );
    list.sort((a, b) =>
      matSort === 'new'
        ? new Date(b.receivedDate).getTime() -
          new Date(a.receivedDate).getTime()
        : new Date(a.receivedDate).getTime() -
          new Date(b.receivedDate).getTime(),
    );
    return list;
  }, [receivedMaterials, matQuery, matSort]);

  const avgAccuracy = useMemo(() => {
    return studentStats?.averageCorrectRate || 0;
  }, [studentStats]);

  const completedCount = useMemo(() => {
    return receivedMaterials.filter((m) => m.status === 'completed').length;
  }, [receivedMaterials]);

  const weakInsights = [];

  const handleViewMaterial = async (materialId: string) => {
    try {
      const material = receivedMaterials.find((m) => m.id === materialId);
      if (!material) {
        await Swal.fire({
          icon: 'error',
          title: '자료를 찾을 수 없습니다',
          confirmButtonColor: '#192b55',
        });
        return;
      }

      const pdfId = material.pdfId;
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
          text || `자료 내용을 불러오지 못했습니다. (status: ${pdfRes.status})`,
        );
      }

      const parsedData = await pdfRes.json();

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

      let labelColor: string | undefined;
      if (parsedData.labelColor) {
        labelColor = parsedData.labelColor.toLowerCase();
      } else if (parsedData.label) {
        labelColor = parsedData.label.toLowerCase();
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

      navigate('/editor', {
        state: {
          fileName: material.title,
          chapters,
          pdfId,
          materialId,
          mode: 'edit',
          from: 'student-room',
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

  const handleViewQA = (sessionId: string, materialTitle: string) => {
    // 별도 페이지로 이동 (state로 데이터 전달)
    navigate(`/chat-history/${sessionId}`, {
      state: {
        sessionId,
        materialTitle,
        studentId: student.id,
        studentName: student.name,
        from: 'student-room',
      },
    });
  };

  const getStatusBadge = (status: string) =>
    status === 'completed'
      ? '완료'
      : status === 'in-progress'
        ? '진행중'
        : '미시작';

  const getStatusColor = (status: string) =>
    status === 'completed'
      ? '#10b981'
      : status === 'in-progress'
        ? '#f59e0b'
        : '#9ca3af';

  const handleBack = () => {
    if (classroomId) {
      navigate(`/classroom/${classroomId}`);
    } else {
      navigate(-1);
    }
  };

  const handleBackHome = () => navigate('/classrooms');

  // ✅ student가 없으면 아무것도 렌더링 안 함
  if (!student) return null;

  return (
    <div className="sr-root student-room-page">
      {/* Header */}
      <header className="cl-header">
        <div className="cl-header-wrapper">
          <h1
            className="cl-header-title cl-header-title--clickable"
            onClick={() => navigate('/classrooms')}
            style={{ cursor: 'pointer' }}
          >
            DO:DREAM
          </h1>
          <div className="cl-header-button">
            <button
              type="button"
              className="cl-logout-button"
              onClick={handleBack}
              title="뒤로가기"
            >
              <ArrowLeft size={18} />
              <span>뒤로가기</span>
            </button>
            <button
              type="button"
              className="cl-logout-button"
              onClick={handleBackHome}
              title="메인으로"
            >
              <Home size={18} />
              <span>메인으로</span>
            </button>
          </div>
        </div>
      </header>

      {/* Sidebar */}
      <aside className="cl-sidebar">
        <div className="cl-sidebar-content">
          <div className="cl-profile-mini">
            {student.avatarUrl ? (
              <img
                className="cl-profile-avatar-mini"
                src={student.avatarUrl}
                alt={`${student.name} 아바타`}
              />
            ) : (
              <div className="sr-avatar-placeholder">👤</div>
            )}
            <h2 className="cl-profile-name-mini">{student.name}</h2>
            <p className="cl-profile-email-mini">{student.grade}</p>
          </div>

          {/* 학습 현황 요약 */}
          <div className="sr-sidebar-stats">
            <div className="sr-sidebar-stat-item">
              <div className="sr-sidebar-stat-label">전체 학습 진도</div>
              <div className="sr-sidebar-stat-value">
                {student.progressRate}%
              </div>
              <div className="sr-sidebar-progress-bar">
                <div
                  className="sr-sidebar-progress-fill"
                  style={{ width: `${student.progressRate}%` }}
                />
              </div>
            </div>

            <div className="sr-sidebar-stat-item">
              <div className="sr-sidebar-stat-label">완료한 자료</div>
              <div className="sr-sidebar-stat-value">
                {completedCount}/{receivedMaterials.length}
              </div>
            </div>

            <div className="sr-sidebar-stat-item">
              <div className="sr-sidebar-stat-label">평균 정답률</div>
              <div className="sr-sidebar-stat-value">{avgAccuracy}%</div>
            </div>

            <div className="sr-sidebar-stat-item">
              <div className="sr-sidebar-stat-label">질문 & 답변</div>
              <div className="sr-sidebar-stat-value">
                {studentQuestions.length}
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="cl-main-fixed">
        <div className="sr-content-wrapper">
          {/* 받은 자료 */}
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
                    placeholder="자료 제목 검색"
                    value={matQuery}
                    onChange={(e) => setMatQuery(e.target.value)}
                  />
                </div>
                <button
                  className="cl-sort-btn cl-control"
                  onClick={() =>
                    setMatSort((s) => (s === 'new' ? 'old' : 'new'))
                  }
                >
                  {matSort === 'new' ? (
                    <SortDesc size={16} />
                  ) : (
                    <SortAsc size={16} />
                  )}
                  <span>{matSort === 'new' ? '최신 순' : '오래된 순'}</span>
                </button>
              </div>
            </div>

            <div className="cl-section-scroll">
              <div className="cl-materials-list">
                {isLoading ? (
                  <p className="cl-empty-hint">불러오는 중입니다…</p>
                ) : filteredMaterials.length === 0 ? (
                  <div className="cl-empty-materials">
                    <FileText size={48} />
                    <p>받은 자료가 없습니다</p>
                    <p className="cl-empty-hint">
                      선생님이 자료를 공유하면 이곳에 표시됩니다.
                    </p>
                  </div>
                ) : (
                  filteredMaterials.map((m) => (
                    <div
                      key={m.id}
                      className="cl-material-item"
                      onClick={() => handleViewMaterial(m.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <div className="cl-material-icon">
                        <FileText size={18} />
                      </div>
                      <div className="cl-material-info">
                        <h3 className="cl-material-title">{m.title}</h3>
                        <div className="cl-material-meta">
                          <span className="cl-material-date">
                            {formatYmdFromIso(m.receivedDate)}
                          </span>
                          <span> · </span>
                          <span>{m.teacher} 발행</span>
                        </div>
                      </div>
                      <div className="sr-material-progress">
                        <div className="sr-progress-bar-small">
                          <div
                            className="sr-progress-fill-small"
                            style={{ width: `${m.progressRate}%` }}
                          />
                        </div>
                        <span
                          className="sr-status-badge"
                          style={{ background: getStatusColor(m.status) }}
                        >
                          {getStatusBadge(m.status)}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>

          {/* 퀴즈 성적 */}
          <section className="cl-card">
            <div className="cl-card-head">
              <div className="cl-head-left">
                <Award size={20} />
                <h3>퀴즈 성적</h3>
              </div>
            </div>

            <div className="cl-section-scroll">
              {quizResults.length === 0 ? (
                <p className="cl-empty-hint">퀴즈 결과가 없습니다.</p>
              ) : (
                <div className="sr-quiz-grid">
                  {quizResults.map((q) => (
                    <div key={q.materialId} className="sr-quiz-card">
                      <div className="sr-quiz-card-header">
                        <h4 className="sr-quiz-card-title">
                          {q.materialTitle}
                        </h4>
                      </div>
                      <div className="sr-quiz-card-body">
                        <div className="sr-quiz-card-row">
                          <span className="sr-quiz-card-label">
                            전체 문제 수
                          </span>
                          <span className="sr-quiz-card-value">
                            총 {q.totalQuizCount}개의 문제 중에서
                          </span>
                        </div>
                        <div className="sr-quiz-card-row">
                          <span className="sr-quiz-card-label">정답 개수</span>
                          <span className="sr-quiz-card-value">
                            {q.correctCount}개 정답
                          </span>
                        </div>
                        <div className="sr-quiz-card-row">
                          <span className="sr-quiz-card-label">정답률</span>
                          <span className="sr-quiz-card-value sr-quiz-rate">
                            {q.correctRate}%
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          {/* Q&A */}
          <section className="cl-card">
            <div className="cl-card-head">
              <div className="cl-head-left">
                <MessageCircle size={20} />
                <h3>질문 & 답변</h3>
              </div>
            </div>

            <div className="cl-section-scroll">
              {studentQuestions.length === 0 ? (
                <p className="cl-empty-hint">질문 & 답변이 없습니다.</p>
              ) : (
                <div className="sr-qa-list">
                  {studentQuestions.map((qa) => (
                    <div
                      key={qa.id}
                      className="sr-qa-item"
                      onClick={() => handleViewQA(qa.id, qa.material_title)}
                      style={{ cursor: 'pointer' }}
                    >
                      <div className="sr-qa-preview-left">
                        <p className="sr-qa-preview-text">
                          {qa.last_message_preview}
                        </p>
                      </div>
                      <div className="sr-qa-preview-right">
                        <span className="sr-topic-badge">
                          {qa.material_title}
                        </span>
                        <span className="sr-qa-date">
                          {formatYmdFromIso(qa.created_at)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
