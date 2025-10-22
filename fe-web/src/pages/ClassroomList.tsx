import { useNavigate } from 'react-router-dom';
import Swal from 'sweetalert2';
import { BookOpen, LogOut, Users } from 'lucide-react';
import './ClassroomList.css';
import schoolImg from '../assets/classList/school.png';
import teacherAvatar from '../assets/classList/teacher.png';
import classImg from '../assets/classList/class.png';

type ClassroomData = {
  id: string;
  grade: string;
  class: string;
  studentCount: number;
  materialCount: number;
  color: string;
};

type ClassroomListProps = {
  onLogout: () => void;
};

export default function ClassroomList({ onLogout }: ClassroomListProps) {
  const navigate = useNavigate();

  const teacher = {
    name: '김싸피',
    email: 'teacher@school.com',
    avatar: teacherAvatar,
  };

  // 담당하는 반 목록
  const classrooms: ClassroomData[] = [
    {
      id: '1',
      grade: '3학년',
      class: '1반',
      studentCount: 28,
      materialCount: 5,
      color: '#4a2d73',
    },
    {
      id: '2',
      grade: '3학년',
      class: '2반',
      studentCount: 26,
      materialCount: 3,
      color: '#0096A6',
    },
    {
      id: '3',
      grade: '2학년',
      class: '1반',
      studentCount: 30,
      materialCount: 8,
      color: '#DD1D5D',
    },
    {
      id: '4',
      grade: '2학년',
      class: '3반',
      studentCount: 25,
      materialCount: 4,
      color: '#EEBF00',
    },
    {
      id: '1',
      grade: '3학년',
      class: '1반',
      studentCount: 28,
      materialCount: 5,
      color: '#4a2d73',
    },
    {
      id: '2',
      grade: '3학년',
      class: '2반',
      studentCount: 26,
      materialCount: 3,
      color: '#0096A6',
    },
    {
      id: '3',
      grade: '2학년',
      class: '1반',
      studentCount: 30,
      materialCount: 8,
      color: '#DD1D5D',
    },
    {
      id: '4',
      grade: '2학년',
      class: '3반',
      studentCount: 25,
      materialCount: 4,
      color: '#EEBF00',
    },
    {
      id: '1',
      grade: '3학년',
      class: '1반',
      studentCount: 28,
      materialCount: 5,
      color: '#4a2d73',
    },
    {
      id: '2',
      grade: '3학년',
      class: '2반',
      studentCount: 26,
      materialCount: 3,
      color: '#0096A6',
    },
    {
      id: '3',
      grade: '2학년',
      class: '1반',
      studentCount: 30,
      materialCount: 8,
      color: '#DD1D5D',
    },
    {
      id: '4',
      grade: '2학년',
      class: '3반',
      studentCount: 25,
      materialCount: 4,
      color: '#EEBF00',
    },
  ];

  const handleSelectClassroom = (classroomId: string) => {
    navigate(`/classroom/${classroomId}`);
  };

  const handleLogout = () => {
    Swal.fire({
      icon: 'question',
      title: '로그아웃 하시겠습니까?',
      showCancelButton: true,
      confirmButtonColor: '#192b55',
      cancelButtonColor: '#d1d5db',
      confirmButtonText: '로그아웃',
      cancelButtonText: '취소',
    }).then((result) => {
      if (result.isConfirmed) {
        Swal.fire({
          icon: 'success',
          title: '로그아웃 되었습니다',
          confirmButtonColor: '#192b55',
        }).then(() => {
          onLogout();
        });
      }
    });
  };

  return (
    <div className="cl-root">
      {/* Header */}
      <header className="cl-header">
        <div className="cl-header-wrapper">
          <h1 className="cl-header-title">DO:DREAM</h1>
          <button className="cl-logout-button" onClick={handleLogout}>
            <LogOut size={18} />
            <span>로그아웃</span>
          </button>
        </div>
      </header>

      {/* Main Content */}
      <div className="cl-container">
        {/* Profile Section */}
        <div className="cl-profile-section">
          <div className="cl-profile-card">
            <img src={schoolImg} alt="학교 아이콘" className="cl-profile-avatar" />
            <div className="cl-profile-info">
              <div className="cl-info">
                <h2 className="cl-profile-name">서울싸피맹학교</h2>
              </div>
              <p className="cl-school-address">서울특별시 용산구 한강로2가 1</p>
            </div>
          </div>

          <div className="cl-profile-card">
            <img className="cl-profile-avatar" src={teacher.avatar} alt={`${teacher.name} 아바타`} />
            <div className="cl-profile-info">
              <div className="cl-info">
                <h2 className="cl-profile-name">{teacher.name}</h2>
                <p className="cl-stat-label">선생님</p>
              </div>
              <p className="cl-profile-email">{teacher.email}</p>
            </div>
          </div>

          <div className="cl-stat-card">
            <div className="cl-stat-item">
              <img src={classImg} alt="자료 아이콘" className="cl-profile-avatar" />
              <div className="cl-info">
                <p className="cl-stat-value">{classrooms.length}</p>
                <p className="cl-stat-label">개 반 담당</p>
              </div>
            </div>
          </div>
        </div>

        {/* Classrooms Section */}
        <div className="cl-classrooms-section">
          <h2 className="cl-section-title">담당 반 선택</h2>
          <p className="cl-section-subtitle">
            자료를 관리할 반을 선택해주세요
          </p>

          <div className="cl-classrooms-grid">
            {classrooms.map((classroom) => (
              <div
                key={classroom.id}
                className="cl-classroom-card"
                onClick={() => handleSelectClassroom(classroom.id)}
                style={{
                  borderTopColor: classroom.color,
                }}
              >
                <div className="cl-classroom-header">
                  <div
                    className="cl-classroom-color-badge"
                    style={{ backgroundColor: classroom.color }}
                  />
                  <div className="cl-classroom-title">
                    <h3>{classroom.grade}</h3>
                    <p>{classroom.class}</p>
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
      </div>
    </div>
  );
}