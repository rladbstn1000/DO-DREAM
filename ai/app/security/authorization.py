"""Current object permissions from Spring's real shared database.

No grants are cached. Missing/unauthorized objects share one 404 response;
SQL failures remain service failures and never become permission grants.
"""
from functools import wraps
import re
from urllib.parse import urlsplit, unquote
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import aliased
from app.common.models import (
    User, RoleEnum, TeacherProfile, StudentProfile, ClassroomTeacher,
    Material, MaterialShare, UploadedFile, Quiz,
)
from app.config import LOCAL_EXTERNAL_STUBS, OBJECT_STORAGE_HOST

MAX_ID = 9223372036854775807
NOT_FOUND = "Object not found"


def denied():
    raise HTTPException(404, NOT_FOUND)


def canonical_id(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise HTTPException(400, "Invalid object identifier")
    value = str(value)
    if not re.fullmatch(r"[1-9][0-9]{0,18}", value) or int(value) > MAX_ID:
        raise HTTPException(400, "Invalid object identifier")
    return int(value)


def document_ref(value):
    if not isinstance(value, str):
        raise HTTPException(400, "Invalid document identifier")
    if value.startswith("pdf_"):
        return "file", canonical_id(value[4:])
    return "material", canonical_id(value)


def teacher_only(user):
    if user.role != "TEACHER":
        raise HTTPException(403, "Teacher role required")


def student_only(user):
    if user.role != "STUDENT":
        raise HTTPException(403, "Student role required")


def fail_closed(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except SQLAlchemyError:
            raise HTTPException(503, "Authorization data unavailable") from None
    return wrapped


@fail_closed
def assigned_student(db, teacher_user_id, student_user_id):
    """Return the current student profile only through User -> Profile FK joins."""
    teacher_user = aliased(User)
    return (db.query(StudentProfile)
        .join(User, User.id == StudentProfile.user_id)
        .join(ClassroomTeacher, ClassroomTeacher.classroom_id == StudentProfile.classroom_id)
        .join(TeacherProfile, TeacherProfile.id == ClassroomTeacher.teacher_id)
        .join(teacher_user, teacher_user.id == TeacherProfile.user_id)
        .filter(StudentProfile.user_id == student_user_id, User.role == RoleEnum.STUDENT,
                TeacherProfile.user_id == teacher_user_id, teacher_user.role == RoleEnum.TEACHER).first())


@fail_closed
def require_assigned_student(db, user, student_id):
    teacher_only(user)
    student_id = canonical_id(student_id)
    profile = assigned_student(db, user.id, student_id)
    if profile is None:
        denied()
    return profile


@fail_closed
def require_file(db, user, file_id):
    teacher_only(user)
    file_id = canonical_id(file_id)
    file = db.query(UploadedFile).filter(UploadedFile.id == file_id,
                                        UploadedFile.uploader_id == user.id).first()
    if file is None:
        denied()
    # A deleted or inconsistent linked material cannot be reopened as an initial file.
    if db.query(Material.id).filter(Material.uploaded_file_id == file.id,
            or_(Material.teacher_id != user.id, Material.deleted_at.is_not(None))).first():
        denied()
    return file


@fail_closed
def student_can_read(db, student_user_id, material):
    if material.post_status != "PUBLISHED" or material.deleted_at is not None:
        return False
    profile = assigned_student(db, material.teacher_id, student_user_id)
    if profile is None:
        return False
    share = db.query(MaterialShare).filter(
        MaterialShare.material_id == material.id,
        MaterialShare.student_id == student_user_id,
        MaterialShare.teacher_id == material.teacher_id,
    ).first()
    if share is None:
        return False
    return share.share_type == "INDIVIDUAL" or (
        share.share_type == "CLASS" and share.class_id == profile.classroom_id)


@fail_closed
def require_material(db, user, material_id):
    material_id = canonical_id(material_id)
    material = db.query(Material).filter(Material.id == material_id,
                                          Material.deleted_at.is_(None)).first()
    if material is None:
        denied()
    file = db.query(UploadedFile).filter(UploadedFile.id == material.uploaded_file_id,
                                        UploadedFile.uploader_id == material.teacher_id).first()
    if file is None:
        denied()
    if user.role == "TEACHER":
        if material.teacher_id != user.id:
            denied()
    elif user.role == "STUDENT":
        if not student_can_read(db, user.id, material):
            denied()
    else:
        raise HTTPException(403, "Unsupported role")
    return material


def require_document(db, user, document_id):
    kind, object_id = document_ref(document_id)
    return require_file(db, user, object_id) if kind == "file" else require_material(db, user, object_id)


def require_history_subject(db, user, student_id):
    student_id = canonical_id(student_id)
    if user.role == "TEACHER":
        require_assigned_student(db, user, student_id)
    else:
        student_only(user)
        if user.id != student_id:
            denied()
    return student_id


@fail_closed
def require_history_material(db, user, student_id, document_id):
    require_history_subject(db, user, student_id)
    kind, object_id = document_ref(document_id)
    if kind != "material":
        denied()
    material = require_material(db, user, object_id)
    if not student_can_read(db, student_id, material):
        denied()
    return material


@fail_closed
def require_quizzes(db, user, material_id, question_ids):
    student_only(user)
    material = require_material(db, user, material_id)
    ids = [canonical_id(value) for value in question_ids]
    if not ids or len(ids) != len(set(ids)):
        raise HTTPException(400, "Invalid question identifiers")
    quizzes = db.query(Quiz).filter(Quiz.id.in_(ids), Quiz.material_id == material.id).all()
    if len(quizzes) != len(ids):
        raise HTTPException(400, "Question does not belong to requested material")
    return {quiz.id: quiz for quiz in quizzes}


def require_object_url(url, key):
    """Bind supplied capability URL to the authorized DB object's exact storage key.

    This checks the authorized object identity; it is not a network SSRF filter.
    Both supported modes use network-free local storage. External file download
    fails closed until a separately reviewed connected-address policy exists.
    """
    if not key:
        denied()
    try:
        parsed = urlsplit(str(url))
        port = parsed.port
    except ValueError:
        raise HTTPException(400, "Invalid object URL") from None
    host = "local-fixture.invalid" if LOCAL_EXTERNAL_STUBS else OBJECT_STORAGE_HOST
    if not host:
        raise HTTPException(503, "Object storage host is not configured")
    path = unquote(parsed.path)
    if (parsed.scheme != "https" or parsed.hostname != host or port not in (None, 443)
            or parsed.username is not None or parsed.password is not None or parsed.fragment
            or (LOCAL_EXTERNAL_STUBS and parsed.query) or path != "/" + key):
        # Backward-compatible synthetic fixture alias is bound only to its one DB key.
        if not (LOCAL_EXTERNAL_STUBS and key == "local/synthetic/lesson.json"
                and str(url) == "https://local-fixture.invalid/sample.json"):
            raise HTTPException(400, "URL does not match the authorized object")
    return str(url)


@fail_closed
def document_json_key(db, document_id):
    kind, object_id = document_ref(document_id)
    if kind == "file":
        file = db.query(UploadedFile).filter(UploadedFile.id == object_id).first()
    else:
        material = db.query(Material).filter(Material.id == object_id).first()
        file = None if material is None else db.query(UploadedFile).filter(
            UploadedFile.id == material.uploaded_file_id).first()
    if file is None or not file.json_s3_key:
        denied()
    return file.json_s3_key
