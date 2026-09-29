package A704.DODREAM.authorization;

import A704.DODREAM.file.entity.UploadedFile;
import A704.DODREAM.file.enums.PostStatus;
import A704.DODREAM.file.repository.UploadedFileRepository;
import A704.DODREAM.material.entity.Material;
import A704.DODREAM.material.entity.MaterialShare;
import A704.DODREAM.material.enums.ShareType;
import A704.DODREAM.material.repository.MaterialRepository;
import A704.DODREAM.material.repository.MaterialShareRepository;
import A704.DODREAM.user.entity.*;
import A704.DODREAM.user.repository.*;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** User IDs and profile IDs are deliberately resolved through their real relationships. */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class AuthorizationPolicy {
    private final UserRepository users;
    private final TeacherProfileRepository teachers;
    private final StudentProfileRepository students;
    private final ClassroomTeacherRepository assignments;
    private final MaterialRepository materials;
    private final MaterialShareRepository shares;
    private final UploadedFileRepository files;

    public User actor(Long id) {
        if (id == null) throw new AuthorizationFailure(HttpStatus.UNAUTHORIZED);
        return users.findById(id).orElseThrow(AuthorizationPolicy::hidden);
    }
    public User role(Long id, Role role) {
        User user = actor(id);
        if (user.getRole() != role) throw new AuthorizationFailure(HttpStatus.FORBIDDEN);
        return user;
    }
    public void teacher(Long id) { role(id, Role.TEACHER); }
    public void student(Long id) { role(id, Role.STUDENT); }
    public Material owned(Long id, Long materialId) {
        teacher(id);
        Material material = live(materialId);
        if (!material.getTeacher().getId().equals(id)
            || !id.equals(material.getUploadedFile().getUploaderId())) throw hidden();
        return material;
    }
    public UploadedFile ownedFile(Long id, Long fileId) {
        teacher(id);
        positive(fileId);
        UploadedFile file = files.findById(fileId).orElseThrow(AuthorizationPolicy::hidden);
        if (!id.equals(file.getUploaderId())) throw hidden();
        // A soft-deleted or contradictory linked material does not become an unowned draft.
        materials.findByUploadedFileId(fileId).ifPresent(material -> {
            if (material.isDeleted() || !id.equals(material.getTeacher().getId())) throw hidden();
        });
        return file;
    }
    public Material read(Long id, Long materialId) {
        return actor(id).getRole() == Role.TEACHER ? owned(id, materialId) : studentMaterial(id, materialId);
    }
    public Material studentMaterial(Long id, Long materialId) {
        student(id);
        Material material = live(materialId);
        if (!studentCanRead(id, material)) throw hidden();
        return material;
    }
    public boolean studentCanRead(Long studentId, Material material) {
        if (material.isDeleted() || material.getPostStatus() != PostStatus.PUBLISHED
            || material.getTeacher().getRole() != Role.TEACHER
            || !material.getTeacher().getId().equals(material.getUploadedFile().getUploaderId())) return false;
        MaterialShare share = shares.findByStudentIdAndMaterialId(studentId, material.getId()).orElse(null);
        if (share == null || !share.getTeacher().getId().equals(material.getTeacher().getId())
            || share.getStudent().getRole() != Role.STUDENT) return false;
        StudentProfile profile = students.findByUserId(studentId).orElse(null);
        if (profile == null || profile.getClassroom() == null
            || !assigned(material.getTeacher().getId(), profile.getClassroom().getId())) return false;
        return share.getShareType() == ShareType.INDIVIDUAL ||
            (share.getShareType() == ShareType.CLASS && share.getClassroom() != null
                && share.getClassroom().getId().equals(profile.getClassroom().getId()));
    }
    public void classroom(Long teacherId, Long classroomId) {
        teacher(teacherId);
        positive(classroomId);
        if (!assigned(teacherId, classroomId)) throw hidden();
    }
    public StudentProfile assignedStudent(Long teacherId, Long studentId) {
        teacher(teacherId);
        StudentProfile profile = students.findByUserId(studentId).orElseThrow(AuthorizationPolicy::hidden);
        if (profile.getUser().getRole() != Role.STUDENT || profile.getClassroom() == null
            || !assigned(teacherId, profile.getClassroom().getId())) throw hidden();
        return profile;
    }
    public Material studentHistory(Long actorId, Long studentId, Long materialId) {
        if (actor(actorId).getRole() == Role.TEACHER) {
            assignedStudent(actorId, studentId);
            owned(actorId, materialId);
        } else if (!actorId.equals(studentId)) throw hidden();
        return studentMaterial(studentId, materialId);
    }
    public boolean historyVisible(Long actorId, Long studentId, Material material) {
        if (actor(actorId).getRole() == Role.TEACHER) {
            assignedStudent(actorId, studentId);
            if (!material.getTeacher().getId().equals(actorId)) return false;
        } else if (!actorId.equals(studentId)) throw hidden();
        return studentCanRead(studentId, material);
    }
    public void historySubject(Long actorId, Long studentId) {
        if (actor(actorId).getRole() == Role.TEACHER) assignedStudent(actorId, studentId);
        else { student(actorId); if (!actorId.equals(studentId)) throw hidden(); }
    }
    private boolean assigned(Long teacherUserId, Long classroomId) {
        TeacherProfile profile = teachers.findByUserId(teacherUserId).orElse(null);
        return profile != null && assignments.existsByClassroomIdAndTeacherId(classroomId, profile.getId());
    }
    private Material live(Long id) {
        positive(id);
        Material material = materials.findById(id).orElseThrow(AuthorizationPolicy::hidden);
        if (material.isDeleted() || material.getUploadedFile() == null) throw hidden();
        return material;
    }
    public static AuthorizationFailure hidden() { return new AuthorizationFailure(HttpStatus.NOT_FOUND); }
    public static AuthorizationFailure invalid() { return new AuthorizationFailure(HttpStatus.BAD_REQUEST); }
    private static void positive(Long id) { if (id == null || id <= 0) throw invalid(); }
}
