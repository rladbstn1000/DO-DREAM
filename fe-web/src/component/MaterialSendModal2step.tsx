import React, { useMemo, useState } from 'react';
import { X, Send, FileText, Check, Search } from 'lucide-react';
import './MaterialSendModal.css';

type StudentLite = {
  id: string;
  name: string;
  grade: string;
  gender?: 'male' | 'female'
  avatarUrl?: string;
  avatar?: string;
};

type Material = {
  id: string;
  title: string;
  uploadDate: string;
  content: string;
};

type ClassroomLite = { id: string; name: string; count: number };

type Props = {
  classrooms: ClassroomLite[];
  studentsByClassroom: Record<string, StudentLite[]>;
  selectedMaterial: Material;
  onClose: () => void;
  onSend: (studentIds: string[], classroomIds: string[]) => void;

  // 이미지 리소스
  schoolImage: string; // src/assets/school.png
  maleImage: string; // src/assets/male.png
  femaleImage: string; // src/assets/female.png
};

export default function MaterialSendModal2Step({
  classrooms,
  studentsByClassroom,
  selectedMaterial,
  onClose,
  onSend,
  schoolImage,
  maleImage,
  femaleImage,
}: Props) {
  const [step, setStep] = useState<1 | 2>(1);
  const [query, setQuery] = useState('');
  const [selectAll, setSelectAll] = useState(false);

  // 선택 상태
  const [selectedClasses, setSelectedClasses] = useState<string[]>([]);
  const [selectedStudents, setSelectedStudents] = useState<string[]>([]);

  // 현재 step에 따른 학생 목록
  const students = useMemo(() => {
    const list = selectedClasses.flatMap(
      (cid) => studentsByClassroom[cid] || [],
    );
    const map = new Map<string, StudentLite>();
    list.forEach((s) => map.set(s.id, s));
    return Array.from(map.values());
  }, [selectedClasses, studentsByClassroom]);

  // 검색 필터
  const filteredClasses = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return classrooms;
    return classrooms.filter((c) => c.name.toLowerCase().includes(q));
  }, [classrooms, query]);

  const filteredStudents = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return students;
    return students.filter(
      (s) =>
        s.name.toLowerCase().includes(q) || s.grade.toLowerCase().includes(q),
    );
  }, [students, query]);

  const toggleClass = (id: string) => {
    setSelectedClasses((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const toggleStudent = (id: string) => {
    setSelectedStudents((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const toggleByKey =
    (fn: (id: string) => void, id: string) => (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        fn(id);
      }
    };

  const toggleSelectAll = () => {
    if (step === 1) {
      if (selectAll) {
        const ids = new Set(filteredClasses.map((c) => c.id));
        setSelectedClasses((prev) => prev.filter((id) => !ids.has(id)));
        setSelectAll(false);
      } else {
        const idsToAdd = filteredClasses
          .map((c) => c.id)
          .filter((id) => !selectedClasses.includes(id));
        setSelectedClasses((prev) => [...prev, ...idsToAdd]);
        setSelectAll(true);
      }
    } else {
      if (selectAll) {
        const ids = new Set(filteredStudents.map((s) => s.id));
        setSelectedStudents((prev) => prev.filter((id) => !ids.has(id)));
        setSelectAll(false);
      } else {
        const idsToAdd = filteredStudents
          .map((s) => s.id)
          .filter((id) => !selectedStudents.includes(id));
        setSelectedStudents((prev) => [...prev, ...idsToAdd]);
        setSelectAll(true);
      }
    }
  };

  const canNext =
    step === 1 ? selectedClasses.length > 0 : selectedStudents.length > 0;

  const headerTitle = step === 1 ? '공유할 반 선택' : '공유할 학생 선택';
  const labelText = '선택된 자료';
  const selectToggleText =
    step === 1
      ? `전체 선택 (${filteredClasses.length}개 반)`
      : `전체 선택 (${filteredStudents.length}명)`;

  const handlePrimary = () => {
    if (step === 1) {
      setQuery('');
      setSelectAll(false);
      setStep(2);
    } else {
      if (selectedStudents.length === 0) return;
      onSend(selectedStudents, selectedClasses);
    }
  };

  const getStudentImage = (s: StudentLite): string | undefined => {

    if (s.avatarUrl) {

      return s.avatarUrl;
    }
    if (s.gender === 'male') {

      return maleImage;
    }
    if (s.gender === 'female') {

      return femaleImage;
    }

    return undefined;
  };

  return (
    <div className="msm-overlay">
      <div className="msm-modal">
        {/* Header */}
        <div className="msm-header">
          <h2>{headerTitle}</h2>
          <button className="msm-close-btn" onClick={onClose} aria-label="닫기">
            <X size={24} />
          </button>
        </div>

        {/* Content */}
        <div className="msm-content">
          {/* Material info */}
          <div className="msm-material-info">
            <div className="msm-material-icon">
              <FileText size={22} />
            </div>
            <div>
              <p className="msm-label">{labelText}</p>
              <p className="msm-material-title">{selectedMaterial.title}</p>
            </div>
          </div>

          {/* Search */}
          <div className="msm-search">
            <Search size={16} className="msm-search-icon" />
            <input
              className="msm-search-input"
              type="text"
              placeholder={
                step === 1
                  ? '반 이름 검색 (예: 3학년 1반)'
                  : '이름 또는 학년/반으로 검색'
              }
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelectAll(false);
              }}
            />
          </div>

          {/* Select All */}
          <button
            type="button"
            className={`msm-select-toggle ${selectAll ? 'is-on' : ''}`}
            onClick={toggleSelectAll}
            aria-pressed={selectAll}
          >
            {selectToggleText}
            {selectAll && <Check className="msm-select-check" size={16} />}
          </button>

          {/* List */}
          <div className="msm-students-list">
            {step === 1
              ? filteredClasses.map((c) => {
                  const checked = selectedClasses.includes(c.id);
                  return (
                    <div
                      key={c.id}
                      className={`msm-student-item ${
                        checked ? 'is-selected' : ''
                      }`}
                      role="button"
                      tabIndex={0}
                      onClick={() => toggleClass(c.id)}
                      onKeyDown={toggleByKey(toggleClass, c.id)}
                      aria-pressed={checked}
                    >
                      {checked && (
                        <span className="msm-selected-badge">
                          <Check size={16} />
                        </span>
                      )}
                      {/* 학교 이미지 */}
                      <img
                        className="msm-avatar-img"
                        src={schoolImage}
                        alt="학교"
                      />
                      <div className="msm-student-text">
                        <p className="msm-name">{c.name}</p>
                        <p className="msm-grade">{c.count}명</p>
                      </div>
                    </div>
                  );
                })
              : filteredStudents.map((s) => {
                  const checked = selectedStudents.includes(s.id);
                  const imgSrc = getStudentImage(s);
                  return (
                    <div
                      key={s.id}
                      className={`msm-student-item ${
                        checked ? 'is-selected' : ''
                      }`}
                      role="button"
                      tabIndex={0}
                      onClick={() => toggleStudent(s.id)}
                      onKeyDown={toggleByKey(toggleStudent, s.id)}
                      aria-pressed={checked}
                    >
                      {checked && (
                        <span className="msm-selected-badge">
                          <Check size={16} />
                        </span>
                      )}

                      {imgSrc ? (
                        <img
                          className="msm-avatar-img"
                          src={imgSrc}
                          alt={`${s.name} 아바타`}
                        />
                      ) : (
                        <span className="msm-avatar-emoji">
                          {s.avatar || '👤'}
                        </span>
                      )}

                      <div className="msm-student-text">
                        <p className="msm-name">{s.name}</p>
                        <p className="msm-grade">{s.grade}</p>
                      </div>
                    </div>
                  );
                })}

            {(step === 1
              ? filteredClasses.length === 0
              : filteredStudents.length === 0) && (
              <div className="msm-empty">검색 결과가 없습니다</div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="msm-footer">
          <button className="msm-cancel-btn" onClick={onClose}>
            취소
          </button>
          <button
            className="msm-send-btn"
            onClick={handlePrimary}
            disabled={!canNext}
            aria-disabled={!canNext}
          >
            {step === 1 ? (
              <span>{selectedClasses.length}개 반 선택</span>
            ) : (
              <>
                <Send size={18} />
                <span>{selectedStudents.length}명에게 공유</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
