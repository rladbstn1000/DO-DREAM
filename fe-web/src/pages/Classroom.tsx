import { useParams, useNavigate } from 'react-router-dom';
import Swal from 'sweetalert2';
import {
  User,
  FolderOpen,
  FileText,
  LogOut,
  ArrowLeft,
  Trash2,
  Search,
  SortDesc,
  SortAsc,
  Tag,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import './Classroom.css';
import male from '../assets/classroom/male.png';
import female from '../assets/classroom/female.png';

type Student = {
  id: string;
  name: string;
  grade: string;
  avatar: string;
  avatarUrl?: string;
  progressRate: number;
};

type Material = {
  id: string;
  title: string;
  uploadDate: string; // YYYY.MM.DD
  content: string;
  label?: 'red' | 'orange' | 'yellow' | 'green' | 'blue' | 'purple' | 'gray';
  teacherId?: string;
};

type ClassroomProps = {
  onNavigateToEditor: (extractedText: string) => void;
  classroomId?: string;
};

const LABELS: Record<
  NonNullable<Material['label']>,
  { name: string; color: string }
> = {
  red: { name: '빨강', color: '#ef4444' },
  orange: { name: '주황', color: '#f97316' },
  yellow: { name: '노랑', color: '#eab308' },
  green: { name: '초록', color: '#22c55e' },
  blue: { name: '파랑', color: '#3b82f6' },
  purple: { name: '보라', color: '#a855f7' },
  gray: { name: '회색', color: '#9ca3af' },
};

function parseDate(d: string) {
  const [y, m, day] = d.split('.').map((x) => parseInt(x, 10));
  return new Date(y, m - 1, day);
}

export default function Classroom({
  onNavigateToEditor,
  classroomId: propClassroomId,
}: ClassroomProps) {
  const { classroomId: urlClassroomId } = useParams<{ classroomId: string }>();
  const navigate = useNavigate();
  const classroomId = urlClassroomId || propClassroomId || '1';

  const [materials, setMaterials] = useState<Material[]>([
    {
      id: '1',
      title: '1학기 수업 자료',
      uploadDate: '2024.03.15',
      content: '첫 번째 자료의 내용입니다.',
      label: 'red',
      teacherId: 'teacher1',
    },
    {
      id: '2',
      title: '학습 참고 자료',
      uploadDate: '2024.03.20',
      content: '학습 참고 자료의 내용입니다.',
      label: 'blue',
      teacherId: 'teacher1',
    },
    {
      id: '3',
      title: '심화 학습 문제',
      uploadDate: '2024.03.25',
      content: '심화 학습 문제입니다.',
      label: 'green',
      teacherId: 'teacher1',
    },
  ]);

  const students: Student[] = [
    {
      id: '1',
      name: '김민준',
      grade: '3학년 1반',
      avatar: '👦🏻',
      avatarUrl: male,
      progressRate: 85,
    },
    {
      id: '2',
      name: '이서연',
      grade: '3학년 1반',
      avatar: '👧🏻',
      avatarUrl: female,
      progressRate: 92,
    },
    {
      id: '3',
      name: '박지호',
      grade: '3학년 2반',
      avatar: '👦🏻',
      avatarUrl: male,
      progressRate: 78,
    },
    {
      id: '4',
      name: '최유진',
      grade: '3학년 2반',
      avatar: '👧🏻',
      avatarUrl: female,
      progressRate: 88,
    },
    {
      id: '5',
      name: '정민수',
      grade: '3학년 3반',
      avatar: '👦🏻',
      avatarUrl: male,
      progressRate: 95,
    },
    {
      id: '6',
      name: '강서윤',
      grade: '3학년 3반',
      avatar: '👧🏻',
      avatarUrl: female,
      progressRate: 81,
    },
  ];

  const classroomInfo: Record<
    string,
    { grade: string; class: string; subject: string }
  > = {
    '1': { grade: '3학년', class: '1반', subject: '국어' },
    '2': { grade: '3학년', class: '2반', subject: '수학' },
    '3': { grade: '2학년', class: '1반', subject: '영어' },
    '4': { grade: '2학년', class: '3반', subject: '과학' },
  };
  const currentClassroom = classroomInfo[classroomId] || classroomInfo['1'];

  const handleLogout = () => {
    Swal.fire({
      icon: 'question',
      title: '로그아웃하시겠습니까?',
      showCancelButton: true,
      confirmButtonColor: '#192b55',
      cancelButtonColor: '#d1d5db',
      reverseButtons: true,
      confirmButtonText: '로그아웃',
      cancelButtonText: '취소',
    }).then((result) => {
      if (result.isConfirmed) {
        Swal.fire({
          icon: 'success',
          title: '로그아웃되었습니다',
          confirmButtonColor: '#192b55',
        });
      }
    });
  };

  /* ===== 자료 툴바 상태 ===== */
  const [matQuery, setMatQuery] = useState('');
  const [matSort, setMatSort] = useState<'new' | 'old'>('new');
  const [activeLabels, setActiveLabels] = useState<Set<Material['label']>>(
    new Set(),
  );

  const toggleLabel = (label: Material['label']) => {
    setActiveLabels((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const filteredMaterials = useMemo(() => {
    const q = matQuery.trim().toLowerCase();
    let list = materials.filter((m) =>
      q ? m.title.toLowerCase().includes(q) : true,
    );
    if (activeLabels.size > 0)
      list = list.filter((m) => m.label && activeLabels.has(m.label));
    list.sort((a, b) =>
      matSort === 'new'
        ? parseDate(b.uploadDate).getTime() - parseDate(a.uploadDate).getTime()
        : parseDate(a.uploadDate).getTime() - parseDate(b.uploadDate).getTime(),
    );
    return list;
  }, [materials, matQuery, matSort, activeLabels]);

  const handleDeleteMaterial = (materialId: string) => {
    Swal.fire({
      title: '자료를 삭제하시겠습니까?',
      text: '이 작업은 되돌릴 수 없습니다',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#d1d5db',
      confirmButtonText: '삭제',
      cancelButtonText: '취소',
      reverseButtons: true,
    }).then((result) => {
      if (result.isConfirmed) {
        setMaterials((prev) => prev.filter((m) => m.id !== materialId));
        Swal.fire({
          icon: 'success',
          title: '자료가 삭제되었습니다',
          confirmButtonColor: '#192b55',
        });
      }
    });
  };

  /* ===== 학생 툴바 상태 ===== */
  const [stuQuery, setStuQuery] = useState('');
  const [stuSort, setStuSort] = useState<'progress' | 'name'>('progress');

  const filteredStudents = useMemo(() => {
    const q = stuQuery.trim().toLowerCase();
    let list = students.filter((s) =>
      q
        ? s.name.toLowerCase().includes(q) || s.grade.toLowerCase().includes(q)
        : true,
    );
    list.sort((a, b) =>
      stuSort === 'progress'
        ? b.progressRate - a.progressRate
        : a.name.localeCompare(b.name, 'ko'),
    );
    return list;
  }, [students, stuQuery, stuSort]);

  /* ===== 좌측 KPI 최신 날짜 ===== */
  const latestDate = useMemo(() => {
    if (materials.length === 0) return '-';
    const latest = materials
      .map((m) => parseDate(m.uploadDate))
      .sort((a, b) => b.getTime() - a.getTime())[0];
    const y = latest.getFullYear();
    const mm = String(latest.getMonth() + 1).padStart(2, '0');
    const dd = String(latest.getDate()).padStart(2, '0');
    return `${y}.${mm}.${dd}`;
  }, [materials]);

  return (
    <div className="cr-root">
      {/* Header */}
      <header className="cr-header">
        <div className="cr-header-wrapper">
          <div className="cr-header-left">
            <h1 className="cr-header-title">DO:DREAM</h1>
          </div>
          <div className="cr-header-right">
            <button
              className="cr-back-chip"
              onClick={() => navigate('/classrooms')}
              aria-label="돌아가기"
            >
              <ArrowLeft size={16} />
              <span>돌아가기</span>
            </button>
            <button className="cr-logout-button" onClick={handleLogout}>
              <LogOut size={18} />
              <span>로그아웃</span>
            </button>
          </div>
        </div>
      </header>

      {/* 좌측 sticky 인포 + 우측 본문 */}
      <div className="cr-shell">
        {/* Left Info Panel (sticky) */}
        <aside className="cr-side">
          <div className="cr-class-badge">
            <span className="cr-class-grade">{currentClassroom.grade}</span>
            <span className="cr-class-class">{currentClassroom.class}</span>
          </div>

          <div className="cr-kpis">
            <div className="cr-kpi">
              <p className="cr-kpi-label">자료</p>
              <p className="cr-kpi-value">{materials.length}개</p>
            </div>
            <div className="cr-kpi">
              <p className="cr-kpi-label">학생</p>
              <p className="cr-kpi-value">{students.length}명</p>
            </div>
            <div className="cr-kpi">
              <p className="cr-kpi-label">최근 업데이트</p>
              <p className="cr-kpi-value">{latestDate}</p>
            </div>
          </div>
        </aside>

        {/* Right Main */}
        <main className="cr-main">
          <div className="cr-main-grid">
            {/* Materials */}
            <section className="cr-section">
              <div className="cr-section-title">
                <FolderOpen size={20} />
                <h3>공유된 학습 자료</h3>
              </div>

              {/* 자료 툴바: 1줄(검색+정렬), 2줄(라벨칩) */}
              <div className="cr-toolbar">
                <div className="cr-toolbar-row">
                  <div className="cr-input-wrap">
                    <Search size={16} />
                    <input
                      className="cr-input"
                      type="text"
                      placeholder="자료 제목 검색"
                      value={matQuery}
                      onChange={(e) => setMatQuery(e.target.value)}
                    />
                  </div>

                  <button
                    className="cr-sort-btn"
                    onClick={() =>
                      setMatSort((s) => (s === 'new' ? 'old' : 'new'))
                    }
                    title={matSort === 'new' ? '오래된 순' : '최신 순'}
                  >
                    {matSort === 'new' ? (
                      <SortDesc size={16} />
                    ) : (
                      <SortAsc size={16} />
                    )}
                    <span>{matSort === 'new' ? '최신 순' : '오래된 순'}</span>
                  </button>
                </div>

                <div
                  className="cr-label-chips"
                  role="listbox"
                  aria-label="라벨 필터"
                >
                  {(
                    Object.keys(LABELS) as Array<NonNullable<Material['label']>>
                  ).map((key) => (
                    <button
                      key={key}
                      className={`cr-chip ${activeLabels.has(key) ? 'active' : ''}`}
                      onClick={() => toggleLabel(key)}
                      title={LABELS[key].name}
                      style={
                        activeLabels.has(key)
                          ? {
                              backgroundColor: LABELS[key].color, // ✅ 배경을 라벨 색으로
                              borderColor: LABELS[key].color, // ✅ 테두리도 같은 색
                              color: '#ffffff',
                            }
                          : undefined
                      }
                    >
                      <Tag size={14} />
                      <span>{LABELS[key].name}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* 자료 리스트 */}
              <div className="cr-materials-list cr-scroll-y">
                {filteredMaterials.length === 0 ? (
                  <div className="cr-empty-state">
                    <FolderOpen size={48} />
                    <p className="cr-empty-main">조건에 맞는 자료가 없습니다</p>
                    <p className="cr-empty-hint">
                      검색어나 라벨 필터를 확인해보세요
                    </p>
                  </div>
                ) : (
                  filteredMaterials.map((material) => (
                    <div key={material.id} className="cr-material-card">
                      {material.label && (
                        <div
                          className="cr-material-label-bar"
                          style={{
                            backgroundColor: LABELS[material.label].color,
                          }}
                        />
                      )}
                      <div className="cr-material-icon">
                        <FileText size={20} />
                      </div>
                      <div className="cr-material-info">
                        <h4>{material.title}</h4>
                        <span>{material.uploadDate}</span>
                      </div>
                      <div className="cr-material-actions">
                        <button
                          className="cr-action-btn delete"
                          onClick={() => handleDeleteMaterial(material.id)}
                          title="자료 삭제"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>

            {/* Students */}
            <section className="cr-section">
              <div className="cr-section-title">
                <User size={20} />
                <h3>학생 관리 ({filteredStudents.length}명)</h3>
              </div>

              {/* 학생 툴바: 1줄(검색+정렬) */}
              <div className="cr-toolbar">
                <div className="cr-toolbar-row">
                  <div className="cr-input-wrap">
                    <Search size={16} />
                    <input
                      className="cr-input"
                      type="text"
                      placeholder="이름 또는 학년/반 검색"
                      value={stuQuery}
                      onChange={(e) => setStuQuery(e.target.value)}
                    />
                  </div>

                  <button
                    className="cr-sort-btn"
                    onClick={() =>
                      setStuSort((s) =>
                        s === 'progress' ? 'name' : 'progress',
                      )
                    }
                    title={stuSort === 'progress' ? '이름순' : '진행률순'}
                  >
                    {stuSort === 'progress' ? (
                      <SortDesc size={16} />
                    ) : (
                      <SortAsc size={16} />
                    )}
                    <span>
                      {stuSort === 'progress' ? '진행률순' : '이름순'}
                    </span>
                  </button>
                </div>
              </div>

              {/* 학생 리스트 */}
              <div className="cr-students-scroll cr-scroll-y">
                <div className="cr-students-list">
                  {filteredStudents.map((student) => (
                    <div
                      key={student.id}
                      className="cr-student-card"
                      onClick={() => navigate(`/student/${student.id}`)}
                    >
                      <div className="cr-student-header">
                        {student.avatarUrl ? (
                          <img
                            className="cr-student-avatar-img"
                            src={student.avatarUrl}
                            alt={`${student.name} 아바타`}
                          />
                        ) : (
                          <div className="cr-student-avatar">
                            {student.avatar}
                          </div>
                        )}

                        <div className="cr-student-info">
                          <h4>{student.name}</h4>
                          <p>{student.grade}</p>
                        </div>
                      </div>

                      {/* 진행률 뷰(슬라이더 아님) */}
                      <div className="cr-student-progress">
                        <div className="cr-progress-header">
                          <span className="cr-progress-label">학습 진행률</span>
                          <span className="cr-progress-percent">
                            {student.progressRate}%
                          </span>
                        </div>
                        <div className="cr-progress-bar">
                          <div
                            className="cr-progress-fill"
                            style={{ width: `${student.progressRate}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}

                  {filteredStudents.length === 0 && (
                    <div className="cr-empty-state" style={{ padding: 24 }}>
                      <User size={36} />
                      <p>조건에 맞는 학생이 없습니다</p>
                      <p className="cr-empty-hint">
                        검색어나 정렬을 확인해보세요
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}
