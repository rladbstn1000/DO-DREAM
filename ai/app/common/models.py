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
