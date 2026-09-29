"""Read-only mappings of the existing Spring schema (all relationship IDs are explicit)."""
import enum
from sqlalchemy import Column, Integer, String, Enum, BigInteger, DateTime, Text
from app.common.db_session import Base


class RoleEnum(enum.Enum):
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"


class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True, index=True)
    name = Column(String, index=True)
    role = Column(Enum(RoleEnum))


class TeacherProfile(Base):
    __tablename__ = "teacher_profiles"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, nullable=False)


class StudentProfile(Base):
    __tablename__ = "student_profiles"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    classroom_id = Column(BigInteger)


class ClassroomTeacher(Base):
    __tablename__ = "classrooms_teachers"
    id = Column(BigInteger, primary_key=True)
    classroom_id = Column(BigInteger, nullable=False)
    # This FK is TeacherProfile.id, unlike materials.teacher_id and JWT sub.
    teacher_id = Column(BigInteger, nullable=False)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id = Column(BigInteger, primary_key=True)
    uploader_id = Column(BigInteger, nullable=False)
    s3_key = Column("s3key", String)
    json_s3_key = Column("jsons3key", String)


class Material(Base):
    __tablename__ = "materials"
    id = Column(BigInteger, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    teacher_id = Column(BigInteger, nullable=False)
    uploaded_file_id = Column(BigInteger, nullable=False)
    post_status = Column(String(20), nullable=False)
    deleted_at = Column(DateTime)


class MaterialShare(Base):
    __tablename__ = "material_shares"
    id = Column(BigInteger, primary_key=True)
    material_id = Column(BigInteger, nullable=False)
    teacher_id = Column(BigInteger, nullable=False)
    student_id = Column(BigInteger, nullable=False)
    share_type = Column(String(20), nullable=False)
    class_id = Column(BigInteger)


class Quiz(Base):
    __tablename__ = "quizzes"
    id = Column(BigInteger, primary_key=True)
    material_id = Column(BigInteger, nullable=False)
    content = Column(Text, nullable=False)
    correct_answer = Column(String, nullable=False)


class GradingAttempt(Base):
    """Spring owns writes/migrations; AI only reads committed execution snapshots."""
    __tablename__ = "grading_attempts"
    id = Column(BigInteger, primary_key=True)
    attempt_id = Column(String(36), nullable=False, unique=True)
    student_id = Column(BigInteger, nullable=False)
    material_id = Column(BigInteger, nullable=False)
    idempotency_key = Column(String(36), nullable=False)
    state = Column(String(20), nullable=False)
    execution_generation = Column(Integer, nullable=False)
    execution_token_hash = Column(String(64))
    deadline_at = Column(DateTime)


class GradingAttemptItem(Base):
    __tablename__ = "grading_attempt_items"
    attempt_id = Column(BigInteger, primary_key=True)
    quiz_id = Column(BigInteger, primary_key=True)
    quiz_version = Column(BigInteger, nullable=False)
    question_number = Column(Integer, nullable=False)
    question_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    question_content = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    student_answer = Column(Text, nullable=False)
    grading_version = Column(String(32), nullable=False)
